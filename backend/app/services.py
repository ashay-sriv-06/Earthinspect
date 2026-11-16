"""Orchestration: seed graph, acquisition -> analysis -> graph evidence, investigations and revisions."""
from __future__ import annotations

import copy
import hashlib
import uuid

from . import analysis as an
from . import db, graph, power
from .cases import MECHANISMS, all_cases, get_case
from .catalog import build_catalog
from .config import POWER_END_YEAR, POWER_START_YEAR, TREND_METHOD_VERSION
from .errors import ApiError
from .geometry import canonical, centroid
from .requirements import REQUIREMENTS

# ------------------------------------------------------------------ seed graph


def seed_graph() -> None:
    """Idempotent ingestion of public reference evidence (cases, sources, interventions, catalog)."""
    with db.tx() as c:
        for mid, m in MECHANISMS.items():
            graph.upsert_node(c, f"mech-{mid}", "Mechanism", m["label"], "reference",
                              props={"family": m["family"], "definition": m["definition"], "mechanism": mid})
        for rid, r in REQUIREMENTS.items():
            graph.upsert_node(c, rid, "Requirement", r["label"], "reference", props={"definition": r["definition"]})
        for v, name in power.SUPPORTED_VARIABLES.items():
            graph.upsert_node(c, f"var-{v}", "Variable", name, "reference", props={"code": v})
        for e in build_catalog():
            graph.upsert_node(c, f"ds-{e['id']}", "Dataset", e["name"], "reference",
                              props={"status": e["status"], "provider": e["provider"], "version": e.get("version"),
                                     "source_url": e["source_url"]})
        for case in all_cases():
            cid = case["id"]
            place = f"place-{cid}"
            graph.upsert_node(c, place, "Place", case["display_name"], "reference",
                              props={"geometry": case["analysis_geometry"], "geometry_origin": case["geometry_origin"],
                                     "event_point": case.get("event_point"), "case_id": cid, "scale": case["scale"]})
            ev = f"event-{cid}"
            graph.upsert_node(c, ev, "Event", case["event_name"], "source_reported",
                              props={"summary": case["summary"], "case_id": cid,
                                     "interval": [case["event_start"], case["event_end"]]},
                              event_time=case["event_start"])
            graph.add_edge(c, ev, "OCCURRED_IN", place, status="source_reported")
            graph.add_edge(c, ev, "HAS_MECHANISM", f"mech-{case['hazard_mechanism']}", status="source_reported")
            for s in case["sources"]:
                graph.upsert_node(c, s["id"], "Source", s["title"], "source_reported" if s["status"] == "verified" else "reference",
                                  props=s, published_time=s.get("published"))
            for i, f in enumerate(case.get("event_facts", [])):
                fid = f"fact-{cid}-{i}"
                graph.upsert_node(c, fid, "Finding", f["claim"], "source_reported",
                                  props={"kind": "event_fact", "case_id": cid, "locator": f.get("locator"),
                                         "excerpt": f.get("excerpt"), "source_id": f["source_id"]},
                                  event_time=case["event_start"])
                graph.add_edge(c, fid, "SUPPORTED_BY", f["source_id"], status="source_reported",
                               props={"locator": f.get("locator")})
                graph.add_edge(c, ev, "HAS_FINDING", fid, status="source_reported")
                graph.add_provenance(c, fid, "source_reported", f["source_id"], f.get("locator"))
            for itv in case.get("interventions", []):
                iid = itv["id"]
                graph.upsert_node(c, iid, "Intervention", itv["title"], "source_reported",
                                  props={**itv, "case_id": cid, "place_label": case["display_name"]},
                                  published_time=itv.get("published"))
                graph.add_edge(c, ev, "RESPONDED_WITH", iid, status="source_reported")
                graph.add_edge(c, iid, "SUPPORTED_BY", itv["source_id"], status="source_reported",
                               props={"locator": itv.get("locator")})
                graph.add_provenance(c, iid, "source_reported", itv["source_id"], itv.get("locator"))
                for m in itv.get("addresses", [case["hazard_mechanism"]]):
                    graph.add_edge(c, iid, "ADDRESSES", f"mech-{m}", status="source_reported")
                for req in itv.get("requirements", []):
                    graph.add_edge(c, iid, "REQUIRES", req["id"], status="source_reported",
                                   props={"decisive": bool(req.get("decisive")), "why": req.get("why")})
                if itv.get("reported_outcome"):
                    oid = f"out-{iid}"
                    graph.upsert_node(c, oid, "Outcome", itv["reported_outcome"], "source_reported",
                                      props={"outcome_type": itv.get("outcome_type"), "case_id": cid,
                                             "source_id": itv["source_id"], "locator": itv.get("locator")})
                    graph.add_edge(c, iid, "REPORTED_OUTCOME", oid, status="source_reported")
                    graph.add_edge(c, oid, "SUPPORTED_BY", itv["source_id"], status="source_reported",
                                   props={"locator": itv.get("locator")})
                for k, lim in enumerate(itv.get("limitations", [])):
                    lid = f"lim-{iid}-{k}"
                    graph.upsert_node(c, lid, "Finding", lim, "source_reported",
                                      props={"kind": "limitation", "case_id": cid, "source_id": itv["source_id"]})
                    graph.add_edge(c, lid, "CONTRADICTS", iid, status="source_reported",
                                   props={"note": "Documented limitation / constraint on this response"})
                    graph.add_edge(c, lid, "SUPPORTED_BY", itv["source_id"], status="source_reported")
                # Hyperedge: documented response context (multi-factor, no implied pairwise causality)
                members = [(ev, "event"), (place, "setting"), (f"mech-{case['hazard_mechanism']}", "mechanism"),
                           (iid, "response"), (itv["source_id"], "source")]
                members += [(r["id"], "prerequisite") for r in itv.get("requirements", [])]
                graph.add_bundle(c, f"bnd-response-{iid}", "documented_response_context", "source_reported",
                                 f"{case['display_name']}: context of '{itv['title']}'", members,
                                 props={"basis": "source_reported", "source_id": itv["source_id"],
                                        "locator": itv.get("locator"), "implementation_status": itv.get("status")},
                                 time_scope=itv.get("published"))


# ------------------------------------------------------------------ analysis pipeline


def _scope_for(place: dict, session_id: str) -> str:
    return "public" if place.get("case_id") else session_id


def run_trends_for(session_id: str, iid: str, variables: list[str] | None = None, force_refresh: bool = False,
                   on_event=None) -> dict:
    """Run the trend family for an investigation and pin it as the investigation's current analysis batch."""
    inv = get_investigation(session_id, iid)
    cfg = inv["config"]
    batch = run_trends(cfg["place"], variables or cfg["variables"], cfg["period"]["start"], cfg["period"]["end"],
                       session_id, force_refresh=force_refresh, on_event=on_event)
    with db.tx() as c:
        r = c.execute("SELECT config_json FROM investigations WHERE id=? AND session_id=?", (iid, session_id)).fetchone()
        cfg2 = db.loads(r["config_json"])
        cfg2["current_batch"] = batch["id"]
        c.execute("UPDATE investigations SET config_json=?, updated_at=? WHERE id=?", (db.dumps(cfg2), db.now_iso(), iid))
    return batch


def run_trends(place: dict, variables: list[str], start: str, end: str, session_id: str,
               force_refresh: bool = False, on_event=None) -> dict:
    """Acquire each variable, run the prespecified trend family with BH adjustment, persist analyses and
    ingest Artifact/Analysis/Finding nodes. Returns batch result + per-step events."""
    on_event = on_event or (lambda *a, **k: None)
    geometry = canonical(place["geometry"])
    y0, y1 = int(start[:4]), int(end[:4])
    if not variables:
        raise ApiError("invalid_request", "Select at least one variable.")
    acquisitions = []
    for v in variables:
        on_event("acquire_started", f"Acquiring {v}", {"variable": v})
        res = power.acquire(v, geometry, y0, y1, force_refresh=force_refresh)
        acquisitions.append(res)
        on_event("cache_" + res["cache_status"],
                 f"{v}: {'cache hit' if res['cache_status'] == 'cached' else res['cache_status']}",
                 {"variable": v, "artifact_id": res["artifact"]["id"], "cache_key": res["artifact"]["cache_key"],
                  "warning": res.get("warning")}, res["duration_ms"])

    art_ids = [a["artifact"]["id"] for a in acquisitions]
    params = {"start": start, "end": end, "variables": variables, "family": "prespecified-batch"}
    key = an.analysis_cache_key("trend_batch", art_ids, params)
    with db.conn() as c:
        row = c.execute("SELECT * FROM analyses WHERE cache_key=?", (key,)).fetchone()
    if row:
        batch = {"id": row["id"], "cache_key": key, "results": db.loads(row["result_json"]), "reused": True}
        on_event("analysis_reused", "Reused existing trend analysis", {"analysis_id": row["id"]})
    else:
        results = []
        for a in acquisitions:
            norm = power.load_normalized(a["artifact"]["id"])
            r = an.trend(norm["rows"], start, end, norm["units"], norm["variable"])
            r["artifact_id"] = a["artifact"]["id"]
            r["artifact_sha256"] = a["artifact"]["sha256"]
            r["longname"] = norm["longname"]
            r["spatial_support"] = {k: v for k, v in norm["support"].items() if k != "cell_centers"}
            r["cell_centers"] = norm["support"]["cell_centers"]
            r["conversions"] = norm["conversions"]
            if norm["variable"] == "PRECTOTCORR":
                totals = {row_["date"]: row_.get("monthly_total_mm") for row_ in norm["rows"]}
                for s in r["series"]:
                    s["monthly_total_mm"] = totals.get(s["date"])
            results.append(r)
        results = an.bh_adjust(results)
        aid = f"ana-{key[:12]}"
        with db.tx() as c:
            c.execute("INSERT OR IGNORE INTO analyses(id,cache_key,kind,artifact_ids,params_json,result_json,created_at)"
                      " VALUES(?,?,?,?,?,?,?)", (aid, key, "trend_batch", db.dumps(art_ids), db.dumps(params),
                                                  db.dumps(results), db.now_iso()))
        batch = {"id": aid, "cache_key": key, "results": results, "reused": False}
        on_event("analysis_created", f"Trend analysis {aid} ({len(results)} variables, BH-adjusted)",
                 {"analysis_id": aid})

    finding_ids = ingest_trend_batch(place, batch, acquisitions, session_id)
    on_event("graph_updated", f"Evidence graph: {len(finding_ids)} finding(s) linked to provenance",
             {"finding_ids": finding_ids})
    batch["finding_ids"] = finding_ids
    batch["acquisitions"] = [{"artifact": a["artifact"], "cache_status": a["cache_status"],
                              "duration_ms": a["duration_ms"], "warning": a.get("warning")} for a in acquisitions]

    # descriptive association between the first two variables (if both present)
    if "T2M" in variables and "PRECTOTCORR" in variables:
        batch["association"] = associate_vars(acquisitions, "T2M", "PRECTOTCORR", start, end)
    return batch


def associate_vars(acquisitions, xv, yv, start, end) -> dict:
    by = {a["artifact"]["variable"]: a["artifact"]["id"] for a in acquisitions}
    key = an.analysis_cache_key("association", [by[xv], by[yv]], {"x": xv, "y": yv, "start": start, "end": end})
    with db.conn() as c:
        row = c.execute("SELECT * FROM analyses WHERE cache_key=?", (key,)).fetchone()
    if row:
        return {"id": row["id"], **db.loads(row["result_json"])}
    xr, yr = power.load_normalized(by[xv]), power.load_normalized(by[yv])
    res = an.associate(xr["rows"], yr["rows"], start, end, xv, yv)
    aid = f"ana-{key[:12]}"
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO analyses(id,cache_key,kind,artifact_ids,params_json,result_json,created_at)"
                  " VALUES(?,?,?,?,?,?,?)", (aid, key, "association", db.dumps([by[xv], by[yv]]),
                                              db.dumps({"x": xv, "y": yv}), db.dumps(res), db.now_iso()))
    return {"id": aid, **res}


def ingest_trend_batch(place: dict, batch: dict, acquisitions: list[dict], session_id: str) -> list[str]:
    scope = _scope_for(place, session_id)
    place_id = place["node_id"]
    fids = []
    with db.tx() as c:
        if scope != "public":
            graph.upsert_node(c, place_id, "Place", place["name"], "analyst_assumption", scope=scope,
                              props={"geometry": place["geometry"], "geometry_origin": place.get("geometry_origin"),
                                     "scale": place.get("scale")})
        for a in acquisitions:
            art = a["artifact"]
            graph.upsert_node(c, art["id"], "Artifact", f"POWER {art['variable']} v{art['version']}", "computed",
                              scope=scope, props={"sha256": art["sha256"], "cache_key": art["cache_key"],
                                                  "retrieved_at": art["retrieved_at"], "origin": art["origin"],
                                                  "source_url": art["manifest"]["source_url"],
                                                  "units": art["manifest"]["units"],
                                                  "spatial_support": art["manifest"]["spatial_support"]})
            graph.add_edge(c, art["id"], "DERIVED_FROM", "ds-power-monthly", scope=scope)
            graph.add_edge(c, art["id"], "MEASURES", f"var-{art['variable']}", scope=scope)
        for r in batch["results"]:
            v = r["variable"]
            anid = f"{batch['id']}-{v}"
            graph.upsert_node(c, anid, "Analysis", f"{v} trend {r['period']['start']}–{r['period']['end']}", "computed",
                              scope=scope, props={"method": r["method"], "mode": r["mode"], "units": r["units"],
                                                  "period": r["period"], "coverage": r["coverage"],
                                                  "batch_id": batch["id"], "artifact_sha256": r["artifact_sha256"],
                                                  "spatial_support": r["spatial_support"]})
            graph.add_edge(c, anid, "DERIVED_FROM", r["artifact_id"], scope=scope)
            graph.add_edge(c, anid, "MEASURES", f"var-{v}", scope=scope)
            fid = f"find-{batch['id'][4:]}-{v}"
            if r["mode"] == "inferential":
                label = r["statement"]
                props = {"kind": "trend", "variable": v, "units": r["units"],
                         "slope_per_decade": r["slope_per_decade"], "ci95_per_decade": r["ci95_per_decade"],
                         "p_value": r["p_value"], "q_value": r.get("q_value"),
                         "significant": r.get("significant_bh", r["significant_at_0_05"]),
                         "significance_basis": "Benjamini–Hochberg q < 0.05 across the variable family",
                         "direction": "increase" if r["slope_per_decade"] > 0 else "decrease"}
            else:
                label = f"{v}: descriptive only — {r['limitation']}"
                props = {"kind": "trend_descriptive", "variable": v, "units": r["units"], "limitation": r["limitation"]}
            props.update({"period": r["period"], "analysis_id": anid, "place_id": place_id,
                          "geometry": place["geometry"], "method_version": TREND_METHOD_VERSION})
            graph.upsert_node(c, fid, "Finding", label, "computed", scope=scope, props=props,
                              event_time=f"{r['period']['start']}/{r['period']['end']}")
            graph.add_edge(c, fid, "DERIVED_FROM", anid, scope=scope)
            graph.add_edge(c, place_id, "HAS_FINDING", fid, scope=scope)
            graph.add_provenance(c, fid, "computed", anid)
            graph.add_provenance(c, fid, "computed", r["artifact_id"])
            fids.append(fid)
        # Hyperedge: environmental context for the place & period (members keep roles; no causal edges implied)
        members = [(place_id, "place")] + [(f, "finding") for f in fids] + [(f"var-{r['variable']}", "variable") for r in batch["results"]]
        graph.add_bundle(c, f"bnd-context-{batch['id']}-{place_id}"[:80], "regional_environmental_context", "computed",
                         f"{place['name']}: regional trend context {batch['results'][0]['period']['start']}–{batch['results'][0]['period']['end']}",
                         members, scope=scope,
                         props={"basis": "computed", "analysis_id": batch["id"],
                                "note": "Co-membership is context only; it does not assert a causal link between variables."},
                         time_scope=f"{batch['results'][0]['period']['start']}/{batch['results'][0]['period']['end']}")
    return fids


# ------------------------------------------------------------------ investigations & revisions

DEFAULT_PERIOD = {"start": f"{POWER_START_YEAR}-01", "end": f"{POWER_END_YEAR}-12"}


def new_session() -> str:
    sid = "s-" + uuid.uuid4().hex
    with db.tx() as c:
        c.execute("INSERT INTO sessions(id, created_at) VALUES(?,?)", (sid, db.now_iso()))
    return sid


def session_exists(sid: str) -> bool:
    with db.conn() as c:
        return bool(c.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone())


def _place_from_case(case_id: str) -> dict:
    case = get_case(case_id)
    return {"name": case["display_name"], "case_id": case_id, "node_id": f"place-{case_id}",
            "geometry": case["analysis_geometry"], "geometry_origin": case["geometry_origin"],
            "scale": case["scale"], "event_point": case.get("event_point")}


def create_investigation(session_id: str, body: dict) -> dict:
    case_id = body.get("case_id")
    if case_id:
        place = _place_from_case(case_id)
        case = get_case(case_id)
        mechanism = case["hazard_mechanism"]
        variables = case["variables"]
        title = body.get("title") or f"{case['display_name']} investigation"
    else:
        p = body.get("place") or {}
        geom = canonical(p.get("geometry") or {})
        name = str(p.get("name") or "Custom place")[:120]
        pid = "place-u-" + hashlib.sha1(db.dumps(geom).encode()).hexdigest()[:10]
        place = {"name": name, "case_id": None, "node_id": pid, "geometry": geom,
                 "geometry_origin": str(p.get("geometry_origin") or "User-confirmed footprint")[:300],
                 "scale": p.get("scale") if p.get("scale") in ("city", "catchment", "regional", "neighbourhood") else None,
                 "lookup": p.get("lookup")}
        mechanism = body.get("mechanism") if body.get("mechanism") in MECHANISMS else None
        variables = [v for v in (body.get("variables") or ["T2M", "PRECTOTCORR", "RH2M", "WS10M"]) if v in power.SUPPORTED_VARIABLES]
        title = str(body.get("title") or f"{name} investigation")[:160]
    lon, lat = centroid(place["geometry"])
    config = {
        "place": place,
        "question": str(body.get("question") or "What is changing here, which historical experiences are relevant, "
                        "what makes them transferable or unsuitable, and what evidence would change that?")[:500],
        "variables": variables,
        "period": body.get("period") or DEFAULT_PERIOD,
        "view": {"center": [lon, lat], "zoom": 6.2, "layers": {"footprint": True, "grid": True, "event": True,
                                                                  "imagery": False, "imagery_opacity": 0.8},
                 "imagery_date": None, "inspector_tab": "analysis"},
    }
    iid = "inv-" + uuid.uuid4().hex[:12]
    state = {"mechanism": mechanism, "scale": place.get("scale"), "requirements": {}, "disputed": []}
    rid = f"rev-{iid[4:]}-0"
    with db.tx() as c:
        c.execute("INSERT INTO investigations(id,session_id,title,config_json,current_revision_id,created_at,updated_at)"
                  " VALUES(?,?,?,?,?,?,?)", (iid, session_id, title, db.dumps(config), rid, db.now_iso(), db.now_iso()))
        c.execute("INSERT INTO revisions(id,investigation_id,session_id,prior_id,seq,kind,changes_json,state_json,rationale,created_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)", (rid, iid, session_id, None, 0, "initial",
                                                   db.dumps({"mechanism": mechanism, "scale": place.get("scale")}),
                                                   db.dumps(state), "Investigation created", db.now_iso()))
        graph.upsert_node(c, iid, "Investigation", title, "analyst_assumption", scope=session_id,
                          props={"place_id": place["node_id"]})
        graph.add_edge(c, iid, "OCCURRED_IN", place["node_id"], status="analyst_assumption", scope=session_id)
    return get_investigation(session_id, iid)


def _owned(session_id: str, iid: str):
    with db.conn() as c:
        r = c.execute("SELECT * FROM investigations WHERE id=? AND session_id=?", (iid, session_id)).fetchone()
    if not r:
        raise ApiError("not_found", "Investigation not found in this session.", status=404)
    return r


def get_investigation(session_id: str, iid: str) -> dict:
    r = _owned(session_id, iid)
    with db.conn() as c:
        revs = c.execute("SELECT id,prior_id,seq,kind,changes_json,rationale,created_at FROM revisions"
                         " WHERE investigation_id=? ORDER BY seq", (iid,)).fetchall()
        cur = c.execute("SELECT state_json FROM revisions WHERE id=?", (r["current_revision_id"],)).fetchone()
    return {
        "id": r["id"], "title": r["title"], "config": db.loads(r["config_json"]),
        "current_revision_id": r["current_revision_id"], "state": db.loads(cur["state_json"]) if cur else {},
        "revisions": [{"id": x["id"], "prior_id": x["prior_id"], "seq": x["seq"], "kind": x["kind"],
                       "changes": db.loads(x["changes_json"]), "rationale": x["rationale"],
                       "created_at": x["created_at"]} for x in revs],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def list_investigations(session_id: str) -> list[dict]:
    with db.conn() as c:
        rows = c.execute("SELECT id,title,config_json,updated_at FROM investigations WHERE session_id=?"
                         " ORDER BY updated_at DESC", (session_id,)).fetchall()
    return [{"id": r["id"], "title": r["title"], "place": db.loads(r["config_json"])["place"]["name"],
             "case_id": db.loads(r["config_json"])["place"].get("case_id"), "updated_at": r["updated_at"]} for r in rows]


def update_view(session_id: str, iid: str, patch: dict) -> dict:
    r = _owned(session_id, iid)
    cfg = db.loads(r["config_json"])
    allowed = {"view", "period", "variables", "question"}
    for k, v in patch.items():
        if k not in allowed:
            raise ApiError("invalid_request", f"Field {k} cannot be changed here.")
        if k == "variables":
            v = [x for x in v if x in power.SUPPORTED_VARIABLES]
        if k == "period":
            an.window_rows([], v["start"], v["end"])  # validates order
        if k == "view":
            v = {**cfg["view"], **v}
        cfg[k] = v
    with db.tx() as c:
        c.execute("UPDATE investigations SET config_json=?, updated_at=? WHERE id=?", (db.dumps(cfg), db.now_iso(), iid))
    return get_investigation(session_id, iid)


def add_revision(session_id: str, iid: str, body: dict) -> dict:
    """kinds: set_requirement (assumption or linked source), set_mechanism, set_scale, dispute, undispute."""
    inv = get_investigation(session_id, iid)
    state = copy.deepcopy(inv["state"])
    kind = body.get("kind")
    rationale = str(body.get("rationale") or "").strip()[:500]
    if not rationale:
        raise ApiError("rationale_required", "Explain why this evidence changes (rationale is required).")
    changes: dict = {}
    extra_nodes = []
    with db.conn() as c:
        seq = c.execute("SELECT MAX(seq) s FROM revisions WHERE investigation_id=?", (iid,)).fetchone()["s"] + 1
    rid = f"rev-{iid[4:]}-{seq}"
    if kind == "set_requirement":
        req = body.get("requirement_id")
        if req not in REQUIREMENTS:
            raise ApiError("invalid_request", "Unknown requirement.")
        st = body.get("state")
        if st not in ("satisfied", "unsatisfied", "unknown"):
            raise ApiError("invalid_request", "State must be satisfied, unsatisfied or unknown.")
        basis = body.get("basis", "analyst_assumption")
        if basis not in ("analyst_assumption", "source_reported"):
            raise ApiError("invalid_request", "Basis must be analyst_assumption or source_reported.")
        entry = {"state": st, "basis": basis, "note": rationale, "via": f"asm-{rid}", "revision_id": rid}
        if basis == "source_reported":
            sid = body.get("source_id")
            try:
                src = graph.get_node(sid, session_id)
            except ApiError:
                raise ApiError("invalid_request", "Link an already-ingested source record.")
            if src["type"] != "Source":
                raise ApiError("invalid_request", "Linked evidence must be a Source node.")
            entry.update({"source_id": sid, "locator": str(body.get("locator") or "")[:200]})
        prev = state["requirements"].get(req)
        if st == "unknown":
            state["requirements"].pop(req, None)
        else:
            state["requirements"][req] = entry
        changes = {"requirement_id": req, "from": prev, "to": entry if st != "unknown" else None}
        extra_nodes.append((req, entry))
    elif kind == "set_mechanism":
        m = body.get("mechanism")
        if m is not None and m not in MECHANISMS:
            raise ApiError("invalid_request", "Unknown mechanism.")
        changes = {"mechanism": {"from": state.get("mechanism"), "to": m}}
        state["mechanism"] = m
    elif kind == "set_scale":
        s = body.get("scale")
        if s not in (None, "neighbourhood", "city", "catchment", "regional"):
            raise ApiError("invalid_request", "Unknown scale.")
        changes = {"scale": {"from": state.get("scale"), "to": s}}
        state["scale"] = s
    elif kind in ("dispute", "undispute"):
        nid = body.get("node_id")
        graph.get_node(nid, session_id)  # must be visible
        d = set(state.get("disputed", []))
        (d.add if kind == "dispute" else d.discard)(nid)
        state["disputed"] = sorted(d)
        changes = {"node_id": nid, "disputed": kind == "dispute"}
    else:
        raise ApiError("invalid_request", "Unknown revision kind.")

    with db.tx() as c:
        c.execute("INSERT INTO revisions(id,investigation_id,session_id,prior_id,seq,kind,changes_json,state_json,rationale,created_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?)", (rid, iid, session_id, inv["current_revision_id"], seq, kind,
                                                   db.dumps(changes), db.dumps(state), rationale, db.now_iso()))
        c.execute("UPDATE investigations SET current_revision_id=?, updated_at=? WHERE id=?", (rid, db.now_iso(), iid))
        for req, entry in extra_nodes:
            nid = f"asm-{rid}"
            label = f"{'Assumption' if entry['basis'] == 'analyst_assumption' else 'Sourced'}: {REQUIREMENTS[req]['label']} — {entry['state']}"
            graph.upsert_node(c, nid, "Assumption", label,
                              "analyst_assumption" if entry["basis"] == "analyst_assumption" else "source_reported",
                              scope=session_id, props={"requirement_id": req, **entry, "revision_id": rid})
            graph.add_edge(c, iid, "ASSESSES", req, status=entry["basis"], scope=session_id,
                           props={"state": entry["state"], "via": nid, "revision_id": rid})
            graph.add_edge(c, nid, "ASSESSES", req, status=entry["basis"], scope=session_id, props={"state": entry["state"]})
            graph.add_edge(c, iid, "HAS_FINDING", nid, status=entry["basis"], scope=session_id)
            if entry["basis"] == "source_reported":
                graph.add_edge(c, nid, "SUPPORTED_BY", entry["source_id"], status="source_reported", scope=session_id,
                               props={"locator": entry.get("locator")})
                graph.add_provenance(c, nid, "source_reported", entry["source_id"], entry.get("locator"))
            else:
                graph.add_provenance(c, nid, "analyst_assumption", rid)
    return get_investigation(session_id, iid)


def switch_revision(session_id: str, iid: str, rid: str) -> dict:
    _owned(session_id, iid)
    with db.tx() as c:
        if not c.execute("SELECT 1 FROM revisions WHERE id=? AND investigation_id=?", (rid, iid)).fetchone():
            raise ApiError("not_found", "Revision not found.", status=404)
        c.execute("UPDATE investigations SET current_revision_id=?, updated_at=? WHERE id=?", (rid, db.now_iso(), iid))
    return get_investigation(session_id, iid)


def revision_state(session_id: str, iid: str, rid: str) -> dict:
    _owned(session_id, iid)
    with db.conn() as c:
        r = c.execute("SELECT state_json FROM revisions WHERE id=? AND investigation_id=?", (rid, iid)).fetchone()
    if not r:
        raise ApiError("not_found", "Revision not found.", status=404)
    return db.loads(r["state_json"])


def latest_findings(session_id: str, iid: str) -> list[dict]:
    """Trend findings for this investigation's place and configured period."""
    inv = get_investigation(session_id, iid)
    batch = inv["config"].get("current_batch")
    if not batch:
        return []
    place_id = inv["config"]["place"]["node_id"]
    with db.conn() as c:
        edges = graph.out_edges(c, place_id, session_id, ["HAS_FINDING"])
        nodes = graph.nodes_by_ids(c, [e["dst"] for e in edges], session_id)
    out = [n for n in nodes.values() if n["props"].get("kind", "").startswith("trend")
           and str(n["props"].get("analysis_id", "")).startswith(batch + "-")]
    return sorted(out, key=lambda n: n["props"]["variable"])


DEMO_SPEC = {
    "case_id": "camp-fire-2018",
    "title": "Demo — Camp Fire 2018 investigation",
    "imagery_date": "2018-11-08",    # event day: MODIS shows the smoke plume
    "imagery_date_b": "2018-10-25",  # two weeks earlier: clear
    "assumption": {
        "kind": "set_requirement", "requirement_id": "req-wui-exposure", "state": "satisfied",
        "basis": "analyst_assumption",
        "rationale": "Demo scenario: target community is adjacent to wildland fuels (planning assumption, not a sourced fact).",
    },
}


def create_demo_investigation(session_id: str) -> dict:
    """Reproduce the canonical demonstration investigation inside the CALLER's session using only existing
    services (case → cached NASA analysis → imagery dates → one labelled planning assumption). Idempotent per session."""
    with db.conn() as c:
        r = c.execute("SELECT id FROM investigations WHERE session_id=? AND title=?", (session_id, DEMO_SPEC["title"])).fetchone()
    if r:
        return get_investigation(session_id, r["id"])
    inv = create_investigation(session_id, {"case_id": DEMO_SPEC["case_id"], "title": DEMO_SPEC["title"]})
    iid = inv["id"]
    run_trends_for(session_id, iid)
    r0 = inv["current_revision_id"]
    update_view(session_id, iid, {"view": {"imagery_date": DEMO_SPEC["imagery_date"], "imagery_date_b": DEMO_SPEC["imagery_date_b"],
                                           "imagery_mix": 0, "imagery_compare": "swipe", "imagery_swipe": 0.5,
                                           "layers": {**inv["config"]["view"]["layers"], "imagery": True},
                                           "inspector_tab": "leads"}})
    inv = add_revision(session_id, iid, dict(DEMO_SPEC["assumption"]))
    return update_view(session_id, iid, {"view": {"last_change": {"from": r0, "to": inv["current_revision_id"]}}})


def latest_public_findings(place_id: str, period: dict) -> list[dict]:
    """Findings for a seed place: newest method version, newest ingestion per variable (older ones stay in the graph)."""
    from .config import TREND_METHOD_VERSION
    with db.conn() as c:
        edges = graph.out_edges(c, place_id, None, ["HAS_FINDING"])
        nodes = graph.nodes_by_ids(c, [e["dst"] for e in edges], None)
    best: dict[str, dict] = {}
    for n in nodes.values():
        p = n["props"]
        if not p.get("kind", "").startswith("trend") or p.get("period") != period or p.get("method_version") != TREND_METHOD_VERSION:
            continue
        if p["variable"] not in best or n["ingested_at"] > best[p["variable"]]["ingested_at"]:
            best[p["variable"]] = n
    return [best[k] for k in sorted(best)]
