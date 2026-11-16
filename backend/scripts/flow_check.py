"""Drive the sprint-2 target flow in the REAL app (headless Chromium) and assert each step.
open investigation → compare two real imagery dates → inspect a finding → investigate evidence →
revise an assumption inline → assessment + trace update → reload and confirm restoration."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
out = Path("../docs/screenshots")
results = []


def check(cond, msg):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + msg)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base)
    pg.wait_for_timeout(1500)

    # 1 open investigation
    pg.get_by_role("button", name="Camp Fire 2018").first.click()
    pg.wait_for_timeout(700)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(2500)
    if pg.get_by_role("button", name="Acquire NASA data").count():
        pg.get_by_role("button", name="Acquire NASA data").click()
        pg.wait_for_timeout(4000)
    check(pg.locator(".timeline").count() == 1, "investigation open with NASA series in timeline")

    # 2 compare two real observation dates
    pg.locator("label.layer", has_text="NASA GIBS MODIS").locator("input").check()
    pg.wait_for_timeout(500)
    pg.get_by_role("button", name="+ Compare a second date").click()
    pg.wait_for_timeout(400)
    b_val = pg.get_by_label("Imagery date B").input_value()
    check(b_val == "2018-10-25", f"date B defaulted to 14 days before A: {b_val}")
    pg.get_by_role("button", name="Check both").click()
    pg.wait_for_timeout(5000)
    txt = pg.locator(".dock").inner_text()
    check("A 2018-11-08" in txt and "B 2018-10-25" in txt, "availability checked for both dates")
    print("     ", [l for l in txt.splitlines() if l.startswith("A 2018") or "· B" in l][:2])
    pg.screenshot(path=str(out / "flow-01-date-A.png"))
    pg.get_by_role("button", name="Flip to B").click()
    pg.wait_for_timeout(2500)
    check("100% B" in pg.locator(".map-legend").inner_text(), "flip shows date B (legend 100% B)")
    pg.screenshot(path=str(out / "flow-02-date-B.png"))

    # 3 inspect a finding from the timeline
    svg = pg.locator("svg.tl-svg")
    box = svg.bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.74, box["y"] + 60)
    pg.mouse.down()
    pg.mouse.up()
    pg.wait_for_timeout(400)
    ro = pg.locator(".tl-readout")
    check(ro.count() == 1 and "pinned" in ro.inner_text() and "anomaly" in ro.inner_text(), "timeline click pins a month with value/anomaly/trend readout")
    print("     ", ro.inner_text().replace("\n", " | ")[:200])
    pg.screenshot(path=str(out / "flow-03-pinned-month.png"))
    ro.get_by_role("button", name="Inspect finding").click()
    pg.wait_for_timeout(1500)
    check(pg.locator(".insp-body").get_by_text("Finding ·").count() > 0, "Inspect finding opens the computed finding's evidence sheet")

    # 4 investigate supporting evidence (navigate provenance, then back)
    prov = pg.locator(".sheet", has_text="Provenance path").locator("button.cite").first
    prov.click()
    pg.wait_for_timeout(1200)
    check(pg.locator("nav.crumbs").count() == 1, "evidence trail breadcrumbs appear after drilling into provenance")
    pg.screenshot(path=str(out / "flow-04-evidence-trail.png"))
    pg.get_by_role("button", name="← Back").click()
    pg.wait_for_timeout(1200)
    check(pg.locator(".insp-body").get_by_text("Finding ·").count() > 0, "Back returns to the finding")

    # 5 revise a relevant assumption inline from a lead
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    first = pg.locator(".sheet", has_text="Candidate").first if pg.locator(".lead-tag.candidate_lead").count() else pg.locator(".sheet:has(.lead-tag)").first
    before_tag = pg.locator(".lead-tag").first.inner_text()
    pg.get_by_role("button", name="Assume satisfied").first.click()
    pg.get_by_label("Rationale").first.fill("Scenario: Paradise-like community adjacent to wildland fuels (planning assumption).")
    pg.get_by_role("button", name="Save revision").click()
    pg.wait_for_timeout(2500)
    banner = pg.locator(".change-banner")
    check(banner.count() == 1, "assessment-updated banner appears after the revision")
    btxt = banner.inner_text() if banner.count() else ""
    print("     ", btxt.replace("\n", " | ")[:300])
    check("→" in btxt, "banner shows before → after states from what-changed")
    pg.screenshot(path=str(out / "flow-05-assessment-updated.png"))
    if banner.get_by_role("button", name="Trace updated lead").count():
        banner.get_by_role("button", name="Trace updated lead").first.click()
        pg.wait_for_timeout(2500)
        check(pg.locator(".tn.chg").count() >= 1, f"trace marks changed nodes ({pg.locator('.tn.chg').count()})")
        check(pg.locator(".tn.s-analyst_assumption").count() >= 1, "new assumption node appears in trace with assumption styling")
        pg.screenshot(path=str(out / "flow-06-trace-changed.png"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)

    # 6 reopen the saved result (full reload from URL)
    url = pg.url
    pg.wait_for_timeout(800)
    pg.goto(url)
    pg.wait_for_timeout(4000)
    check(pg.get_by_label("Imagery date B").count() == 1 and pg.get_by_label("Imagery date B").input_value() == "2018-10-25", "reload restores comparison date B")
    check("100% B" in pg.locator(".map-legend").inner_text(), "reload restores A/B mix")
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    check(pg.locator(".change-banner").count() == 1, "reload restores the last assessment change")
    pg.get_by_role("tab", name="Changes").click()
    pg.wait_for_timeout(800)
    check("Planning assumption" in pg.locator(".insp-body").inner_text() or "R1" in pg.locator(".insp-body").inner_text(), "revision R1 persisted after reload")
    pg.get_by_role("tab", name="Evidence").click()
    pg.wait_for_timeout(1200)
    check(pg.locator(".insp-body .sheet").count() > 0, "reload restores the selected evidence sheet")
    pg.screenshot(path=str(out / "flow-07-reopened.png"))
    check(not errs, f"no page errors ({errs[:2]})")
    b.close()
print(f"{sum(results)}/{len(results)} passed")
