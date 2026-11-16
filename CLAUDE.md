# EarthInspect — durable product contract

**One sentence:** EarthInspect helps people investigate environmental change, compare lessons from past disasters, and trace every planning lead back to its contextual assumptions, measured findings, and original sources.

Active spec: `EARTHINSPECT_BUILD_PACK.txt` (17 prompts). Progress: `BUILD_STATE.md`. Evidence of checks: `VERIFICATION.md`.

## Run
```powershell
# backend (Python 3.12)
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
# frontend (Node 22+)
cd ..\frontend; npm ci; npx vite build
# serve API + built UI on http://127.0.0.1:8000
cd ..\backend; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# optional: prewarm the 4 cases with real NASA data, run checks
.\.venv\Scripts\python -m scripts.prewarm
.\.venv\Scripts\python -m pytest -q tests
.\.venv\Scripts\python scripts\e2e_check.py
```
Dev UI with hot reload: `cd frontend; npx vite` (proxies `/api` to :8000).

## Module boundaries (backend/app)
| module | responsibility |
|---|---|
| `power.py` | NASA POWER monthly acquisition, normalization, immutable hashed artifacts, cache keys, snapshot fallback |
| `analysis.py` | deterministic OLS+HAC trend, BH family, anomalies, descriptive associations (no LLM) |
| `graph.py` | SQLite typed graph: nodes, edges, relationship_bundles (hyperedges), provenance, bounded traversals |
| `services.py` | seed graph, acquisition→analysis→graph ingestion, investigations, immutable revisions |
| `matching.py` | deterministic contextual matching (rules `match-rules-1.1`), what-changed |
| `copilot.py` | tool registry, guided workflow, Anthropic tool loop, answer validation, event log |
| `trace.py` / `report.py` | trace subgraph; CSV/JSON/HTML exports |
| `catalog.py` | CMR-verified dataset catalog with capability statuses |
| `cases.py` + `data/cases.json` | 4 source-backed case files (built by `scripts/build_cases.py`) |

Frontend (`frontend/src`): `App.tsx` shell/state, `MapView.tsx` (MapLibre + GIBS), `Timeline.tsx`, `panels.tsx`, `CopilotPanel.tsx`, `TraceView.tsx` (React Flow), `dialogs.tsx`.

## Data honesty rules (non-negotiable)
- POWER meteorology is MERRA-2 reanalysis-derived, regional and monthly. Never call it satellite measurement, inundation, cloudburst intensity, fire spread or reservoir storage.
- Show actual results, including non-significant ones ("no statistically detectable linear trend under this method").
- Never zero-fill, interpolate or compress missing months; inference needs ≥120 consecutive valid months (product rule).
- Event facts, later recommendations, projected outcomes, user assumptions and hypotheses stay distinct (status field + UI badge).
- Prerequisites (drainage, evacuation capacity, budget…) are never inferred from climate data: unknown until sourced or assumed.
- Match score is ordinal, not a probability. Source outcomes never become forecasts for a target.
- No fake progress, fabricated statistics, or controls without a real action. Test fixtures never appear as evidence.
- Server-side fetches only to allow-listed hosts (POWER, GIBS, CMR, Open-Meteo geocoder). Keys stay server-side.

## Visual system (frozen — "Field Atlas")
ink `#111820`, panel `#1b252e`, paper `#f4f1ea`, teal `#58c7b1` (selection/computed), amber `#d5a555` (hypothesis/assumption), muted red `#d57a6c` (conflict). Inter for UI with tabular numerals, Source Serif 4 for case titles, JetBrains Mono for ids. 6–10px radii, 32px controls, motion 120/160/200ms, reduced-motion honoured. Further design work must improve a workflow.
