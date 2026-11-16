# EarthInspect — Recording Guide

Built from the verified build (commit `42340d2` plus one wording fix: the Changes tab now says "Highest-ranked lead" using titles, matching the Leads banner).

**Rehearsal.** The click sequence below was rehearsed in a real headless Chromium against the running app on 2026-11-15, at 1440×900 and at 1536×864 (the CSS size of a 1920×1080 screen at 125% zoom). Every step completed with no page errors. Logs are in `docs/rehearsal_1440x900.txt` and `docs/rehearsal_1536x864.txt`; frames are in `docs/recording/<size>/`. Raw clicking takes about 34 s; the rest of the 2 minutes is narration pace.

---

## 1. Recording preparation

**Start the app** (PowerShell, repo root, in a terminal that stays off screen):
```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
**Recording URL:** http://127.0.0.1:8000

**Browser and viewport**
- Use a fresh **InPrivate or Incognito window**. It gets its own session, so earlier investigations and revisions won't appear.
- On a 1920×1080 screen, set browser zoom to **125%** and maximise the window (or press F11 for full screen). On a smaller screen, use a 1440×900 window at 100%. Both layouts were checked for clipping.
- Hide the bookmarks bar. Close every other tab. Keep terminals, dev tools, `.env` files and test scripts off screen.

**Prepare the demo through the UI** (≈1 minute, not recorded):
1. In the left dock under **CASE FILES**, click **Camp Fire 2018**.
2. In the case sheet, click **Open investigation**.
3. On the **Analysis** tab, click **Acquire NASA data**. This reuses cached NASA files and takes about 3–5 s.
4. In the dock under **LAYERS**, tick **NASA GIBS MODIS true colour**. Date A fills in as **11/08/2018**.
5. Click **+ Compare a second date**. Date B fills in as **10/25/2018**, and Swipe mode is on.
6. Wait until both badges next to the dates say **loaded**. This also warms the browser tile cache.
7. Click the **Leads** tab, then the **Analysis** tab. The Analysis tab is what reopens.
8. Click **Camp Fire 2018** in **CASE FILES** again to park on the read-only case file.

**Initial state for take 1**
- The header says "Camp Fire 2018 · case file (read-only)".
- The case sheet "Camp Fire, Butte County, November 2018" is visible, with its **Open investigation** button.
- Under **MY INVESTIGATIONS**, "Camp Fire 2018 investigation" is listed.
- No revisions exist yet.

**Reset for another take.** Close the private window, open a new one, and repeat the prep. Re-activating R0 in an existing session isn't recommended: revisions are never deleted, so "What changed?" would list the earlier take's revision as well.

**Expected waits** (good spots for an edit cut)

| Moment | Typical wait |
|---|---|
| After **Open investigation**: the map fits and tiles draw | ~4–5 s |
| After **Trace evidence**: the graph builds | ~2–3 s |
| After **Save revision**: the match re-runs and the banner appears | ~2–3 s |
| After **Preview report ↗**: a new tab opens | ~1–2 s |

**If imagery is unavailable.** The date badges show **missing** or **error** instead of **loaded**. Do not change the dates. Say "NASA imagery for that date isn't available right now", skip the swipe section, and continue. The rest of the investigation works without imagery (verified). Record later if NASA GIBS is having an outage.

**Do not:**
- open the **Copilot** tab (no model key is configured; only "Guided analysis" would run);
- show `/api` URLs or the terminal;
- change dates, rules or features for the story.

---

## 2. Two-minute script (≈240 words)

| Timestamp | Exact website action | Spoken narration | What to keep visible |
|---|---|---|---|
| **0:00–0:15** | Start on the parked Camp Fire case file. Click **Open investigation**, then wait about 4 s for the map. | "This is EarthInspect. It connects environmental observations, lessons from past disasters, and the evidence behind every conclusion. Here's a retrospective look at the 2018 Camp Fire in California." | Header "Camp Fire 2018 investigation · 2001-01 – 2024-12"; map with the date labels **A · 2018-11-08** and **B · 2018-10-25** |
| **0:15–0:35** | Drag the round **⟨ ⟩** divider slowly to the right (A covers most of the map), then slowly to the left (B covers it), then back to the middle. | "These are real NASA satellite images of the same area. On the left, November eighth, 2018. On the right, October twenty-fifth. As I move the divider, you can see a large plume on the event day that isn't there two weeks earlier. This is a visual comparison only." | Both date labels; the badges **loaded / loaded** in the dock; the orange line "Visual comparison only — no burned area, smoke extent or prediction is derived from colours" |
| **0:35–0:55** | With the **Analysis** tab open, hover the first card, **Temperature at 2 Meters (T2M)**. Optionally point at the green trend line in the bottom chart. | "Underneath is long-term context. From 2001 to 2024, regional temperature rose 0.475 degrees Celsius per decade, with a 95 percent interval from 0.144 to 0.807. That's a regional trend, separate from the event imagery, and not the cause of this fire." | **+0.475 C per decade**; **95% CI [+0.144, +0.807]**; **Period 2001-01 – 2024-12**; the timeline chart |
| **0:55–1:20** | Click the **Leads (3)** tab. Scroll to the second card, "Resilient, multi-modal emergency notification system…", and click **Trace evidence**. In the graph, click the top node **SOURCE · NIST Technical Note 2252**. | "Next, planning lessons. This response, a multi-channel emergency notification system, comes from NIST's investigation of the fire. Trace it, and each link is visible: the NIST report, what it observed, and what we still don't know. Some conditions are our own analyst mappings, and the app labels them that way." | The right panel showing **Source · NIST Technical Note 2252** with **Open source ↗**; the graph's UNKNOWN requirement nodes; the focus bar now showing `src-cf-nist-tn2252` |
| **1:20–1:45** | Click **Close**. On the notification card, in the row "Community adjacent to wildland fuels…", click **Assume satisfied**. Type `Scenario: the community borders wildland fuels.` and click **Save revision**. In **ASSESSMENT UPDATED**, scroll to the notification entry's **Why this changed** and show the **Conditional assessment** box. Then click the **Changes** tab and, under **WHAT CHANGED?**, click **Compare**. | "Now I'll add one planning assumption: the community borders wildland fuels. It's saved as an assumption, not a fact. Under it, notification becomes a candidate lead, and the app marks that as conditional. Evacuation planning still needs local evidence about route capacity. The two can work together. Neither replaces the other." | "req-wui-exposure: unknown (not recorded) → satisfied (planning assumption — not a sourced fact)"; **Conditional assessment.**; the **Highest-ranked lead** line; the revision now shown as **R1** |
| **1:45–2:00** | Click **Export ▾**, then **Preview report ↗**. In the new tab, scroll slowly past the T2M chart. | "Everything is saved and exportable. What you get is a planning lead you can inspect: the evidence behind it, its limits, and the assumptions it depends on." | Report title "Camp Fire 2018 investigation"; the **NASA data / Historical document / Hypothesis / assumption** legend; the T2M finding |

Word count: about 240.

---

## 3. Sixty-second version (≈115 words)

Use the same prep. It skips the Changes-tab compare and uses the Leads banner instead.

| Timestamp | Exact website action | Spoken narration | What to keep visible |
|---|---|---|---|
| **0:00–0:08** | Click **Open investigation**. | "EarthInspect connects environmental observations, past planning lessons, and the evidence behind each conclusion. This is a retrospective look at the 2018 Camp Fire." | Header and the two date labels |
| **0:08–0:20** | Drag the **⟨ ⟩** divider right, then left. | "Real NASA imagery: November eighth on the left, October twenty-fifth on the right. A visual comparison, nothing automated." | **A · 2018-11-08**, **B · 2018-10-25**, both **loaded** |
| **0:20–0:30** | Point at the **Temperature at 2 Meters** card. | "Regional temperature rose 0.475 degrees Celsius per decade from 2001 to 2024. Context, not cause." | **+0.475 C per decade**, **95% CI [+0.144, +0.807]** |
| **0:30–0:42** | Click **Leads (3)**, then **Trace evidence** on the notification card, then click the **NIST Technical Note 2252** node. | "This notification response comes from NIST's investigation. Trace it to the report, and to the conditions we mapped ourselves." | The NIST source panel with **Open source ↗** |
| **0:42–0:55** | Click **Close**, then **Assume satisfied** on "Community adjacent to wildland fuels…". Type the rationale and click **Save revision**. | "Add one assumption: the community borders wildland fuels. Notification becomes a conditional lead. Evacuation planning still needs route-capacity evidence. They complement each other." | **ASSESSMENT UPDATED**, **planning assumption — not a sourced fact**, **Conditional assessment.** |
| **0:55–1:00** | Click **Export ▾**, then **Preview report ↗**. | "The evidence, the limits, and the assumptions, in one report." | Report title and legend |

---

## 4. Implemented now vs future plans (for Q&A or captions)

**Implemented and shown:**
- real NASA POWER trends with uncertainty;
- real NASA GIBS imagery on two dates, with swipe;
- source-backed case files and the evidence graph;
- labelled assumptions and conditional assessments;
- saved revisions;
- the exported report.

**Not implemented, and not to be claimed:**
- live or continuous monitoring (the update check is manual);
- trained graph prediction;
- automatic smoke, burn or flood detection from imagery;
- rescue or evacuation routing;
- a working LLM copilot (no key configured; "Guided analysis" is deterministic and labelled).

**Future plans, if asked:** more NASA data adapters such as GPM precipitation, more case files with independent review, sourced local infrastructure data, and an evaluated model-backed copilot.
