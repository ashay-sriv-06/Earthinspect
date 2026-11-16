# EarthInspect — submission copy

## Problem
Planners hear that "a city like ours" solved a flood, fire or drought, but two problems sit under that claim. First, regional climate signals are rarely shown with honest uncertainty. Second, lessons travel without their context. Copenhagen's 2011 cloudburst and Brisbane's 2011 flood are both "floods", yet one is intense local rainfall overwhelming drains and the other is a river catchment overtopping its banks. A response that works for one can be a partial answer, or the wrong one, for the other.

## What we built (all verified in the running app)
- **Variable selection.** A searchable catalog of 16 NASA entries: 13 product identifiers verified against Earthdata CMR, plus POWER, GIBS and CMR as services. Each entry shows what the variable measures, what it cannot resolve, and whether this app can actually analyse it. There is **one** numerical adapter (NASA POWER) and **one** imagery layer (GIBS MODIS true colour), and the catalog counts them separately.
- **Regional acquisition.** NASA POWER monthly regional requests on the MERRA-2 grid (0.5° × 0.625°) produce an area-weighted mean over the cells actually returned. Those cells are drawn on the map. Each artifact is immutable and content-hashed, with a request manifest. Identical requests are served from cache; changed geometry, period or variable produces a new key.
- **Time-series visualization.** Raw and anomaly views against a declared baseline, the fitted trend line, event intervals marked separately, missing months flagged, and brush-then-Apply windowing that creates a new labelled analysis.
- **Rate and significance.** OLS with calendar-month effects and HAC uncertainty (12 lags, 24-lag sensitivity check), requiring at least 120 consecutive valid months. Output is the slope per decade, a 95% CI, p, and Benjamini–Hochberg q across the variable family. Results from the real data include:
  - Copenhagen T2M: +0.587 °C/decade, CI [+0.340, +0.835], q < 0.001.
  - Copenhagen precipitation: +0.036 mm/day/decade, CI [−0.248, +0.321]. This is no detectable trend, and the app shows it as such.
  - Camp Fire region: T2M +0.475 °C/decade, q = 0.0099; WS10M +0.050 m/s/decade, q = 0.0099.
- **Applied context: evidence-aware transfer.** Four source-backed case files feed a typed evidence graph with hyperedge bundles. A deterministic matching engine sorts documented responses into four groups: candidate leads; leads that need local evidence; partial, component-only leads (a different mechanism in the same hazard family); and excluded responses. Every lead can be traced back to the NASA artifact hash and to the page or section of the original document.
- **Copilot.** A server-side tool-using agent with ten narrowly scoped tools. It writes a real execution log, rejects citations or numbers that didn't come from tool output, and falls back to a keyless "Guided analysis" that runs the same tools from deterministic templates.
- **Learning from new evidence, concretely.** Add a planning assumption or link a source and the app creates an immutable revision, re-evaluates the dependent match, and shows a "What changed?" diff. NASA data is not refetched. Old revisions stay inspectable.
- **Any place.** Search a place or enter coordinates, confirm the footprint, and the same pipeline runs. Tested on Nairobi as a functional test location, not as validation.

## NASA data used
NASA POWER Monthly & Annual API v2.10.0 (T2M, PRECTOTCORR, RH2M, WS10M; MERRA-2-derived); NASA GIBS WMTS (MODIS Terra Corrected Reflectance True Color, Blue Marble shaded relief, Coastlines, Reference Labels); NASA Earthdata CMR collection search (catalog verification and live discovery).

## Evidence-graph contribution
Measured trends, source-reported facts, projected and observed outcomes, analyst assumptions, and hypotheses are kept as different node and edge statuses, and the UI renders them differently. Multi-factor contexts are stored as first-class bundles with member roles, and membership never implies a causal edge. Matching reads only persisted relationships (ADDRESSES, REQUIRES, REPORTED_OUTCOME, CONTRADICTS). On an 8-question smoke test written by the builders, graph-assisted retrieval returned:
- 21/21 same-family source matches, against 16/21 for a keyword baseline over the same corpus;
- all 9 required qualifications (mismatch, unknown prerequisite, projected outcome, retrospective-only status), against 0 for the baseline, which cannot express them;
- 0 unsupported leads, against 8.

Source correctness tied on 3 of the 8 questions. This is a smoke test, not proof of general superiority.

## Limits
POWER is coarse, reanalysis-derived and monthly. It cannot measure cloudburst intensity, inundation, fire spread or reservoir storage. Four case files are illustrative, not a validation set. The "decisive" prerequisite flags are analyst judgements. The LLM copilot path was verified only up to provider authentication in this build, because no key was available. Guided analysis is fully verified. Public deployment was not performed. The Dockerfile has not been built here.

## Next steps
Numerical adapters for GPM IMERG, SMAP and GRACE-FO; event-scale precipitation; more case files with independent review; evaluated temporal link prediction; sourced infrastructure layers for local prerequisites.

**Inspect the change. Trace the evidence. Compare what might transfer.**
