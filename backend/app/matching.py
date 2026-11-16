"""Deterministic, explainable contextual matching between a target investigation and the solutions graph.

Not a trained link-prediction model. Every candidate is derived from persisted graph edges
(ADDRESSES, REQUIRES, REPORTED_OUTCOME, CONTRADICTS) and the investigation's revision state.
The ordinal score is NOT a probability of success.
"""
from __future__ import annotations

import hashlib

from . import db, graph
from .cases import MECHANISMS
from .config import MATCH_RULE_VERSION
from .requirements import REQUIREMENTS, SCALE_ORDER
from .services import get_investigation, latest_findings, revision_state

W_MECH = 3.0
W_SCALE = 1.0
W_REQ = 2.0
W_SIGNAL = 0.5  # monthly regional context is weak evidence for any specific intervention


def _feature(name, state, weight, detail, evidence=None, kind="context"):
    return {"feature": name, "state": state, "weight": weight, "detail": detail, "evidence": evidence or [],
            "kind": kind}


def context_for(session_id: str, iid: str, rid: str | None = None) -> dict:
    inv = get_investigation(session_id, iid)
    rid = rid or inv["current_revision_id"]
    state = revision_state(session_id, iid, rid)
    findings = latest_findings(session_id, iid)
    disputed = set(state.get("disputed", []))
    return {
        "investigation_id": iid,
        "revision_id": rid,
        "place": inv["config"]["place"],
        "mechanism": state.get("mechanism"),
        "scale": state.get("scale"),
        "requirements": state.get("requirements", {}),
        "disputed": sorted(disputed),
        "findings": [
            {"id": f["id"], "variable": f["props"]["variable"], "kind": f["props"]["kind"],
             "significant": f["props"].get("significant"), "direction": f["props"].get("direction"),
             "slope_per_decade": f["props"].get("slope_per_decade"), "units": f["props"].get("units"),
             "q_value": f["props"].get("q_value"), "disputed": f["id"] in disputed}
            for f in findings
        ],
    }


def _interventions(session_id):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM nodes WHERE type='Intervention' AND scope='public' ORDER BY id").fetchall()
        out = []
        for r in rows:
            n = graph.node_dict(r)
            n["addresses"] = [e["dst"] for e in graph.out_edges(c, n["id"], session_id, ["ADDRESSES"])]
            n["requires"] = graph.out_edges(c, n["id"], session_id, ["REQUIRES"])
            n["outcomes"] = list(graph.nodes_by_ids(
                c, [e["dst"] for e in graph.out_edges(c, n["id"], session_id, ["REPORTED_OUTCOME"])], session_id).values())
            n["conflicts"] = list(graph.nodes_by_ids(
                c, [e["src"] for e in graph.in_edges(c, n["id"], session_id, ["CONTRADICTS"])], session_id).values())
            out.append(n)
    return out


def evaluate(ctx: dict, itv: dict) -> dict:
    p = itv["props"]
    feats = []
    hard = []
    decisive_unknown = []
    # --- mechanism
    t_mech = ctx["mechanism"]
    i_mechs = [a.replace("mech-", "") for a in itv["addresses"]]
    q_edges = [f"ADDRESSES:{itv['id']}->mech-{m}" for m in i_mechs]
    if not t_mech:
        feats.append(_feature("mechanism", "unknown", W_MECH,
                              "Target hazard mechanism not established; cannot judge transfer.", q_edges, "decisive"))
        decisive_unknown.append("Establish the target's hazard mechanism.")
    elif t_mech in i_mechs:
        feats.append(_feature("mechanism", "compatible", W_MECH,
                              f"Both concern {MECHANISMS[t_mech]['label'].lower()}.", q_edges + [f"mech-{t_mech}"], "decisive"))
    elif any(MECHANISMS[m]["family"] == MECHANISMS[t_mech]["family"] for m in i_mechs):
        feats.append(_feature("mechanism", "mismatch", W_MECH,
                              f"Same hazard family ({MECHANISMS[t_mech]['family']}) but different mechanism: source addressed "
                              f"{', '.join(MECHANISMS[m]['label'].lower() for m in i_mechs)}; target is "
                              f"{MECHANISMS[t_mech]['label'].lower()}. At most a partial, component-level lead.",
                              q_edges + [f"mech-{t_mech}"], "decisive"))
    else:
        feats.append(_feature("mechanism", "incompatible", W_MECH,
                              f"Different hazard family: {MECHANISMS[i_mechs[0]]['label'] if i_mechs else '?'} vs "
                              f"{MECHANISMS[t_mech]['label']}.", q_edges, "decisive"))
        hard.append("Hazard mechanism belongs to a different family.")
    # --- scale
    t_scale, i_scale = ctx["scale"], p.get("scale")
    if not t_scale or not i_scale:
        feats.append(_feature("scale", "unknown", W_SCALE, "Target or response spatial scale not established."))
    elif t_scale == i_scale:
        feats.append(_feature("scale", "compatible", W_SCALE, f"Both operate at {t_scale} scale."))
    else:
        gap = abs(SCALE_ORDER.index(t_scale) - SCALE_ORDER.index(i_scale)) if t_scale in SCALE_ORDER and i_scale in SCALE_ORDER else 9
        feats.append(_feature("scale", "mismatch", W_SCALE,
                              f"Response designed at {i_scale} scale; target framed at {t_scale} scale"
                              + (" (large scale gap)." if gap >= 2 else ".")))
    # --- prerequisites
    for e in itv["requires"]:
        rid = e["dst"]
        decisive = bool(e["props"].get("decisive"))
        known = ctx["requirements"].get(rid)
        label = REQUIREMENTS.get(rid, {}).get("label", rid)
        ev = [e["id"], rid]
        if known and known.get("via"):
            ev.append(known["via"])
        if not known:
            feats.append(_feature(f"requires:{rid}", "unknown", W_REQ,
                                  f"{label}: not established for the target (not inferred from climate data).",
                                  ev, "decisive" if decisive else "prerequisite"))
            if decisive:
                decisive_unknown.append(f"Establish: {label}.")
        elif known["state"] == "satisfied":
            basis = "planning assumption" if known["basis"] == "analyst_assumption" else "linked source"
            feats.append(_feature(f"requires:{rid}", "compatible", W_REQ, f"{label}: satisfied ({basis}).",
                                  ev + ([known["source_id"]] if known.get("source_id") else []),
                                  "decisive" if decisive else "prerequisite"))
        else:
            basis = "planning assumption" if known["basis"] == "analyst_assumption" else "linked source"
            feats.append(_feature(f"requires:{rid}", "incompatible", W_REQ, f"{label}: not satisfied ({basis}).",
                                  ev, "decisive" if decisive else "prerequisite"))
            if decisive:
                hard.append(f"Decisive prerequisite not satisfied: {label}.")
    # --- environmental context signals (weak)
    for s in p.get("signals", []):
        f = next((x for x in ctx["findings"] if x["variable"] == s["variable"]), None)
        if not f:
            feats.append(_feature(f"signal:{s['variable']}", "unknown", W_SIGNAL,
                                  f"No {s['variable']} trend computed for the target yet."))
        elif f["disputed"]:
            feats.append(_feature(f"signal:{s['variable']}", "unknown", W_SIGNAL,
                                  f"{s['variable']} finding is marked disputed; treated as unknown.", [f["id"]]))
        elif f["kind"] != "trend":
            feats.append(_feature(f"signal:{s['variable']}", "unknown", W_SIGNAL,
                                  f"{s['variable']}: descriptive only (insufficient coverage for inference).", [f["id"]]))
        elif not f["significant"]:
            feats.append(_feature(f"signal:{s['variable']}", "unknown", W_SIGNAL,
                                  f"{s['variable']}: no statistically detectable linear trend under this method "
                                  f"({f['slope_per_decade']:+.3f} {f['units']}/decade). {s.get('note', '')}".strip(), [f["id"]]))
        elif f["direction"] == s["direction"]:
            feats.append(_feature(f"signal:{s['variable']}", "compatible", W_SIGNAL,
                                  f"{s['variable']} shows a detectable {f['direction']} ({f['slope_per_decade']:+.3f} "
                                  f"{f['units']}/decade). Context only. {s.get('note', '')}".strip(), [f["id"]]))
        else:
            feats.append(_feature(f"signal:{s['variable']}", "mismatch", W_SIGNAL,
                                  f"{s['variable']} trend is a detectable {f['direction']}, opposite to the context "
                                  f"this response addressed. {s.get('note', '')}".strip(), [f["id"]]))

    total_w = sum(x["weight"] for x in feats)
    known_w = sum(x["weight"] for x in feats if x["state"] != "unknown")
    match_w = sum(x["weight"] for x in feats if x["state"] == "compatible")
    mech_state = feats[0]["state"]
    if hard:
        eligibility = "excluded"
    elif mech_state == "mismatch":
        # A different mechanism caps transfer at a component lead, whatever local evidence shows.
        eligibility = "partial_component_only"
    elif decisive_unknown:
        eligibility = "needs_local_evidence"
    else:
        eligibility = "candidate_lead"
    next_ev = list(decisive_unknown)
    next_ev += [f"Establish: {REQUIREMENTS.get(x['feature'].split(':', 1)[1], {}).get('label', x['feature'])}."
                for x in feats if x["state"] == "unknown" and x["kind"] == "prerequisite"]
    if mech_state == "mismatch":
        next_ev.append("Identify which part of the target's hazard (if any) is driven by the mechanism this response addressed.")
    return {
        "intervention_id": itv["id"],
        "title": itv["label"],
        "source_case": p.get("case_id"),
        "source_place": p.get("place_label"),
        "implementation_status": p.get("status"),
        "category": p.get("category"),
        "scale": p.get("scale"),
        "outcome_evidence_type": p.get("outcome_type"),
        "outcomes": [{"id": o["id"], "label": o["label"], "type": o["props"].get("outcome_type")} for o in itv["outcomes"]],
        "conflicts": [{"id": c["id"], "label": c["label"]} for c in itv["conflicts"]],
        "source_id": p.get("source_id"),
        "locator": p.get("locator"),
        "features": feats,
        "matched": [x for x in feats if x["state"] == "compatible"],
        "mismatches": [x for x in feats if x["state"] in ("mismatch", "incompatible")],
        "unknowns": [x for x in feats if x["state"] == "unknown"],
        "match_score": round(match_w / total_w, 3) if total_w else 0.0,
        "coverage": round(known_w / total_w, 3) if total_w else 0.0,
        "eligibility": eligibility,
        "exclusion_reasons": hard,
        "next_evidence": next_ev[:5],
        "score_note": "Ordinal weighted share of matched features; not a probability of success.",
    }


ELIG_RANK = {"candidate_lead": 0, "needs_local_evidence": 1, "partial_component_only": 2, "excluded": 3}


def run_match(session_id: str, iid: str, rid: str | None = None, persist: bool = True) -> dict:
    ctx = context_for(session_id, iid, rid)
    gv = graph.graph_version(None)  # public solutions graph version
    inputs = {k: ctx[k] for k in ("mechanism", "scale", "requirements", "disputed")}
    inputs["findings"] = [{k: f[k] for k in ("id", "variable", "significant", "direction", "disputed", "kind")}
                          for f in ctx["findings"]]
    key = hashlib.sha256(db.dumps({"inv": iid, "inputs": inputs, "gv": gv, "rule": MATCH_RULE_VERSION}).encode()).hexdigest()[:24]
    with db.conn() as c:
        row = c.execute("SELECT * FROM match_runs WHERE cache_key=?", (key,)).fetchone()
    if row:
        res = db.loads(row["result_json"])
        res.update({"id": row["id"], "reused": True, "revision_id": ctx["revision_id"]})
        return res
    evals = [evaluate(ctx, itv) for itv in _interventions(session_id)]
    evals.sort(key=lambda e: (ELIG_RANK[e["eligibility"]], -e["match_score"], -e["coverage"], e["intervention_id"]))
    leads = [e for e in evals if e["eligibility"] != "excluded"][:3]
    excluded = [e for e in evals if e["eligibility"] == "excluded"]
    shown = {e["intervention_id"] for e in leads}
    others = [e for e in evals if e["eligibility"] != "excluded" and e["intervention_id"] not in shown]
    insufficient = not ctx["mechanism"]
    result = {
        "investigation_id": iid,
        "revision_id": ctx["revision_id"],
        "graph_version": gv,
        "rule_version": MATCH_RULE_VERSION,
        "context": ctx,
        "leads": leads,
        "other_candidates": others,
        "excluded": excluded,
        "insufficient_context": insufficient,
        "query": {
            "description": "For each Intervention node: follow ADDRESSES→Mechanism, REQUIRES→Requirement (decisive flag), "
                           "REPORTED_OUTCOME→Outcome and incoming CONTRADICTS; compare with the investigation's revision "
                           "state (mechanism, scale, requirement assessments) and computed Finding nodes.",
            "interventions_considered": len(evals),
            "edge_types": ["ADDRESSES", "REQUIRES", "REPORTED_OUTCOME", "CONTRADICTS", "HAS_FINDING", "ASSESSES"],
        },
    }
    mid = "match-" + key[:12]
    if persist:
        with db.tx() as c:
            c.execute("INSERT OR IGNORE INTO match_runs(id,cache_key,investigation_id,revision_id,graph_version,rule_version,"
                      "inputs_json,result_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (mid, key, iid, ctx["revision_id"], gv, MATCH_RULE_VERSION, db.dumps(inputs), db.dumps(result),
                       db.now_iso()))
            for e in leads:
                graph.add_edge(c, e["intervention_id"], "CANDIDATE_FOR", iid, status="hypothesis", scope=session_id,
                               props={"match_run": mid, "eligibility": e["eligibility"], "match_score": e["match_score"],
                                      "revision_id": ctx["revision_id"]})
    result.update({"id": mid, "reused": False})
    return result


def what_changed(session_id: str, iid: str, from_rid: str, to_rid: str) -> dict:
    a = run_match(session_id, iid, from_rid)
    b = run_match(session_id, iid, to_rid)
    inv = get_investigation(session_id, iid)
    revs = {r["id"]: r for r in inv["revisions"]}
    by_a = {e["intervention_id"]: e for e in a["leads"] + a["other_candidates"] + a["excluded"]}
    by_b = {e["intervention_id"]: e for e in b["leads"] + b["other_candidates"] + b["excluded"]}
    rank_a = {e["intervention_id"]: i for i, e in enumerate(a["leads"])}
    rank_b = {e["intervention_id"]: i for i, e in enumerate(b["leads"])}
    diffs = []
    for iv in sorted(set(by_a) | set(by_b)):
        ea, eb = by_a.get(iv), by_b.get(iv)
        changed_feats = []
        fa = {f["feature"]: f for f in (ea or {}).get("features", [])}
        for f in (eb or {}).get("features", []):
            if fa.get(f["feature"], {}).get("state") != f["state"]:
                changed_feats.append({"feature": f["feature"], "from": fa.get(f["feature"], {}).get("state"),
                                      "to": f["state"], "detail": f["detail"]})
        diffs.append({
            "after_features": [{k: f[k] for k in ("feature", "state", "kind", "weight", "detail")} for f in (eb or {}).get("features", [])],
            "before_features": [{k: f[k] for k in ("feature", "state", "kind", "weight")} for f in (ea or {}).get("features", [])],
            "source_id": (eb or ea).get("source_id"), "locator": (eb or ea).get("locator"),
            "intervention_id": iv, "title": (eb or ea)["title"], "source_place": (eb or ea)["source_place"],
            "eligibility": {"from": ea and ea["eligibility"], "to": eb and eb["eligibility"]},
            "match_score": {"from": ea and ea["match_score"], "to": eb and eb["match_score"]},
            "coverage": {"from": ea and ea["coverage"], "to": eb and eb["coverage"]},
            "lead_rank": {"from": rank_a.get(iv), "to": rank_b.get(iv)},
            "changed_features": changed_feats,
            "changed": bool(changed_feats) or (ea and eb and ea["eligibility"] != eb["eligibility"]),
        })
    top_a = a["leads"][0]["intervention_id"] if a["leads"] else None
    top_b = b["leads"][0]["intervention_id"] if b["leads"] else None
    # revisions between
    seq_a, seq_b = revs[from_rid]["seq"], revs[to_rid]["seq"]
    lo, hi = sorted((seq_a, seq_b))
    responsible = [r for r in inv["revisions"] if lo < r["seq"] <= hi]
    return {
        "from": {"revision_id": from_rid, "match_run": a["id"], "reused": a["reused"]},
        "to": {"revision_id": to_rid, "match_run": b["id"], "reused": b["reused"]},
        "responsible_revisions": responsible,
        "top_lead": {"from": top_a, "to": top_b, "changed": top_a != top_b},
        "candidates": diffs,
        "unchanged_note": None if top_a != top_b else
        "The top lead did not change. Remaining unknowns: " + "; ".join(b["leads"][0]["next_evidence"] if b["leads"] else []),
        "artifacts_reused": "Revisions do not change acquisition inputs; NASA artifacts and trend analyses are reused unchanged.",
        "rule_version": MATCH_RULE_VERSION,
        "rules": {
            "eligibility": [
                "excluded: different hazard family, or a decisive prerequisite recorded as not satisfied",
                "partial_component_only: same hazard family, different mechanism",
                "needs_local_evidence: any decisive prerequisite (or the mechanism) still unknown",
                "candidate_lead: mechanism compatible and every decisive prerequisite satisfied",
            ],
            "ordering": "Leads are ordered by eligibility (candidate → needs evidence → partial), then ordinal match "
                        "score, then coverage. Ordering reflects evidence completeness for this target; it does not "
                        "mean one response replaces another.",
            "weights": {"mechanism": W_MECH, "prerequisite": W_REQ, "scale": W_SCALE, "climate_signal": W_SIGNAL},
        },
    }
