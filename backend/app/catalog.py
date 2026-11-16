"""Curated NASA dataset catalog. Identifiers/versions verified against NASA CMR on 2026-11-15
(see data/cmr_verification.json). Capability status reflects what THIS app implements, not what exists."""
from __future__ import annotations

import json
import re

import httpx

from .config import SEED_DIR
from .errors import ApiError

# metadata_only | imagery_view | downloadable_source | analysis_ready
CATALOG = [
    {
        "id": "power-monthly",
        "name": "NASA POWER Monthly & Annual (meteorology)",
        "provider": "NASA LaRC POWER",
        "short_name": None,
        "version": "API v2.10.0 (observed in response header)",
        "kind": "service",
        "variables": [
            {"code": "T2M", "name": "Temperature at 2 m", "units": "°C", "definition": "Monthly mean air temperature 2 m above the surface."},
            {"code": "PRECTOTCORR", "name": "Precipitation (corrected)", "units": "mm/day", "definition": "Monthly mean bias-corrected precipitation rate; not inundation, not sub-daily intensity."},
            {"code": "RH2M", "name": "Relative humidity at 2 m", "units": "%", "definition": "Monthly mean relative humidity."},
            {"code": "WS10M", "name": "Wind speed at 10 m", "units": "m/s", "definition": "Monthly mean wind speed 10 m above the surface."},
        ],
        "spatial": "MERRA-2 native grid 0.5° lat × 0.625° lon (regional) or nearest cell (point)",
        "temporal": "Monthly; this app requests 2001–2024",
        "coverage": "1981–present (monthly API)",
        "cadence": "Monthly values finalized after the month; see POWER docs",
        "source_url": "https://power.larc.nasa.gov/docs/services/api/temporal/monthly/",
        "auth": "None",
        "access": ["REST API (JSON)"],
        "caveats": [
            "Meteorology is derived from the MERRA-2 reanalysis model, not a direct satellite instrument measurement.",
            "Coarse grid: cannot resolve street-level, sub-daily or cloudburst-scale rainfall.",
            "Variables share model ancestry; agreement between them is not independent corroboration.",
        ],
        "hazards": ["flood", "drought", "heat", "fire", "wind"],
        "status": "analysis_ready",
    },
    {
        "id": "gibs-modis-truecolor",
        "name": "GIBS MODIS Terra Corrected Reflectance (True Color)",
        "provider": "NASA ESDIS GIBS",
        "short_name": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "version": "WMTS layer",
        "kind": "imagery service",
        "variables": [{"code": "TrueColor", "name": "Visual true-color imagery", "units": "image", "definition": "Daily corrected-reflectance RGB image tiles."}],
        "spatial": "WMTS GoogleMapsCompatible_Level9 (~250 m at max zoom)",
        "temporal": "Daily",
        "coverage": "2000–present",
        "cadence": "Daily",
        "source_url": "https://nasa-gibs.github.io/gibs-api-docs/access-advanced-topics/",
        "auth": "None",
        "access": ["WMTS REST tiles"],
        "caveats": ["Visual context only: pixel colours are not numerical observations.", "Clouds frequently obscure the surface."],
        "hazards": ["flood", "fire", "drought"],
        "status": "imagery_view",
    },
    {
        "id": "cmr-discovery",
        "name": "NASA Earthdata CMR (discovery)",
        "provider": "NASA ESDIS",
        "short_name": None,
        "version": "Search API",
        "kind": "discovery infrastructure",
        "variables": [],
        "spatial": "n/a", "temporal": "n/a", "coverage": "n/a", "cadence": "n/a",
        "source_url": "https://cmr.earthdata.nasa.gov/search/",
        "auth": "None for collection search",
        "access": ["collections.json search"],
        "caveats": ["A discovery index, not a measurement mission."],
        "hazards": [],
        "status": "metadata_only",
    },
]

_EXTERNAL = [
    ("M2TMNXSLV", "MERRA-2 monthly single-level diagnostics", "GES DISC", "Reanalysis 2-D monthly fields (temperature, humidity, wind…)",
     "0.5° × 0.625°", "Monthly", ["heat", "drought", "flood"], "Earthdata Login", "downloadable_source",
     ["Reanalysis model output; the underlying source of POWER meteorology."]),
    ("GPM_3IMERGM", "GPM IMERG Final Precipitation L3 monthly", "GES DISC", "Satellite-gauge merged precipitation rate",
     "0.1° × 0.1°", "Monthly", ["flood", "drought"], "Earthdata Login", "metadata_only",
     ["Precipitation estimate, not flooded area.", "Monthly means cannot show cloudburst intensity."]),
    ("MOD11A2", "MODIS Terra Land Surface Temperature 8-day", "LP DAAC", "Land surface (skin) temperature, day/night",
     "1 km", "8-day", ["heat", "drought", "fire"], "Earthdata Login", "metadata_only",
     ["Skin temperature differs from 2 m air temperature.", "Clear-sky only."]),
    ("MOD13Q1", "MODIS Terra Vegetation Indices 16-day", "LP DAAC", "NDVI / EVI vegetation greenness",
     "250 m", "16-day", ["drought", "fire"], "Earthdata Login", "metadata_only",
     ["Greenness is a proxy; it does not measure fuel moisture directly."]),
    ("MCD64A1", "MODIS Burned Area monthly", "LP DAAC", "Burned-area date per 500 m pixel",
     "500 m", "Monthly", ["fire"], "Earthdata Login", "metadata_only",
     ["Small or fast fires and cloud cover can be missed."]),
    ("VNP14IMGTDL_NRT", "VIIRS S-NPP 375 m Active Fire NRT (FIRMS)", "LANCE / FIRMS", "Active fire detections (thermal anomalies)",
     "375 m", "Per overpass", ["fire"], "FIRMS map key for API", "metadata_only",
     ["Detections are hotspots, not fire perimeters.", "Not a live evacuation or routing service."]),
    ("SPL3SMP_E", "SMAP Enhanced L3 Soil Moisture daily", "NSIDC", "Surface (~5 cm) soil moisture",
     "9 km", "Daily", ["drought", "flood"], "Earthdata Login", "metadata_only",
     ["Surface layer only; not groundwater or reservoir storage.", "Coverage from 2015."]),
    ("GLDAS_NOAH025_M", "GLDAS Noah Land Surface Model monthly", "GES DISC", "Modeled soil moisture, runoff, evapotranspiration",
     "0.25°", "Monthly", ["drought", "flood"], "Earthdata Login", "metadata_only",
     ["Model output forced by observations; not direct measurement."]),
    ("TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4", "GRACE/GRACE-FO JPL Mascon water storage", "PO.DAAC", "Terrestrial water storage anomaly (equivalent water height)",
     "~3° mascons (0.5° grid)", "Monthly", ["drought"], "Earthdata Login", "metadata_only",
     ["Very coarse; city-scale storage cannot be resolved.", "Gap between missions 2017–2018."]),
    ("AIRS3STM", "Aqua AIRS L3 monthly standard retrieval", "GES DISC", "Atmospheric temperature and humidity profiles",
     "1° × 1°", "Monthly", ["heat"], "Earthdata Login", "metadata_only",
     ["Retrieval quality depends on cloud conditions."]),
    ("OMNO2d", "OMI/Aura NO2 tropospheric column daily", "GES DISC", "Nitrogen dioxide column (air quality / smoke context)",
     "0.25°", "Daily", ["fire"], "Earthdata Login", "metadata_only",
     ["Column amount, not surface concentration.", "Row anomaly affects coverage."]),
    ("SRTMGL1", "SRTM Global 1 arc second elevation", "LP DAAC", "Terrain elevation",
     "~30 m", "Static (Feb 2000)", ["flood"], "Earthdata Login", "metadata_only",
     ["Surface model including some buildings/vegetation; not a drainage network."]),
    ("HLSL30", "Harmonized Landsat Sentinel-2 (Landsat 30 m)", "LP DAAC", "Surface reflectance imagery",
     "30 m", "~2–3 days combined", ["flood", "fire", "drought"], "Earthdata Login", "metadata_only",
     ["Imagery requires classification before it says anything about water or burn extent."]),
]


def _load_cmr():
    p = SEED_DIR / "cmr_verification.json"
    return json.loads(p.read_text()) if p.exists() else {"results": {}}


def build_catalog() -> list[dict]:
    cmr = _load_cmr()
    out = [dict(e, verification={"method": "manual: live API response / official docs", "verified": True}) for e in CATALOG]
    for sn, name, provider, measures, spatial, temporal, hazards, auth, status, caveats in _EXTERNAL:
        entries = cmr["results"].get(sn) or []
        top = entries[0] if isinstance(entries, list) and entries else None
        out.append({
            "id": sn.lower(),
            "name": name,
            "provider": provider,
            "short_name": sn,
            "version": top["version"] if top else None,
            "kind": "collection",
            "variables": [{"code": sn, "name": measures, "units": "see product docs", "definition": measures}],
            "spatial": spatial,
            "temporal": temporal,
            "coverage": (f"{(top['time_start'] or '')[:10]} – {(top['time_end'] or 'present')[:10]}" if top else "unknown"),
            "cadence": temporal,
            "source_url": f"https://search.earthdata.nasa.gov/search?q={sn}",
            "cmr_concept_id": top["concept_id"] if top else None,
            "cmr_title": top["title"] if top else None,
            "auth": auth,
            "access": ["Earthdata Search / CMR granule download"],
            "caveats": caveats,
            "hazards": hazards,
            "status": status,
            "verification": {"method": "NASA CMR collection search", "verified": bool(top), "verified_at": cmr.get("verified_at")},
        })
    return out


STATUS_EXPLAIN = {
    "analysis_ready": "Numerical adapter implemented: can be acquired and trend-tested in this app.",
    "imagery_view": "Visual context layer only; not used for numerical analysis.",
    "downloadable_source": "Verified product; numerical adapter not implemented in this build.",
    "metadata_only": "Catalog metadata only; no adapter implemented in this build.",
}

HAZARD_SYNONYMS = {
    "flood": ["flood", "rain", "cloudburst", "storm", "inundation", "pluvial", "river"],
    "drought": ["drought", "dry", "water", "reservoir", "rainfall deficit"],
    "fire": ["fire", "wildfire", "burn", "smoke"],
    "heat": ["heat", "hot", "temperature", "warming"],
}


def search(q: str = "", hazard: str | None = None) -> list[dict]:
    items = build_catalog()
    ql = (q or "").lower().strip()
    hz = set()
    for h, words in HAZARD_SYNONYMS.items():
        if any(w in ql for w in words) or hazard == h:
            hz.add(h)
    res = []
    for e in items:
        text = " ".join([e["name"], e.get("short_name") or "", e["provider"], " ".join(v["name"] + " " + v["code"] for v in e["variables"])]).lower()
        score = 0
        if not ql and not hz:
            score = 1
        if ql and ql in text:
            score += 3
        if hz & set(e["hazards"]):
            score += 2
        if score:
            e = dict(e, status_explanation=STATUS_EXPLAIN[e["status"]], relevance=_why(e, hz))
            res.append((score + (1 if e["status"] == "analysis_ready" else 0), e))
    res.sort(key=lambda x: -x[0])
    return [e for _, e in res]


def _why(e: dict, hz: set) -> str:
    if e["id"] == "power-monthly":
        if "flood" in hz:
            return ("Monthly precipitation rate gives regional wetness context. It does not measure flooded area, river "
                    "levels, or sub-daily cloudburst intensity.")
        if "drought" in hz:
            return "Monthly precipitation and temperature give regional dryness/heat context; they do not measure reservoir storage."
        if "fire" in hz:
            return "Temperature, humidity and wind give regional fire-weather context; they do not measure fuel or fire spread."
        return "Regional monthly meteorology from MERRA-2; analysis-ready in this app."
    return e["caveats"][0] if e["caveats"] else ""


def cmr_live_search(keyword: str) -> list[dict]:
    """Small live CMR discovery query against a fixed host; keyword is sanitized."""
    kw = re.sub(r"[^A-Za-z0-9 _\-.]", "", keyword or "")[:60]
    if not kw:
        raise ApiError("invalid_query", "Enter a keyword to search NASA CMR.")
    try:
        r = httpx.get("https://cmr.earthdata.nasa.gov/search/collections.json",
                      params={"keyword": kw, "page_size": 10}, timeout=20)
        r.raise_for_status()
    except Exception as ex:
        raise ApiError("provider_unavailable", f"NASA CMR search failed ({type(ex).__name__}).", status=503)
    return [
        {"title": e.get("title"), "short_name": e.get("short_name"), "version": e.get("version_id"),
         "data_center": e.get("data_center"), "concept_id": e.get("id"), "status": "metadata_only",
         "status_explanation": STATUS_EXPLAIN["metadata_only"]}
        for e in r.json().get("feed", {}).get("entry", [])
    ]
