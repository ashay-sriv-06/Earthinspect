"""Portable work products: normalized CSV, investigation JSON, self-contained printable HTML."""
from __future__ import annotations

import csv
import html
import io
import json

from . import db, graph, matching, power, services
from .cases import MECHANISMS
from .config import POWER_END_YEAR
from .errors import ApiError
from .requirements import REQUIREMENTS


def current_batch(session_id: str, iid: str) -> dict | None:
    findings = services.latest_findings(session_id, iid)
    if not findings:
        return None
    an_id = findings[0]["props"]["analysis_id"]
    node = graph.get_node(an_id, session_id)
    with db.conn() as c:
        r = c.execute("SELECT * FROM analyses WHERE id=?", (node["props"]["batch_id"],)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "results": db.loads(r["result_json"]), "artifact_ids": db.loads(r["artifact_ids"]),
            "finding_ids": [f["id"] for f in findings], "created_at": r["created_at"]}


def _bundle(session_id, iid):
    inv = services.get_investigation(session_id, iid)
    batch = current_batch(session_id, iid)
    if not batch:
        raise ApiError("no_results", "Run the trend analysis before exporting (Acquire NASA data).", status=409)
    match = matching.run_match(session_id, iid)
    arts = [power.get_artifact(a) for a in batch["artifact_ids"]]
    src_ids = sorted({e.get("source_id") for e in match["leads"] + match["excluded"] if e.get("source_id")})
    sources = []
    for s in src_ids:
        try:
            sources.append(graph.get_node(s, session_id)["props"])
        except ApiError:
            pass
    return inv, batch, match, arts, sources


def export_csv(session_id, iid) -> str:
    inv, batch, *_ = _bundle(session_id, iid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# EarthInspect normalized series", inv["title"], f"place={inv['config']['place']['name']}",
                f"analysis={batch['id']}"])
    w.writerow(["variable", "units", "date", "value", "anomaly_vs_baseline", "monthly_total_mm", "artifact_id", "artifact_sha256"])
    for r in batch["results"]:
        for s in r["series"]:
            w.writerow([r["variable"], r["units"], s["date"], "" if s["value"] is None else s["value"],
                        "" if s["anomaly"] is None else s["anomaly"], s.get("monthly_total_mm") or "",
                        r["artifact_id"], r["artifact_sha256"]])
    return buf.getvalue()


def export_json(session_id, iid) -> dict:
    inv, batch, match, arts, sources = _bundle(session_id, iid)
    results = []
    for r in batch["results"]:
        results.append({k: v for k, v in r.items() if k not in ("series", "trend_line", "cell_centers")})
    return {
        "format": "earthinspect-investigation/1",
        "exported_at": db.now_iso(),
        "investigation": {"id": inv["id"], "title": inv["title"], "question": inv["config"]["question"],
                          "place": inv["config"]["place"], "period": inv["config"]["period"],
                          "revision_id": inv["current_revision_id"], "state": inv["state"],
                          "revisions": inv["revisions"]},
        "graph_version": match["graph_version"],
        "analysis": {"id": batch["id"], "results": results, "finding_ids": batch["finding_ids"]},
        "artifacts": [{"id": a["id"], "sha256": a["sha256"], "retrieved_at": a["retrieved_at"], "origin": a["origin"],
                       "source_url": a["manifest"]["source_url"], "units": a["manifest"]["units"],
                       "spatial_support": a["manifest"]["spatial_support"]} for a in arts],
        "match_run": {"id": match["id"], "rule_version": match["rule_version"], "leads": match["leads"],
                      "excluded": [{"intervention_id": e["intervention_id"], "reasons": e["exclusion_reasons"]} for e in match["excluded"]]},
        "sources": sources,
        "reproduction": "Raw series are not embedded. To reproduce, re-request each artifact's source_url and compare "
                        "the response SHA-256 with 'sha256' (identical only if NASA POWER has not reprocessed the data), "
                        "or obtain the referenced artifact files from the originating EarthInspect instance.",
    }


def _svg_chart(r: dict, w=640, h=150) -> str:
    pts = [(i, s["anomaly"]) for i, s in enumerate(r["series"]) if s["anomaly"] is not None]
    if not pts:
        return ""
    ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys)
    if hi == lo:
        hi = lo + 1
    n = len(r["series"])
    pad = 28

    def X(i):
        return pad + (w - pad - 6) * i / max(1, n - 1)

    def Y(v):
        return 6 + (h - 24) * (1 - (v - lo) / (hi - lo))
    path = []
    prev = None
    for i, s in enumerate(r["series"]):
        if s["anomaly"] is None:
            prev = None
            continue
        path.append(("M" if prev is None else "L") + f"{X(i):.1f},{Y(s['anomaly']):.1f}")
        prev = i
    tl = ""
    if r.get("trend_line"):
        a, b = r["trend_line"][0]["value"], r["trend_line"][-1]["value"]
        tl = f'<line x1="{X(0):.1f}" y1="{Y(a):.1f}" x2="{X(n - 1):.1f}" y2="{Y(b):.1f}" stroke="#0f6d5f" stroke-width="2"/>'
    zero = f'<line x1="{pad}" x2="{w - 6}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#bbb" stroke-dasharray="3 3"/>' if lo < 0 < hi else ""
    years = ""
    for i, s in enumerate(r["series"]):
        if s["date"].endswith("-01") and int(s["date"][:4]) % 4 == 1:
            years += f'<text x="{X(i):.1f}" y="{h - 4}" font-size="9" fill="#555">{s["date"][:4]}</text>'
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{html.escape(r["variable"])} anomaly series">'
            f'<text x="2" y="12" font-size="9" fill="#555">{hi:.2f}</text><text x="2" y="{h - 16}" font-size="9" fill="#555">{lo:.2f}</text>'
            f'{zero}<path d="{" ".join(path)}" fill="none" stroke="#5b6b78" stroke-width="1"/>{tl}{years}</svg>')


def export_html(session_id, iid) -> str:
    inv, batch, match, arts, sources = _bundle(session_id, iid)
    e = html.escape
    place = inv["config"]["place"]
    g = place["geometry"]
    geom = (f"bbox W{g['west']} S{g['south']} E{g['east']} N{g['north']}" if g["type"] == "bbox"
            else f"point {g['lon']}, {g['lat']}")
    mech = inv["state"].get("mechanism")
    rows = []
    for r in batch["results"]:
        if r["mode"] == "inferential":
            stat = (f"{r['slope_per_decade']:+.3f} {e(r['units'])}/decade; 95% CI [{r['ci95_per_decade'][0]:+.3f}, "
                    f"{r['ci95_per_decade'][1]:+.3f}]; p={r['p_value']:.4f}; BH q={r['q_value']:.4f}")
        else:
            stat = "Descriptive only: " + e(r["limitation"])
        rows.append(f"""<section class="var"><h3>{e(r['longname'])} <code>{e(r['variable'])}</code></h3>
<p class="stat">{stat}</p><p>{e(r.get('statement', ''))}</p>
{_svg_chart(r)}
<p class="meta">Anomaly vs calendar-month baseline {e(r['baseline']['start'])}–{e(r['baseline']['end'])}; green line = fitted linear trend.
n={r['n_valid']}/{r['n_months_requested']} months · coverage {r['coverage']:.0%} · support: {e(r['spatial_support']['kind'].replace('_', ' '))}
({r['spatial_support']['cell_count']} cell(s), footprint W{r['spatial_support']['footprint']['west']} S{r['spatial_support']['footprint']['south']}
E{r['spatial_support']['footprint']['east']} N{r['spatial_support']['footprint']['north']}) · artifact <code>{e(r['artifact_id'])}</code>
sha256 <code>{e(r['artifact_sha256'][:16])}…</code></p>
{''.join(f'<p class="meta">{e(cv)}</p>' for cv in r.get('conversions', []))}</section>""")
    leads = []
    for l in match["leads"]:
        feats = "".join(f"<li class='{e(f['state'])}'><b>{e(f['state'])}</b> — {e(f['detail'])}</li>" for f in l["features"])
        leads.append(f"""<section class="lead"><h3>{e(l['title'])}</h3>
<p><b>Source setting:</b> {e(l['source_place'] or '')} · <b>Status:</b> {e((l['implementation_status'] or '').replace('_', ' '))}
· <b>Outcome evidence:</b> {e(l['outcome_evidence_type'] or 'none')} · <b>Eligibility:</b> {e(l['eligibility'].replace('_', ' '))}
· <b>Ordinal match</b> {l['match_score']:.2f} / <b>coverage</b> {l['coverage']:.2f} (not a probability)</p>
<ul class="feats">{feats}</ul>
<p><b>Next evidence:</b> {e('; '.join(l['next_evidence']) or '—')}</p>
<p class="meta">Source: <code>{e(l['source_id'] or '')}</code> {e(l.get('locator') or '')}</p></section>""")
    excl = "".join(f"<li>{e(x['title'])} ({e(x['source_place'] or '')}): {e('; '.join(x['exclusion_reasons']))}</li>" for x in match["excluded"])
    srcs = "".join(f"<li><a href='{e(s.get('url', ''))}'>{e(s.get('title', ''))}</a> — {e(s.get('publisher', ''))}"
                   f" ({e(str(s.get('published') or 'n.d.'))}); retrieved {e(s.get('retrieved', ''))}; {e(s.get('status', ''))}</li>" for s in sources)
    art_list = "".join(f"<li><code>{e(a['id'])}</code> {e(a['manifest']['variable'])} · retrieved {e(a['retrieved_at'])} · {e(a['origin'])}"
                       f" · <a href='{e(a['manifest']['source_url'])}'>request URL</a> · sha256 <code>{e(a['sha256'])}</code></li>" for a in arts)
    reqs = inv["state"].get("requirements", {})
    req_html = "".join(f"<li><b>{e(REQUIREMENTS[k]['label'])}</b>: {e(v['state'])} — "
                       f"{'PLANNING ASSUMPTION (not a sourced fact)' if v['basis'] == 'analyst_assumption' else 'linked source ' + e(v.get('source_id', ''))}"
                       f"; rationale: {e(v.get('note', ''))}</li>" for k, v in reqs.items()) or "<li>None recorded — all local prerequisites unknown.</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(inv['title'])} — EarthInspect report</title>
<style>
body{{font:14px/1.5 "Inter","Segoe UI",system-ui,sans-serif;color:#1b252e;background:#f4f1ea;margin:0}}
main{{max-width:860px;margin:0 auto;padding:32px 24px}}
h1{{font:600 26px/1.2 Georgia,"Times New Roman",serif;margin:0 0 4px}} h2{{font:600 13px/1 system-ui;letter-spacing:.08em;text-transform:uppercase;color:#4b5a66;border-top:1px solid #c9c4b8;padding-top:16px;margin-top:28px}}
h3{{font-size:15px;margin:14px 0 4px}} code{{font:12px ui-monospace,Consolas,monospace;background:#e9e4d8;padding:0 3px;border-radius:3px}}
.stat{{font-variant-numeric:tabular-nums;font-weight:600}} .meta{{color:#56636e;font-size:12px}}
.tag{{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;border:1px solid #9aa5ad;margin-right:6px}}
.nasa{{border-color:#0f6d5f;color:#0f6d5f}} .doc{{border-color:#7a5a12;color:#7a5a12}} .hyp{{border-color:#9b6b10;color:#9b6b10;border-style:dashed}}
.feats li.compatible::marker{{color:#0f6d5f}} .feats li.mismatch::marker,.feats li.incompatible::marker{{color:#a33}}
.feats li.unknown{{color:#555}} section.var,section.lead{{background:#fff;border:1px solid #ddd6c8;border-radius:8px;padding:12px 16px;margin:10px 0}}
@media print{{body{{background:#fff}} section{{break-inside:avoid}}}}
</style></head><body><main>
<p class="meta">EarthInspect investigation report · exported {e(db.now_iso())} · graph {e(match['graph_version'])} · revision {e(inv['current_revision_id'])}</p>
<h1>{e(inv['title'])}</h1>
<p>{e(inv['config']['question'])}</p>
<p><b>Place:</b> {e(place['name'])} · <b>Geometry:</b> {e(geom)} · <b>Origin:</b> {e(place.get('geometry_origin') or '')}<br>
<b>Analysis period:</b> {e(inv['config']['period']['start'])} to {e(inv['config']['period']['end'])} ·
<b>Hazard mechanism:</b> {e(MECHANISMS[mech]['label'] if mech else 'not established')} · <b>Scale:</b> {e(inv['state'].get('scale') or 'not established')}</p>
<p><span class="tag nasa">NASA data</span> computed from NASA POWER (MERRA-2-derived) monthly series ·
<span class="tag doc">Historical document</span> reported by a cited source ·
<span class="tag hyp">Hypothesis / assumption</span> not verified</p>
<h2><span class="tag nasa">NASA data</span>Environmental change: computed findings</h2>
<p class="meta">Method: OLS with intercept, years elapsed and calendar-month effects; HAC (Newey–West) SE, 12 lags (sensitivity 24);
≥120 consecutive valid months required; Benjamini–Hochberg across the {len(batch['results'])}-variable family. Confidence intervals describe
uncertainty about the fitted linear slope, not predictions of future disasters. POWER meteorology is reanalysis-derived and coarse.</p>
{''.join(rows)}
<h2><span class="tag hyp">Hypothesis</span>Planning leads from historical precedents</h2>
<p class="meta">Match run <code>{e(match['id'])}</code>, rules {e(match['rule_version'])}. Outcomes stay attached to their original setting and are never
forecasts for this place. {('<b>Context insufficient:</b> the hazard mechanism must be established first.' if match['insufficient_context'] else '')}</p>
{''.join(leads) or '<p>No precedent passed the contextual rules.</p>'}
<h3>Excluded precedents (negative evidence)</h3><ul>{excl or '<li>None</li>'}</ul>
<h2>Local prerequisites recorded for this investigation</h2><ul>{req_html}</ul>
<h2><span class="tag doc">Historical document</span>Sources</h2><ul>{srcs or '<li>—</li>'}</ul>
<h2><span class="tag nasa">NASA data</span>Data artifacts</h2><ul>{art_list}</ul>
<p class="meta">Data: NASA Langley Research Center POWER Project. This report contains no API keys, session credentials or chat logs.</p>
</main></body></html>"""
