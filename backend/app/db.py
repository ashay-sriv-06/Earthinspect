"""SQLite persistence. One file, WAL mode, short-lived connections per operation."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS investigations (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  title TEXT NOT NULL,
  config_json TEXT NOT NULL,
  current_revision_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inv_session ON investigations(session_id);

-- Immutable acquisition artifacts. (cache_key, version) is unique; force refresh adds a version.
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  cache_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  provider TEXT NOT NULL,
  variable TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  raw_path TEXT NOT NULL,
  norm_path TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  origin TEXT NOT NULL,
  UNIQUE(cache_key, version)
);

CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  cache_key TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  artifact_ids TEXT NOT NULL,
  params_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Evidence graph. scope = 'public' or a session id.
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  label TEXT NOT NULL,
  status TEXT NOT NULL,
  scope TEXT NOT NULL,
  props_json TEXT NOT NULL,
  event_time TEXT,
  published_time TEXT,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_nodes_type ON nodes(type);
CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  scope TEXT NOT NULL,
  props_json TEXT NOT NULL,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS ix_edges_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS relationship_bundles (
  id TEXT PRIMARY KEY,
  assertion_type TEXT NOT NULL,
  evidence_status TEXT NOT NULL,
  label TEXT NOT NULL,
  scope TEXT NOT NULL,
  version INTEGER NOT NULL,
  props_json TEXT NOT NULL,
  time_scope TEXT,
  ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bundle_members (
  bundle_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (bundle_id, node_id, role)
);
CREATE TABLE IF NOT EXISTS provenance (
  subject_id TEXT NOT NULL,
  basis TEXT NOT NULL,          -- computed | source_reported | analyst_assumption | hypothesis
  ref_id TEXT NOT NULL,         -- analysis/artifact id, source id, revision id
  locator TEXT,
  PRIMARY KEY (subject_id, basis, ref_id)
);

CREATE TABLE IF NOT EXISTS revisions (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  prior_id TEXT,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  changes_json TEXT NOT NULL,
  state_json TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS match_runs (
  id TEXT PRIMARY KEY,
  cache_key TEXT NOT NULL UNIQUE,
  investigation_id TEXT NOT NULL,
  revision_id TEXT,
  graph_version TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS copilot_runs (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  question TEXT NOT NULL,
  status TEXT NOT NULL,
  answer_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS tool_events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  label TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  duration_ms INTEGER,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = _connect()
        conn.executescript(SCHEMA)
        conn.close()
        _initialized = True


@contextmanager
def conn():
    init_db()
    c = _connect()
    try:
        yield c
    finally:
        c.close()


@contextmanager
def tx():
    """Transactional write block."""
    init_db()
    c = _connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def dumps(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def loads(s):
    return json.loads(s) if s else None
