"""Record the REAL EarthInspect UI following docs/RECORDING_GUIDE.md (2-minute table) as a 1920x1080 MP4.
Prep runs in an unrecorded context; the take is recorded in a second context sharing the same session cookie.
A visible cursor is injected (headless browsers draw none). No audio is recorded.
Usage: python scripts/record_demo.py [2min|60s]"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

VERSION = sys.argv[1] if len(sys.argv) > 1 else "2min"
BASE = "http://127.0.0.1:8000"
OUT = Path("../docs/video")
OUT.mkdir(parents=True, exist_ok=True)
RAW = OUT / f"raw_{VERSION}"
shutil.rmtree(RAW, ignore_errors=True)

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id = '__cur';
    c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:20px;height:20px;border-radius:50%;' +
      'background:rgba(255,255,255,.92);border:2px solid #111820;box-shadow:0 0 0 3px rgba(88,199,177,.55);' +
      'z-index:2147483647;pointer-events:none;transform:translate(-50%,-50%);transition:transform 90ms';
    document.documentElement.appendChild(c);
    document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px' }, true);
    document.addEventListener('mousedown', () => c.style.transform = 'translate(-50%,-50%) scale(.65)', true);
    document.addEventListener('mouseup', () => c.style.transform = 'translate(-50%,-50%) scale(1)', true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
"""

# cue sheet (seconds) per version: section start times
CUES = {
    "2min": {"open": 0, "swipe": 15, "measure": 35, "trace": 55, "revise": 80, "report": 105, "end": 120},
    "60s": {"open": 0, "swipe": 8, "measure": 20, "trace": 30, "revise": 42, "report": 55, "end": 60},
}[VERSION]


def run():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
        # ---------- PREP (not recorded) ----------
        prep = b.new_context(viewport={"width": 1536, "height": 864})
        pg = prep.new_page()
        pg.goto(BASE); pg.wait_for_timeout(1500)
        pg.get_by_role("button", name="Camp Fire 2018").first.click(); pg.wait_for_timeout(1200)
        pg.get_by_role("button", name="Open investigation").click(); pg.wait_for_timeout(2500)
        if pg.get_by_role("button", name="Acquire NASA data").count():
            pg.get_by_role("button", name="Acquire NASA data").click(); pg.wait_for_timeout(5000)
        pg.locator("label.layer", has_text="NASA GIBS MODIS").locator("input").check(); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="+ Compare a second date").click(); pg.wait_for_timeout(5000)
        assert pg.get_by_test_id("img-state-A").inner_text() == "loaded" and pg.get_by_test_id("img-state-B").inner_text() == "loaded", "imagery not loaded"
        pg.get_by_role("tab", name="Leads").click(); pg.wait_for_timeout(1200)
        pg.get_by_role("tab", name="Analysis").click(); pg.wait_for_timeout(1000)
        cookies = prep.cookies()
        prep.close()

        # ---------- TAKE (recorded) ----------
        ctx = b.new_context(viewport={"width": 1536, "height": 864},
                            record_video_dir=str(RAW), record_video_size={"width": 1536, "height": 864})  # upscaled to 1920x1080 by ffmpeg
        ctx.add_cookies(cookies)
        ctx.add_init_script(CURSOR_JS)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE)   # no localStorage carried over → app shows the start screen
        pg.wait_for_timeout(1800)
        t0 = time.time()
        marks = []

        def at(sec):  # pad until the cue time
            d = sec - (time.time() - t0)
            if d > 0:
                pg.wait_for_timeout(int(d * 1000))

        def mark(label):
            marks.append((round(time.time() - t0, 2), label))
            print(f"  {marks[-1][0]:6.2f}s  {label}")

        def center(loc):
            bb = loc.bounding_box()
            return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2

        def glide(loc, steps=25):
            x, y = center(loc)
            pg.mouse.move(x, y, steps=steps)
            return x, y

        def glide_click(loc, steps=25, pause=250):
            loc.scroll_into_view_if_needed()
            x, y = glide(loc, steps)
            pg.wait_for_timeout(pause)
            pg.mouse.click(x, y)

        def smooth_into_view(loc):
            loc.evaluate("e => e.scrollIntoView({behavior: 'smooth', block: 'center'})")
            pg.wait_for_timeout(900)

        pg.mouse.move(760, 430)
        # 0:00 OPEN
        mark("start screen")
        pg.wait_for_timeout(1000)
        glide_click(pg.get_by_role("button", name="Camp Fire 2018").first)
        pg.wait_for_timeout(1800 if VERSION == "2min" else 900)
        glide_click(pg.get_by_role("button", name="Open investigation"))
        mark("open investigation clicked")
        pg.wait_for_timeout(4500)

        # 0:15 SWIPE
        at(CUES["swipe"]); mark("swipe")
        h = pg.locator(".swipe-handle"); mw = pg.locator(".mapwrap").bounding_box()
        x, y = glide(h, 20)
        slow = 1 if VERSION == "2min" else 0.6
        pg.mouse.down(); pg.mouse.move(mw["x"] + mw["width"] * 0.85, y, steps=int(40 * slow)); pg.mouse.up()
        pg.wait_for_timeout(int(2200 * slow))
        x, y = glide(pg.locator(".swipe-handle"), 10)
        pg.mouse.down(); pg.mouse.move(mw["x"] + mw["width"] * 0.15, y, steps=int(55 * slow)); pg.mouse.up()
        pg.wait_for_timeout(int(2200 * slow))
        x, y = glide(pg.locator(".swipe-handle"), 10)
        pg.mouse.down(); pg.mouse.move(mw["x"] + mw["width"] * 0.5, y, steps=int(28 * slow)); pg.mouse.up()
        if VERSION == "2min":
            pg.wait_for_timeout(600)
            glide(pg.locator(".dock").get_by_text("Visual comparison only"), 30)

        # 0:35 MEASURE
        at(CUES["measure"]); mark("measure")
        card = pg.locator(".sheet", has_text="Temperature at 2 Meters").first
        glide(card.locator(".stat-big"), 30); pg.wait_for_timeout(2500 if VERSION == "2min" else 1500)
        glide(card.get_by_text("95% CI").first, 20); pg.wait_for_timeout(2500 if VERSION == "2min" else 1500)
        if VERSION == "2min":
            glide(card.get_by_text("2001-01 – 2024-12").first, 20); pg.wait_for_timeout(2500)
            svg = pg.locator("svg.tl-svg").bounding_box()
            pg.mouse.move(svg["x"] + svg["width"] * 0.4, svg["y"] + 75, steps=30)
            pg.mouse.move(svg["x"] + svg["width"] * 0.85, svg["y"] + 70, steps=60)

        # 0:55 TRACE
        at(CUES["trace"]); mark("trace")
        glide_click(pg.get_by_role("tab", name="Leads"))
        pg.wait_for_timeout(1500)
        notif = pg.locator(".sheet", has_text="Resilient, multi-modal emergency notification").first
        smooth_into_view(notif.locator("h3"))
        glide(notif.locator("h3"), 20); pg.wait_for_timeout(1500 if VERSION == "2min" else 600)
        glide_click(notif.get_by_role("button", name="Trace evidence"))
        pg.wait_for_timeout(3200)
        node = pg.locator(".tn", has_text="NIST Technical Note").first
        glide_click(node, steps=35, pause=400)
        pg.wait_for_timeout(1200)
        glide(pg.locator("aside[aria-label='Selected trace node']").get_by_text("Open source").first, 30)
        if VERSION == "2min":
            pg.wait_for_timeout(3000)
            glide(pg.locator(".tn", has_text="Community adjacent").first, 40); pg.wait_for_timeout(2500)

        # 1:20 REVISE
        at(CUES["revise"]); mark("revise")
        glide_click(pg.get_by_role("button", name="Close"), steps=20)
        pg.wait_for_timeout(900)
        notif = pg.locator(".sheet", has_text="Resilient, multi-modal emergency notification").first
        row = notif.locator(".feat", has_text="Community adjacent to wildland fuels")
        smooth_into_view(row)
        glide_click(row.get_by_role("button", name="Assume satisfied"))
        pg.wait_for_timeout(500)
        inp = pg.get_by_label("Rationale").first
        glide_click(inp, steps=12)
        inp.press_sequentially("Scenario: the community borders wildland fuels.", delay=28 if VERSION == "2min" else 12)
        pg.wait_for_timeout(400)
        glide_click(pg.get_by_role("button", name="Save revision"), steps=15)
        pg.wait_for_timeout(2800)
        banner = pg.locator(".change-banner")
        smooth_into_view(banner.locator("p").first)
        pg.wait_for_timeout(1800 if VERSION == "2min" else 800)
        entry = banner.locator("div", has_text="Resilient, multi-modal emergency notification system").locator(".explain .cond").first
        smooth_into_view(entry)
        glide(entry, 30)
        pg.wait_for_timeout(3000 if VERSION == "2min" else 1500)
        if VERSION == "2min":
            glide_click(pg.get_by_role("tab", name="Changes"))
            pg.wait_for_timeout(800)
            wc = pg.locator(".sheet", has_text="What changed?")
            smooth_into_view(wc)
            glide_click(wc.get_by_role("button", name="Compare"))
            pg.wait_for_timeout(1500)
            glide(wc.get_by_text("Highest-ranked lead").first, 25)

        # 1:45 REPORT
        at(CUES["report"]); mark("report")
        glide_click(pg.locator("summary", has_text="Export"), steps=25)
        pg.wait_for_timeout(900)
        link = pg.get_by_role("link", name="Preview report ↗")
        link.evaluate("a => a.removeAttribute('target')")   # open in the same tab so the take stays one continuous video
        glide_click(link, steps=15)
        pg.wait_for_url("**/export.html**")
        pg.wait_for_load_state()
        pg.wait_for_timeout(1500)
        for _ in range(6 if VERSION == "2min" else 3):
            pg.mouse.wheel(0, 160); pg.wait_for_timeout(700)
        at(CUES["end"]); mark("end")
        video = pg.video
        ctx.close()
        b.close()
        print("page errors:", errs)
        return Path(video.path()), marks


webm, marks = run()
lead_trim = 1.8  # page-load time before t0
mp4 = OUT / f"EarthInspect_{VERSION}_screen.mp4"
ff = imageio_ffmpeg.get_ffmpeg_exe()
cmd = [ff, "-y", "-ss", f"{lead_trim:.2f}", "-i", str(webm), "-t", str(CUES["end"] + 0.5), "-r", "24",
       "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
       "-movflags", "+faststart", "-an", str(mp4)]
subprocess.run(cmd, check=True, capture_output=True)
print("wrote", mp4, mp4.stat().st_size // 1024, "KB")
(OUT / f"cues_{VERSION}.txt").write_text("\n".join(f"{t:6.2f}s  {l}" for t, l in marks), encoding="utf-8")
