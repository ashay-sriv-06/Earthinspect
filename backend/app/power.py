"""NASA POWER monthly acquisition with immutable, content-hashed artifacts.

Contract verified against the live API on 2026-11-15:
  GET https://power.larc.nasa.gov/api/temporal/monthly/regional?parameters=P&community=RE&
      longitude-min=..&longitude-max=..&latitude-min=..&latitude-max=..&start=YYYY&end=YYYY&format=JSON
  - one parameter per regional request, >= 2 degree range on each axis
  - response: GeoJSON FeatureCollection, one Point feature per MERRA-2 grid cell centre,
    properties.parameter[P] = {"YYYYMM": value, "YYYY13": annual value}; header.fill_value = -999
  - parameters[P] = {"units": ..., "longname": ...}; header.sources = ["MERRA2"]
  GET .../monthly/point?parameters=P,...&community=RE&longitude=..&latitude=..  (nearest grid cell)
"""
from __future__ import annotations

import calendar
import hashlib
import json
import math
import threading
import time
import uuid
from urllib.parse import urlencode

import httpx

from . import db
from .config import (
    ARTIFACT_DIR,
    HTTP_RETRIES,
    HTTP_TIMEOUT_S,
    NORMALIZATION_VERSION,
    POWER_END_YEAR,
    POWER_START_YEAR,
    SNAPSHOT_DIR,
)
from .errors import ApiError
from .geometry import canonical, centroid, is_regional_capable

POWER_BASE = "https://power.larc.nasa.gov/api/temporal/monthly"
SUPPORTED_VARIABLES = {
    "T2M": "Temperature at 2 Meters",
    "PRECTOTCORR": "Precipitation Corrected",
    "RH2M": "Relative Humidity at 2 Meters",
    "WS10M": "Wind Speed at 10 Meters",
}
# MERRA-2 native grid used by POWER meteorology (observed in responses: 0.5 deg lat x 0.625 deg lon)
GRID_DLAT = 0.5
GRID_DLON = 0.625

_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _key_locks_guard:
        return _key_locks.setdefault(key, threading.Lock())


def request_spec(variable: str, geometry: dict, start_year: int, end_year: int) -> dict:
    if variable not in SUPPORTED_VARIABLES:
        raise ApiError("unsupported_variable", f"{variable} is not wired to the POWER adapter.")
    geometry = canonical(geometry)
    start_year, end_year = int(start_year), int(end_year)
    if not (1981 <= start_year <= end_year <= POWER_END_YEAR):
        raise ApiError(
            "invalid_period", f"Period must lie within 1981–{POWER_END_YEAR} with start <= end."
        )
    if geometry["type"] == "bbox":
        if not is_regional_capable(geometry):
            raise ApiError(
                "region_too_small",
                "POWER regional requests need at least 2° in latitude and longitude. "
                "Use a nearest-grid-cell point request or enlarge the box.",
            )
        endpoint = "regional"
        params = {
            "parameters": variable,
            "community": "RE",
            "longitude-min": geometry["west"],
            "longitude-max": geometry["east"],
            "latitude-min": geometry["south"],
            "latitude-max": geometry["north"],
            "start": start_year,
            "end": end_year,
            "format": "JSON",
        }
    else:
        endpoint = "point"
        params = {
            "parameters": variable,
            "community": "RE",
            "longitude": geometry["lon"],
            "latitude": geometry["lat"],
            "start": start_year,
            "end": end_year,
            "format": "JSON",
        }
    url = f"{POWER_BASE}/{endpoint}?{urlencode(params)}"
    key_material = {
        "provider": "nasa-power",
        "endpoint": endpoint,
        "variable": variable,
        "geometry": geometry,
        "start_year": start_year,
        "end_year": end_year,
        "normalization": NORMALIZATION_VERSION,
    }
    cache_key = hashlib.sha256(db.dumps(key_material).encode()).hexdigest()[:24]
    return {**key_material, "url": url, "cache_key": cache_key}


def _fetch(url: str) -> dict:
    last_err = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            r = httpx.get(url, timeout=HTTP_TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            try:
                body = r.json()
                msgs = body.get("messages") or body.get("detail") or body
            except Exception:
                msgs = r.text[:300]
            if 400 <= r.status_code < 500:
                raise ApiError(
                    "provider_rejected",
                    f"NASA POWER rejected the request: {msgs}",
                    status=502,
                    detail={"provider_status": r.status_code},
                )
            last_err = f"HTTP {r.status_code}"
        except ApiError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = type(e).__name__
        time.sleep(1.5 * (attempt + 1))
    raise ApiError(
        "provider_unavailable",
        f"NASA POWER did not respond successfully after {HTTP_RETRIES + 1} attempts ({last_err}).",
        status=503,
    )


def month_iter(start_year: int, end_year: int):
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            yield y, m


def normalize(raw: dict, spec: dict) -> dict:
    """Return normalized monthly table + spatial support. Missing months are kept as None."""
    var = spec["variable"]
    header = raw.get("header", {})
    fill = header.get("fill_value", -999.0)
    meta = (raw.get("parameters") or {}).get(var, {})
    units = meta.get("units")
    feats = raw.get("features") if raw.get("type") == "FeatureCollection" else [raw]
    cells = []
    for f in feats or []:
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        series = (f.get("properties", {}).get("parameter") or {}).get(var, {})
        vals = {}
        for k, v in series.items():
            if len(k) != 6 or k[4:] == "13":  # exclude annual summary keys (YYYY13)
                continue
            vals[k] = None if (v is None or float(v) == float(fill)) else float(v)
        cells.append({"lon": coords[0], "lat": coords[1], "values": vals})
    if not cells:
        raise ApiError("provider_empty", "NASA POWER returned no grid cells for this request.", status=502)

    # area weights ~ cos(latitude) for equal-angle cells
    weights = [math.cos(math.radians(c["lat"])) for c in cells]
    rows = []
    for y, m in month_iter(spec["start_year"], spec["end_year"]):
        k = f"{y}{m:02d}"
        num = den = 0.0
        n_valid = 0
        for c, w in zip(cells, weights):
            v = c["values"].get(k)
            if v is not None:
                num += v * w
                den += w
                n_valid += 1
        value = round(num / den, 4) if n_valid == len(cells) and den > 0 else None  # require full cell coverage
        row = {"date": f"{y}-{m:02d}", "value": value, "cells_valid": n_valid, "cells_total": len(cells)}
        if var == "PRECTOTCORR" and value is not None:
            days = calendar.monthrange(y, m)[1]
            row["monthly_total_mm"] = round(value * days, 3)
            row["days_in_month"] = days
        rows.append(row)

    lats = sorted({c["lat"] for c in cells})
    lons = sorted({c["lon"] for c in cells})
    dlat = min((b - a for a, b in zip(lats, lats[1:])), default=GRID_DLAT)
    dlon = min((b - a for a, b in zip(lons, lons[1:])), default=GRID_DLON)
    support = {
        "kind": "area_weighted_grid_mean" if len(cells) > 1 else "nearest_grid_cell",
        "cell_count": len(cells),
        "cell_size_deg": {"lat": dlat, "lon": dlon},
        "cell_centers": [[c["lon"], c["lat"]] for c in cells],
        "footprint": {
            "type": "bbox",
            "west": round(min(lons) - dlon / 2, 4),
            "east": round(max(lons) + dlon / 2, 4),
            "south": round(min(lats) - dlat / 2, 4),
            "north": round(max(lats) + dlat / 2, 4),
        },
        "weighting": "cos(latitude) area weights; month kept only if every cell is valid"
        if len(cells) > 1
        else "single grid cell nearest the requested point (not a city average)",
    }
    return {
        "variable": var,
        "longname": meta.get("longname") or SUPPORTED_VARIABLES[var],
        "units": units,
        "sources": header.get("sources"),
        "api_version": (header.get("api") or {}).get("version"),
        "fill_value": fill,
        "time_standard": header.get("time_standard"),
        "rows": rows,
        "support": support,
        "conversions": (
            [
                "PRECTOTCORR is a monthly mean precipitation rate (mm/day). monthly_total_mm = rate × actual "
                "calendar days in that month. Trend analysis uses the rate."
            ]
            if var == "PRECTOTCORR"
            else []
        ),
    }


def _artifact_row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "cache_key": r["cache_key"],
        "version": r["version"],
        "provider": r["provider"],
        "variable": r["variable"],
        "manifest": db.loads(r["manifest_json"]),
        "sha256": r["sha256"],
        "retrieved_at": r["retrieved_at"],
        "origin": r["origin"],
    }


def get_artifact(artifact_id: str) -> dict:
    with db.conn() as c:
        r = c.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    if not r:
        raise ApiError("not_found", "Artifact not found.", status=404)
    return _artifact_row_to_dict(r)


def load_normalized(artifact_id: str) -> dict:
    with db.conn() as c:
        r = c.execute("SELECT norm_path FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    if not r:
        raise ApiError("not_found", "Artifact not found.", status=404)
    return json.loads((ARTIFACT_DIR / r["norm_path"]).read_text(encoding="utf-8"))


def latest_for_key(cache_key: str):
    with db.conn() as c:
        return c.execute(
            "SELECT * FROM artifacts WHERE cache_key=? ORDER BY version DESC LIMIT 1", (cache_key,)
        ).fetchone()


def _store(spec: dict, raw_bytes: bytes, origin: str, retrieved_at: str | None = None) -> dict:
    raw = json.loads(raw_bytes)
    norm = normalize(raw, spec)
    sha = hashlib.sha256(raw_bytes).hexdigest()
    with db.tx() as c:
        prev = c.execute(
            "SELECT MAX(version) v FROM artifacts WHERE cache_key=?", (spec["cache_key"],)
        ).fetchone()["v"]
        version = (prev or 0) + 1
        aid = f"art-{spec['cache_key'][:12]}-v{version}"
        raw_name = f"{aid}.raw.json"
        norm_name = f"{aid}.norm.json"
        (ARTIFACT_DIR / raw_name).write_bytes(raw_bytes)
        (ARTIFACT_DIR / norm_name).write_text(json.dumps(norm), encoding="utf-8")
        manifest = {
            "provider": "NASA POWER (Prediction Of Worldwide Energy Resources)",
            "source_model": "MERRA-2 reanalysis-derived meteorology (not an independent satellite instrument)",
            "api_version": norm["api_version"],
            "endpoint": spec["endpoint"],
            "community": "RE",
            "variable": spec["variable"],
            "longname": norm["longname"],
            "units": norm["units"],
            "geometry_requested": spec["geometry"],
            "spatial_support": {k: v for k, v in norm["support"].items() if k != "cell_centers"},
            "period": {"start": f"{spec['start_year']}-01", "end": f"{spec['end_year']}-12"},
            "aggregation": norm["support"]["weighting"],
            "quality_rules": [
                f"fill value {norm['fill_value']} -> missing",
                "annual summary keys (YYYY13) excluded",
                "missing months kept on the calendar (never zero-filled)",
            ],
            "conversions": norm["conversions"],
            "normalization_version": NORMALIZATION_VERSION,
            "source_url": spec["url"],
            "retrieved_at": retrieved_at or db.now_iso(),
            "raw_sha256": sha,
        }
        c.execute(
            "INSERT INTO artifacts(id,cache_key,version,provider,variable,manifest_json,sha256,raw_path,norm_path,retrieved_at,origin)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                aid,
                spec["cache_key"],
                version,
                "nasa-power",
                spec["variable"],
                db.dumps(manifest),
                sha,
                raw_name,
                norm_name,
                manifest["retrieved_at"],
                origin,
            ),
        )
        r = c.execute("SELECT * FROM artifacts WHERE id=?", (aid,)).fetchone()
    return _artifact_row_to_dict(r)


def acquire(variable: str, geometry: dict, start_year: int = POWER_START_YEAR,
            end_year: int = POWER_END_YEAR, force_refresh: bool = False) -> dict:
    """Return {"artifact": ..., "cache_status": "fetched"|"cached"|"snapshot", "duration_ms": int}."""
    spec = request_spec(variable, geometry, start_year, end_year)
    t0 = time.perf_counter()
    with _lock_for(spec["cache_key"]):  # dedupe concurrent identical requests
        existing = latest_for_key(spec["cache_key"])
        if existing and not force_refresh:
            return {
                "artifact": _artifact_row_to_dict(existing),
                "cache_status": "cached",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "request": spec,
            }
        try:
            raw = _fetch(spec["url"])
            art = _store(spec, json.dumps(raw).encode(), origin="fetched")
            status = "fetched"
        except ApiError as e:
            # Fallback 1: previous real artifact for the same request (force refresh failed)
            if existing:
                return {
                    "artifact": _artifact_row_to_dict(existing),
                    "cache_status": "snapshot",
                    "warning": f"{e.message} Showing the saved source snapshot retrieved {existing['retrieved_at']}.",
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                    "request": spec,
                }
            # Fallback 2: shipped snapshot of a previously acquired real response
            snap = SNAPSHOT_DIR / f"{spec['cache_key']}.json"
            if snap.exists():
                snap_doc = json.loads(snap.read_text(encoding="utf-8"))
                art = _store(spec, json.dumps(snap_doc["raw"]).encode(), origin="snapshot",
                             retrieved_at=snap_doc["retrieved_at"])
                return {
                    "artifact": art,
                    "cache_status": "snapshot",
                    "warning": f"{e.message} Using saved source snapshot retrieved {snap_doc['retrieved_at']}.",
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                    "request": spec,
                }
            raise
    return {
        "artifact": art,
        "cache_status": status,
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "request": spec,
    }


def export_snapshots() -> int:
    """Copy the latest raw artifact for each cache key into SNAPSHOT_DIR (real data only)."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with db.conn() as c:
        rows = c.execute(
            "SELECT a.* FROM artifacts a JOIN (SELECT cache_key, MAX(version) v FROM artifacts GROUP BY cache_key) m"
            " ON a.cache_key=m.cache_key AND a.version=m.v WHERE a.origin='fetched'"
        ).fetchall()
    for r in rows:
        raw = json.loads((ARTIFACT_DIR / r["raw_path"]).read_text(encoding="utf-8"))
        (SNAPSHOT_DIR / f"{r['cache_key']}.json").write_text(
            json.dumps({"retrieved_at": r["retrieved_at"], "raw": raw}), encoding="utf-8"
        )
        n += 1
    return n


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
