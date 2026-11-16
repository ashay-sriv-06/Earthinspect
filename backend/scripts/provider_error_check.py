"""Check graceful handling of a model-provider error (server started with an INVALID key on :8001)."""
import sys
import time

import httpx

c = httpx.Client(base_url=sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001", timeout=120)
print("llm advertised:", c.get("/api/meta").json()["llm"])
inv = c.post("/api/investigations", json={"case_id": "brisbane-2011"}).json()
rid = c.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is changing here?", "mode": "llm"}).json()["run_id"]
for _ in range(60):
    r = c.get(f"/api/copilot/{rid}").json()
    if r["status"] != "running":
        break
    time.sleep(0.5)
print("llm run status:", r["status"], "| error:", r["error"])
print("events:", [(e["type"], e["label"]) for e in r["events"]])
assert r["status"] == "error" and "sk-ant" not in str(r), "secret leaked or wrong state"
a = c.post(f"/api/investigations/{inv['id']}/analyze", json={}).json()
print("trends still work:", a["id"], [x["variable"] for x in a["results"]])
g = c.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What is changing here?", "mode": "guided"}).json()["run_id"]
for _ in range(60):
    r = c.get(f"/api/copilot/{g}").json()
    if r["status"] != "running":
        break
    time.sleep(0.5)
print("guided fallback:", r["status"], len(r["answer"]["findings"]), "findings")
