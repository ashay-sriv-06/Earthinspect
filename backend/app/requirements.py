"""Generic, transferable requirement concepts. Source-specific statements stay attached to their case;
these are the prerequisites matching reasons about. Nothing here is inferred from temperature or rainfall."""

REQUIREMENTS = {
    "req-open-space-retention": {
        "label": "Open space that can be redesigned to hold or convey stormwater",
        "definition": "Parks, squares and streets that can be reshaped to temporarily store or channel surface water.",
    },
    "req-drainage-capacity-known": {
        "label": "Known sewer/drainage capacity and overflow points",
        "definition": "A mapped understanding of where the drainage system is overwhelmed in intense rain.",
    },
    "req-long-term-capital-funding": {
        "label": "Multi-decade capital funding mechanism",
        "definition": "A financing route (e.g. utility tariffs, municipal budget) for works built over 20+ years.",
    },
    "req-catchment-governance": {
        "label": "Catchment-scale governance (upstream land and dams)",
        "definition": "Authority or coordination that spans the river catchment beyond city limits.",
    },
    "req-flood-gauge-network": {
        "label": "Rainfall and river-gauge network feeding forecasts",
        "definition": "Real-time gauges and a forecasting service that can issue river-level warnings.",
    },
    "req-flood-dam-storage": {
        "label": "Flood-mitigation dam storage with operating rules",
        "definition": "Reservoir capacity reserved for floods and documented release procedures.",
    },
    "req-flood-hazard-mapping": {
        "label": "Flood hazard mapping used in land-use planning",
        "definition": "Official flood extent/level maps that planning decisions must consider.",
    },
    "req-multichannel-alerting": {
        "label": "Multi-channel emergency alerting that reaches residents",
        "definition": "Warnings through several channels, robust to loss of power or cell service.",
    },
    "req-evacuation-route-capacity": {
        "label": "Known evacuation route capacity and alternative egress",
        "definition": "Assessment of how many vehicles routes can carry and whether alternatives exist.",
    },
    "req-wui-exposure": {
        "label": "Community adjacent to wildland fuels",
        "definition": "Homes in or next to flammable vegetation (wildland–urban interface).",
    },
    "req-household-metering": {
        "label": "Household water metering and billing",
        "definition": "Metered connections so restrictions, tariffs and flow limits can be applied and tracked.",
    },
    "req-public-communication": {
        "label": "Public communication capacity for behaviour change",
        "definition": "Channels and trust to explain restrictions and report progress to residents.",
    },
    "req-reservoir-dependence": {
        "label": "Supply dependent on rain-fed surface reservoirs",
        "definition": "Most water comes from reservoirs refilled by rainfall.",
    },
    "req-hydraulic-modelling": {
        "label": "Hydraulic / hydrologic models of local catchments",
        "definition": "Models that show where water flows and accumulates for design events.",
    },
    "req-flood-route-legal-basis": {
        "label": "Legal basis to finance and use streets as flood routes",
        "definition": "Law or regulation letting utilities fund surface works and roads carry floodwater.",
    },
    "req-receiving-water": {
        "label": "Gravity flow routes to a receiving water body",
        "definition": "Harbour, sea or river that surface water can be routed to.",
    },
    "req-pressure-zoned-network": {
        "label": "Water network that can be split into pressure zones",
        "definition": "Distribution network with valves/controllers allowing zone-by-zone pressure reduction.",
    },
    "req-restriction-authority": {
        "label": "Legal authority to impose water restrictions and tariffs",
        "definition": "Municipal powers to set and enforce use limits and drought pricing.",
    },
    "req-safety-zone-sites": {
        "label": "Candidate open areas for wildfire safety zones",
        "definition": "Large paved or irrigated areas that can be maintained as last-resort refuges.",
    },
    "req-alternative-sources": {
        "label": "Feasible alternative water sources",
        "definition": "Groundwater, reuse or desalination that could be developed.",
    },
}

SCALE_ORDER = ["street", "neighbourhood", "city", "catchment", "regional"]
