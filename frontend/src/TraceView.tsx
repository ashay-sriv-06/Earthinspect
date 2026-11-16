import { useEffect, useMemo, useState } from 'react'
import { ReactFlow, Background, Controls, MarkerType, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { GEdge, GNode } from './api'
import { api, humanize } from './api'
import { StatusBadge } from './panels'

interface Trace { intervention_id: string; investigation_id: string; evaluation: any; match_run_id: string; graph_version: string; nodes: GNode[]; edges: GEdge[]; bundles: any[] }

const LAYER_TITLES = ['Sources & datasets', 'Artifacts & events', 'Analyses', 'Findings & assumptions', 'Mechanism & requirements', 'Response', 'Target investigation']

export default function TraceView({ invId, interventionId, onClose, onNode, onFocusFinding, changed = [], initialSel, onSelectClaim }: { invId: string; interventionId: string; onClose: () => void; onNode: (id: string) => void; onFocusFinding: (n: GNode) => void; changed?: string[]; initialSel?: string | null; onSelectClaim?: (id: string) => void }) {
  const [t, setT] = useState<Trace | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [pulse, setPulse] = useState(true)
  const [view, setView] = useState<'graph' | 'table'>('graph')
  useEffect(() => {
    setT(null); setErr(null)
    api.get<Trace>(`/api/investigations/${invId}/trace/${encodeURIComponent(interventionId)}`).then(x => { setT(x); setSel(initialSel && x.nodes.some(n => n.id === initialSel) ? initialSel : interventionId); setPulse(true); setTimeout(() => setPulse(false), 400) }).catch(e => setErr(e.message))
  }, [invId, interventionId])
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [onClose])

  const { nodes, edges } = useMemo(() => {
    if (!t) return { nodes: [] as Node[], edges: [] as Edge[] }
    const byLayer: Record<number, GNode[]> = {}
    t.nodes.forEach(n => { (byLayer[n.layer ?? 3] ||= []).push(n) })
    const nodes: Node[] = []
    // Deterministic top-to-bottom layered layout: one row per evidence layer (stable positions; no force layout).
    const maxN = Math.max(...Object.values(byLayer).map(ns => ns.length))
    const COLW = 205, ROWH = 104
    const rowOrder = Object.keys(byLayer).map(Number).sort((a, b) => a - b)
    rowOrder.forEach((l, r) => nodes.push({
      id: `hdr-${l}`, position: { x: -(maxN * COLW) / 2 - 150, y: r * ROWH + 18 }, draggable: false, selectable: false, focusable: false,
      data: { label: <div style={{ color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.07em', fontSize: 10, textAlign: 'right' }}>{LAYER_TITLES[l]}</div> },
      style: { padding: 0, border: 0, background: 'transparent', width: 130, pointerEvents: 'none' },
    }))
    rowOrder.forEach((l, r) => byLayer[l].forEach((n, i) => {
      const ns = byLayer[l]
      const a = n.assessment?.state
      nodes.push({
        id: n.id, position: { x: i * COLW - ((ns.length - 1) * COLW) / 2 - 95, y: r * ROWH }, draggable: false,
        data: { label: <div className={`tn ${n.type} s-${n.status} ${a ? 'a-' + a : ''} ${sel === n.id ? 'sel' : ''} ${changed.includes(n.id) ? 'chg' : ''}`}><div className="ty"><span>{changed.includes(n.id) ? '● changed · ' : ''}{n.type}</span><span>{a ? (a === 'compatible' ? '✓' : a === 'unknown' ? '?' : '✕') + ' ' + a : n.status === 'hypothesis' ? 'hyp' : ''}</span></div><div className="lb">{n.label}</div></div> },
        style: { padding: 0, border: 0, background: 'transparent', width: 190 },
        sourcePosition: 'bottom' as any, targetPosition: 'top' as any,
      })
    }))
    const edges: Edge[] = t.edges.map(e => {
      const hyp = e.status === 'hypothesis' || e.status === 'analyst_assumption'
      const conflict = e.type === 'CONTRADICTS'
      const color = conflict ? '#d57a6c' : hyp ? '#d5a555' : e.status === 'computed' ? '#58c7b1' : '#8db7de'
      const srcL = t.nodes.find(n => n.id === e.src)?.layer ?? 0, dstL = t.nodes.find(n => n.id === e.dst)?.layer ?? 0
      const [s, d] = srcL <= dstL ? [e.src, e.dst] : [e.dst, e.src]
      return {
        id: e.id, source: s, target: d, label: e.type, className: pulse ? 'pulse' : '',
        style: { stroke: color, strokeWidth: 1.5, strokeDasharray: hyp ? '6 4' : undefined },
        labelStyle: { fill: '#a9b5be', fontSize: 9 }, labelBgStyle: { fill: '#111820' },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
      }
    })
    return { nodes, edges }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, sel, pulse, changed.join('|')])

  const selNode = t?.nodes.find(n => n.id === sel)
  const pick = (id: string) => {
    setSel(id); onSelectClaim?.(id)
    const n = t?.nodes.find(x => x.id === id)
    if (n?.type === 'Finding' && n.props.kind?.startsWith('trend')) onFocusFinding(n)
  }

  return (
    <div className="overlay" role="dialog" aria-label="Evidence trace">
      <div className="overlay-h">
        <h2>Trace evidence</h2>
        {t && <span className="small muted">{t.evaluation.title} · {t.evaluation.source_place} · {humanize(t.evaluation.eligibility)} · match run <code>{t.match_run_id}</code> · graph {t.graph_version}</span>}
        <span className="spacer" />
        <div className="seg" role="group" aria-label="View"><button aria-pressed={view === 'graph'} onClick={() => setView('graph')}>Graph</button><button aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button></div>
        <button className="btn sm" onClick={onClose}>Close <span className="kbd">Esc</span></button>
      </div>
      {err && <div className="empty" style={{ margin: 16 }}><h3>Trace unavailable</h3><p>{err}</p></div>}
      {!t && !err && <div className="row" style={{ padding: 16 }}><span className="spinner" /> Building trace from persisted graph…</div>}
      {t && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 340px', minHeight: 0 }}>
          <div style={{ position: 'relative', minHeight: 0 }}>
            {view === 'graph' ? (
              <>
                <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.3} nodesDraggable={false} nodesConnectable={false}
                  onNodeClick={(_, n) => !n.id.startsWith('hdr-') && pick(n.id)} fitViewOptions={{ padding: 0.08 }} proOptions={{ hideAttribution: true }} colorMode="dark">
                  <Background color="#26333d" gap={24} />
                  <Controls showInteractive={false} />
                </ReactFlow>
                <div className="map-legend" style={{ bottom: 10, left: 'auto', right: 10 }}>
                  <div className="li"><span style={{ width: 18, borderTop: '2px solid #58c7b1' }} />computed (NASA data)</div>
                  <div className="li"><span style={{ width: 18, borderTop: '2px solid #8db7de' }} />source-documented</div>
                  <div className="li"><span style={{ width: 18, borderTop: '2px dashed #d5a555' }} />hypothesis / assumption</div>
                  <div className="li"><span style={{ width: 18, borderTop: '2px solid #d57a6c' }} />conflict / limitation</div>
                </div>
              </>
            ) : (
              <div style={{ overflow: 'auto', height: '100%' }}>
                <table className="tbl"><thead><tr><th>Type</th><th>Node</th><th>Status</th><th>Assessment</th></tr></thead>
                  <tbody>{t.nodes.map(n => <tr key={n.id} className={sel === n.id ? 'sel' : ''} onClick={() => pick(n.id)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && pick(n.id)}><td>{n.type}</td><td>{n.label.slice(0, 110)}</td><td className="on-dark"><StatusBadge status={n.status} /></td><td>{n.assessment ? `${n.assessment.state}: ${n.assessment.detail.slice(0, 80)}` : ''}</td></tr>)}</tbody></table>
                <table className="tbl" style={{ marginTop: 12 }}><thead><tr><th>From</th><th>Relation</th><th>To</th><th>Status</th></tr></thead>
                  <tbody>{t.edges.map(e => <tr key={e.id}><td><code>{e.src.slice(0, 28)}</code></td><td>{e.type}</td><td><code>{e.dst.slice(0, 28)}</code></td><td>{e.status}</td></tr>)}</tbody></table>
              </div>
            )}
          </div>
          <aside style={{ borderLeft: '1px solid var(--line)', overflow: 'auto', padding: 12, background: 'var(--panel)' }} aria-label="Selected trace node">
            {selNode && (
              <div className="sheet">
                <div className="row" style={{ justifyContent: 'space-between' }}><span className="small muted">{selNode.type}</span><StatusBadge status={selNode.status} /></div>
                <h3 style={{ marginTop: 4 }}>{selNode.label}</h3>
                {selNode.assessment && <p className="small"><span className={`st ${selNode.assessment.state}`}>{selNode.assessment.state}</span> — {selNode.assessment.detail}</p>}
                {selNode.type === 'Source' && <p className="small"><a href={selNode.props.url} target="_blank" rel="noreferrer">Open source ↗</a> · {selNode.props.locator}</p>}
                {selNode.type === 'Analysis' && <p className="small">{selNode.props.method?.model}; {selNode.props.method?.uncertainty}. Units {selNode.props.units}; {selNode.props.period?.start}–{selNode.props.period?.end}; coverage {Math.round((selNode.props.coverage || 0) * 100)}%; artifact hash <code>{selNode.props.artifact_sha256?.slice(0, 16)}…</code></p>}
                {selNode.type === 'Artifact' && <p className="small">SHA-256 <code>{selNode.props.sha256?.slice(0, 24)}…</code> · retrieved {selNode.props.retrieved_at} · <a href={selNode.props.source_url} target="_blank" rel="noreferrer">request ↗</a></p>}
                {selNode.type === 'Intervention' && <p className="small">Original setting: {selNode.props.place_label} · {humanize(selNode.props.status)} · outcome evidence: {selNode.props.outcome_type}</p>}
                {selNode.type === 'Outcome' && <p className="small">{selNode.props.outcome_type} outcome reported for {selNode.props.case_id}; not a forecast for this place.</p>}
                <button className="btn sm" onClick={() => onNode(selNode.id)}>Open full evidence sheet</button>
              </div>
            )}
            <div className="h-sec">Why this lead</div>
            {t.evaluation.features.map((f: any) => <p key={f.feature} className="small" style={{ margin: '4px 0' }}><span className={`st ${f.state}`} style={{ color: f.state === 'compatible' ? 'var(--teal)' : f.state === 'unknown' ? 'var(--text-3)' : 'var(--red)' }}>{f.state}</span> {f.detail}</p>)}
            {t.bundles.length > 0 && <><div className="h-sec">Bundles</div>{t.bundles.map((b: any) => <p key={b.id} className="small">{b.label} — {b.members.map((m: any) => `${m.role}`).join(', ')}</p>)}</>}
          </aside>
        </div>
      )}
    </div>
  )
}
