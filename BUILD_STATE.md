# BUILD_STATE

Start: 2026-11-15 18:35 PST. User deadline: 23:15 PST (5 h). Budget scaled from 450 to ~280 min with the pack's cut order. Elapsed at checkpoint: ~50 min of wall clock (environment setup included Python, Node and Git installs via winget).

| # | Phase | Status | Acceptance evidence |
|---|---|---|---|
| 01 | Foundation & first slice | ✅ | FastAPI + SQLite + React/Vite. Investigation persists across refresh and process restart (e2e run before and after restart). |
| 02 | Visual system & shell | ✅ | Field Atlas tokens frozen in CLAUDE.md. Dock, map, inspector tabs, timeline and command palette all wired to real actions. Inspected at 1440×900 and 1280×800. |
| 03 | Four case files | ✅ | `data/cases.json`: 13 sources (10 verified, 3 marked unavailable), 29 event facts and 12 responses, all with locators. |
| 04 | NASA catalog | ✅ | 16 entries (13 CMR-verified IDs). Status-aware UI. Live CMR search. 1 numerical and 1 imagery adapter, counted separately. |
| 05 | Acquisition & caching | ✅ | Real regional POWER artifacts, SHA-256, manifests, versioned force refresh, per-key locks, snapshot fallback, cache states shown in UI. |
| 06 | Trend & association | ✅ | OLS + HAC(12), sensitivity at 24 lags, BH, ≥120-month rule, anomalies, residual correlations. 10 numerical tests. |
| 07 | Geospatial workspace | ✅ | MapLibre with GIBS basemap and imagery (date control and availability check), footprint and grid-cell layers, brush → Apply window, persisted view. |
| 08 | Evidence graph & bundles | ✅ | Typed nodes and edges, bundles with roles, provenance table, idempotent ingestion, bounded traversals. |
| 09 | Solutions graph | ✅ | 12 interventions: implemented vs proposed vs retrospective, observed vs projected, limitations as CONTRADICTS. |
| 10 | Contextual matching | ✅ | Rules match-rules-1.1. Unknown ≠ false. Persisted match runs plus hypothesis bridge edges. Tests for the sensitivity and stability requirements. |
| 11 | Copilot | ✅ (LLM path verified to auth only) | 10 tools, event log, cancel/timeout, citation and number validation, Guided analysis. Missing key and provider error both tested. |
| 12 | New place | ✅ | Open-Meteo geocoder or coordinates. Nairobi functional test with its own artifacts. |
| 13 | Trace evidence | ✅ | Layered React Flow view and table, persisted edges only, mismatch and unknown states, path pulse with reduced motion respected. |
| 14 | Revisions | ✅ | Immutable revisions, activate prior, "What changed?", assumptions never promoted to sourced facts. |
| 15 | Compare & export | ✅ | Aligned comparison; CSV, JSON and HTML exports verified. |
| 16 | Verification | ✅ | VERIFICATION.md: 18 pytest, 31 e2e, provider error, UI flows, 8-question eval. |
| 17 | Packaging & submission | ⚠️ partial | Dockerfile, README, demo script and submission copy written. **No public deployment** (no credentials). Docker build not run (Docker absent). |

## Remaining issues / next
- Configure `ANTHROPIC_API_KEY` to exercise the LLM copilot end to end.
- Choose a host with a persistent volume (e.g. a container platform), build the Dockerfile, and verify from a fresh session.
- Optional: more numerical adapters (GPM IMERG), more case files, and an independent review of the requirement mappings.
