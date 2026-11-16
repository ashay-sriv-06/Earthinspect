"""Persistent typed evidence graph in SQLite with first-class relationship bundles (hyperedges).

Edge semantics (directed src -> dst):
  DERIVED_FROM  computed object came from dst (Finding->Analysis, Analysis->Artifact, Artifact->Dataset)
  MEASURES      Analysis/Artifact measures Variable
  OCCURRED_IN   Event/Investigation located in Place
  SUPPORTED_BY  claim/intervention/outcome is supported by Source (props.locator)
  CONTRADICTS   claim conflicts with dst
  REQUIRES      Intervention requires Requirement (props.decisive)
  ADDRESSES     Intervention targets Mechanism
  HAS_MECHANISM Event exhibits Mechanism
  RESPONDED_WITH Event -> Intervention documented for that event
  REPORTED_OUTCOME Intervention -> Outcome
  ASSESSES      Investigation -> Requirement (props.state) via assumption/source
  CANDIDATE_FOR hypothesis bridge Intervention -> Investigation (status=hypothesis)
  SUPERSEDES    newer node replaces dst without deleting it
  HAS_FINDING   Investigation/Place -> Finding
Bundle membership never implies pairwise causal edges.
"""
from __future__ import annotations

import hashlib
from collections import deque

from . import db
from .errors import ApiError

NODE_TYPES = {
    "Place", "Event", "Variable", "Dataset", "Artifact", "Analysis", "Finding", "Source",
    "Intervention", "Requirement", "Outcome", "Investigation", "Mechanism", "Assumption",
}
EDGE_TYPES = {
    "DERIVED_FROM", "MEASURES", "OCCURRED_IN", "SUPPORTED_BY", "CONTRADICTS", "REQUIRES", "ADDRESSES",
    "HAS_MECHANISM", "RESPONDED_WITH", "REPORTED_OUTCOME", "ASSESSES", "CANDIDATE_FOR", "SUPERSEDES",
    "HAS_FINDING",
}
STATUSES = {"computed", "source_reported", "analyst_assumption", "hypothesis", "reference", "disputed", "superseded"}
BASES = {"computed", "source_reported", "analyst_assumption", "hypothesis"}


def _eid(src: str, typ: str, dst: str) -> str:
    return "e-" + hashlib.sha1(f"{src}|{typ}|{dst}".encode()).hexdigest()[:16]


def upsert_node(c, nid: str, typ: str, label: str, status: str, scope: str = "public", props: dict | None = None,
                event_time: str | None = None, published_time: str | None = None, replace: bool = False) -> None:
    if typ not in NODE_TYPES:
        raise ApiError("invalid_graph_write", f"Unknown node type {typ}.")
    if status not in STATUSES:
        raise ApiError("invalid_graph_write", f"Unknown status {status}.")
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
    c.execute(
        f"{verb} INTO nodes(id,type,label,status,scope,props_json,event_time,published_time,ingested_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (nid, typ, label, status, scope, db.dumps(props or {}), event_time, published_time, db.now_iso()),
    )


def add_edge(c, src: str, typ: str, dst: str, status: str = "computed", scope: str = "public",
             props: dict | None = None) -> str:
    if typ not in EDGE_TYPES:
        raise ApiError("invalid_graph_write", f"Unknown edge type {typ}.")
    eid = _eid(src, typ, dst)
    c.execute(
        "INSERT OR IGNORE INTO edges(id,src,dst,type,status,scope,props_json,ingested_at) VALUES(?,?,?,?,?,?,?,?)",
        (eid, src, dst, typ, status, scope, db.dumps(props or {}), db.now_iso()),
    )
    return eid


def add_provenance(c, subject_id: str, basis: str, ref_id: str, locator: str | None = None) -> None:
    if basis not in BASES:
        raise ApiError("invalid_graph_write", f"Unknown provenance basis {basis}.")
    c.execute("INSERT OR IGNORE INTO provenance(subject_id,basis,ref_id,locator) VALUES(?,?,?,?)",
              (subject_id, basis, ref_id, locator))


def add_bundle(c, bid: str, assertion_type: str, evidence_status: str, label: str, members: list[tuple[str, str]],
               scope: str = "public", props: dict | None = None, time_scope: str | None = None) -> None:
    """members: [(node_id, role)]. Every bundle must carry provenance via props['basis'] and refs."""
    if evidence_status not in STATUSES:
        raise ApiError("invalid_graph_write", f"Unknown evidence status {evidence_status}.")
    exists = c.execute("SELECT version FROM relationship_bundles WHERE id=?", (bid,)).fetchone()
    if exists:
        return
    c.execute(
        "INSERT INTO relationship_bundles(id,assertion_type,evidence_status,label,scope,version,props_json,time_scope,ingested_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (bid, assertion_type, evidence_status, label, scope, 1, db.dumps(props or {}), time_scope, db.now_iso()),
    )
    for nid, role in members:
        c.execute("INSERT OR IGNORE INTO bundle_members(bundle_id,node_id,role) VALUES(?,?,?)", (bid, nid, role))


# ---------------------------------------------------------------- reads

def _visible(scope_col: str, session_id: str | None) -> tuple[str, tuple]:
    if session_id:
        return f"({scope_col}='public' OR {scope_col}=?)", (session_id,)
    return f"{scope_col}='public'", ()


def node_dict(r) -> dict:
    return {
        "id": r["id"], "type": r["type"], "label": r["label"], "status": r["status"],
        "props": db.loads(r["props_json"]), "event_time": r["event_time"],
        "published_time": r["published_time"], "ingested_at": r["ingested_at"],
        "scope": "public" if r["scope"] == "public" else "session",
    }


def edge_dict(r) -> dict:
    return {"id": r["id"], "src": r["src"], "dst": r["dst"], "type": r["type"], "status": r["status"],
            "props": db.loads(r["props_json"])}


def get_node(nid: str, session_id: str | None) -> dict:
    cond, args = _visible("scope", session_id)
    with db.conn() as c:
        r = c.execute(f"SELECT * FROM nodes WHERE id=? AND {cond}", (nid, *args)).fetchone()
        if not r:
            raise ApiError("not_found", f"Evidence node {nid} not found.", status=404)
        d = node_dict(r)
        d["provenance"] = [dict(p) for p in c.execute(
            "SELECT basis, ref_id, locator FROM provenance WHERE subject_id=?", (nid,)).fetchall()]
        d["bundles"] = bundles_for(c, nid, session_id)
    return d


def bundles_for(c, nid: str, session_id: str | None) -> list[dict]:
    cond, args = _visible("b.scope", session_id)
    rows = c.execute(
        f"SELECT b.* FROM relationship_bundles b JOIN bundle_members m ON m.bundle_id=b.id WHERE m.node_id=? AND {cond}",
        (nid, *args)).fetchall()
    return [bundle_dict(c, r) for r in rows]


def bundle_dict(c, r) -> dict:
    members = c.execute(
        "SELECT m.node_id, m.role, n.type, n.label, n.status FROM bundle_members m LEFT JOIN nodes n ON n.id=m.node_id"
        " WHERE m.bundle_id=? ORDER BY m.role", (r["id"],)).fetchall()
    return {
        "id": r["id"], "assertion_type": r["assertion_type"], "evidence_status": r["evidence_status"],
        "label": r["label"], "version": r["version"], "time_scope": r["time_scope"],
        "props": db.loads(r["props_json"]),
        "members": [{"node_id": m["node_id"], "role": m["role"], "type": m["type"], "label": m["label"],
                     "status": m["status"]} for m in members],
    }


def get_bundle(bid: str, session_id: str | None) -> dict:
    cond, args = _visible("scope", session_id)
    with db.conn() as c:
        r = c.execute(f"SELECT * FROM relationship_bundles WHERE id=? AND {cond}", (bid, *args)).fetchone()
        if not r:
            raise ApiError("not_found", "Bundle not found.", status=404)
        return bundle_dict(c, r)


def out_edges(c, nid, session_id, types=None):
    cond, args = _visible("scope", session_id)
    q = f"SELECT * FROM edges WHERE src=? AND {cond}"
    params = [nid, *args]
    if types:
        q += f" AND type IN ({','.join('?' * len(types))})"
        params += list(types)
    return [edge_dict(r) for r in c.execute(q, params).fetchall()]


def in_edges(c, nid, session_id, types=None):
    cond, args = _visible("scope", session_id)
    q = f"SELECT * FROM edges WHERE dst=? AND {cond}"
    params = [nid, *args]
    if types:
        q += f" AND type IN ({','.join('?' * len(types))})"
        params += list(types)
    return [edge_dict(r) for r in c.execute(q, params).fetchall()]


def nodes_by_ids(c, ids, session_id) -> dict[str, dict]:
    if not ids:
        return {}
    cond, args = _visible("scope", session_id)
    ids = list(ids)
    rows = c.execute(f"SELECT * FROM nodes WHERE id IN ({','.join('?' * len(ids))}) AND {cond}",
                     (*ids, *args)).fetchall()
    return {r["id"]: node_dict(r) for r in rows}


PROVENANCE_TYPES = ("DERIVED_FROM", "MEASURES", "SUPPORTED_BY", "REPORTED_OUTCOME")


def provenance_path(nid: str, session_id: str | None, max_depth: int = 6, max_nodes: int = 40) -> dict:
    """Follow ancestry edges from a node to its immutable artifacts and sources (bounded BFS)."""
    with db.conn() as c:
        seen = {nid}
        edges = []
        q = deque([(nid, 0)])
        while q and len(seen) < max_nodes:
            cur, d = q.popleft()
            if d >= max_depth:
                continue
            for e in out_edges(c, cur, session_id, PROVENANCE_TYPES):
                edges.append(e)
                if e["dst"] not in seen:
                    seen.add(e["dst"])
                    q.append((e["dst"], d + 1))
        nodes = nodes_by_ids(c, seen, session_id)
    return {"root": nid, "nodes": list(nodes.values()), "edges": edges}


def dependents(nid: str, session_id: str | None, max_depth: int = 5) -> list[str]:
    """Nodes that (transitively) depend on nid — used for invalidation after revisions."""
    with db.conn() as c:
        seen, q = set(), deque([(nid, 0)])
        while q:
            cur, d = q.popleft()
            if d >= max_depth:
                continue
            for e in in_edges(c, cur, session_id):
                if e["src"] not in seen:
                    seen.add(e["src"])
                    q.append((e["src"], d + 1))
    return sorted(seen)


def places_sharing_mechanism(mechanism_id: str, session_id: str | None) -> list[dict]:
    with db.conn() as c:
        evs = in_edges(c, mechanism_id, session_id, ["HAS_MECHANISM"])
        nodes = nodes_by_ids(c, [e["src"] for e in evs], session_id)
    return list(nodes.values())


def neighborhood(nid: str, session_id: str | None, limit: int = 30) -> dict:
    with db.conn() as c:
        es = (out_edges(c, nid, session_id) + in_edges(c, nid, session_id))[:limit]
        ids = {nid} | {e["src"] for e in es} | {e["dst"] for e in es}
        nodes = nodes_by_ids(c, ids, session_id)
        bundles = bundles_for(c, nid, session_id)
    return {"root": nid, "nodes": list(nodes.values()), "edges": es, "bundles": bundles}


def graph_version(session_id: str | None) -> str:
    cond, args = _visible("scope", session_id)
    with db.conn() as c:
        n = c.execute(f"SELECT COUNT(*), MAX(ingested_at) FROM nodes WHERE {cond}", args).fetchone()
        e = c.execute(f"SELECT COUNT(*), MAX(ingested_at) FROM edges WHERE {cond}", args).fetchone()
        ids = c.execute(f"SELECT id, status FROM nodes WHERE {cond} ORDER BY id", args).fetchall()
        eids = c.execute(f"SELECT id, status FROM edges WHERE {cond} ORDER BY id", args).fetchall()
    h = hashlib.sha1(("|".join(f"{r[0]}:{r[1]}" for r in ids) + "#" +
                      "|".join(f"{r[0]}:{r[1]}" for r in eids)).encode()).hexdigest()[:10]
    return f"g{n[0]}.{e[0]}-{h}"


def stats(session_id: str | None) -> dict:
    cond, args = _visible("scope", session_id)
    with db.conn() as c:
        nt = c.execute(f"SELECT type, COUNT(*) n FROM nodes WHERE {cond} GROUP BY type", args).fetchall()
        et = c.execute(f"SELECT type, COUNT(*) n FROM edges WHERE {cond} GROUP BY type", args).fetchall()
        nb = c.execute(f"SELECT COUNT(*) FROM relationship_bundles WHERE {cond}", args).fetchone()[0]
    return {"nodes": {r["type"]: r["n"] for r in nt}, "edges": {r["type"]: r["n"] for r in et}, "bundles": nb,
            "version": graph_version(session_id)}
