# 2-minute demo script (describes only verified behaviour)

Setup before recording: start the server, run `python -m scripts.prewarm`, and open http://127.0.0.1:8000. In one browser session, prepare a Brisbane investigation, a Copenhagen investigation, and a Nairobi investigation (a saved run). If the copilot model key isn't configured, use **Guided analysis** and say so.

**0:00–0:15 — The question.** Open *Brisbane 2011 investigation*. Read the bar: "riverine catchment flood". Say: *"What is changing here, which historical experiences are relevant, what makes them transferable or unsuitable, and what evidence would change that?"*

**0:15–0:40 — NASA trend with uncertainty.** On the Analysis tab, show PRECTOTCORR: **−0.152 mm/day per decade, 95% CI [−0.486, +0.181], q = 0.49**. Say: *"No statistically detectable linear trend under this method. We show that, we don't hide it."* Click T2M: +0.268 °C/decade, CI crosses zero. Point at the map: the amber box is the requested footprint, the dashed teal cells are the 15 actual MERRA-2 cells, and the series is an area-weighted mean. Click *Source request* to show the NASA POWER URL and the artifact SHA-256.

**0:40–1:05 — Another flood case, and why it doesn't simply transfer.** Open the Leads tab. The Brisbane responses come first (catchment flood study, dam operations, flood mapping) and keep their own source city. Scroll to *Also considered*: Copenhagen's Cloudburst plan is **"Partial — component only"**. The reason given is the same hazard family but a different mechanism (pluvial vs riverine), designed at city scale where the target is a catchment.

**1:05–1:25 — Trace the lead.** Click *Trace evidence* on the Copenhagen plan. Read the graph top to bottom: NASA dataset → artifact → PRECTOTCORR analysis → finding. Next comes the red **mismatch** mechanism, then the unknown requirements, then the response. The Copenhagen plan source and its **projected** outcome (the Climate-ADAPT DKK 11 bn estimate) sit alongside. A dashed amber edge marks the hypothesis bridge to this investigation. Click the Source node to open the original document link.

**1:25–1:45 — Change the evidence.** Switch to *Copenhagen 2011 investigation*, then open the Changes tab:
- Add a planning assumption: "Gravity flow routes to a receiving water body = satisfied".
- Link a source: the Copenhagen plan, for open space.

Open *What changed?* comparing R0 to the active revision. The combined surface/tunnel plan moves **needs local evidence → candidate lead** and becomes the new top lead (previously the legislative amendment), and the responsible revisions are listed. The note confirms the NASA artifacts and trend analysis were reused, not refetched. The assumption keeps its "Planning assumption" badge.

**1:45–2:00 — A fifth place, same pipeline.** Open *Nairobi, Kenya investigation* (a saved run created through *+ New place* with the geocoder). Its trends come from its own NASA request: T2M +0.113 °C/decade, CI [−0.038, +0.264]. Every lead names Copenhagen as its source city, and the local prerequisites stay unknown. Click *Export → Printable report*. Close on: **"Inspect the change. Trace the evidence. Compare what might transfer."**
