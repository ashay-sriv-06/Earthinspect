"""EarthInspect API + static frontend (single deployable process)."""
from __future__ import annotations

import re
import threading

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import catalog, copilot, db, graph, matching, power, report, services, trace
from .cases import MECHANISMS, all_cases, get_case
from .config import DATA_DIR, FRONTEND_DIST, POWER_END_YEAR, POWER_START_YEAR
from .errors import ApiError
from .geometry import canonical
from .requirements import REQUIREMENTS

app = FastAPI(title="EarthInspect", version="1.0.0")
COOKIE = "ei_sid"


@app.on_event("startup")
def _startup():
    db.init_db()
    services.seed_graph()


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return JSONResponse(exc.to_dict(), status_code=exc.status)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse({"error": {"code": "internal", "message": "Unexpected server error.", "detail": {}}}, status_code=500)


@app.middleware("http")
async def session_mw(request: Request, call_next):
    sid = request.cookies.get(COOKIE)
    new = False
    if not (sid and re.fullmatch(r"s-[0-9a-f]{32}", sid) and services.session_exists(sid)):
        if request.url.path.startswith("/api/"):
            sid = services.new_session()
            new = True
        else:
            sid = None
    request.state.sid = sid
    resp = await call_next(request)
    if new:
        resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 90)
    return resp


def sid(request: Request) -> str:
    return request.state.sid


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health():
    with db.conn() as c:
        n_art = c.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    return {"status": "ok", "db": "sqlite", "data_dir_writable": DATA_DIR.exists(), "artifacts": n_art,
            "llm": copilot.llm_available(), "persistence": "SQLite + artifact directory at EARTHINSPECT_DATA_DIR"}


@app.get("/api/meta")
def meta(request: Request):
    cat = catalog.build_catalog()
    return {
        "mechanisms": MECHANISMS, "requirements": REQUIREMENTS, "variables": power.SUPPORTED_VARIABLES,
        "period_bounds": {"start": f"{POWER_START_YEAR}-01", "end": f"{POWER_END_YEAR}-12"},
        "llm": copilot.llm_available(),
        "catalog_counts": {"entries": len(cat), "analysis_ready_adapters": sum(e["status"] == "analysis_ready" for e in cat),
                           "imagery_adapters": sum(e["status"] == "imagery_view" for e in cat)},
        "graph": graph.stats(sid(request)),
    }


# ------------------------------------------------------------------ cases & catalog

@app.get("/api/cases")
def cases():
    return all_cases()


@app.get("/api/cases/{case_id}")
def case(case_id: str, request: Request):
    c = get_case(case_id)
    c["computed_findings"] = services.latest_public_findings(f"place-{case_id}", services.DEFAULT_PERIOD)
    return c


@app.get("/api/catalog")
def catalog_search(q: str = "", hazard: str | None = None):
    return catalog.search(q, hazard)


@app.get("/api/catalog/cmr")
def catalog_cmr(q: str):
    return catalog.cmr_live_search(q)


# ------------------------------------------------------------------ investigations

@app.get("/api/investigations")
def inv_list(request: Request):
    return services.list_investigations(sid(request))


@app.post("/api/investigations")
async def inv_create(request: Request):
    return services.create_investigation(sid(request), await request.json())


@app.get("/api/investigations/{iid}")
def inv_get(iid: str, request: Request):
    return services.get_investigation(sid(request), iid)


@app.patch("/api/investigations/{iid}")
async def inv_patch(iid: str, request: Request):
    return services.update_view(sid(request), iid, await request.json())


@app.post("/api/investigations/{iid}/analyze")
async def inv_analyze(iid: str, request: Request):
    body = await request.json() if (await request.body()) else {}
    events = []
    batch = services.run_trends_for(sid(request), iid, body.get("variables"), force_refresh=bool(body.get("force_refresh")),
                                    on_event=lambda t, l, p, d=None: events.append({"type": t, "label": l, "payload": p, "duration_ms": d}))
    batch["events"] = events
    return batch


@app.get("/api/investigations/{iid}/results")
def inv_results(iid: str, request: Request):
    b = report.current_batch(sid(request), iid)
    if not b:
        return {"batch": None}
    arts = [power.get_artifact(a) for a in b["artifact_ids"]]
    inv = services.get_investigation(sid(request), iid)
    assoc = None
    if {"T2M", "PRECTOTCORR"} <= {a["variable"] for a in arts}:
        assoc = services.associate_vars([{"artifact": a} for a in arts], "T2M", "PRECTOTCORR",
                                        inv["config"]["period"]["start"], inv["config"]["period"]["end"])
    return {"batch": b, "artifacts": arts, "association": assoc}


@app.get("/api/artifacts/{aid}")
def artifact(aid: str):
    return power.get_artifact(aid)


@app.get("/api/investigations/{iid}/match")
def inv_match(iid: str, request: Request, revision: str | None = None):
    return matching.run_match(sid(request), iid, revision)


@app.post("/api/investigations/{iid}/revisions")
async def inv_revise(iid: str, request: Request):
    return services.add_revision(sid(request), iid, await request.json())


@app.post("/api/investigations/{iid}/revisions/{rid}/activate")
def inv_switch(iid: str, rid: str, request: Request):
    return services.switch_revision(sid(request), iid, rid)


@app.get("/api/investigations/{iid}/what-changed")
def inv_changed(iid: str, request: Request, frm: str, to: str):
    return matching.what_changed(sid(request), iid, frm, to)


@app.get("/api/investigations/{iid}/trace/{intervention_id}")
def inv_trace(iid: str, intervention_id: str, request: Request):
    return trace.build(sid(request), iid, intervention_id)


@app.get("/api/investigations/{iid}/export.csv")
def exp_csv(iid: str, request: Request):
    return PlainTextResponse(report.export_csv(sid(request), iid), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{iid}.csv"'})


@app.get("/api/investigations/{iid}/export.json")
def exp_json(iid: str, request: Request):
    return JSONResponse(report.export_json(sid(request), iid),
                        headers={"Content-Disposition": f'attachment; filename="{iid}.json"'})


@app.get("/api/investigations/{iid}/export.html")
def exp_html(iid: str, request: Request, inline: int = 0):
    h = {} if inline else {"Content-Disposition": f'attachment; filename="{iid}-report.html"'}
    return HTMLResponse(report.export_html(sid(request), iid), headers=h)


# ------------------------------------------------------------------ copilot

@app.post("/api/investigations/{iid}/copilot")
async def cp_start(iid: str, request: Request):
    b = await request.json()
    return {"run_id": copilot.start(sid(request), iid, b.get("question", ""), b.get("mode", "guided"))}


@app.get("/api/investigations/{iid}/copilot")
def cp_list(iid: str, request: Request):
    return copilot.list_runs(sid(request), iid)


@app.get("/api/copilot/{rid}")
def cp_get(rid: str, request: Request, since: int = 0):
    return copilot.get_run(sid(request), rid, since)


@app.post("/api/copilot/{rid}/cancel")
def cp_cancel(rid: str, request: Request):
    return copilot.cancel(sid(request), rid)


# ------------------------------------------------------------------ graph

@app.get("/api/graph/stats")
def g_stats(request: Request):
    return graph.stats(sid(request))


@app.get("/api/graph/node/{nid}")
def g_node(nid: str, request: Request):
    return graph.get_node(nid, sid(request))


@app.get("/api/graph/provenance/{nid}")
def g_prov(nid: str, request: Request):
    return graph.provenance_path(nid, sid(request))


@app.get("/api/graph/neighborhood/{nid}")
def g_nb(nid: str, request: Request):
    return graph.neighborhood(nid, sid(request))


@app.get("/api/graph/bundle/{bid}")
def g_bundle(bid: str, request: Request):
    return graph.get_bundle(bid, sid(request))


@app.get("/api/graph/sources")
def g_sources(request: Request):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM nodes WHERE type='Source' AND scope='public' ORDER BY id").fetchall()
    return [graph.node_dict(r) for r in rows]


# ------------------------------------------------------------------ compare

def _side(ref: str, s: str) -> dict:
    kind, _, ident = ref.partition(":")
    if kind == "case":
        c = get_case(ident)
        fs = services.latest_public_findings(f"place-{ident}", services.DEFAULT_PERIOD)
        with db.conn() as cn:
            itvs = [graph.node_dict(r) for r in cn.execute(
                "SELECT * FROM nodes WHERE type='Intervention' AND json_extract(props_json,'$.case_id')=?", (ident,)).fetchall()]
        return {"ref": ref, "name": c["display_name"], "mechanism": c["hazard_mechanism"], "scale": c["scale"],
                "geometry": c["analysis_geometry"], "geometry_origin": c["geometry_origin"],
                "period": services.DEFAULT_PERIOD, "event": {"start": c["event_start"], "end": c["event_end"], "summary": c["summary"]},
                "findings": fs, "responses": itvs}
    if kind == "inv":
        inv = services.get_investigation(s, ident)
        fs = services.latest_findings(s, ident)
        return {"ref": ref, "name": inv["config"]["place"]["name"], "mechanism": inv["state"].get("mechanism"),
                "scale": inv["state"].get("scale"), "geometry": inv["config"]["place"]["geometry"],
                "geometry_origin": inv["config"]["place"].get("geometry_origin"), "period": inv["config"]["period"],
                "event": None, "findings": fs, "responses": []}
    raise ApiError("invalid_request", "Reference must be case:<id> or inv:<id>.")


@app.get("/api/compare")
def compare(a: str, b: str, request: Request):
    A, B = _side(a, sid(request)), _side(b, sid(request))
    rows = []
    vars_ = sorted({f["props"]["variable"] for f in A["findings"]} | {f["props"]["variable"] for f in B["findings"]})
    for v in vars_:
        fa = next((f for f in A["findings"] if f["props"]["variable"] == v), None)
        fb = next((f for f in B["findings"] if f["props"]["variable"] == v), None)
        comparable = bool(fa and fb and fa["props"].get("units") == fb["props"].get("units")
                          and fa["props"]["period"] == fb["props"]["period"])
        rows.append({"variable": v, "a": fa, "b": fb, "directly_comparable": comparable,
                     "note": None if comparable else "Not directly comparable (missing result, different units or period)."})
    return {"a": A, "b": B, "variables": rows,
            "spatial_note": "Both are regional area-weighted MERRA-2 grid means over analyst-selected boxes; they do not represent the same land area or city-scale conditions."}


# ------------------------------------------------------------------ geo helpers (fixed hosts only)

@app.get("/api/geocode")
def geocode(q: str):
    q = re.sub(r"[^\w ,.\-']", "", q, flags=re.UNICODE)[:80].strip()
    if len(q) < 2:
        raise ApiError("invalid_query", "Enter at least two characters.")
    try:
        r = httpx.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": q, "count": 6, "format": "json"}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        raise ApiError("geocoder_unavailable", f"Geocoder unavailable ({type(e).__name__}). Enter coordinates instead.", status=503)
    return [{"name": x.get("name"), "admin1": x.get("admin1"), "country": x.get("country"),
             "lat": x.get("latitude"), "lon": x.get("longitude"), "source": "Open-Meteo Geocoding (GeoNames)"}
            for x in r.json().get("results", []) or []]


GIBS_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"


@app.get("/api/imagery/check")
def imagery_check(date: str, z: int = 5, x: int = 17, y: int = 10):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ApiError("invalid_date", "Date must be YYYY-MM-DD.")
    z, x, y = max(0, min(int(z), 9)), max(0, int(x)), max(0, int(y))
    url = f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{GIBS_LAYER}/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
    try:
        r = httpx.get(url, timeout=15)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
    except Exception:
        return {"available": None, "reason": "GIBS did not respond", "layer": GIBS_LAYER}
    return {"available": ok, "status": r.status_code, "layer": GIBS_LAYER, "date": date,
            "reason": None if ok else "No imagery tile for this date/location."}


# ------------------------------------------------------------------ static frontend

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Unknown API route."}}, status_code=404)
        f = FRONTEND_DIST / path
        if path and f.is_file() and FRONTEND_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
