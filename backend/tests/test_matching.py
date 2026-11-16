"""Matching acceptance (Prompt 10) and revision isolation (Prompt 14) on a fresh temporary database.
Uses only the seeded public graph (case files); no network access."""
import os
import tempfile

os.environ["EARTHINSPECT_DATA_DIR"] = tempfile.mkdtemp(prefix="ei-match-")

import pytest  # noqa: E402

from app import db, services  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.matching import _interventions, evaluate  # noqa: E402

db.init_db()
services.seed_graph()
ITV = {i["id"]: i for i in _interventions(None)}
A = lambda st: {"state": st, "basis": "analyst_assumption", "note": "t"}  # noqa: E731


def ctx(mech="pluvial_urban_flood", scale="city", reqs=None, findings=None):
    return {"mechanism": mech, "scale": scale, "requirements": reqs or {}, "findings": findings or [], "disputed": []}


def ev(iid, c):
    return evaluate(c, ITV[iid])


def test_mechanism_change_changes_eligibility():
    tunnel = "int-cph-combined-surface-tunnel"
    assert ev(tunnel, ctx("pluvial_urban_flood"))["eligibility"] == "needs_local_evidence"
    assert ev(tunnel, ctx("riverine_catchment_flood", "catchment"))["eligibility"] == "partial_component_only"
    assert ev(tunnel, ctx("multiyear_drought"))["eligibility"] == "excluded"


def test_unknown_mechanism_never_compatible():
    e = ev("int-cph-combined-surface-tunnel", ctx(None, None))
    assert e["eligibility"] == "needs_local_evidence"
    assert e["features"][0]["state"] == "unknown"


def test_decisive_prerequisites_drive_eligibility():
    tunnel = "int-cph-combined-surface-tunnel"
    both = {"req-open-space-retention": A("satisfied"), "req-receiving-water": A("satisfied")}
    assert ev(tunnel, ctx(reqs=both))["eligibility"] == "candidate_lead"
    # removing decisive evidence returns it to an unknown state, not compatible and not false
    one = {"req-open-space-retention": A("satisfied")}
    e = ev(tunnel, ctx(reqs=one))
    assert e["eligibility"] == "needs_local_evidence"
    assert any(f["feature"] == "requires:req-receiving-water" and f["state"] == "unknown" for f in e["features"])
    # decisive prerequisite not satisfied -> hard exclusion with reason
    e = ev(tunnel, ctx(reqs={"req-open-space-retention": A("unsatisfied")}))
    assert e["eligibility"] == "excluded" and e["exclusion_reasons"]


def test_unrelated_change_leaves_result_stable():
    tunnel = "int-cph-combined-surface-tunnel"
    base = ev(tunnel, ctx())
    other = ev(tunnel, ctx(reqs={"req-household-metering": A("satisfied")}))  # not a prerequisite of this response
    assert base["eligibility"] == other["eligibility"]
    assert base["match_score"] == other["match_score"] and base["coverage"] == other["coverage"]


def test_disputed_finding_becomes_unknown():
    f = [{"id": "find-x", "variable": "PRECTOTCORR", "kind": "trend", "significant": True, "direction": "increase",
          "slope_per_decade": 0.2, "units": "mm/day", "q_value": 0.01, "disputed": False}]
    sig = ev("int-cph-combined-surface-tunnel", ctx(findings=f))
    assert any(x["feature"] == "signal:PRECTOTCORR" and x["state"] == "compatible" for x in sig["features"])
    f[0]["disputed"] = True
    dis = ev("int-cph-combined-surface-tunnel", ctx(findings=f))
    assert any(x["feature"] == "signal:PRECTOTCORR" and x["state"] == "unknown" for x in dis["features"])


def test_score_is_ordinal_and_explained():
    e = ev("int-ct-restrictions-tariffs", ctx("multiyear_drought"))
    assert 0 <= e["match_score"] <= 1 and "not a probability" in e["score_note"]
    assert e["source_id"] and e["locator"]


def test_revisions_persist_and_are_session_isolated():
    s1, s2 = services.new_session(), services.new_session()
    inv = services.create_investigation(s1, {"case_id": "copenhagen-2011"})
    r0 = inv["current_revision_id"]
    inv = services.add_revision(s1, inv["id"], {"kind": "set_requirement", "requirement_id": "req-open-space-retention",
                                                "state": "satisfied", "basis": "analyst_assumption", "rationale": "scenario"})
    assert inv["current_revision_id"] != r0 and len(inv["revisions"]) == 2
    assert inv["state"]["requirements"]["req-open-space-retention"]["basis"] == "analyst_assumption"
    assert services.revision_state(s1, inv["id"], r0)["requirements"] == {}  # prior revision preserved
    with pytest.raises(ApiError):
        services.get_investigation(s2, inv["id"])
    with pytest.raises(ApiError):
        services.add_revision(s2, inv["id"], {"kind": "set_scale", "scale": "city", "rationale": "x"})
    # an assumption cannot be promoted to a sourced fact without linking an ingested Source node
    with pytest.raises(ApiError):
        services.add_revision(s1, inv["id"], {"kind": "set_requirement", "requirement_id": "req-receiving-water",
                                              "state": "satisfied", "basis": "source_reported", "source_id": "not-a-source",
                                              "rationale": "x"})


def test_seed_graph_idempotent():
    from app import graph
    before = graph.stats(None)
    services.seed_graph()
    assert graph.stats(None)["nodes"] == before["nodes"]
