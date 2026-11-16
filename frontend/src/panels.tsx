import { useEffect, useState } from 'react'
import type { Artifact, Bundle, CaseFile, Evaluation, GNode, Investigation, MatchRun, Meta, Results, TrendResult } from './api'
import { api, fmt, fmtP, humanize } from './api'

export function StatusBadge({ status, dark }: { status: string; dark?: boolean }) {
  const map: Record<string, [string, string]> = {
    computed: ['b-computed', 'Computed · NASA data'],
    source_reported: ['b-source', 'Source-reported'],
    analyst_assumption: ['b-assume', 'Planning assumption'],
    hypothesis: ['b-hyp', 'Hypothesis'],
    reference: ['b-neutral', 'Reference'],
    disputed: ['b-conflict', 'Disputed'],
    superseded: ['b-neutral', 'Superseded'],
  }
  const [c, l] = map[status] || ['b-neutral', humanize(status)]
  return <span className={`badge ${c}`} style={dark ? undefined : undefined}>{l}</span>
}

export function ImplBadge({ status }: { status: string }) {
  const m: Record<string, [string, string]> = {
    implemented: ['b-source', '● Implemented'],
    proposed: ['b-hyp', '○ Proposed'],
    retrospective_recommendation: ['b-assume', '◇ Retrospective recommendation'],
  }
  const [c, l] = m[status] || ['b-neutral', humanize(status)]
  return <span className={`badge ${c}`}>{l}</span>
}
export function OutcomeBadge({ type }: { type: string }) {
  const m: Record<string, [string, string]> = {
    observed: ['b-source', 'Observed outcome'], projected: ['b-hyp', 'Projected outcome'],
    modeled: ['b-hyp', 'Modeled outcome'], none: ['b-neutral', 'No reported outcome'],
  }
  const [c, l] = m[type] || ['b-neutral', humanize(type || 'none')]
  return <span className={`badge ${c}`}>{l}</span>
}

/* ------------------------------------------------------------ case file */
export function CasePanel({ c, onOpen, busy, onNode }: { c: CaseFile; onOpen: () => void; busy: boolean; onNode: (id: string) => void }) {
  const src = (id: string) => c.sources.find(s => s.id === id)
  return (
    <div>
      <div className="sheet">
        <p className="muted small">Case file · {c.mechanism.label}</p>
        <h2 className="case-title">{c.event_name}</h2>
        <p className="small muted num">Event interval {c.event_start} → {c.event_end}</p>
        <p>{c.summary}</p>
        <div className="row wrap" style={{ marginTop: 8 }}>
          <button className="btn primary" onClick={onOpen} disabled={busy}>{busy ? 'Opening…' : 'Open investigation'}</button>
        </div>
      </div>
      <div className="sheet">
        <h4>Analysis footprint (separate from event geography)</h4>
        <p className="small">{c.geometry_origin}</p>
        {c.event_point && <p className="small muted">Event marker: {c.event_point.label}</p>}
        <h4>Questions to investigate</h4>
        <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{c.questions.map(q => <li key={q}>{q}</li>)}</ul>
      </div>
      <div className="sheet">
        <h4>Event facts <StatusBadge status="source_reported" /></h4>
        {c.event_facts.map((f, i) => (
          <p key={i} className="small">{f.claim} <a href={src(f.source_id)?.url} target="_blank" rel="noreferrer">{src(f.source_id)?.publisher}{f.locator ? `, ${f.locator}` : ''}</a>
            {f.excerpt && <span className="muted"> — “{f.excerpt}”</span>}</p>
        ))}
      </div>
      <div className="sheet">
        <h4>Documented responses</h4>
        {c.interventions.map(iv => (
          <div key={iv.id} style={{ borderTop: '1px solid var(--paper-line)', padding: '8px 0' }}>
            <div className="row wrap"><b>{iv.title}</b></div>
            <div className="row wrap" style={{ margin: '4px 0' }}><ImplBadge status={iv.status} /><OutcomeBadge type={iv.outcome_type} /></div>
            <p className="small">{iv.objective}</p>
            <button className="btn sm" onClick={() => onNode(iv.id)}>Open evidence sheet</button>
          </div>
        ))}
      </div>
      <div className="sheet">
        <h4>Sources</h4>
        {c.sources.map(s => (
          <p key={s.id} className="small">
            <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a><br />
            <span className="muted">{s.publisher} · {s.published || 'n.d.'} · retrieved {s.retrieved} · {s.status === 'verified' ? 'verified' : 'unavailable'}</span>
          </p>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ analysis */
export function AnalysisPanel(p: {
  inv: Investigation; results: Results | null; busy: boolean; onAcquire: (force?: boolean) => void
  onSelectVar: (v: string) => void; selectedVar: string | null; onNode: (id: string) => void; acqEvents: any[]
}) {
  const b = p.results?.batch
  const [openMethod, setOpenMethod] = useState(false)
  if (!b) {
    return (
      <div className="empty">
        <h3>No environmental data yet</h3>
        <p>Acquire NASA POWER monthly {p.inv.config.variables.join(', ')} for {p.inv.config.place.name}, {p.inv.config.period.start} to {p.inv.config.period.end}, then run the trend family.</p>
        <p className="small muted">Regional, MERRA-2-derived meteorology. Identical requests reuse cached artifacts.</p>
        <button className="btn primary" onClick={() => p.onAcquire(false)} disabled={p.busy}>{p.busy ? <><span className="spinner" />Acquiring…</> : 'Acquire NASA data'}</button>
        {p.acqEvents.length > 0 && <AcqLog events={p.acqEvents} />}
      </div>
    )
  }
  const arts = Object.fromEntries((p.results?.artifacts || []).map(a => [a.id, a])) as Record<string, Artifact>
  const r0 = b.results[0]
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <span className="small muted">Analysis <code>{b.id}</code> · {b.results.length}-variable family · BH-adjusted</span>
        <button className="btn sm" onClick={() => p.onAcquire(true)} disabled={p.busy} title="Re-request from NASA POWER. Creates a new artifact version; old evidence is kept.">Force refresh</button>
      </div>
      {p.acqEvents.length > 0 && <AcqLog events={p.acqEvents} />}
      {b.results.map((r, i) => <TrendCard key={r.variable} r={r} fid={b.finding_ids.find(f => f.endsWith('-' + r.variable)) || b.finding_ids[i]} art={arts[r.artifact_id]}
        selected={p.selectedVar === r.variable} onSelect={() => p.onSelectVar(r.variable)} onNode={p.onNode} />)}
      {p.results?.association && <AssocCard a={p.results.association} />}
      <div className="sheet">
        <button className="btn sm" onClick={() => setOpenMethod(!openMethod)} aria-expanded={openMethod}>{openMethod ? 'Hide' : 'Show'} method & spatial support</button>
        {openMethod && (
          <div className="small" style={{ marginTop: 8 }}>
            <p><b>Model:</b> {r0.method.model}</p>
            <p><b>Uncertainty:</b> {r0.method.uncertainty}</p>
            <p><b>Rule:</b> {r0.method.rule}</p>
            <ul style={{ paddingLeft: 18 }}>{r0.method.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
            <p><b>Spatial support:</b> {humanize(r0.spatial_support.kind)} — {r0.spatial_support.cell_count} cell(s) of {r0.spatial_support.cell_size_deg.lat}° × {r0.spatial_support.cell_size_deg.lon}°; {r0.spatial_support.weighting}.</p>
            <p><b>Effective footprint:</b> <span className="num">W {r0.spatial_support.footprint.west} · S {r0.spatial_support.footprint.south} · E {r0.spatial_support.footprint.east} · N {r0.spatial_support.footprint.north}</span></p>
            <p><b>Anomaly baseline:</b> {r0.baseline.start} to {r0.baseline.end} ({r0.baseline.definition}).</p>
          </div>
        )}
      </div>
    </div>
  )
}

function AcqLog({ events }: { events: any[] }) {
  return (
    <div className="events on-dark" aria-label="Acquisition log">
      {events.map((e, i) => (
        <div key={i} className="ev" style={{ cursor: 'default' }}>
          <span className={`dot ${e.type.includes('fetched') || e.type.includes('created') || e.type.includes('graph') ? 'ok' : e.type.includes('cached') || e.type.includes('reused') ? 'ok' : e.type.includes('snapshot') ? 'warn' : ''}`} />
          <span>{e.label}{e.payload?.warning && <span style={{ color: 'var(--amber)' }}> — {e.payload.warning}</span>}</span>
          <span className="d">{e.duration_ms != null ? `${e.duration_ms} ms` : ''}</span>
        </div>
      ))}
    </div>
  )
}

function TrendCard({ r, fid, art, selected, onSelect, onNode }: { r: TrendResult; fid: string; art?: Artifact; selected: boolean; onSelect: () => void; onNode: (id: string) => void }) {
  const sig = r.significant_at_0_05
  return (
    <div className={`sheet ${selected ? 'selected' : ''}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3>{r.longname} <code>{r.variable}</code></h3>
        <StatusBadge status="computed" />
      </div>
      {r.mode === 'inferential' ? (
        <>
          <div className="row" style={{ alignItems: 'baseline', gap: 6 }}>
            <span className="stat-big">{fmt(r.slope_per_decade)}</span><span className="muted">{r.units} per decade</span>
          </div>
          <p className="small num">95% CI [{fmt(r.ci95_per_decade![0])}, {fmt(r.ci95_per_decade![1])}] · p = {fmtP(r.p_value)} · BH q = {fmtP(r.q_value ?? null)}</p>
          <p className="small">{r.statement}</p>
          <p className="small muted num">HAC 24-lag sensitivity: CI [{fmt(r.sensitivity.ci95_per_decade[0])}, {fmt(r.sensitivity.ci95_per_decade[1])}], p = {fmtP(r.sensitivity.p_value)}</p>
          {!sig && <p className="small muted">Not significant at 0.05 under this method — shown, not hidden.</p>}
        </>
      ) : (
        <>
          <p className="small" style={{ color: 'var(--amber-ink)' }}><b>Descriptive only.</b> {r.limitation}</p>
          {r.suggested_interval && <p className="small">Longest qualifying contiguous interval: {r.suggested_interval.start} – {r.suggested_interval.end} ({r.suggested_interval.months} months).</p>}
        </>
      )}
      <dl className="kv" style={{ marginTop: 6 }}>
        <dt>Period</dt><dd>{r.period.start} – {r.period.end} · {r.n_valid}/{r.n_months_requested} months ({Math.round(r.coverage * 100)}%)</dd>
        <dt>Support</dt><dd>{humanize(r.spatial_support.kind)} ({r.spatial_support.cell_count} cells)</dd>
        <dt>Artifact</dt><dd><code>{r.artifact_id}</code>{art && <> · {art.origin === 'snapshot' ? 'saved source snapshot' : art.origin} {art.retrieved_at.slice(0, 10)}</>}</dd>
        <dt>SHA-256</dt><dd><code>{r.artifact_sha256.slice(0, 20)}…</code></dd>
        {r.conversions.length > 0 && <><dt>Units</dt><dd>{r.conversions[0]}</dd></>}
      </dl>
      <div className="row wrap" style={{ marginTop: 8 }}>
        <button className="btn sm" onClick={onSelect} aria-pressed={selected}>Show in timeline</button>
        <button className="btn sm" onClick={() => onNode(fid)}>Trace provenance</button>
        {art && <a className="btn sm" href={art.manifest.source_url} target="_blank" rel="noreferrer">Source request</a>}
      </div>
    </div>
  )
}

function AssocCard({ a }: { a: any }) {
  return (
    <div className="sheet">
      <div className="row" style={{ justifyContent: 'space-between' }}><h3>Association {a.x} ~ {a.y}</h3><span className="badge b-hyp">Descriptive</span></div>
      <dl className="kv">
        <dt>Raw Pearson r</dt><dd>{a.raw_pearson_r?.toFixed(3)}</dd>
        <dt>Residual r</dt><dd>{a.residual_pearson_r?.toFixed(3)} <span className="muted">(after each variable's trend + seasonal cycle)</span></dd>
        <dt>Lagged residual r</dt><dd>{a.lagged_residual_r.map((l: any) => `${l.lag_months} mo: ${l.residual_r?.toFixed(2)}`).join(' · ')}</dd>
        <dt>Overlap</dt><dd>{a.overlap_months} months, {a.missing_months} missing</dd>
      </dl>
      <ul className="small muted" style={{ paddingLeft: 18, marginBottom: 0 }}>{a.method.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
    </div>
  )
}

/* ------------------------------------------------------------ leads */
export function LeadsPanel(p: { inv: Investigation; meta: Meta; match: MatchRun | null; busy: boolean; onRun: () => void; onTrace: (id: string) => void; onNode: (id: string) => void; onRevise: (body: any) => Promise<void>; hasResults: boolean }) {
  const [mech, setMech] = useState(p.inv.state.mechanism || '')
  const [scale, setScale] = useState(p.inv.state.scale || '')
  useEffect(() => { setMech(p.inv.state.mechanism || ''); setScale(p.inv.state.scale || '') }, [p.inv.state.mechanism, p.inv.state.scale])
  const m = p.match
  return (
    <div>
      <div className="sheet">
        <h4 style={{ marginTop: 0 }}>Target context <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}>(changes create revisions)</span></h4>
        <div className="grid2">
          <label className="field"><span>Hazard mechanism</span>
            <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={mech} onChange={e => setMech(e.target.value)}>
              <option value="">Not established</option>
              {Object.entries(p.meta.mechanisms).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select></label>
          <label className="field"><span>Spatial scale</span>
            <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={scale} onChange={e => setScale(e.target.value)}>
              <option value="">Not established</option>
              {['neighbourhood', 'city', 'catchment', 'regional'].map(s => <option key={s} value={s}>{s}</option>)}
            </select></label>
        </div>
        {(mech !== (p.inv.state.mechanism || '') || scale !== (p.inv.state.scale || '')) && (
          <button className="btn sm primary" onClick={async () => {
            const why = window.prompt('Rationale for this context change (stored with the revision):')
            if (!why) return
            if (mech !== (p.inv.state.mechanism || '')) await p.onRevise({ kind: 'set_mechanism', mechanism: mech || null, rationale: why })
            if (scale !== (p.inv.state.scale || '')) await p.onRevise({ kind: 'set_scale', scale: scale || null, rationale: why })
          }}>Save context revision</button>
        )}
      </div>
      <div className="row" style={{ justifyContent: 'space-between', margin: '4px 0 8px' }}>
        <span className="small muted">{m ? <>Match <code>{m.id}</code> · rules {m.rule_version} · {m.reused ? 'reused' : 'new'}</> : 'Not yet evaluated'}</span>
        <button className="btn sm primary" onClick={p.onRun} disabled={p.busy}>{p.busy ? 'Evaluating…' : m ? 'Re-evaluate' : 'Find precedents'}</button>
      </div>
      {!p.hasResults && <p className="small muted">Tip: acquire NASA data first so environmental context features can be assessed (otherwise they stay unknown).</p>}
      {m && m.insufficient_context && <div className="empty" style={{ marginBottom: 10 }}><h3>Context insufficient</h3><p>The target's hazard mechanism is not established, so no precedent can be judged transferable. Establish it above; every candidate stays “needs local evidence” until then.</p></div>}
      {m && m.leads.map((e, i) => <LeadCard key={e.intervention_id} e={e} rank={i + 1} onTrace={p.onTrace} onNode={p.onNode} />)}
      {m && m.leads.length === 0 && <div className="empty"><h3>No eligible precedent</h3><p>No documented response passed the contextual rules. See exclusions below for what does not transfer.</p></div>}
      {m && m.other_candidates.length > 0 && (
        <>
          <div className="h-sec">Also considered ({m.other_candidates.length})</div>
          {m.other_candidates.map(e => (
            <div key={e.intervention_id} className="sheet" style={{ padding: '8px 12px' }}>
              <span className={`lead-tag ${e.eligibility}`}>{humanize(e.eligibility)}</span> <b>{e.title}</b> <span className="muted small">— {e.source_place}</span>
              {e.mismatches.slice(0, 1).map(f => <p key={f.feature} className="small" style={{ margin: '4px 0' }}><span className="st mismatch">✕ {f.state}</span> {f.detail}</p>)}
              <button className="btn sm" onClick={() => p.onTrace(e.intervention_id)}>Trace evidence</button>
            </div>
          ))}
        </>
      )}
      {m && m.excluded.length > 0 && (
        <>
          <div className="h-sec">Excluded — negative evidence ({m.excluded.length})</div>
          {m.excluded.map(e => (
            <div key={e.intervention_id} className="sheet" style={{ opacity: .9 }}>
              <span className="lead-tag excluded">Excluded</span> <b>{e.title}</b> <span className="muted small">— {e.source_place}</span>
              <ul className="small" style={{ paddingLeft: 18, margin: '4px 0' }}>{e.exclusion_reasons.map(r => <li key={r}>{r}</li>)}</ul>
              <button className="btn sm" onClick={() => p.onTrace(e.intervention_id)}>Trace evidence</button>
            </div>
          ))}
        </>
      )}
      {m && (
        <details className="small muted" style={{ marginTop: 8 }}>
          <summary>Graph query behind these leads</summary>
          <p>{m.query.description}</p>
          <p>{m.query.interventions_considered} interventions considered · edges: {m.query.edge_types.join(', ')} · solutions graph {m.graph_version}</p>
        </details>
      )}
    </div>
  )
}

function LeadCard({ e, rank, onTrace, onNode }: { e: Evaluation; rank: number; onTrace: (id: string) => void; onNode: (id: string) => void }) {
  const label: Record<string, string> = { candidate_lead: 'Candidate lead', partial_component_only: 'Partial — component only', needs_local_evidence: 'Needs local evidence' }
  return (
    <div className="sheet">
      <div className="row" style={{ justifyContent: 'space-between' }}><span className={`lead-tag ${e.eligibility}`}>{rank}. {label[e.eligibility] || e.eligibility}</span><span className="badge b-hyp">Hypothesis link</span></div>
      <h3 style={{ marginTop: 4 }}>{e.title}</h3>
      <p className="small muted">From {e.source_place} · {humanize(e.category)} · {e.scale} scale</p>
      <div className="row wrap" style={{ margin: '4px 0 8px' }}><ImplBadge status={e.implementation_status} /><OutcomeBadge type={e.outcome_evidence_type} /></div>
      <div className="grid2 small" style={{ marginBottom: 6 }}>
        <div title={e.score_note}>Match (ordinal) <b className="num">{e.match_score.toFixed(2)}</b><div className="meter"><i style={{ width: `${e.match_score * 100}%` }} /></div></div>
        <div title="Share of feature weight whose state is known">Coverage <b className="num">{e.coverage.toFixed(2)}</b><div className="meter cov"><i style={{ width: `${e.coverage * 100}%` }} /></div></div>
      </div>
      {e.features.map(f => (
        <div className="feat" key={f.feature}><span className={`st ${f.state}`}>{f.state === 'compatible' ? '✓ ' : f.state === 'unknown' ? '? ' : '✕ '}{f.state}</span><span>{f.detail}</span></div>
      ))}
      {e.conflicts.length > 0 && <><h4>Documented limitations</h4>{e.conflicts.map(c => <p key={c.id} className="small"><span className="badge b-conflict">Limitation</span> {c.label}</p>)}</>}
      {e.next_evidence.length > 0 && <><h4>Next evidence needed</h4><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{e.next_evidence.map(n => <li key={n}>{n}</li>)}</ul></>}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn sm primary" onClick={() => onTrace(e.intervention_id)}>Trace evidence</button>
        <button className="btn sm" onClick={() => onNode(e.intervention_id)}>Response sheet</button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ evidence sheet (any node) */
export function EvidencePanel({ nodeId, onNode, onDispute, disputed, onFocusFinding }: { nodeId: string | null; onNode: (id: string) => void; onDispute: (id: string, on: boolean) => void; disputed: string[]; onFocusFinding: (n: GNode) => void }) {
  const [n, setN] = useState<GNode | null>(null)
  const [prov, setProv] = useState<{ nodes: GNode[]; edges: any[] } | null>(null)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    if (!nodeId) return
    setErr(null); setBundle(null)
    api.get<GNode>(`/api/graph/node/${encodeURIComponent(nodeId)}`).then(x => { setN(x); if (x.type === 'Finding' && x.props.kind?.startsWith('trend')) onFocusFinding(x) }).catch(e => setErr(e.message))
    api.get<any>(`/api/graph/provenance/${encodeURIComponent(nodeId)}`).then(setProv).catch(() => setProv(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId])
  if (!nodeId) return <div className="empty"><h3>Evidence sheet</h3><p>Select a finding, response, citation or graph node to inspect its provenance.</p></div>
  if (err) return <div className="empty"><h3>Not available</h3><p>{err}</p></div>
  if (!n) return <div className="row"><span className="spinner" /> Loading…</div>
  const p = n.props
  const isDisputed = disputed.includes(n.id)
  return (
    <div>
      <div className="sheet">
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted small">{n.type} · <code>{n.id}</code></span><StatusBadge status={isDisputed ? 'disputed' : n.status} /></div>
        <h3 style={{ marginTop: 4 }}>{n.label}</h3>
        {n.type === 'Intervention' && <InterventionSheet p={p} />}
        {n.type === 'Finding' && p.kind?.startsWith('trend') && (
          <dl className="kv">
            <dt>Variable</dt><dd>{p.variable} ({p.units})</dd>
            <dt>Period</dt><dd>{p.period.start} – {p.period.end}</dd>
            {p.slope_per_decade !== undefined && <><dt>Slope/decade</dt><dd>{fmt(p.slope_per_decade)} [{fmt(p.ci95_per_decade[0])}, {fmt(p.ci95_per_decade[1])}]</dd><dt>p / BH q</dt><dd>{fmtP(p.p_value)} / {fmtP(p.q_value)}</dd></>}
            <dt>Method</dt><dd>{p.method_version}</dd>
          </dl>
        )}
        {n.type === 'Source' && <><p className="small"><a href={p.url} target="_blank" rel="noreferrer">Open original source ↗</a></p><dl className="kv"><dt>Publisher</dt><dd>{p.publisher}</dd><dt>Published</dt><dd>{p.published || 'n.d.'}</dd><dt>Retrieved</dt><dd>{p.retrieved}</dd><dt>Locator</dt><dd>{p.locator}</dd><dt>Status</dt><dd>{p.status}</dd></dl></>}
        {n.type === 'Artifact' && <dl className="kv"><dt>SHA-256</dt><dd><code>{p.sha256}</code></dd><dt>Retrieved</dt><dd>{p.retrieved_at} ({p.origin})</dd><dt>Units</dt><dd>{p.units}</dd><dt>Support</dt><dd>{humanize(p.spatial_support?.kind)}</dd><dt>Request</dt><dd><a href={p.source_url} target="_blank" rel="noreferrer">NASA POWER URL ↗</a></dd></dl>}
        {n.type === 'Analysis' && <dl className="kv"><dt>Mode</dt><dd>{p.mode}</dd><dt>Units</dt><dd>{p.units}</dd><dt>Period</dt><dd>{p.period.start} – {p.period.end}</dd><dt>Coverage</dt><dd>{Math.round(p.coverage * 100)}%</dd><dt>Method</dt><dd>{p.method.version}: {p.method.model}</dd><dt>Uncertainty</dt><dd>{p.method.uncertainty}</dd><dt>Artifact hash</dt><dd><code>{p.artifact_sha256?.slice(0, 20)}…</code></dd></dl>}
        {n.type === 'Outcome' && <p className="small"><OutcomeBadge type={p.outcome_type} /> Reported for {p.case_id}; never transferred as a forecast.</p>}
        {(n.type === 'Requirement' || n.type === 'Mechanism') && <p className="small">{p.definition}</p>}
        {n.type === 'Assumption' && <p className="small">{p.basis === 'analyst_assumption' ? 'Planning assumption entered by the analyst — not a sourced fact.' : `Linked source ${p.source_id} ${p.locator || ''}`}<br />Rationale: {p.note}</p>}
        {p.locator && n.type !== 'Source' && <p className="small muted">Locator: {p.locator}</p>}
        {p.excerpt && <p className="small muted">“{p.excerpt}”</p>}
        <p className="small muted num">Ingested {n.ingested_at}{n.event_time ? ` · event time ${n.event_time}` : ''}{n.published_time ? ` · published ${n.published_time}` : ''}</p>
        {(n.type === 'Finding' || n.type === 'Outcome') && (
          <button className="btn sm" onClick={() => onDispute(n.id, !isDisputed)}>{isDisputed ? 'Remove dispute' : 'Mark claim disputed'}</button>
        )}
      </div>
      {prov && prov.edges.length > 0 && (
        <div className="sheet">
          <h4 style={{ marginTop: 0 }}>Provenance path (persisted edges)</h4>
          {prov.edges.map(e => {
            const dst = prov.nodes.find(x => x.id === e.dst)
            return <p key={e.id} className="small"><code>{e.src.slice(0, 26)}</code> <b>{e.type}</b> → <button className="cite" onClick={() => onNode(e.dst)}>{dst?.type || ''}</button> {dst?.label.slice(0, 80)}</p>
          })}
        </div>
      )}
      {n.bundles && n.bundles.length > 0 && (
        <div className="sheet">
          <h4 style={{ marginTop: 0 }}>Relationship bundles (hyperedges)</h4>
          {n.bundles.map(b => <p key={b.id} className="small"><button className="cite" onClick={() => setBundle(b)}>{b.id.slice(0, 28)}</button> {humanize(b.assertion_type)} · <StatusBadge status={b.evidence_status} /></p>)}
          {bundle && (
            <div style={{ marginTop: 6, borderTop: '1px solid var(--paper-line)', paddingTop: 6 }}>
              <p className="small"><b>{bundle.label}</b></p>
              <table className="small" style={{ width: '100%' }}><thead><tr><th align="left">Role</th><th align="left">Member</th></tr></thead>
                <tbody>{bundle.members.map(m => <tr key={m.node_id + m.role}><td>{m.role}</td><td><button className="cite" onClick={() => onNode(m.node_id)}>{m.type}</button> {m.label?.slice(0, 60)}</td></tr>)}</tbody></table>
              <p className="small muted">{bundle.props.note || 'Co-membership records multi-factor context; it does not create pairwise causal edges.'}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function InterventionSheet({ p }: { p: any }) {
  return (
    <>
      <div className="row wrap" style={{ margin: '4px 0 6px' }}><ImplBadge status={p.status} /><OutcomeBadge type={p.outcome_type} /></div>
      <p className="small muted">{p.place_label} · {humanize(p.category)} · {p.scale} scale{p.time_horizon ? ` · ${p.time_horizon}` : ''}</p>
      <h4>What was done or recommended</h4><p className="small">{p.objective}</p>
      <h4>What the source reports</h4><p className="small">{p.reported_outcome || 'No outcome reported by the source.'} {p.outcome_type && p.outcome_type !== 'none' && <span className="muted">({p.outcome_type}; stays attached to {p.place_label})</span>}</p>
      <h4>Conditions it depends on</h4>
      <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{(p.requirements || []).map((r: any) => <li key={r.id}>{r.why || r.id}{r.decisive ? ' (decisive)' : ''}</li>)}</ul>
      {p.constraints?.length > 0 && <><h4>Documented constraints</h4><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{p.constraints.map((c: string) => <li key={c}>{c}</li>)}</ul></>}
      <h4>What we do not know</h4>
      <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
        {(p.limitations || []).map((l: string) => <li key={l}>{l}</li>)}
        {p.outcome_type !== 'observed' && <li>Observed effectiveness is not documented in this source.</li>}
        <li>Cost and effect size at the target place are unknown; source outcomes are not forecasts.</li>
      </ul>
      <p className="small muted" style={{ marginTop: 6 }}>Source <code>{p.source_id}</code>{p.locator ? ` · ${p.locator}` : ''}{p.published ? ` · published ${p.published}` : ''}</p>
    </>
  )
}

/* ------------------------------------------------------------ evidence changes / revisions */
export function ChangesPanel(p: { inv: Investigation; meta: Meta; onRevise: (b: any) => Promise<void>; onActivate: (rid: string) => void; match: MatchRun | null; onNode: (id: string) => void }) {
  const [req, setReq] = useState('')
  const [state, setState] = useState('satisfied')
  const [basis, setBasis] = useState<'analyst_assumption' | 'source_reported'>('analyst_assumption')
  const [why, setWhy] = useState('')
  const [srcId, setSrcId] = useState('')
  const [loc, setLoc] = useState('')
  const [sources, setSources] = useState<GNode[]>([])
  const [diff, setDiff] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [from, setFrom] = useState('')
  useEffect(() => { api.get<GNode[]>('/api/graph/sources').then(setSources).catch(() => {}) }, [])
  const relevant = new Set<string>()
  p.match?.leads.concat(p.match.other_candidates || []).forEach(e => e.features.forEach(f => f.feature.startsWith('requires:') && relevant.add(f.feature.slice(9))))
  const reqs = Object.entries(p.meta.requirements).sort(([a], [b]) => (relevant.has(b) ? 1 : 0) - (relevant.has(a) ? 1 : 0))
  const cur = p.inv.revisions.find(r => r.id === p.inv.current_revision_id)
  const prior = from || (cur?.prior_id ?? '')
  return (
    <div>
      <div className="sheet">
        <h4 style={{ marginTop: 0 }}>Record local evidence</h4>
        <p className="small muted">Prerequisites are never inferred from climate data. Assumptions stay labelled as assumptions.</p>
        <label className="field"><span>Prerequisite</span>
          <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={req} onChange={e => setReq(e.target.value)}>
            <option value="">Choose…</option>
            {reqs.map(([k, v]) => <option key={k} value={k}>{relevant.has(k) ? '★ ' : ''}{v.label}{p.inv.state.requirements[k] ? ` — currently ${p.inv.state.requirements[k].state}` : ''}</option>)}
          </select></label>
        <div className="grid2">
          <label className="field"><span>State</span>
            <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={state} onChange={e => setState(e.target.value)}>
              <option value="satisfied">Satisfied</option><option value="unsatisfied">Not satisfied</option><option value="unknown">Unknown (clear)</option>
            </select></label>
          <label className="field"><span>Basis</span>
            <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={basis} onChange={e => setBasis(e.target.value as any)}>
              <option value="analyst_assumption">Planning assumption</option><option value="source_reported">Linked source</option>
            </select></label>
        </div>
        {basis === 'source_reported' && (
          <div className="grid2">
            <label className="field"><span>Ingested source</span>
              <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={srcId} onChange={e => setSrcId(e.target.value)}>
                <option value="">Choose…</option>{sources.map(s => <option key={s.id} value={s.id}>{s.label.slice(0, 60)}</option>)}
              </select></label>
            <label className="field"><span>Page / section</span><input className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={loc} onChange={e => setLoc(e.target.value)} /></label>
          </div>
        )}
        <label className="field"><span>Rationale (required)</span><textarea className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={why} onChange={e => setWhy(e.target.value)} placeholder="e.g. Scenario: assume municipal parks can be regraded for retention" /></label>
        <button className="btn primary sm" disabled={!req || !why.trim() || busy || (basis === 'source_reported' && !srcId)} onClick={async () => {
          setBusy(true)
          try { await p.onRevise({ kind: 'set_requirement', requirement_id: req, state, basis, rationale: why, source_id: srcId || undefined, locator: loc || undefined }); setWhy('') } finally { setBusy(false) }
        }}>{basis === 'analyst_assumption' ? 'Add planning assumption' : 'Link source'}</button>
      </div>

      <div className="h-sec">Revisions ({p.inv.revisions.length})</div>
      {[...p.inv.revisions].reverse().map(r => (
        <div key={r.id} className="sheet" style={{ padding: '8px 12px' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span className="small"><b>R{r.seq}</b> · {humanize(r.kind)} {r.id === p.inv.current_revision_id && <span className="badge b-computed">Active</span>}</span>
            <span className="row">
              {r.id !== p.inv.current_revision_id && <button className="btn sm" onClick={() => p.onActivate(r.id)}>Activate</button>}
            </span>
          </div>
          <p className="small" style={{ margin: '2px 0' }}>{r.rationale}</p>
          <p className="small muted num">{r.created_at}</p>
        </div>
      ))}
      <div className="sheet">
        <h4 style={{ marginTop: 0 }}>What changed?</h4>
        <div className="row">
          <select className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} value={prior} onChange={e => setFrom(e.target.value)}>
            {p.inv.revisions.filter(r => r.id !== p.inv.current_revision_id).map(r => <option key={r.id} value={r.id}>R{r.seq} {humanize(r.kind)}</option>)}
          </select>
          <span className="small">→ active</span>
          <button className="btn sm primary" disabled={!prior} onClick={async () => setDiff(await api.get(`/api/investigations/${p.inv.id}/what-changed?frm=${prior}&to=${p.inv.current_revision_id}`))}>Compare</button>
        </div>
        {diff && <WhatChanged d={diff} onNode={p.onNode} />}
      </div>
    </div>
  )
}

function WhatChanged({ d, onNode }: { d: any; onNode: (id: string) => void }) {
  const changed = d.candidates.filter((c: any) => c.changed)
  return (
    <div className="small" style={{ marginTop: 8 }}>
      <p><b>Responsible:</b> {d.responsible_revisions.map((r: any) => `R${r.seq} ${humanize(r.kind)} — “${r.rationale}”`).join('; ') || '—'}</p>
      <p><b>Top lead:</b> {d.top_lead.changed ? `changed (${d.top_lead.from} → ${d.top_lead.to})` : 'unchanged'}</p>
      {d.unchanged_note && <p className="muted">{d.unchanged_note}</p>}
      <p className="muted">{d.artifacts_reused} Match runs: {d.from.match_run} ({d.from.reused ? 'reused' : 'computed'}) → {d.to.match_run} ({d.to.reused ? 'reused' : 'computed'}).</p>
      {changed.length === 0 && <p>No candidate's eligibility or features changed.</p>}
      {changed.map((c: any) => (
        <div key={c.intervention_id} style={{ borderTop: '1px solid var(--paper-line)', padding: '6px 0' }}>
          <button className="cite" onClick={() => onNode(c.intervention_id)}>{c.intervention_id}</button> <b>{c.title}</b> ({c.source_place})
          <p>Eligibility: {humanize(c.eligibility.from)} → <b>{humanize(c.eligibility.to)}</b> · match {c.match_score.from?.toFixed(2)} → {c.match_score.to?.toFixed(2)} · coverage {c.coverage.from?.toFixed(2)} → {c.coverage.to?.toFixed(2)}</p>
          {c.changed_features.map((f: any) => <p key={f.feature} className="muted">{f.feature}: {f.from} → <span className={`st ${f.to}`}>{f.to}</span></p>)}
        </div>
      ))}
    </div>
  )
}
