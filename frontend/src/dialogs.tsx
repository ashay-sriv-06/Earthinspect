import { useEffect, useMemo, useRef, useState } from 'react'
import type { CaseFile, Geometry, Meta } from './api'
import { api, fmt, fmtP, humanize } from './api'

/* ------------------------------------------------------------ new place */
export function NewPlaceDialog({ meta, onClose, onCreate }: { meta: Meta; onClose: () => void; onCreate: (body: any) => Promise<void> }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<any[]>([])
  const [gErr, setGErr] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [lookup, setLookup] = useState<string | null>(null)
  const [mode, setMode] = useState<'bbox' | 'point'>('bbox')
  const [half, setHalf] = useState('1.0')
  const [mech, setMech] = useState('')
  const [scale, setScale] = useState('')
  const [question, setQuestion] = useState('What is changing here, which historical experiences are relevant, and what evidence would change that?')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const first = useRef<HTMLInputElement>(null)
  useEffect(() => { first.current?.focus(); const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [onClose])

  const geom: Geometry | null = useMemo(() => {
    const la = +lat, lo = +lon, h = +half
    if (!lat || !lon || isNaN(la) || isNaN(lo)) return null
    if (mode === 'point') return { type: 'point', lon: +lo.toFixed(4), lat: +la.toFixed(4) }
    return { type: 'bbox', west: +(lo - h).toFixed(4), south: +(la - h).toFixed(4), east: +(lo + h).toFixed(4), north: +(la + h).toFixed(4) }
  }, [lat, lon, half, mode])
  const problems: string[] = []
  if (geom) {
    if (geom.type === 'bbox') {
      if (geom.west < -180 || geom.east > 180) problems.push('Box crosses the antimeridian; not supported — move the centre or use a point.')
      if (geom.south < -90 || geom.north > 90) problems.push('Box extends past a pole.')
      if (+half * 2 < 2) problems.push('POWER regional requests need ≥2° per side; enlarge or choose nearest grid cell.')
      if (+half * 2 > 10) problems.push('Each side must be ≤10°.')
    } else if (Math.abs(geom.lat) > 90 || Math.abs(geom.lon) > 180) problems.push('Coordinates out of range.')
  }

  const search = async () => {
    setGErr(null); setHits([])
    try { const r = await api.get<any[]>(`/api/geocode?q=${encodeURIComponent(q)}`); setHits(r); if (!r.length) setGErr('No matches. Enter coordinates instead.') } catch (e: any) { setGErr(e.message) }
  }
  return (
    <div className="modal-bg" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="np-h">
        <div className="modal-h"><h2 id="np-h">Investigate another place</h2><button className="btn ghost sm" onClick={onClose}>Close</button></div>
        <div className="modal-b">
          <p className="small muted">Same acquisition, analysis, provenance and matching pipeline as the case files. No disaster narrative is invented: without an event record, this is a regional trend investigation.</p>
          <div className="row"><input ref={first} className="input" placeholder="Search a place (Open-Meteo geocoder)" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && q.length > 1 && search()} /><button className="btn" onClick={search} disabled={q.length < 2}>Search</button></div>
          {gErr && <p className="small" style={{ color: 'var(--amber)' }}>{gErr}</p>}
          {hits.length > 0 && <div style={{ margin: '6px 0' }}>{hits.map((h, i) => (
            <button key={i} className="palette-item" onClick={() => { setName(`${h.name}${h.country ? ', ' + h.country : ''}`); setLat(String(h.lat)); setLon(String(h.lon)); setLookup(`${h.source}: ${h.name}, ${h.admin1 || ''} ${h.country || ''} (${h.lat}, ${h.lon})`); setHits([]) }}>
              <span>{h.name}{h.admin1 ? `, ${h.admin1}` : ''}{h.country ? `, ${h.country}` : ''}</span><span className="why num">{(+h.lat).toFixed(3)}, {(+h.lon).toFixed(3)}</span>
            </button>))}</div>}
          <div className="grid2" style={{ marginTop: 8 }}>
            <label className="field"><span>Name</span><input className="input" value={name} onChange={e => setName(e.target.value)} /></label>
            <div className="grid2"><label className="field"><span>Lat</span><input className="input num" value={lat} onChange={e => { setLat(e.target.value); setLookup(null) }} /></label><label className="field"><span>Lon</span><input className="input num" value={lon} onChange={e => { setLon(e.target.value); setLookup(null) }} /></label></div>
          </div>
          <label className="field"><span>Analysis footprint</span>
            <div className="row">
              <div className="seg"><button aria-pressed={mode === 'bbox'} onClick={() => setMode('bbox')}>Regional box</button><button aria-pressed={mode === 'point'} onClick={() => setMode('point')}>Nearest grid cell</button></div>
              {mode === 'bbox' && <><span className="small muted">half-width °</span><input className="input num" style={{ width: 70 }} value={half} onChange={e => setHalf(e.target.value)} /></>}
            </div></label>
          {geom && <p className="small num muted">{geom.type === 'bbox' ? `W ${geom.west} · S ${geom.south} · E ${geom.east} · N ${geom.north} (area-weighted mean of MERRA-2 cells inside)` : `Point ${geom.lat}, ${geom.lon} → single nearest 0.5°×0.625° cell, not a city average`}</p>}
          {problems.map(p => <p key={p} className="small" style={{ color: 'var(--red)' }}>{p}</p>)}
          <div className="grid2">
            <label className="field"><span>Hazard mechanism</span><select className="input" value={mech} onChange={e => setMech(e.target.value)}><option value="">Not established (ask later)</option>{Object.entries(meta.mechanisms).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
            <label className="field"><span>Scale</span><select className="input" value={scale} onChange={e => setScale(e.target.value)}><option value="">Not established</option>{['neighbourhood', 'city', 'catchment', 'regional'].map(s => <option key={s}>{s}</option>)}</select></label>
          </div>
          <label className="field"><span>Question</span><textarea className="input" rows={2} value={question} onChange={e => setQuestion(e.target.value)} /></label>
          {err && <p className="small" style={{ color: 'var(--red)' }}>{err}</p>}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn primary" disabled={!geom || !name.trim() || problems.length > 0 || busy} onClick={async () => {
              setBusy(true); setErr(null)
              try {
                await onCreate({ place: { name: name.trim(), geometry: geom, geometry_origin: mode === 'bbox' ? `User-confirmed ${+half * 2}°×${+half * 2}° box around ${lookup ? 'geocoded point' : 'entered coordinates'}` : 'User-confirmed point (nearest POWER grid cell)', scale: scale || null, lookup }, mechanism: mech || null, question, title: `${name.trim()} investigation` })
              } catch (e: any) { setErr(e.message); setBusy(false) }
            }}>{busy ? 'Creating…' : 'Confirm footprint & acquire'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ compare */
export function CompareView({ cases, invs, initialA, onClose }: { cases: CaseFile[]; invs: { id: string; title: string }[]; initialA: string; onClose: () => void }) {
  const opts = [...cases.map(c => ({ v: `case:${c.id}`, l: c.display_name })), ...invs.map(i => ({ v: `inv:${i.id}`, l: `My: ${i.title}` }))]
  const [a, setA] = useState(initialA)
  const [b, setB] = useState(opts.find(o => o.v !== initialA)?.v || '')
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { if (a && b && a !== b) { setErr(null); api.get(`/api/compare?a=${a}&b=${b}`).then(setD).catch(e => setErr(e.message)) } }, [a, b])
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [onClose])
  const g = (x: any) => x.type === 'bbox' ? `W${x.west} S${x.south} E${x.east} N${x.north}` : `pt ${x.lat}, ${x.lon}`
  const cell = (f: any) => !f ? <span className="muted">not computed</span> : f.props.slope_per_decade !== undefined
    ? <span className="num"><b>{fmt(f.props.slope_per_decade)}</b> {f.props.units}/dec<br /><span className="muted">CI [{fmt(f.props.ci95_per_decade[0])}, {fmt(f.props.ci95_per_decade[1])}] · q {fmtP(f.props.q_value)}</span></span>
    : <span className="muted">descriptive only</span>
  return (
    <div className="overlay" role="dialog" aria-label="Case comparison">
      <div className="overlay-h"><h2>Compare</h2>
        <select className="input" style={{ width: 240 }} value={a} onChange={e => setA(e.target.value)}>{opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}</select>
        <span className="muted">vs</span>
        <select className="input" style={{ width: 240 }} value={b} onChange={e => setB(e.target.value)}>{opts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}</select>
        <span className="spacer" /><button className="btn sm" onClick={onClose}>Close <span className="kbd">Esc</span></button></div>
      <div style={{ overflow: 'auto', padding: 16 }}>
        {err && <div className="empty"><p>{err}</p></div>}
        {a === b && <p className="muted">Choose two different items.</p>}
        {d && a !== b && (
          <table className="tbl" style={{ maxWidth: 1100 }}>
            <thead><tr><th style={{ width: 180 }}>Field</th><th>{d.a.name}</th><th>{d.b.name}</th></tr></thead>
            <tbody>
              <tr><td>Hazard mechanism</td><td>{humanize(d.a.mechanism) || '—'}</td><td>{humanize(d.b.mechanism) || '—'}{d.a.mechanism && d.b.mechanism && d.a.mechanism !== d.b.mechanism && <><br /><span style={{ color: 'var(--amber)' }}>Different mechanism — lessons do not transfer automatically</span></>}</td></tr>
              <tr><td>Scale</td><td>{d.a.scale || '—'}</td><td>{d.b.scale || '—'}</td></tr>
              <tr><td>Analysis geometry</td><td className="num">{g(d.a.geometry)}<br /><span className="muted">{d.a.geometry_origin}</span></td><td className="num">{g(d.b.geometry)}<br /><span className="muted">{d.b.geometry_origin}</span></td></tr>
              <tr><td>Analysis period</td><td>{d.a.period.start} – {d.a.period.end}</td><td>{d.b.period.start} – {d.b.period.end}</td></tr>
              <tr><td>Event evidence</td><td>{d.a.event ? <>{d.a.event.start} → {d.a.event.end}<br /><span className="muted">{d.a.event.summary.slice(0, 220)}…</span></> : <span className="muted">No event record (regional trend investigation)</span>}</td><td>{d.b.event ? <>{d.b.event.start} → {d.b.event.end}<br /><span className="muted">{d.b.event.summary.slice(0, 220)}…</span></> : <span className="muted">No event record (regional trend investigation)</span>}</td></tr>
              {d.variables.map((v: any) => <tr key={v.variable}><td>{v.variable} trend{!v.directly_comparable && <><br /><span className="muted small">{v.note}</span></>}</td><td>{cell(v.a)}</td><td>{cell(v.b)}</td></tr>)}
              <tr><td>Documented responses</td><td>{d.a.responses.map((r: any) => <div key={r.id}>{r.label} <span className="muted">({humanize(r.props.status)}, {r.props.outcome_type})</span></div>)}{!d.a.responses.length && <span className="muted">—</span>}</td><td>{d.b.responses.map((r: any) => <div key={r.id}>{r.label} <span className="muted">({humanize(r.props.status)}, {r.props.outcome_type})</span></div>)}{!d.b.responses.length && <span className="muted">—</span>}</td></tr>
              <tr><td>Transfer limitations</td><td colSpan={2} className="muted">{d.spatial_note} Outcomes reported in one setting are never forecasts for the other.</td></tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ command palette */
export interface Cmd { id: string; label: string; hint?: string; run: () => void; disabled?: string | null }
export function Palette({ cmds, onClose }: { cmds: Cmd[]; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const list = cmds.filter(c => c.label.toLowerCase().includes(q.toLowerCase()))
  const inp = useRef<HTMLInputElement>(null)
  useEffect(() => { inp.current?.focus() }, [])
  const go = (c?: Cmd) => { if (c && !c.disabled) { onClose(); c.run() } }
  return (
    <div className="modal-bg" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input ref={inp} className="input" placeholder="Type a command…" value={q} onChange={e => { setQ(e.target.value); setI(0) }}
          onKeyDown={e => { if (e.key === 'Escape') onClose(); if (e.key === 'ArrowDown') { e.preventDefault(); setI(Math.min(list.length - 1, i + 1)) } if (e.key === 'ArrowUp') { e.preventDefault(); setI(Math.max(0, i - 1)) } if (e.key === 'Enter') go(list[i]) }} aria-controls="pal-list" />
        <div id="pal-list" role="listbox" style={{ padding: '4px 0 8px' }}>
          {list.map((c, k) => <button key={c.id} role="option" aria-selected={k === i} className="palette-item" onMouseEnter={() => setI(k)} onClick={() => go(c)} disabled={!!c.disabled} style={c.disabled ? { opacity: .45 } : undefined}>
            <span>{c.label}</span><span className="why">{c.disabled || c.hint}</span></button>)}
          {!list.length && <p className="muted small" style={{ padding: '6px 14px' }}>No matching command.</p>}
        </div>
      </div>
    </div>
  )
}
