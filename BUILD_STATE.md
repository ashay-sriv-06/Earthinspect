# BUILD_STATE

Start: 2026-11-15 18:35 PST. User deadline: 23:15 PST (5 h). Budget scaled from 450 to ~280 min with the pack's cut order. Elapsed at checkpoint: ~50 min of wall clock (environment setup included Python, Node and Git installs via winget).

| # | Phase | Status | Acceptance evidence |
|---|---|---|---|
| 01 | Foundation & first slice | ✅ | FastAPI + SQLite + React/Vite. Investigation persists across refresh and process restart (e2e run before and after restart). |
| 02 | Visual system & shell | ✅ | Field Atlas tokens frozen in CLAUDE.md. Dock, map, inspector tabs, timeline and command palette all wired to real actions. Inspected at 1440×900 and 1280×800. |
| 03 | Four case files | ✅ | `data/cases.json`: 13 sources (10 verified, 3 marked unavailable), 29 event facts and 12 responses, all with locators. |
| 04 | NASA catalog | ✅ | 16 entries (13 CMR-verified IDs). Status-aware UI. Live CMR search. 1 numerical and 1 imagery adapter, counted separately. |
| 05 | Acquisition & caching | ✅ | Real regional POWER artifacts, SHA-256, manifests, versioned force refresh, per-key locks, snapshot fallback, cache states shown in UI. |
| 06 | Trend & association | ✅ | OLS + HAC(12), sensitivity at 24 lags, BH (significance judged on q; method v1.1), ≥120-month rule, anomalies, residual correlations. 10 numerical tests. |
| 07 | Geospatial workspace | ✅ | MapLibre with GIBS basemap and imagery (date control and availability check), footprint and grid-cell layers, brush → Apply window, persisted view. |
| 08 | Evidence graph & bundles | ✅ | Typed nodes and edges, bundles with roles, provenance table, idempotent ingestion, bounded traversals. |
| 09 | Solutions graph | ✅ | 12 interventions: implemented vs proposed vs retrospective, observed vs projected, limitations as CONTRADICTS. |
| 10 | Contextual matching | ✅ | Rules match-rules-1.1. Unknown ≠ false. Persisted match runs plus hypothesis bridge edges. Tests for the sensitivity and stability requirements. |
| 11 | Copilot | ✅ (LLM path verified to auth only) | 10 tools, event log, cancel/timeout, citation and number validation, Guided analysis. Missing key and provider error both tested. |
| 12 | New place | ✅ | Open-Meteo geocoder or coordinates. Nairobi functional test with its own artifacts. |
| 13 | Trace evidence | ✅ | Layered React Flow view and table, persisted edges only, mismatch and unknown states, path pulse with reduced motion respected. |
| 14 | Revisions | ✅ | Immutable revisions, activate prior, "What changed?", assumptions never promoted to sourced facts. |
| 15 | Compare & export | ✅ | Aligned comparison; CSV, JSON and HTML exports verified. |
| 16 | Verification | ✅ | VERIFICATION.md: 20 pytest, 31 e2e, provider error, UI flows, 8-question eval. |
| 17 | Packaging & submission | ⚠️ partial | Dockerfile, README, demo script and submission copy written. **No public deployment** (no credentials). Docker build not run (Docker absent). |

## Remaining issues / next
- Configure `ANTHROPIC_API_KEY` to exercise the LLM copilot end to end.
- Choose a host with a persistent volume (e.g. a container platform), build the Dockerfile, and verify from a fresh session.
- Optional: more numerical adapters (GPM IMERG), more case files, and an independent review of the requirement mappings.


## Sprint 2 — interactivity (60 min)
Start 2026-11-15 22:09 PST · **Deadline 23:09 PST** · verification from 23:01.
Target flow: open investigation → compare real observation dates → inspect a finding → investigate supporting evidence → revise a relevant assumption → see graph + assessment update → reopen saved result.
Phases (derived from the target flow; the pasted brief did not list them):
1. Compare real observation dates (two GIBS dates, availability-checked, crossfade/flicker)
2. Inspect a finding (timeline hover readout + click-to-inspect month, finding focus)
3. Investigate supporting evidence (navigable provenance with back history)
4. Revise a relevant assumption inline from a lead's unknown prerequisite
5. See graph + assessment update (automatic before→after diff, trace refresh with changed nodes marked)
6. Reopen saved result (persist compare dates, selected evidence, last change; restore on reload)


### Sprint 2 results (verified 22:16, real app, headless Chromium — scripts/flow_check.py → 18/18; docs/flow_check_output.txt)
| phase | status | what actually works |
|---|---|---|
| 1 Compare dates | ✅ | Second GIBS date (defaults to A−14 d), A↔B crossfade slider + Flip, availability check for both dates (Camp Fire: 2018-11-08 plume vs 2018-10-25 clear). Real tiles only. |
| 2 Inspect a finding | ✅ | Timeline hover readout; click pins a month: value, monthly total (precip), anomaly vs baseline, fitted trend, missing-month and event-window flags, artifact id; Inspect finding → evidence sheet. |
| 3 Supporting evidence | ✅ | Breadcrumb trail + Back across provenance hops; Used-by list from persisted incoming edges. |
| 4 Revise assumption | ✅ | Inline on each prerequisite row: Assume satisfied / not satisfied / Link source / Clear, rationale required; labelled as planning assumption or linked source. |
| 5 Graph + assessment update | ✅ | Automatic what-changed banner (eligibility, match, coverage, feature states, top lead); Trace marks changed nodes and shows the new Assumption node. Example: assuming WUI exposure moved top lead evacuation planning → multichannel notification (needs local evidence → candidate lead). |
| 6 Reopen saved result | ✅ | Reload restores imagery A/B + mix, inspector tab, evidence trail/selected node, last change banner, revisions. |
Regression: pytest 20/20, e2e 31/31. Finished 22:17, ~52 min before deadline. No backend schema changes; view state uses the existing investigation view config.

## Sprint 3 — canonical demo state (22:21 PST)
**Inspection (verified in code, not just the report):**
| concern | frontend | backend endpoint → function |
|---|---|---|
| Investigation selection/persistence | `App.tsx` openInv (L78), patchView (L96), ?inv= URL + localStorage | GET/POST `/api/investigations`, GET/PATCH `/api/investigations/{iid}` → services.create_investigation / get_investigation / update_view |
| GIBS imagery dates | `App.tsx` imageryDate/imageryDateB/imageryMix, checkImagery; `MapView.tsx` gibs/gibsB layers | GET `/api/imagery/check` (main.py); dates stored in view config via PATCH |
| Findings & provenance | `panels.tsx` AnalysisPanel/TrendCard, EvidencePanel; `Timeline.tsx` readout | POST `/analyze` → services.run_trends_for; GET `/results`; GET `/api/graph/node`, `/provenance`, `/neighborhood` |
| Matching & revisions | `panels.tsx` LeadsPanel/ReqActions/ChangeBanner/ChangesPanel; `App.tsx` revise/loadChange | GET `/match` → matching.run_match; POST `/revisions` → services.add_revision; POST `/revisions/{rid}/activate`; GET `/what-changed` |
| Graph rendering | `TraceView.tsx` (React Flow, layered) | GET `/trace/{intervention_id}` → trace.build |
| Copilot | `CopilotPanel.tsx` (polls run) | POST/GET `/copilot`, GET `/api/copilot/{rid}`, POST cancel → copilot.start/_execute (guided | llm) |
Server-side model credential: **not configured** (`/api/health` llm.available=false); guided mode only.
Demo choice: Camp Fire 2018 — complete v1.1 analysis, working GIBS dates 2018-11-08 (plume) / 2018-10-25 (clear), assumption *WUI exposure satisfied* changes top lead (evacuation planning → multichannel notification). Existing copy inv-3973d5c0d363 is owned by a test session (isolation holds), so the demo is reproduced per caller.

**Checklist (next five phases → files/endpoints):**
1. Canonical demo: `POST /api/demo` (main.py) → services.create_demo_investigation (create_investigation → run_trends_for → update_view → add_revision); `App.tsx` "Open demo investigation" (empty state + palette).
2. Canonical focus state: `App.tsx` single `focus` = {investigation, revision, claim, observation date, graph version}; stale-response guard on investigation switch; focus bar in inspector footer.
3. Observation dates → claim: date A/B shown in focus bar; `Timeline.tsx` marks imagery dates on the series.
4. Claim → evidence → revision: EvidencePanel / ReqActions reuse `/api/graph/*` + `/revisions` (no new endpoints).
5. Update + reopen: `/what-changed` banner + `/trace` with changed nodes; `?inv=` reload restores focus (view config).

**Sprint 3 result (22:23):** `POST /api/demo` reproduces the canonical Camp Fire demo in the caller's session (idempotent; isolation preserved). `App.tsx` keeps one canonical focus {investigation, revision, claim, observation date, graph version} shown in the inspector focus bar; stale async responses from a previously selected investigation are dropped. `scripts/demo_check.py` 13/13 (docs/demo_check_output.txt). Regression: pytest 20/20, e2e 31/31, flow 18/18. Model credential: not configured (guided mode only).

