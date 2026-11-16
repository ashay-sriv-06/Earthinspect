"""Public, read-only seed case files. Facts come from data/cases.json (source-verified research);
analysis geometry here is an explicit analyst selection, stored separately from event geography."""
from __future__ import annotations

import json

from .config import SEED_DIR
from .errors import ApiError

MECHANISMS = {
    "pluvial_urban_flood": {
        "label": "Urban pluvial (surface-water) flooding",
        "family": "flood",
        "definition": "Intense local rainfall exceeds drainage/sewer capacity and water collects on streets and low ground.",
        "typical_scale": "city",
    },
    "riverine_catchment_flood": {
        "label": "Riverine / catchment flooding",
        "family": "flood",
        "definition": "Rain accumulated over a large catchment raises river levels and the river overtops its banks.",
        "typical_scale": "catchment",
    },
    "wui_wildfire": {
        "label": "Wildland–urban interface wildfire",
        "family": "fire",
        "definition": "Wildfire spreads from wildland vegetation into communities, driven by fuels, weather and terrain.",
        "typical_scale": "regional",
    },
    "multiyear_drought": {
        "label": "Multi-year drought / water-supply shortfall",
        "family": "drought",
        "definition": "Several years of below-normal inflows deplete reservoirs relative to demand.",
        "typical_scale": "regional",
    },
}

# Analysis footprints: analyst-selected regional boxes, >= 2 deg per axis because POWER regional requires it.
ANALYSIS_GEOMETRY = {
    "copenhagen-2011": {
        "geometry": {"type": "bbox", "west": 11.5, "south": 54.7, "east": 13.5, "north": 56.7},
        "origin": "Analyst selection: 2°×2° box centred near Copenhagen (includes Zealand, Øresund and southern Sweden). "
                  "Not a drainage or flood boundary; POWER regional requests need ≥2° per axis.",
        "scale": "city",
        "questions": [
            "Has regional monthly precipitation changed since 2001, and can monthly data say anything about cloudburst intensity?",
            "Which conditions made surface-water retention feasible in Copenhagen?",
        ],
        "variables": ["PRECTOTCORR", "T2M", "RH2M", "WS10M"],
    },
    "brisbane-2011": {
        "geometry": {"type": "bbox", "west": 151.5, "south": -28.5, "east": 153.5, "north": -26.5},
        "origin": "Analyst selection: 2°×2° box roughly spanning the Brisbane River catchment region. "
                  "Not the mapped catchment boundary.",
        "scale": "catchment",
        "questions": [
            "What regional rainfall context surrounds the January 2011 river flood?",
            "Why are city-scale surface-water measures not a complete answer to catchment flooding?",
        ],
        "variables": ["PRECTOTCORR", "T2M", "RH2M", "WS10M"],
    },
    "camp-fire-2018": {
        "geometry": {"type": "bbox", "west": -122.6, "south": 38.8, "east": -120.6, "north": 40.8},
        "origin": "Analyst selection: 2°×2° box around Paradise, CA (Butte County foothills and Sacramento Valley). "
                  "Not a fire perimeter.",
        "scale": "regional",
        "questions": [
            "Has regional temperature, humidity or wind changed in ways relevant to fire weather?",
            "What did NIST document about notification, evacuation and temporary refuge?",
        ],
        "variables": ["T2M", "RH2M", "WS10M", "PRECTOTCORR"],
    },
    "cape-town-2015-2018": {
        "geometry": {"type": "bbox", "west": 18.0, "south": -35.0, "east": 20.0, "north": -33.0},
        "origin": "Analyst selection: 2°×2° box covering Cape Town and the Western Cape supply-dam region "
                  "(includes ocean cells). Not a catchment boundary.",
        "scale": "regional",
        "questions": [
            "How does 2015–2017 precipitation compare with the longer 2001–2024 record?",
            "Which demand-management actions are documented, and which commitments came later?",
        ],
        "variables": ["PRECTOTCORR", "T2M", "RH2M", "WS10M"],
    },
}


def _load() -> list[dict]:
    p = SEED_DIR / "cases.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def all_cases() -> list[dict]:
    out = []
    for c in _load():
        g = ANALYSIS_GEOMETRY.get(c["id"])
        if not g:
            continue
        mech = MECHANISMS[c["hazard_mechanism"]]
        out.append({
            **c,
            "analysis_geometry": g["geometry"],
            "geometry_origin": g["origin"],
            "scale": g["scale"],
            "questions": g["questions"],
            "variables": g["variables"],
            "mechanism": {"id": c["hazard_mechanism"], **mech},
            "kind": "seed_case",
            "read_only": True,
        })
    return out


def get_case(case_id: str) -> dict:
    for c in all_cases():
        if c["id"] == case_id:
            return c
    raise ApiError("not_found", f"Case {case_id} not found.", status=404)
