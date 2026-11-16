"""Prompt 4: copilot on the canonical demo with available credentials (none configured → guided only)."""
import time

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=120)
ok = []


def check(cond, m):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + m)


meta = c.get("/api/meta").json()
check(meta["llm"]["available"] is False and "not set" in (meta["llm"]["reason"] or ""), "server reports no model credential (value never exposed)")
inv = c.post("/api/demo").json()
r = c.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What can be learned here, and which assumptions does it depend on?", "mode": "llm"})
check(r.status_code == 409 and r.json()["error"]["code"] == "llm_unavailable", "LLM mode refused cleanly without a key (no paid call attempted)")
rid = c.post(f"/api/investigations/{inv['id']}/copilot", json={"question": "What can be learned here, and which assumptions does it depend on?", "mode": "guided"}).json()["run_id"]
for _ in range(80):
    g = c.get(f"/api/copilot/{rid}").json()
    if g["status"] != "running":
        break
    time.sleep(0.5)
a = g["answer"] or {}
check(g["status"] == "done" and "Guided analysis" in a.get("label", ""), f"guided run done and labelled ({a.get('label')})")
types = [e["type"] for e in g["events"]]
check("tool_call" in types and "cache_cached" in types and "match_run" in types, f"real tool events: {sorted(set(types))}")
mu = a.get("mismatches_unknowns", [])
asm = [i for i in mu if "In effect at revision" in i["text"]]
check(asm and asm[0]["cites"] and asm[0]["cites"][0].startswith("asm-"), f"answer states the assumption in effect, cited to its node: {asm[0]['text'][:120] if asm else None} {asm[0]['cites'] if asm else ''}")
check(any("Retrospective case" in i["text"] for i in mu), "answer carries the retrospective notice")
check(all(i["cites"] for i in a.get("findings", [])[:-1]) and all(i["cites"] for i in a.get("precedents", [])), "findings and precedents all cited")
check(not a.get("removed_claims"), f"no unsupported claims needed removal ({len(a.get('removed_claims', []))})")
print(f"{sum(ok)}/{len(ok)} passed")
