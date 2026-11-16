"""Prompt 2 acceptance in the real app: A/B swipe on real dated GIBS imagery, per-side states, persistence,
check-for-updates timestamp, missing imagery handled without breaking the investigation."""
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
    pg.wait_for_timeout(1200)
    pg.get_by_role("button", name="Open demo investigation").click()
    pg.wait_for_timeout(7000)
    inv = pg.evaluate("new URLSearchParams(location.search).get('inv')")
    check(pg.locator(".swipe-handle").count() == 1, "swipe divider rendered")
    check(pg.locator(".swipe-label.left").inner_text() == "A · 2018-11-08" and pg.locator(".swipe-label.right").inner_text() == "B · 2018-10-25",
          "actual observation date labelled on each side")
    check(pg.get_by_test_id("img-state-A").inner_text() == "loaded" and pg.get_by_test_id("img-state-B").inner_text() == "loaded",
          f"both real tiles loaded (A={pg.get_by_test_id('img-state-A').inner_text()}, B={pg.get_by_test_id('img-state-B').inner_text()})")
    mb = pg.locator(".mapwrap").bounding_box()
    pg.mouse.move(mb["x"] + mb["width"] * 0.2, mb["y"] + mb["height"] * 0.7)
    pg.mouse.down(); pg.mouse.move(mb["x"] + mb["width"] * 0.25, mb["y"] + mb["height"] * 0.6, steps=6); pg.mouse.up()
    pg.wait_for_timeout(1500)
    center_before = pg.evaluate("fetch('/api/investigations/" + inv + "').then(r=>r.json()).then(j=>j.config.view.center)")
    print("      user-moved camera saved:", center_before)
    pg.screenshot(path="../docs/screenshots/p2-swipe-50.png")
    h = pg.locator(".swipe-handle").bounding_box()
    mw = pg.locator(".mapwrap").bounding_box()
    pg.mouse.move(h["x"] + 1, h["y"] + h["height"] / 2)
    pg.mouse.down()
    pg.mouse.move(mw["x"] + mw["width"] * 0.3, h["y"] + h["height"] / 2, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(1200)
    clip = pg.locator(".swipe-b").evaluate("e => e.style.clipPath")
    check("inset(0px 0px 0px 3" in clip or "inset(0 0 0 3" in clip, f"dragging the divider moves the clip ({clip})")
    pg.screenshot(path="../docs/screenshots/p2-swipe-30.png")
    # opacity via existing control
    pg.locator("label.row", has_text="Opacity").locator("input").fill("0.5")
    pg.wait_for_timeout(300)
    # tab changes keep camera
    pg.get_by_role("tab", name="Analysis").click()
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(800)
    # check for updates
    pg.get_by_role("button", name="Check for updates").click()
    pg.wait_for_timeout(4000)
    lc = pg.get_by_test_id("latest-check").inner_text()
    check("Newest MODIS date on GIBS" in lc and "checked 20" in lc and "no background monitoring" in lc, f"check-for-updates shows real result + timestamp: {lc[:110]}")
    pg.get_by_role("button", name="Check both").click()
    pg.wait_for_timeout(5000)
    check("A 2018-11-08: tile available" in pg.locator(".dock").inner_text() and "B 2018-10-25: tile available" in pg.locator(".dock").inner_text(), "server-side tile check confirms both dates")
    pg.wait_for_timeout(800)
    # reopen saved view
    pg.goto(f"{base}/?inv={inv}")
    pg.wait_for_timeout(6000)
    v = pg.evaluate("fetch('/api/investigations/" + inv + "').then(r=>r.json()).then(j=>j.config.view)")
    check(abs(v["imagery_swipe"] - 0.3) < 0.05 and v["imagery_date_b"] == "2018-10-25" and abs(v["layers"]["imagery_opacity"] - 0.5) < 0.01,
          f"reopen restores swipe {v['imagery_swipe']}, date B {v['imagery_date_b']}, opacity {v['layers']['imagery_opacity']}")
    check(v["center"] == center_before, f"camera preserved through panel changes ({v['center']})")
    check("inset(0px 0px 0px 3" in pg.locator(".swipe-b").evaluate("e => e.style.clipPath") or "inset(0 0 0 3" in pg.locator(".swipe-b").evaluate("e => e.style.clipPath"), "reopened map shows the saved swipe position")
    # missing imagery: a date GIBS has no tile for → 'missing', investigation still usable
    miss = pg.evaluate("fetch('/api/imagery/check?date=2030-01-01&z=5&x=5&y=12').then(r=>r.json())")
    check(miss["state"] == "missing" and miss["available"] is False, f"server distinguishes missing imagery ({miss['state']}, HTTP {miss.get('status')})")
    pg.get_by_label("Imagery date B").fill("2001-01-01")  # MODIS exists; verify a different real date loads
    pg.wait_for_timeout(5000)
    check(pg.get_by_test_id("img-state-B").inner_text() in ("loaded", "missing"), f"changing B reloads real tiles (state {pg.get_by_test_id('img-state-B').inner_text()})")
    pg.evaluate("fetch('/api/investigations/" + inv + "',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({view:{imagery_date_b:'2030-01-01'}})})")
    pg.wait_for_timeout(800)
    pg.goto(f"{base}/?inv={inv}")
    pg.wait_for_timeout(6000)
    check(pg.get_by_test_id("img-state-B").inner_text() in ("missing", "error"), f"unavailable date B shown as {pg.get_by_test_id('img-state-B').inner_text()}, not substituted")
    check(pg.locator(".swipe-label.right").inner_text() == "B · 2030-01-01", "label keeps the requested date (no silent substitution)")
    pg.screenshot(path="../docs/screenshots/p2-missing-B.png")
    pg.get_by_role("tab", name="Analysis").click()
    pg.wait_for_timeout(800)
    check(pg.locator(".insp-body .sheet").count() >= 4, "analysis remains usable with failed imagery")
    pg.evaluate("fetch('/api/investigations/" + inv + "',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({view:{imagery_date_b:'2018-10-25'}})})")
    check(not errs, f"no page errors {errs[:2]}")
    b.close()
print(f"{sum(ok)}/{len(ok)} passed")
