"""Capture screenshots of the REAL running app with headless Microsoft Edge (Playwright).
Usage: python scripts/screens.py [outdir] [base]"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(sys.argv[1] if len(sys.argv) > 1 else "../docs/screenshots")
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
out.mkdir(parents=True, exist_ok=True)
errors = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    for (w, h) in ((1440, 900), (1280, 800)):
        ctx = b.new_context(viewport={"width": w, "height": h})
        pg = ctx.new_page()
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base)
        pg.wait_for_timeout(2500)
        pg.screenshot(path=str(out / f"{w}-01-home.png"))
        pg.get_by_role("button", name="Copenhagen 2011").first.click()
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(out / f"{w}-02-casefile.png"))
        pg.get_by_role("button", name="Open investigation").click()
        pg.wait_for_timeout(2500)
        if pg.get_by_role("button", name="Acquire NASA data").count():
            pg.get_by_role("button", name="Acquire NASA data").click()
            pg.wait_for_timeout(4000)
        pg.screenshot(path=str(out / f"{w}-03-analysis.png"))
        pg.get_by_role("tab", name="Leads").click()
        pg.wait_for_timeout(1500)
        if pg.get_by_role("button", name="Find precedents").count():
            pg.get_by_role("button", name="Find precedents").click()
            pg.wait_for_timeout(1500)
        pg.screenshot(path=str(out / f"{w}-04-leads.png"))
        pg.get_by_role("button", name="Trace evidence").first.click()
        pg.wait_for_timeout(2500)
        pg.screenshot(path=str(out / f"{w}-05-trace.png"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(500)
        pg.get_by_role("tab", name="Copilot").click()
        pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Guided analysis").click()
        pg.get_by_label("Question").fill("What is changing here, which historical experiences are relevant?")
        pg.get_by_role("button", name="Ask", exact=True).click()
        pg.wait_for_timeout(5000)
        pg.screenshot(path=str(out / f"{w}-06-copilot.png"))
        pg.get_by_role("tab", name="Changes").click()
        pg.wait_for_timeout(800)
        pg.screenshot(path=str(out / f"{w}-07-changes.png"))
        pg.get_by_role("banner").get_by_role("button", name="Compare").click()
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(out / f"{w}-08-compare.png"))
        pg.keyboard.press("Escape")
        pg.get_by_role("button", name="+ New place").click()
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(out / f"{w}-09-newplace.png"))
        pg.keyboard.press("Escape")
        ctx.close()
    b.close()
print("console errors:", len(errors))
for e in errors[:15]:
    print("  ", e[:240])
