"""Query NASA CMR for each catalog short name and record the verified version/title/coverage.
Writes backend/app/data/cmr_verification.json. Run: python scripts/verify_catalog_cmr.py"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

SHORT_NAMES = [
    "M2TMNXSLV", "GPM_3IMERGM", "MOD11A2", "MOD13Q1", "MCD64A1", "VNP14IMGTDL_NRT", "MCD14ML",
    "SPL3SMP_E", "GLDAS_NOAH025_M", "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4", "AIRS3STM",
    "OMNO2d", "SRTMGL1", "HLSL30",
]
out = {}
for sn in SHORT_NAMES:
    try:
        r = httpx.get("https://cmr.earthdata.nasa.gov/search/collections.json",
                      params={"short_name": sn, "page_size": 20}, timeout=30)
        entries = r.json().get("feed", {}).get("entry", [])
        out[sn] = [
            {"version": e.get("version_id"), "title": e.get("title"), "data_center": e.get("data_center"),
             "time_start": e.get("time_start"), "time_end": e.get("time_end"), "concept_id": e.get("id")}
            for e in entries
        ]
    except Exception as ex:  # noqa
        out[sn] = {"error": str(ex)}
    print(sn, json.dumps(out[sn])[:300], file=sys.stderr)
doc = {"verified_at": datetime.now(timezone.utc).isoformat(), "endpoint": "https://cmr.earthdata.nasa.gov/search/collections.json", "results": out}
Path(__file__).resolve().parent.parent.joinpath("app/data/cmr_verification.json").write_text(json.dumps(doc, indent=1))
