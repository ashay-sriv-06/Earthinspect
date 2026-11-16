"""End-to-end API acceptance check against a running server (default http://127.0.0.1:8000).
Exercises: session isolation, case investigation, cache reuse, match, revision -> what-changed, guided copilot,
trace, new place (Nairobi functional test location), exports, provider-error handling."""
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
A = httpx.Client(base_url=BASE, timeout=180)
B = httpx.Client(base_url=BASE, timeout=180)
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or c  # noqa: E731
res = {}

h = A.get("/api/health").json()
ok(h["status"] == "ok", f"health ok, artifacts={h['artifacts']}, llm={h['llm']['available']}")
cases = A.get("/api/cases").json()
ok(len(cases) == 4, "four case files")
for c in cases:
    ok(all(i.get("source_id") and i.get("locator") for i in c["interventions"]), f"{c['id']}: every intervention has source locator")

inv = A.post("/api/investigations", json={"case_id": "copenhagen-2011"}).json()
iid = inv["id"]
an = A.post(f"/api/investigations/{iid}/analyze", json={}).json()
st = [e["type"] for e in an["events"]]
ok("cache_cached" in st and "cache_fetched" not in st, f"case data reused from cache: {st.count('cache_cached')} cached")
ok(an["reused"], "trend analysis reused (prewarmed)")
r = A.get(f"/api/investigations/{iid}/results").json()
t2m = next(x for x in r["batch"]["results"] if x["variable"] == "T2M")
ok(t2m["mode"] == "inferential" and t2m["q_value"] is not None, f"Copenhagen T2M {t2m['slope_per_decade']:+.3f} C/dec q={t2m['q_value']:.2g}")

# isolation
ok(B.get(f"/api/investigations/{iid}").status_code == 404, "other session cannot read investigation")
ok(B.post(f"/api/investigations/{iid}/revisions", json={"kind": "set_scale", "scale": "city", "rationale": "x"}).status_code == 404, "other session cannot revise")

# provenance
fid = r["batch"]["finding_ids"][0]
p = A.get(f"/api/graph/provenance/{fid}").json()
types = {n["type"] for n in p["nodes"]}
ok({"Finding", "Analysis", "Artifact", "Dataset"} <= types, f"provenance reaches {sorted(types)}")

# match
m = A.get(f"/api/investigations/{iid}/match").json()
lead_ids = [l["intervention_id"] for l in m["leads"]]
ok(m["leads"] and m["leads"][0]["source_case"] == "copenhagen-2011", f"leads: {[(l['intervention_id'], l['eligibility']) for l in m['leads']]}")
ok(any(e["source_case"] == "camp-fire-2018" for e in m["excluded"]), "wildfire responses excluded for pluvial target")
bri = next((e for e in m["leads"] + m["other_candidates"] if e["source_case"] == "brisbane-2011"), None)
ok(bri is None or bri["eligibility"] == "partial_component_only", f"Brisbane response is mechanism mismatch for Copenhagen: {bri and bri['eligibility']}")

# revision -> what changed
rev0 = A.get(f"/api/investigations/{iid}").json()["current_revision_id"]
inv2 = A.post(f"/api/investigations/{iid}/revisions", json={"kind": "set_requirement", "requirement_id": "req-open-space-retention",
             "state": "satisfied", "basis": "analyst_assumption", "rationale": "Scenario: parks can be regraded"}).json()
rev1 = inv2["current_revision_id"]
wc = A.get(f"/api/investigations/{iid}/what-changed", params={"frm": rev0, "to": rev1}).json()
ch = [c for c in wc["candidates"] if c["changed"]]
ok(ch and any("req-open-space-retention" in f["feature"] for c in ch for f in c["changed_features"]), f"what-changed: {[(c['intervention_id'], c['eligibility']) for c in ch]}")
g_before = A.get("/api/graph/stats").json()
an2 = A.post(f"/api/investigations/{iid}/analyze", json={}).json()
g_after = A.get("/api/graph/stats").json()
ok(g_before["nodes"] == g_after["nodes"] and g_before["edges"].get("DERIVED_FROM") == g_after["edges"].get("DERIVED_FROM"),
   f"repeat ingestion idempotent (nodes {sum(g_after['nodes'].values())}, bundles {g_after['bundles']})")
ok(an2["reused"] and all(e["type"] != "cache_fetched" for e in an2["events"]), "revision did not trigger refetch")
ok(A.get(f"/api/investigations/{iid}/match", params={"revision": rev0}).json()["reused"], "prior revision match still inspectable (reused)")

# trace
tr = A.get(f"/api/investigations/{iid}/trace/{m['leads'][0]['intervention_id']}").json()
tt = {n["type"] for n in tr["nodes"]}
ok({"Intervention", "Source", "Requirement", "Mechanism"} <= tt and "Artifact" in tt, f"trace node types {sorted(tt)} edges={len(tr['edges'])}")

# guided copilot
run = A.post(f"/api/investigations/{iid}/copilot", json={"question": "What is changing here and which historical experiences are relevant?", "mode": "guided"}).json()["run_id"]
for _ in range(120):
    g = A.get(f"/api/copilot/{run}").json()
    if g["status"] != "running":
        break
    time.sleep(0.5)
ok(g["status"] == "done", f"guided run {g['status']} with {len(g['events'])} events: {[e['type'] for e in g['events']][:12]}")
ok(g["answer"] and g["answer"]["findings"] and all(i["cites"] for i in g["answer"]["findings"][:-1]), "answer findings cited")
llm = A.post(f"/api/investigations/{iid}/copilot", json={"question": "x", "mode": "llm"})
ok(llm.status_code in (200, 409), f"llm mode without key -> {llm.status_code} {llm.json().get('error', {}).get('code')}")

# exports
for fmt_ in ("csv", "json", "html"):
    e = A.get(f"/api/investigations/{iid}/export.{fmt_}")
    ok(e.status_code == 200 and len(e.content) > 500, f"export {fmt_}: {len(e.content)} bytes")
ej = A.get(f"/api/investigations/{iid}/export.json").json()
ok(ej["graph_version"] and ej["artifacts"][0]["sha256"], "export JSON carries graph version + artifact hashes")

# new place (functional test location, not validation)
np_ = A.post("/api/investigations", json={"place": {"name": "Nairobi, Kenya", "geometry": {"type": "bbox", "west": 35.82, "south": -2.29, "east": 37.82, "north": -0.29}, "geometry_origin": "Functional test: 2x2 deg box around geocoded point"}, "mechanism": "pluvial_urban_flood"}).json()
t0 = time.time()
na = A.post(f"/api/investigations/{np_['id']}/analyze", json={}).json()
ok(not na.get("error"), f"new place analysis {na.get('id')} in {time.time() - t0:.1f}s; cache states {[e['type'] for e in na['events'] if e['type'].startswith('cache')]}")
res["new_place_artifacts"] = [a["artifact"]["id"] for a in na["acquisitions"]]
nm = A.get(f"/api/investigations/{np_['id']}/match").json()
ok(all(l["source_place"] for l in nm["leads"]), f"new place leads keep source city: {[(l['source_place'], l['eligibility']) for l in nm['leads']]}")
na2 = A.post(f"/api/investigations/{np_['id']}/analyze", json={}).json()
ok(all(e["type"] != "cache_fetched" for e in na2["events"]), "repeat new-place request reused cache")
bad = A.post("/api/investigations", json={"place": {"name": "x", "geometry": {"type": "bbox", "west": 179, "south": 0, "east": -179, "north": 2}}})
ok(bad.status_code == 400 and bad.json()["error"]["code"] == "antimeridian_unsupported", "antimeridian rejected")
print(json.dumps(res))
