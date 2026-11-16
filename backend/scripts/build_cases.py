"""Merge source-verified research (data/cases_research.json) with a curated analyst overlay into data/cases.json.

The overlay adds ONLY structure the app reasons with: display names, mapping of each documented prerequisite to a
generic requirement concept (with an analyst 'decisive' judgement, labelled as such), and the environmental context
signals each response addressed. It adds no facts, numbers or outcomes."""
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "app" / "data"
research = json.loads((D / "cases_research.json").read_text(encoding="utf-8"))

NAMES = {
    "copenhagen-2011": ("Copenhagen 2011", "Copenhagen cloudburst, 2 July 2011"),
    "brisbane-2011": ("Brisbane 2011", "Brisbane River flood, January 2011"),
    "camp-fire-2018": ("Camp Fire 2018", "Camp Fire, Butte County, November 2018"),
    "cape-town-2015-2018": ("Cape Town 2015–2018", "Cape Town water crisis, 2015–2018"),
}

R = lambda rid, why, decisive=False: {"id": rid, "why": why, "decisive": decisive}  # noqa: E731
PRECIP_NOTE = "Monthly mean precipitation cannot resolve cloudburst or flood-peak intensity; context only."
OVERLAY = {
    "int-cph-combined-surface-tunnel": {
        "requirements": [R("req-open-space-retention", "Public open space for temporary detention (plan prerequisite)", True),
                         R("req-receiving-water", "Flow routes to a receiving water body (harbour/sea)", True),
                         R("req-drainage-capacity-known", "Knowledge of where sewers are overwhelmed"),
                         R("req-long-term-capital-funding", "Multi-decade financing of the works")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "increase", "note": PRECIP_NOTE}],
    },
    "int-cph-service-level": {
        "requirements": [R("req-hydraulic-modelling", "Hydraulic modelling of catchments", True),
                         R("req-drainage-capacity-known", "Mapped drainage capacity")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "increase", "note": PRECIP_NOTE}],
    },
    "int-cph-legislation": {
        "requirements": [R("req-flood-route-legal-basis", "Legal basis for utilities to finance surface flood routes", True)],
        "signals": [],
    },
    "int-bri-catchment-flood-study": {
        "requirements": [R("req-catchment-governance", "Multi-agency collaboration across the catchment", True),
                         R("req-flood-gauge-network", "Rainfall, stream-flow and tide records"),
                         R("req-hydraulic-modelling", "Catchment hydrologic models")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "increase", "note": PRECIP_NOTE}],
    },
    "int-bri-dam-operations": {
        "requirements": [R("req-flood-dam-storage", "Multi-purpose reservoir with flood storage", True),
                         R("req-catchment-governance", "Authority over upstream dam operations", True)],
        "signals": [],
    },
    "int-bri-flood-mapping-public": {
        "requirements": [R("req-flood-hazard-mapping", "Flood studies and mapping available", True),
                         R("req-public-communication", "Public web platform and outreach")],
        "signals": [],
    },
    "int-cf-evacuation-planning": {
        "requirements": [R("req-wui-exposure", "Community adjacent to wildland fuels", True),
                         R("req-evacuation-route-capacity", "Defined evacuation zones, routes and capacity", True)],
        "signals": [{"variable": "T2M", "direction": "increase", "note": "Regional warming is fire-weather context, not fuel or ignition evidence."}],
    },
    "int-cf-notification": {
        "requirements": [R("req-wui-exposure", "Community exposed to fast-moving wildfire", True),
                         R("req-multichannel-alerting", "Multiple alerting channels with backup power")],
        "signals": [],
    },
    "int-cf-safety-zones": {
        "requirements": [R("req-wui-exposure", "Community adjacent to wildland fuels", True),
                         R("req-safety-zone-sites", "Candidate open areas of adequate size", True)],
        "signals": [{"variable": "RH2M", "direction": "decrease", "note": "Lower humidity is fire-weather context only."}],
    },
    "int-ct-pressure-management": {
        "requirements": [R("req-pressure-zoned-network", "Network divisible into pressure zones", True),
                         R("req-reservoir-dependence", "Supply-shortfall context (rain-fed reservoirs)")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "decrease", "note": "Regional precipitation is not reservoir inflow or storage."}],
    },
    "int-ct-restrictions-tariffs": {
        "requirements": [R("req-restriction-authority", "Legal authority for restrictions and tariffs", True),
                         R("req-household-metering", "Metering and billing", True),
                         R("req-public-communication", "Public communication capacity"),
                         R("req-reservoir-dependence", "Dam-level monitoring with trigger thresholds")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "decrease", "note": "Regional precipitation is not reservoir inflow or storage."}],
    },
    "int-ct-new-supply-programme": {
        "requirements": [R("req-alternative-sources", "Groundwater, reuse or desalination resources", True),
                         R("req-long-term-capital-funding", "Capital financing")],
        "signals": [{"variable": "PRECTOTCORR", "direction": "decrease", "note": "Regional precipitation is not reservoir inflow or storage."}],
    },
}

out = []
for c in research:
    dn, en = NAMES[c["id"]]
    c = dict(c, display_name=dn, event_name=en)
    for itv in c["interventions"]:
        ov = OVERLAY[itv["id"]]
        itv["requirements"] = ov["requirements"]
        itv["signals"] = ov["signals"]
        itv["overlay_note"] = ("Requirement mapping and 'decisive' flags are analyst judgements linking the documented "
                               "prerequisites to generic concepts; they are not claims made by the source.")
    out.append(c)
(D / "cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote", len(out), "cases")
