"""Smoke-test evaluation: graph-assisted contextual retrieval vs a keyword baseline on the SAME evidence corpus.
Eight questions with source-backed expected distinctions. This is a smoke test, not proof of general superiority.
Usage: python -m scripts.eval_retrieval  (writes ../docs/eval_results.json)"""
import json
import re
from pathlib import Path

from app import db, services
from app.matching import ELIG_RANK, _interventions, evaluate

db.init_db()
services.seed_graph()
ITV = _interventions(None)
FAMILY = {"pluvial_urban_flood": "flood", "riverine_catchment_flood": "flood", "wui_wildfire": "fire", "multiyear_drought": "drought"}
CASE_MECH = {"copenhagen-2011": "pluvial_urban_flood", "brisbane-2011": "riverine_catchment_flood",
             "camp-fire-2018": "wui_wildfire", "cape-town-2015-2018": "multiyear_drought"}
S = lambda st: {"state": st, "basis": "analyst_assumption", "note": "eval"}  # noqa: E731

Q = [
    {"id": "Q1-flood-mechanism-mismatch", "q": "Our river city floods when the catchment rains for days. Should we build cloudburst parks and surface water retention like Copenhagen?",
     "ctx": {"mechanism": "riverine_catchment_flood", "scale": "catchment", "requirements": {}},
     "must_flag": {"int-cph-combined-surface-tunnel": ["partial_component_only", "excluded"]},
     "basis": "Copenhagen plan addresses pluvial cloudbursts (Climate-ADAPT); Brisbane 2011 was a river/catchment flood (BoM)."},
    {"id": "Q2-unknown-prerequisite", "q": "Dense city with cloudburst flooding: should we adopt surface retention and tunnels?",
     "ctx": {"mechanism": "pluvial_urban_flood", "scale": "city", "requirements": {}},
     "must_flag": {"int-cph-combined-surface-tunnel": ["needs_local_evidence"]},
     "basis": "Plan prerequisite: public open space for detention (Cloudburst plan) — unknown for the target."},
    {"id": "Q3-projected-outcome", "q": "What benefit did Copenhagen's cloudburst plan achieve for flood damage?",
     "ctx": {"mechanism": "pluvial_urban_flood", "scale": "city", "requirements": {}},
     "must_outcome": {"int-cph-combined-surface-tunnel": "projected"},
     "basis": "Economic results are projections in the plan, not observed outcomes (Climate-ADAPT)."},
    {"id": "Q4-wildfire-no-live-routing", "q": "During a wildfire can we route evacuees live to temporary refuge areas and safety zones?",
     "ctx": {"mechanism": "wui_wildfire", "scale": "city", "requirements": {}},
     "must_flag": {"int-cf-safety-zones": ["needs_local_evidence"]},
     "must_status": {"int-cf-safety-zones": "retrospective_recommendation"},
     "basis": "NIST TN 2252: refuge areas are a last resort; recommendations are retrospective, not a routing service."},
    {"id": "Q5-new-city-insufficient", "q": "What should a new coastal city do about water and floods and fire?",
     "ctx": {"mechanism": None, "scale": None, "requirements": {}},
     "expect_all_unresolved": True,
     "basis": "No mechanism established: no precedent may be presented as transferable."},
    {"id": "Q6-drought-demand-ready", "q": "Our metered city faces a reservoir drought; which demand management measures and tariffs and restrictions are relevant?",
     "ctx": {"mechanism": "multiyear_drought", "scale": "city", "requirements": {"req-restriction-authority": S("satisfied"), "req-household-metering": S("satisfied")}},
     "must_flag": {"int-ct-restrictions-tariffs": ["candidate_lead"]},
     "basis": "Cape Town Water Strategy: restrictions & tariffs implemented during the crisis; prerequisites supplied as assumptions."},
    {"id": "Q7-drought-vs-flood-green-space", "q": "Drought city: should we create green parks and water retention space for water?",
     "ctx": {"mechanism": "multiyear_drought", "scale": "city", "requirements": {}},
     "must_flag": {"int-cph-combined-surface-tunnel": ["excluded"]},
     "basis": "Flood retention (Copenhagen) addresses a different hazard family than supply drought."},
    {"id": "Q8-prerequisite-unsatisfied", "q": "Pluvial flooding city with no available open space: surface retention parks?",
     "ctx": {"mechanism": "pluvial_urban_flood", "scale": "city", "requirements": {"req-open-space-retention": S("unsatisfied")}},
     "must_flag": {"int-cph-combined-surface-tunnel": ["excluded"]},
     "basis": "Decisive prerequisite (open space for detention) not satisfied."},
]


def keyword(q):
    toks = set(re.findall(r"[a-z]{4,}", q.lower()))
    scored = []
    for it in ITV:
        p = it["props"]
        text = " ".join([it["label"], p.get("objective", ""), p.get("category", ""), " ".join(p.get("prerequisites", []))]).lower()
        s = sum(1 for t in toks if t in text)
        scored.append((s, it["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [i for _, i in scored[:3]]


def graph_method(ctx):
    full = {**ctx, "findings": [], "disputed": []}
    ev = [evaluate(full, it) for it in ITV]
    ev.sort(key=lambda e: (ELIG_RANK[e["eligibility"]], -e["match_score"], e["intervention_id"]))
    return {e["intervention_id"]: e for e in ev}, [e["intervention_id"] for e in ev if e["eligibility"] != "excluded"][:3]


case_of = {it["id"]: it["props"]["case_id"] for it in ITV}
status_of = {it["id"]: it["props"]["status"] for it in ITV}
outcome_of = {it["id"]: it["props"]["outcome_type"] for it in ITV}
rows = []
tot = {"graph": {"source_correct": 0, "mismatch_detected": 0, "unsupported": 0}, "keyword": {"source_correct": 0, "mismatch_detected": 0, "unsupported": 0}}
for q in Q:
    by, gtop = graph_method(q["ctx"])
    ktop = keyword(q["q"])
    fam = FAMILY.get(q["ctx"]["mechanism"]) if q["ctx"]["mechanism"] else None
    res = {"id": q["id"], "basis": q["basis"], "graph_top3": gtop, "keyword_top3": ktop}
    for name, top in (("graph", gtop), ("keyword", ktop)):
        # source correctness: returned leads come from the same hazard family (and carry a source locator)
        sc = sum(1 for i in top if fam and FAMILY[CASE_MECH[case_of[i]]] == fam)
        # unsupported: a lead presented without qualification that is from another family, or any confident lead with no mechanism
        if name == "graph":
            uns = sum(1 for i in top if by[i]["eligibility"] == "candidate_lead" and (not fam or FAMILY[CASE_MECH[case_of[i]]] != fam))
        else:
            uns = sum(1 for i in top if not fam or FAMILY[CASE_MECH[case_of[i]]] != fam)
        # mismatch / qualification detection
        md, need = 0, 0
        for iid, ok_states in q.get("must_flag", {}).items():
            need += 1
            if name == "graph" and by[iid]["eligibility"] in ok_states:
                md += 1
        for iid, otype in q.get("must_outcome", {}).items():
            need += 1
            if name == "graph" and by[iid]["outcome_evidence_type"] == otype == outcome_of[iid]:
                md += 1
        for iid, st in q.get("must_status", {}).items():
            need += 1
            if name == "graph" and by[iid]["implementation_status"] == st:
                md += 1
        if q.get("expect_all_unresolved"):
            need += 1
            if name == "graph" and all(by[i]["eligibility"] in ("needs_local_evidence",) for i in top):
                md += 1
        res[name] = {"source_correct": f"{sc}/{len(top)}" if fam else "n/a (no mechanism)", "qualifications_detected": f"{md}/{need}", "unsupported": uns}
        tot[name]["source_correct"] += sc
        tot[name]["mismatch_detected"] += md
        tot[name]["unsupported"] += uns
    res["need"] = sum(len(q.get(k, {})) for k in ("must_flag", "must_outcome", "must_status")) + (1 if q.get("expect_all_unresolved") else 0)
    rows.append(res)
total_need = sum(r["need"] for r in rows)
summary = {
    "questions": len(Q),
    "graph": {**tot["graph"], "qualifications_possible": total_need, "source_correct_possible": 21},
    "keyword": {**tot["keyword"], "qualifications_possible": total_need, "source_correct_possible": 21},
    "notes": [
        "Keyword baseline ranks the same intervention records by token overlap; it carries no mechanism, prerequisite or outcome-type reasoning, so it cannot score qualification checks.",
        "Eight questions are a smoke test written by the builders; they are not an independent benchmark.",
    ],
}
out = Path(__file__).resolve().parent.parent.parent / "docs" / "eval_results.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
for r in rows:
    print(r["id"], "| graph", r["graph"], r["graph_top3"], "| keyword", r["keyword"], r["keyword_top3"])
print(json.dumps(summary, indent=1))
