# 2-minute demo script (canonical Camp Fire demo — verified behaviour only)

Setup: start the server and open http://127.0.0.1:8000. Click **Open demo investigation**. This calls `POST /api/demo`, which rebuilds the same investigation in your own session: the cached NASA analysis, MODIS imagery for 2018-11-08 and 2018-10-25, and one labelled planning assumption. No model key is configured, so the copilot runs as **Guided analysis**, and the demo says so.

**0:00–0:15 — Frame it honestly.** The Leads tab shows **"Retrospective analysis"**. The NIST report and the post-event imagery did not exist before the fire, so these leads are lessons in hindsight, not foresight. The focus bar (inspector footer) shows the one investigation, revision, observation dates and graph version that every panel is using.

**0:15–0:40 — Real observations, compared visually.** Drag the swipe divider:
- **A · 2018-11-08** on the left shows the smoke plume over Paradise.
- **B · 2018-10-25** on the right is clear.

Both badges say *loaded*. Click **Check for updates**: GIBS reports its newest MODIS date, with a UTC checked-at time; this is a manual check, not monitoring. Point to the label *"Visual comparison only — no burned area, smoke extent or prediction is derived from colours"*. Imagery dates are separate from the 2001–2024 trend window.

**0:40–1:00 — A computed finding and its evidence.** On the timeline, click a month to pin it: the real T2M value, anomaly, fitted trend and artifact ID appear. Click *Inspect finding*, then *Show in evidence graph*. The trace opens with the same finding selected. Click the **NIST Technical Note** source node: the focus bar's claim updates and the original-document link appears.

**1:00–1:40 — The assumption, explained, and conditional.** In the Leads tab, the **Assessment updated** banner shows:
- the exact assumption text and `req-wui-exposure: unknown (not recorded) → satisfied (planning assumption — not a sourced fact)`;
- **Why this changed**: rule `match-rules-1.1`, and a table of the decisive prerequisites before and after;
- **Multichannel notification** moving to *candidate lead*, because its only decisive prerequisites are the mechanism and WUI exposure;
- **Evacuation planning** still at *needs local evidence*, because `req-evacuation-route-capacity` is unknown.

Then say the important part: **"Conditional assessment."** WUI exposure is an analyst-added applicability condition. It is *not among the prerequisites NIST lists* (those are marked *not listed by source*). The ranking orders leads by completeness of evidence. It does not mean notification replaces evacuation planning: they are separate NIST recommendations (R-N and R-EP) and can be complementary.

**1:40–2:00 — Reopen and persist.** Reload the page. The swipe position, both dates, opacity, camera, selected claim, revision R1 and the explained change all come back. Close on: **"Inspect the change. Trace the evidence. Compare what might transfer."**
