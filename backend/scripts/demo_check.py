"""Acceptance: fresh browser session → Open demo investigation → canonical focus consistent across panels → reload."""
import sys

from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ok = []


def check(c, m):
    ok.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base)
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Open demo investigation").click()
    pg.wait_for_timeout(5000)
    inv_id = pg.evaluate("new URLSearchParams(location.search).get('inv')")
    fb = pg.get_by_test_id("focus-bar")
    check(inv_id and fb.count() == 1 and inv_id in fb.inner_text(), f"demo opened; focus bar shows same investigation as URL ({inv_id})")
    check("Demo — Camp Fire 2018" in pg.locator(".cmdbar").inner_text(), "command bar names the same investigation")
    check("R1" in fb.inner_text(), "focus bar shows revision R1 (labelled assumption applied)")
    check("obs A 2018-11-08" in fb.inner_text(), "focus bar shows observation date A 2018-11-08")
    check(pg.get_by_label("Imagery date B").input_value() == "2018-10-25", "imagery date B = 2018-10-25")
    check(pg.locator(".change-banner").count() == 1, "leads show the assessment change produced by the assumption")
    check("graph g" in fb.inner_text(), "focus bar shows graph version from the match run")
    pg.get_by_role("button", name="Overlay", exact=True).click()
    pg.wait_for_timeout(300)
    pg.get_by_role("button", name="Flip to B").click()
    pg.wait_for_timeout(800)
    check("obs B 2018-10-25" in fb.inner_text(), "flipping imagery updates the canonical observation date")
    pg.get_by_role("tab", name="Analysis").click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Trace provenance").first.click()
    pg.wait_for_timeout(1200)
    claim = pg.locator(".insp-body .sheet code").first.inner_text()
    check(claim and claim[:15] in fb.inner_text(), f"selected claim in focus bar matches evidence sheet ({claim})")
    pg.screenshot(path="../docs/screenshots/demo-canonical-focus.png")
    # second investigation then back: no stale panels
    pg.get_by_role("button", name="Copenhagen 2011").first.click()
    pg.wait_for_timeout(1500)
    check(pg.get_by_test_id("focus-bar").count() == 0, "case preview clears investigation focus (no stale investigation shown)")
    pg.goto(f"{base}/?inv={inv_id}")
    pg.wait_for_timeout(4000)
    fb = pg.get_by_test_id("focus-bar")
    check(inv_id in fb.inner_text() and "R1" in fb.inner_text() and "obs B 2018-10-25" in fb.inner_text(), "reload restores the same canonical focus")
    # idempotent demo endpoint
    again = pg.evaluate("fetch('/api/demo',{method:'POST'}).then(r=>r.json()).then(j=>j.id)")
    check(again == inv_id, "POST /api/demo is idempotent per session")
    check(not errs, f"no page errors {errs[:2]}")
    b.close()
print(f"{sum(ok)}/{len(ok)} passed")
