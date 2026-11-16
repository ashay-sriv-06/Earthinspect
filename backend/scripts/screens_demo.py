"""Drive demo flows in the REAL app (headless Chromium) and save screenshots to docs/screenshots/demo-*.png."""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else "../docs/screenshots")
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
out.mkdir(parents=True, exist_ok=True)
errors = []


def fld(pg, caption, root="body"):
    return pg.locator(root).locator("label.field").filter(has=pg.locator("span", has_text=re.compile("^" + re.escape(caption))))
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("dialog", lambda d: d.accept("Demo: context set from the case file"))
    pg.goto(base)
    pg.wait_for_timeout(1500)

    # 1) Camp Fire with NASA imagery on the event date
    pg.get_by_role("button", name="Camp Fire 2018").first.click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(2500)
    pg.get_by_label("NASA GIBS MODIS true colour").check() if pg.get_by_label("NASA GIBS MODIS true colour").count() else None
    pg.locator("label.layer", has_text="NASA GIBS MODIS").locator("input").check()
    pg.wait_for_timeout(600)
    pg.get_by_role("button", name="Check").click()
    pg.wait_for_timeout(5000)
    pg.screenshot(path=str(out / "demo-01-campfire-imagery.png"))

    # 2) Brisbane: Copenhagen retention shows as a partial (mechanism mismatch) lead
    pg.get_by_role("button", name="Brisbane 2011").first.click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(2500)
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    pg.mouse.wheel(0, 0)
    also = pg.locator(".sheet", has_text="Cloudburst Management Plan: combined surface")
    if also.count():
        also.first.scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(out / "demo-02-brisbane-mismatch.png"))
    if also.count():
        also.first.get_by_role("button", name="Trace evidence").click()
        pg.wait_for_timeout(2500)
        pg.screenshot(path=str(out / "demo-03-trace-mismatch.png"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)

    # 3) Copenhagen: add a planning assumption, then What changed?
    pg.get_by_role("button", name="Copenhagen 2011").first.click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(2500)
    pg.get_by_role("tab", name="Changes").click()
    pg.wait_for_timeout(800)
    sel = fld(pg, "Prerequisite").locator("select")
    sel.select_option("req-receiving-water")
    fld(pg, "Rationale").locator("textarea").fill("Scenario: harbour outfalls assumed available for gravity flow routes (planning assumption, not sourced).")
    pg.get_by_role("button", name="Add planning assumption").click()
    pg.wait_for_timeout(1500)
    fld(pg, "Prerequisite").locator("select").select_option("req-open-space-retention")
    fld(pg, "Basis").locator("select").select_option("source_reported")
    pg.wait_for_timeout(300)
    fld(pg, "Ingested source").locator("select").select_option("src-cph-plan2012")
    fld(pg, "Page / section").locator("input").fill("Cloudburst plan: surface solutions section")
    fld(pg, "Rationale").locator("textarea").fill("Plan documents parks and squares used for detention in Copenhagen.")
    pg.get_by_role("button", name="Link source").click()
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Compare", exact=True).last.click()
    pg.wait_for_timeout(2000)
    pg.screenshot(path=str(out / "demo-04-what-changed.png"))
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(out / "demo-05-leads-after-revision.png"))

    # 4) New place via geocoder
    pg.get_by_role("button", name="+ New place").click()
    pg.wait_for_timeout(500)
    pg.get_by_placeholder("Search a place").fill("Nairobi")
    pg.get_by_role("button", name="Search", exact=True).click()
    pg.wait_for_timeout(3000)
    pg.locator(".palette-item", has_text="Nairobi").first.click()
    fld(pg, "Hazard mechanism", ".modal").locator("select").select_option("pluvial_urban_flood")
    fld(pg, "Scale", ".modal").locator("select").select_option("city")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(out / "demo-06-newplace-form.png"))
    pg.get_by_role("button", name="Confirm footprint & acquire").click()
    pg.wait_for_timeout(9000)
    pg.screenshot(path=str(out / "demo-07-newplace-analysis.png"))
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(out / "demo-08-newplace-leads.png"))
    b.close()
print("page errors:", errors)
