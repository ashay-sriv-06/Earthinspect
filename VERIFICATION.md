# VERIFICATION — EarthInspect (2026-11-15/16, local build)

Every check below was **executed** in this build environment (Windows 11, Python 3.12.10, Node 26.13.1). Raw outputs are in `docs/e2e_output.txt`, `docs/provider_error_output.txt` and `docs/eval_results.json`. Screenshots are in `docs/screenshots/` and were captured from the real running app with headless Chromium.

## Counts
| item | count |
|---|---|
| Catalog entries | 16 (13 product IDs verified against NASA CMR on 2026-11-15, plus POWER, GIBS and CMR as services) |
| Numerical adapters actually implemented | **1** (NASA POWER monthly: T2M, PRECTOTCORR, RH2M, WS10M) |
| Imagery adapters | **1** (GIBS MODIS Terra Corrected Reflectance True Color; basemap also from GIBS) |
| Case files | 4. Sources: 13 records, 10 verified and 3 marked unavailable (Brisbane QFCI final report PDF not text-extractable, QFCI final-report page unreachable, original Cape Town strategy URL refused) |
| Documented responses | 12 (3 per case), each with a source id and page/section locator |
| Real NASA POWER artifacts for seed cases | 16 (4 cases × 4 variables), all fetched live, snapshots exported |
| Graph (public) after seed + case analyses | 211 nodes, 20 relationship bundles (v1.0 and v1.1 analyses both retained; nothing overwritten) |

## Automated tests (`pytest -q tests` → 20 passed)
- Trend recovery with seasonality: synthetic slope 0.3/decade is recovered within 0.06, and the CI covers the truth.
- A null trend is not forced significant.
- A gap in the window blocks inference, preserves 288 calendar months, and suggests the longest qualifying contiguous interval.
- Series under 120 months stay descriptive only.
- Absent months stay on the calendar as `None`.
- BH: q ≥ p, and the family size is recorded.
- Normalization excludes `YYYY13` annual keys, maps fill −999 to missing, converts leap-February totals with 29 days, and reports cell size 0.625°.
- Cache keys are stable for identical inputs and change with geometry, period or variable. Analysis cache keys also change when the trend method version changes (added after the bug below).
- Significance wording and flags follow the BH-adjusted q, not the raw p.
- Geometry: the antimeridian is rejected, polygons are rejected, and boxes under 2° are rejected for regional requests.
- Residual correlation removes shared trend and season (raw r > 0.9 drops to |r| < 0.2 for independent noise).
- Matching rules:
  - Changing the mechanism changes eligibility (pluvial → needs evidence, riverine → partial, drought → excluded).
  - An unknown mechanism is never compatible.
  - Decisive prerequisites drive candidate / unknown / excluded.
  - Unrelated changes leave results stable.
  - A disputed finding becomes unknown.
  - The score is labelled ordinal.
- Revisions persist, prior state is preserved, a second session cannot read or revise, and an assumption cannot be promoted to a sourced fact without an ingested Source node.
- Seed ingestion is idempotent.

## End-to-end against the running server (`scripts/e2e_check.py` → 31 PASS, 0 FAIL)
This was run before and after a server process restart, against the same SQLite data.
- Health; 4 case files; every intervention has a source locator.
- Copenhagen investigation: data reused from cache (4 cached, 0 fetched), and the analysis reused.
- Session isolation: another session gets 404 when reading or revising.
- The provenance path from a finding reaches Analysis → Artifact → Dataset and Variable.
- Matching:
  - Copenhagen responses lead.
  - Camp Fire responses are excluded for a pluvial target.
  - Brisbane responses are `partial_component_only` for Copenhagen.
- Revisions:
  - An assumption revision changes the open-space feature.
  - The repeated analysis is reused and nothing is refetched.
  - Graph ingestion is idempotent (node counts unchanged).
  - The prior revision's match stays inspectable.
- Trace contains Intervention, Source, Requirement, Mechanism, Artifact, Analysis, Finding, Investigation and Place nodes, with 23 persisted edges.
- Guided copilot: 23 real events, cache hits, and a cited answer.
- LLM mode without a key returns 409 `llm_unavailable`, and everything else keeps working.
- Exports: CSV (140 kB), JSON (28 kB; graph version plus artifact hashes) and HTML (31 kB) all download.
- New place, Nairobi (functional test location, not validation):
  - Own NASA request: artifacts `art-5ef1021e9e03-v1`, `art-f9a6fd2686f2-v1`, `art-b8c4b1cbd985-v1`, `art-1c47f908da9a-v1`, fetched in 3.4 s, all from cache on repeat.
  - Every lead keeps "Copenhagen 2011" as its source city.
  - No code change or manifest was added for it.
- An antimeridian box is rejected with `antimeridian_unsupported`.

## Provider error (`scripts/provider_error_check.py`, server started with an invalid key)
- The LLM run reached the Anthropic API and got `401 authentication_error`. The run ended in state `error` with code `provider_error`, the log said "Maps, trends and evidence remain available", and no key text appeared in the output.
- Trend analysis and Guided analysis still completed on the same server.
- **Not verified:** a successful LLM tool loop. No API key was available, so the `llm` path is verified only up to authentication.

## UI (real app; headless Chromium at 1440×900 and 1280×800)
- 0 page errors across the main flows: home, case file, open investigation, analysis, leads, trace, guided copilot, changes, compare, new-place dialog.
- Fixed during verification:
  - The CARTO basemap required an API key, so the basemap switched to NASA GIBS.
  - The MapLibre v6 module worker was not bundled, so it is now bundled via `?worker&url`.
  - The trace graph was illegible at fit-to-width, so it now uses a top-to-bottom layered layout.
  - Some buttons clipped at 1280px.
- WebGL disabled: the map shows "Map unavailable … Charts, tables and evidence remain fully usable", and the analysis and timeline work. Reduced motion is honoured through CSS media queries; the test used `reduced_motion='reduce'`.
- Demo flows driven through the UI (`scripts/screens_demo.py`):
  - Camp Fire with GIBS imagery for 2018-11-08: the tile availability check passed and the smoke plume is visible.
  - Brisbane: the Copenhagen plan shows "Partial — component only" and the trace highlights the mechanism mismatch.
  - Copenhagen: an assumption plus a linked source turns the tunnel plan from needs-local-evidence into a candidate lead, and "What changed?" shows it.
  - Nairobi via geocoder.

## Scientific results on real data (2001-01 to 2024-12, 288/288 months each)
| case | variable | slope/decade | 95% CI | p | BH q |
|---|---|---|---|---|---|
| Copenhagen | PRECTOTCORR | +0.036 mm/day | [−0.248, +0.321] | 0.80 | 0.80 |
| Copenhagen | T2M | +0.587 °C | [+0.340, +0.835] | 3.3e−6 | 1.3e−5 |
| Copenhagen | RH2M | −0.568 % | [−1.114, −0.022] | 0.042 | 0.083 |
| Brisbane | PRECTOTCORR | −0.152 mm/day | [−0.486, +0.181] | 0.37 | 0.49 |
| Brisbane | T2M | +0.268 °C | [−0.025, +0.560] | 0.073 | 0.29 |
| Camp Fire | T2M | +0.475 °C | [+0.144, +0.807] | 0.005 | 0.0099 |
| Camp Fire | WS10M | +0.050 m/s | [+0.017, +0.083] | 0.0028 | 0.0099 |
| Camp Fire | RH2M | −1.658 % | [−3.606, +0.290] | 0.095 | 0.127 |
| Cape Town | PRECTOTCORR | +0.221 mm/day | [+0.032, +0.410] | 0.022 | 0.087 |
| Cape Town | T2M | −0.119 °C | [−0.247, +0.009] | 0.068 | 0.136 |

Cape Town's 2001–2024 linear precipitation slope is nominally positive (p = 0.022) but not significant after BH (q = 0.087), even though 2015–2017 was a severe drought. Copenhagen RH2M behaves the same way (p = 0.042, q = 0.083). The app labels both cases "nominally significant but not after Benjamini–Hochberg adjustment". A multi-year deficit is not a linear trend. The app shows the event band on the timeline and does not use the trend as drought evidence.

## Retrieval smoke test (`scripts/eval_retrieval.py`, 8 questions)
| method | same-family sources (of 21) | required qualifications detected (of 9) | unsupported leads |
|---|---|---|---|
| Graph-assisted matching | 21 | 9 | 0 |
| Keyword baseline (same corpus) | 16 | 0 | 8 |

Source correctness tied on Q3, Q6 and Q8. The baseline has no mechanism, prerequisite or outcome-type reasoning, so the qualification column is partly a structural difference. The questions were written by the builders: this is a smoke test, not proof of general superiority.

## Defects found and fixed during verification
- **Significance overstated.** Statements used raw p < 0.05 while BH q was ≥ 0.05 (Copenhagen RH2M, Cape Town PRECTOTCORR). Fixed in method version `trend-ols-hac-1.1`: wording and the matching engine's `significant` flag now use BH q.
- **Cache-invalidation bug.** `analysis_cache_key` checked `kind == "trend"` while batches use `"trend_batch"`, so a trend method-version bump did not invalidate cached analyses. Fixed; a regression test was added; analyses were recomputed with the NASA artifacts reused.
- **Mixed findings risk.** Findings from different batches (method versions or variable families) for the same place could mix. Each investigation now pins its `current_batch`.
- **Eligibility ordering.** "Needs local evidence" outranked a mechanism mismatch. Now a mismatch caps transfer at "partial (component only)" (`match-rules-1.1`).
- **UI.** The CARTO basemap needed a key; the MapLibre worker wasn't bundled; the trace graph was illegible; some buttons clipped at 1280px. All fixed.

## Limitations and unresolved items
- **No public deployment.** No hosting credentials were available. The app runs locally at http://127.0.0.1:8000, which is not a public URL. The Dockerfile has not been built (Docker is not installed).
- **LLM copilot:** only verified up to authentication (see above).
- **Sources:**
  - The Brisbane Inquiry final report could not be text-extracted, so the Queensland Government 2013 implementation update, which quotes the recommendations verbatim, is used instead.
  - Cape Town strategy locators are section names, not page numbers.
  - Cape Town event dates are year-level placeholders, with a `date_note`.
- **Matching:** the requirement mappings and "decisive" flags are analyst judgements, labelled in the data (`overlay_note`).
- **Imagery check:** tested one tile at zoom 5 near the footprint centre. Cloud cover is not assessed. Headless runs logged occasional HTTP 500s from external GIBS tile requests. They were not reproducible on direct tile requests, the app server logged no 500s, and the map degrades gracefully.
- **Not built (cut per pack order):** 3D, animated playback, dual synchronized maps, additional numerical providers, daily feeds.

## Sprint 3 / Prompts 2–6 (2026-11-15 22:41 PST, local, headless Chromium + API)
| suite | result | output |
|---|---|---|
| pytest | 20/20 | — |
| API e2e | 31/31 | docs/e2e_output.txt |
| interactive target flow | 18/18 | docs/flow_check_output.txt |
| canonical demo + focus | 13/13 | docs/demo_check_output.txt |
| A/B imagery swipe, states, persistence, update check | 15/15 | docs/imagery_check_output.txt |
| synchronized inspection + explained assumption change | 17/17 | docs/explain_check_output.txt |
| copilot (no credential → guided) | 8/8 | docs/copilot_check_output.txt |

Findings worth stating plainly:
- **Imagery.** MODIS tiles for 2018-11-08 and 2018-10-25 load for the Camp Fire footprint. A 2030 date returns HTTP 404 and is shown as *missing*, never substituted. The comparison is visual only.
- **Assumption change is conditional.** The demo's assumption (eq-wui-exposure = satisfied) moves multichannel notification to *candidate lead*. That prerequisite is an analyst-added applicability condition, not one of NIST's listed prerequisites, so the UI labels the change a conditional assessment. The matching rules were not changed to produce it.
- **Retrospective.** The case uses post-event documents and imagery, and the UI says so.
- **LLM copilot.** It remains unverified end to end because no server-side credential is configured. Guided mode is the verified path.
