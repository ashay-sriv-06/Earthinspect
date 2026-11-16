"""Rehearse the recording click sequence in the real app (headless Chromium), timing each step and
capturing visible text + screenshots. Usage: python scripts/rehearse_recording.py [width height]"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1440, 900)
base = "http://127.0.0.1:8000"
out = Path(f"../docs/recording/{W}x{H}")
out.mkdir(parents=True, exist_ok=True)
log = []
t0 = None


def step(name, pg, shot=True):
    el = time.time() - t0 if t0 else 0
    log.append((round(el, 1), name))
    print(f"[{el:6.1f}s] {name}")
    if shot:
        pg.screenshot(path=str(out / f"{len(log):02d}-{name.split(':')[0].replace(' ', '_')}.png"))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    pg = b.new_context(viewport={"width": W, "height": H}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    # ---------------- PREP (not recorded) ----------------
    pg.goto(base)
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Camp Fire 2018").first.click()
    pg.wait_for_timeout(1200)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(2500)
    if pg.get_by_role("button", name="Acquire NASA data").count():
        pg.get_by_role("button", name="Acquire NASA data").click()
        pg.wait_for_timeout(5000)
    pg.locator("label.layer", has_text="NASA GIBS MODIS").locator("input").check()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="+ Compare a second date").click()
    pg.wait_for_timeout(4000)   # tiles for both dates load and are browser-cached
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    pg.get_by_role("tab", name="Analysis").click()   # this tab is restored when the investigation reopens
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Camp Fire 2018").first.click()   # park on the read-only case file
    pg.wait_for_timeout(2000)
    print("PREP state:", pg.locator(".cmdbar .bar-title").inner_text())
    pg.screenshot(path=str(out / "00-initial-state.png"))

    # ---------------- RECORDING ----------------
    t0 = time.time()
    step("0 case file visible", pg)
    pg.get_by_role("button", name="Open investigation").click()
    pg.wait_for_timeout(4500)
    step("1 demo investigation open", pg)
    print("   bar:", pg.locator(".cmdbar .bar-title").inner_text())
    print("   labels:", pg.locator(".swipe-label.left").inner_text(), "|", pg.locator(".swipe-label.right").inner_text(),
          "| states", pg.get_by_test_id("img-state-A").inner_text(), pg.get_by_test_id("img-state-B").inner_text())

    # swipe
    h = pg.locator(".swipe-handle").bounding_box()
    mw = pg.locator(".mapwrap").bounding_box()
    y = h["y"] + h["height"] / 2
    pg.mouse.move(h["x"] + 1, y); pg.mouse.down()
    pg.mouse.move(mw["x"] + mw["width"] * 0.82, y, steps=25); pg.mouse.up()
    pg.wait_for_timeout(1200)
    step("2 swipe right shows A 2018-11-08", pg)
    h = pg.locator(".swipe-handle").bounding_box()
    pg.mouse.move(h["x"] + 1, y); pg.mouse.down()
    pg.mouse.move(mw["x"] + mw["width"] * 0.18, y, steps=25); pg.mouse.up()
    pg.wait_for_timeout(1200)
    step("3 swipe left shows B 2018-10-25", pg)
    h = pg.locator(".swipe-handle").bounding_box()
    pg.mouse.move(h["x"] + 1, y); pg.mouse.down()
    pg.mouse.move(mw["x"] + mw["width"] * 0.5, y, steps=15); pg.mouse.up()
    pg.wait_for_timeout(600)

    # numerical finding
    card = pg.locator(".sheet", has_text="Temperature at 2 Meters").first
    card.scroll_into_view_if_needed()
    print("   T2M card:", card.inner_text().replace("\n", " | ")[:330])
    step("4 T2M finding card", pg)

    # evidence connection
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(1500)
    print("   leads:", [x.inner_text().replace("\n", " ")[:90] for x in pg.locator(".insp-body .sheet h3").all()[:3]])
    notif = pg.locator(".sheet", has_text="Resilient, multi-modal emergency notification").first
    notif.scroll_into_view_if_needed()
    step("5 leads with notification card", pg)
    notif.get_by_role("button", name="Trace evidence").click()
    pg.wait_for_timeout(3000)
    step("6 trace open", pg)
    pg.locator(".tn", has_text="NIST Technical Note").first.click()
    pg.wait_for_timeout(1000)
    aside = pg.locator("aside[aria-label='Selected trace node']").inner_text()
    print("   aside:", aside.replace("\n", " | ")[:260])
    print("   focus bar:", pg.get_by_test_id("focus-bar").inner_text().replace("\n", " | "))
    step("7 NIST source selected", pg)
    pg.get_by_role("button", name="Close").click()
    pg.wait_for_timeout(800)

    # conditional revision
    notif = pg.locator(".sheet", has_text="Resilient, multi-modal emergency notification").first
    notif.scroll_into_view_if_needed()
    row = notif.locator(".feat", has_text="Community adjacent to wildland fuels")
    row.get_by_role("button", name="Assume satisfied").click()
    pg.wait_for_timeout(400)
    pg.get_by_label("Rationale").first.fill("Scenario: the community borders wildland fuels.")
    step("8 inline assumption form", pg)
    pg.get_by_role("button", name="Save revision").click()
    pg.wait_for_timeout(3000)
    banner = pg.locator(".change-banner")
    print("   banner:", banner.inner_text().replace("\n", " | ")[:700])
    banner.scroll_into_view_if_needed()
    step("9 assessment updated banner", pg)
    pg.locator(".change-banner .explain .cond").last.scroll_into_view_if_needed()
    step("10 conditional explanation", pg)
    pg.get_by_role("tab", name="Changes").click()
    pg.wait_for_timeout(800)
    wc = pg.locator(".sheet", has_text="What changed?")
    wc.scroll_into_view_if_needed()
    wc.get_by_role("button", name="Compare").click()
    pg.wait_for_timeout(2000)
    print("   what changed:", wc.inner_text().replace("\n", " | ")[:500])
    step("11 what changed compare", pg)

    # work product
    pg.locator("summary", has_text="Export").click()
    pg.wait_for_timeout(500)
    step("12 export menu", pg)
    with pg.context.expect_page() as newp:
        pg.get_by_role("link", name="Preview report ↗").click()
    rp = newp.value
    rp.wait_for_load_state()
    rp.wait_for_timeout(1200)
    print("   report title:", rp.title())
    rp.screenshot(path=str(out / "13-report.png"))
    step("13 report tab", pg, shot=False)
    print("page errors:", errs)
    b.close()
print("TIMELINE", log)
