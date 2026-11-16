"""Build the focused 'Trace evidence' subgraph for one planning lead. Every edge is read from persistence."""
from __future__ import annotations

from . import db, graph, matching, services
from .errors import ApiError

LAYER = {"Source": 0, "Dataset": 0, "Artifact": 1, "Outcome": 1, "Analysis": 2, "Event": 1, "Finding": 3,
         "Assumption": 3, "Mechanism": 4, "Requirement": 4, "Intervention": 5, "Investigation": 6, "Place": 6,
         "Variable": 1}


def build(session_id: str, iid: str, intervention_id: str) -> dict:
    inv = services.get_investigation(session_id, iid)
    match = matching.run_match(session_id, iid)
    ev = next((e for e in match["leads"] + match["other_candidates"] + match["excluded"]
               if e["intervention_id"] == intervention_id), None)
    if not ev:
        raise ApiError("not_found", "Intervention not evaluated for this investigation.", status=404)
    ids: set[str] = {intervention_id, iid}
    edges: dict[str, dict] = {}
    with db.conn() as c:
        def take(es):
            for e in es:
                edges[e["id"]] = e
                ids.add(e["src"])
                ids.add(e["dst"])
        # solution side
        take(graph.out_edges(c, intervention_id, session_id, ["ADDRESSES", "REQUIRES", "SUPPORTED_BY", "REPORTED_OUTCOME"]))
        take(graph.in_edges(c, intervention_id, session_id, ["CONTRADICTS", "RESPONDED_WITH"]))
        for o in graph.out_edges(c, intervention_id, session_id, ["REPORTED_OUTCOME"]):
            take(graph.out_edges(c, o["dst"], session_id, ["SUPPORTED_BY"]))
        # bridge (hypothesis) edge from the persisted match run
        take([e for e in graph.out_edges(c, intervention_id, session_id, ["CANDIDATE_FOR"]) if e["dst"] == iid])
        # target side: investigation -> place, requirement assessments, findings with ancestry
        take(graph.out_edges(c, iid, session_id, ["OCCURRED_IN"]))
        req_ids = {e["dst"] for e in graph.out_edges(c, intervention_id, session_id, ["REQUIRES"])}
        state_reqs = inv["state"].get("requirements", {})
        for e in graph.out_edges(c, iid, session_id, ["ASSESSES"]):
            via = e["props"].get("via")
            cur = state_reqs.get(e["dst"])
            if e["dst"] in req_ids and cur and cur.get("via") == via:
                take([e])
                take([x for x in graph.out_edges(c, via, session_id, ["ASSESSES", "SUPPORTED_BY"])])
        signal_vars = {s["variable"] for s in graph.get_node(intervention_id, session_id)["props"].get("signals", [])}
        if not signal_vars:  # keep the trace focused: show NASA ancestry for the primary variable only
            signal_vars = {inv["config"]["variables"][0]}
        place_id = inv["config"]["place"]["node_id"]
        for f in services.latest_findings(session_id, iid):
            if f["props"]["variable"] in signal_vars:
                take([e for e in graph.out_edges(c, place_id, session_id, ["HAS_FINDING"]) if e["dst"] == f["id"]])
                p = graph.provenance_path(f["id"], session_id, max_depth=3)
                for e in p["edges"]:
                    if e["type"] in ("DERIVED_FROM",):
                        edges[e["id"]] = e
                        ids.update([e["src"], e["dst"]])
        nodes = graph.nodes_by_ids(c, ids, session_id)
        bundles = graph.bundles_for(c, intervention_id, session_id)
    # requirement states for this investigation
    feat_by = {f["feature"]: f for f in ev["features"]}
    out_nodes = []
    for n in nodes.values():
        n = dict(n)
        n["layer"] = LAYER.get(n["type"], 3)
        if n["id"] == iid:
            n["layer"] = 6
        if n["type"] == "Requirement":
            f = feat_by.get(f"requires:{n['id']}")
            n["assessment"] = {"state": f["state"], "detail": f["detail"]} if f else None
        if n["type"] == "Mechanism":
            f = feat_by.get("mechanism")
            n["assessment"] = {"state": f["state"], "detail": f["detail"]} if f else None
        if n["type"] == "Finding" and n["props"].get("kind", "").startswith("trend"):
            f = feat_by.get(f"signal:{n['props']['variable']}")
            n["assessment"] = {"state": f["state"], "detail": f["detail"]} if f else None
        out_nodes.append(n)
    out_nodes.sort(key=lambda n: (n["layer"], n["type"], n["id"]))
    valid = {n["id"] for n in out_nodes}
    return {
        "intervention_id": intervention_id,
        "investigation_id": iid,
        "evaluation": ev,
        "match_run_id": match["id"],
        "graph_version": match["graph_version"],
        "nodes": out_nodes,
        "edges": [e for e in edges.values() if e["src"] in valid and e["dst"] in valid],
        "bundles": bundles,
    }
