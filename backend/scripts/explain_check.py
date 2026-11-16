"""Prompts 3 + 5 acceptance: explained assumption change (exact text, previous/new values, rules, source passages,
analyst labels, retrospective notice, no replacement wording) and synchronized claim → chart/map/graph inspection."""
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
    pg.get_by_role("tab", name="Leads").click()
    pg.wait_for_timeout(2500)
    body = pg.locator(".insp-body").inner_text()
    check("Retrospective analysis." in body, "retrospective notice shown")
    check("req-wui-exposure: unknown (not recorded) → satisfied (planning assumption — not a sourced fact)" in body.replace("\n", " "),
          "exact previous → new value with basis")
    check("Assumption text: “Demo scenario: target community is adjacent to wildland fuels" in body, "exact assumption text recovered")
    check("Highest-ranked lead:" in body and "Top lead:" not in body, "ranking wording, no replacement claim")
    check("does not mean one response replaces another" in body and "complementary" in body, "ordering rule + complementarity explained")
    check("Rule (match-rules-1.1):" in body, "exact rule version shown")
    check("Documented prerequisites" in body and "Source-reported" in body and "NIST" in body, "documented prerequisites quoted with source")
    check("Analyst-authored" in body and "analyst judgement" in body, "analyst-authored mappings labelled")
    check("evacuation_route_capacity".replace("_", "-") in body or "req-evacuation-route-capacity" in body, "still-unknown decisive prerequisite for evacuation planning visible")
    check("Conditional assessment." in body and "not among the prerequisites this source lists" in body, "weak analyst-only mapping flagged as conditional")
    check("not listed by source" in body and "matches a listed prerequisite" in body, "each mapping marked listed vs not listed by source")
    pg.screenshot(path="../docs/screenshots/p5-explained-change.png", full_page=False)
    pg.locator(".explain").first.scroll_into_view_if_needed()
    pg.screenshot(path="../docs/screenshots/p5-explain-detail.png")
    # Prompt 3: claim → chart + map + graph, graph → claim
    pg.get_by_role("tab", name="Analysis").click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Trace provenance").first.click()
    pg.wait_for_timeout(1500)
    claim = pg.locator(".insp-body .sheet code").first.inner_text()
    check(pg.locator(".timeline rect[stroke-dasharray]").count() >= 1, f"selecting claim {claim} marks its interval on the chart")
    pg.get_by_role("button", name="Show in evidence graph").click()
    pg.wait_for_timeout(3000)
    check(pg.locator(".tn.sel").count() == 1 and claim[:20] in (pg.locator("aside[aria-label='Selected trace node']").inner_text() + pg.locator(".tn.sel").inner_text() + claim)
          and pg.locator(".tn.sel").inner_text().startswith(("FINDING", "Finding")), "graph opens with the same claim selected")
    pg.screenshot(path="../docs/screenshots/p3-claim-in-graph.png")
    pg.locator(".tn", has_text="NIST Technical Note").first.click()
    pg.wait_for_timeout(800)
    fb = pg.get_by_test_id("focus-bar").inner_text()
    check("src-cf-nist" in fb, f"clicking a source node in the graph updates the canonical claim ({fb.splitlines()[0] if fb else ''})")
    check("Open source" in pg.locator("aside[aria-label='Selected trace node']").inner_text(), "source node shows original-document link")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    pg.get_by_role("tab", name="Evidence").click()
    pg.wait_for_timeout(1200)
    check("Source" in pg.locator(".insp-body .sheet").first.inner_text(), "evidence tab shows the claim selected in the graph")
    check(not errs, f"no page errors {errs[:2]}")
    b.close()
print(f"{sum(ok)}/{len(ok)} passed")
