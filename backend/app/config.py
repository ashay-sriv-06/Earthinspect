"""Runtime configuration. All secrets come from the environment and never reach the browser."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = Path(os.environ.get("EARTHINSPECT_DATA_DIR", ROOT / "var")).resolve()
ARTIFACT_DIR = DATA_DIR / "artifacts"
DB_PATH = DATA_DIR / "earthinspect.sqlite3"
SNAPSHOT_DIR = ROOT / "snapshots"  # previously acquired real artifacts shipped for offline demos
FRONTEND_DIST = Path(os.environ.get("EARTHINSPECT_FRONTEND_DIST", ROOT.parent / "frontend" / "dist")).resolve()
SEED_DIR = Path(__file__).resolve().parent / "data"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
# The model id must be supplied explicitly; we do not guess a "latest" name.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "").strip()

HTTP_TIMEOUT_S = float(os.environ.get("EARTHINSPECT_HTTP_TIMEOUT", "60"))
HTTP_RETRIES = 2

# Only these hosts may be contacted server-side. No arbitrary URL fetches.
ALLOWED_HOSTS = {
    "power.larc.nasa.gov",
    "gibs.earthdata.nasa.gov",
    "cmr.earthdata.nasa.gov",
    "geocoding-api.open-meteo.com",
}

POWER_START_YEAR = 2001
POWER_END_YEAR = 2024
NORMALIZATION_VERSION = "norm-1.0"
TREND_METHOD_VERSION = "trend-ols-hac-1.1"  # 1.1: significance wording/flags use BH-adjusted q
ASSOC_METHOD_VERSION = "assoc-1.0"
MATCH_RULE_VERSION = "match-rules-1.1"

for d in (DATA_DIR, ARTIFACT_DIR):
    d.mkdir(parents=True, exist_ok=True)
