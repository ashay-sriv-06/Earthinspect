import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CaseFile, GNode, Investigation, MatchRun, Meta, Results } from './api'
import { api, humanize } from './api'
import MapView, { type Layers } from './MapView'
import Timeline from './Timeline'
import { AnalysisPanel, CasePanel, ChangesPanel, EvidencePanel, LeadsPanel } from './panels'
import CopilotPanel from './CopilotPanel'
import TraceView from './TraceView'
import { CompareView, NewPlaceDialog, Palette, type Cmd } from './dialogs'

type Tab = 'case' | 'analysis' | 'leads' | 'copilot' | 'evidence' | 'changes'
const TABS: [Tab, string][] = [['case', 'Case'], ['analysis', 'Analysis'], ['leads', 'Leads'], ['copilot', 'Copilot'], ['evidence', 'Evidence'], ['changes', 'Changes']]
const DEFAULT_LAYERS: Layers = { footprint: true, grid: true, event: true, imagery: false, imagery_opacity: 0.8, basemap: true }

function Logo() {
  return <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden><circle cx="16" cy="16" r="12.5" fill="none" stroke="#58C7B1" strokeWidth="2.5" /><path d="M5.5 18c5-4 15 2 21-3" stroke="#D5A555" strokeWidth="2.5" fill="none" /><circle cx="21" cy="11" r="2.2" fill="#E7EAEC" /></svg>
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [cases, setCases] = useState<CaseFile[]>([])
  const [invList, setInvList] = useState<{ id: string; title: string; place: string; case_id: string | null }[]>([])
  const [inv, setInv] = useState<Investigation | null>(null)
  const [preview, setPreview] = useState<CaseFile | null>(null)
  const [results, setResults] = useState<Results | null>(null)
  const [match, setMatch] = useState<MatchRun | null>(null)
  const [tab, setTab] = useState<Tab>('case')
  const [nodeId, setNodeId] = useState<string | null>(null)
  const [traceId, setTraceId] = useState<string | null>(null)
  const [compare, setCompare] = useState(false)
  const [newPlace, setNewPlace] = useState(false)
  const [palette, setPalette] = useState(false)
  const [dockOpen, setDockOpen] = useState(true)
  const [inspOpen, setInspOpen] = useState(true)
  const [selVar, setSelVar] = useState<string | null>(null)
  const [focus, setFocus] = useState<{ start: string; end: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [acqEvents, setAcqEvents] = useState<any[]>([])
  const [toast, setToast] = useState<{ msg: string; err?: boolean } | null>(null)
  const [flyKey, setFlyKey] = useState('')
  const [highlight, setHighlight] = useState(false)
  const [catQ, setCatQ] = useState('')
  const [cat, setCat] = useState<any[]>([])
  const [cmr, setCmr] = useState<any[] | null>(null)
  const [imgCheck, setImgCheck] = useState<string | null>(null)
  const [health, setHealth] = useState<'ok' | 'down' | 'checking'>('checking')
  const viewTimer = useRef<number | null>(null)
  const lastFocus = useRef<HTMLElement | null>(null)

  const say = (msg: string, err = false) => { setToast({ msg, err }); window.setTimeout(() => setToast(null), err ? 6000 : 3500) }
  const fail = (e: any) => say(e?.message || String(e), true)

  // ------------------------------------------------ boot
  useEffect(() => {
    api.get('/api/health').then(() => setHealth('ok')).catch(() => setHealth('down'))
    api.get<Meta>('/api/meta').then(setMeta).catch(fail)
    api.get<CaseFile[]>('/api/cases').then(setCases).catch(fail)
    api.get<any[]>('/api/catalog').then(setCat).catch(() => {})
    refreshList().then(list => {
      const fromUrl = new URLSearchParams(location.search).get('inv')
      let last: string | null = null
      try { last = localStorage.getItem('ei_last_inv') } catch { /* storage unavailable */ }
      const id = fromUrl || last
      if (id && list.some(i => i.id === id)) openInv(id, true)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const refreshList = async () => { const l = await api.get<any[]>('/api/investigations'); setInvList(l); return l }

  // ------------------------------------------------ investigation lifecycle
  // Canonical selection: every async result is tagged with the investigation it belongs to and dropped if the
  // user has since switched, so no panel can silently show a different investigation than the focus bar.
  const activeInv = useRef<string | null>(null)
  const isActive = (id: string) => activeInv.current === id
  const loadResults = useCallback(async (id: string) => {
    const r = await api.get<Results>(`/api/investigations/${id}/results`)
    if (activeInv.current !== id) return r
    setResults(r)
    if (r.batch && !selVar) setSelVar(r.batch.results[0]?.variable || null)
    return r
  }, [selVar])

  const openInv = async (id: string, fly = true) => {
    activeInv.current = id
    setResults(null); setMatch(null); setChange(null)
    try {
      const i = await api.get<Investigation>(`/api/investigations/${id}`)
      if (!isActive(id)) return
      setInv(i); setPreview(null); setMatch(null); setAcqEvents([]); setFocus(null)
      setNodeId(i.config.view.selected_node || null); setTrail(i.config.view.evidence_trail || [])
      setSelVar(i.config.view.selected_variable || null)
      setTab((i.config.view.inspector_tab as Tab) || 'analysis')
      try { localStorage.setItem('ei_last_inv', id) } catch { /* ignore */ }
      history.replaceState(null, '', `?inv=${id}`)
      if (fly) setFlyKey((i.config.view.camera_saved ? 'restore:' : 'fit:') + id + Date.now())
      setChange(null)
      const r = await loadResults(id)
      if (!isActive(id)) return
      if (r.batch) api.get<MatchRun>(`/api/investigations/${id}/match`).then(m => isActive(id) && setMatch(m)).catch(() => {})
      const lc = i.config.view.last_change
      if (lc && i.revisions.some(x => x.id === lc.from) && lc.to === i.current_revision_id) loadChange(id, lc.from, lc.to)
    } catch (e) { fail(e) }
  }

  const patchView = (patch: Partial<Investigation['config']['view']>) => {
    if (!inv) return
    const next = { ...inv, config: { ...inv.config, view: { ...inv.config.view, ...patch } } }
    setInv(next)
    if (viewTimer.current) window.clearTimeout(viewTimer.current)
    viewTimer.current = window.setTimeout(() => { api.patch(`/api/investigations/${inv.id}`, { view: next.config.view }).catch(() => {}) }, 500)
  }
  const layers: Layers = { ...DEFAULT_LAYERS, ...(inv?.config.view.layers || {}) }
  const setLayer = (k: keyof Layers, v: any) => patchView({ layers: { ...layers, [k]: v } })
  const switchTab = (t: Tab) => { setTab(t); if (inv) patchView({ inspector_tab: t }) }

  const openCase = async (c: CaseFile) => {
    activeInv.current = null
    const full = await api.get<CaseFile>(`/api/cases/${c.id}`)
    setPreview(full); setInv(null); setResults(null); setMatch(null); setTab('case'); setFlyKey(c.id + Date.now())
    history.replaceState(null, '', location.pathname)
  }
  const createFromCase = async (c: CaseFile) => {
    const existing = invList.find(i => i.case_id === c.id)
    if (existing) return openInv(existing.id)
    setBusy('open')
    try { const i = await api.post<Investigation>('/api/investigations', { case_id: c.id }); await refreshList(); await openInv(i.id); say(`Investigation saved: ${i.title}`) } catch (e) { fail(e) } finally { setBusy(null) }
  }
  const acquire = async (force = false) => {
    if (!inv) return
    setBusy('acquire'); setAcqEvents([])
    try {
      const b = await api.post<any>(`/api/investigations/${inv.id}/analyze`, { force_refresh: force })
      setAcqEvents(b.events || [])
      await loadResults(inv.id)
      setMatch(await api.get<MatchRun>(`/api/investigations/${inv.id}/match`))
      const counts = (b.events || []).reduce((a: any, e: any) => { a[e.type] = (a[e.type] || 0) + 1; return a }, {})
      say(`${counts.cache_fetched || 0} fetched · ${counts.cache_cached || 0} cached · ${counts.cache_snapshot || 0} snapshot · analysis ${b.reused ? 'reused' : 'created'}`)
    } catch (e) { fail(e) } finally { setBusy(null) }
  }
  const applyWindow = async (start: string, end: string) => {
    if (!inv) return
    setBusy('acquire')
    try {
      const i = await api.patch<Investigation>(`/api/investigations/${inv.id}`, { period: { start, end } })
      setInv(i)
      const b = await api.post<any>(`/api/investigations/${inv.id}/analyze`, {})
      setAcqEvents(b.events || [])
      await loadResults(inv.id)
      setMatch(await api.get<MatchRun>(`/api/investigations/${inv.id}/match`))
      say(`New labelled analysis for ${start} – ${end} (${b.reused ? 'reused' : 'created'}).`)
    } catch (e) { fail(e) } finally { setBusy(null) }
  }
  const runMatch = async () => {
    if (!inv) return
    setBusy('match')
    try { setMatch(await api.get<MatchRun>(`/api/investigations/${inv.id}/match`)) } catch (e) { fail(e) } finally { setBusy(null) }
  }
  const [change, setChange] = useState<any>(null)
  const loadChange = async (id: string, from: string, to: string) => {
    try { const d = await api.get(`/api/investigations/${id}/what-changed?frm=${from}&to=${to}`); if (isActive(id)) setChange(d) } catch { setChange(null) }
  }
  const openDemo = async () => {
    setBusy('open')
    try { const i = await api.post<Investigation>('/api/demo'); await refreshList(); await openInv(i.id); say('Demo investigation ready: Camp Fire 2018 with two real imagery dates and one labelled planning assumption.') }
    catch (e) { fail(e) } finally { setBusy(null) }
  }
  const revise = async (body: any) => {
    if (!inv) return
    const before = inv.current_revision_id
    try {
      const i = await api.post<Investigation>(`/api/investigations/${inv.id}/revisions`, body)
      setMatch(await api.get<MatchRun>(`/api/investigations/${inv.id}/match`))
      await loadChange(inv.id, before, i.current_revision_id)
      const view = { ...i.config.view, ...inv.config.view, last_change: { from: before, to: i.current_revision_id } }
      setInv({ ...i, config: { ...i.config, view } })
      if (viewTimer.current) window.clearTimeout(viewTimer.current)
      api.patch(`/api/investigations/${inv.id}`, { view }).catch(() => {})
      say(`Revision R${i.revisions[i.revisions.length - 1].seq} saved; dependent match re-evaluated (NASA artifacts reused).`)
    } catch (e) { fail(e) }
  }
  const changedNodes = useMemo(() => {
    if (!change || !traceId) return [] as string[]
    const c = change.candidates.find((x: any) => x.intervention_id === traceId)
    const ids = (c?.changed_features || []).filter((f: any) => f.feature.startsWith('requires:')).map((f: any) => f.feature.slice(9))
    return ids.length ? [...ids, `asm-${change.to.revision_id}`, traceId] : []
  }, [change, traceId])
  const activate = async (rid: string) => {
    if (!inv) return
    try { const i = await api.post<Investigation>(`/api/investigations/${inv.id}/revisions/${rid}/activate`); setInv(i); setChange(null); patchView({ last_change: null }); setMatch(await api.get<MatchRun>(`/api/investigations/${inv.id}/match`)); say('Switched revision; later revisions are kept.') } catch (e) { fail(e) }
  }
  const [trail, setTrail] = useState<string[]>([])
  const [imgStateRaw, setImgState] = useState<{ A: string; B: string }>({ A: 'loading', B: 'loading' })
  // Server probe verdict for a specific date wins over map tile events for that same date (no race on slow hosts).
  const [imgProbe, setImgProbe] = useState<{ A?: { date: string; st: string }; B?: { date: string; st: string } }>({})
  const showNode = (id: string, fromTrail = false) => {
    setNodeId(id); setTab('evidence'); setInspOpen(true)
    const next = fromTrail ? trail.slice(0, trail.indexOf(id) + 1) : [...trail.filter(x => x !== id), id].slice(-10)
    setTrail(next)
    if (inv) patchView({ selected_node: id, evidence_trail: next, inspector_tab: 'evidence' })
  }
  const focusFinding = (n: GNode) => { if (n.props?.variable) setSelVar(n.props.variable); if (n.props?.period) setFocus(n.props.period); setHighlight(h => !h) }
  const trace = (id: string) => { lastFocus.current = document.activeElement as HTMLElement; setTraceId(id) }
  const closeTrace = () => { setTraceId(null); window.setTimeout(() => lastFocus.current?.focus(), 0) }

  // ------------------------------------------------ keyboard
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(p => !p) } }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [])

  // ------------------------------------------------ derived
  const caseOf = inv?.config.place.case_id ? cases.find(c => c.id === inv.config.place.case_id) : preview
  const r0 = results?.batch?.results[0]
  const geometry = inv?.config.place.geometry || preview?.analysis_geometry || null
  const eventPoint = inv ? (inv.config.place.event_point || null) : (preview?.event_point || null)
  const imageryDate = inv?.config.view.imagery_date ?? caseOf?.event_start ?? null
  const imageryDateB = inv?.config.view.imagery_date_b ?? null
  const imageryMix = inv?.config.view.imagery_mix ?? 0
  const today = new Date().toISOString().slice(0, 10)
  const sideState = (side: 'A' | 'B', d: string | null) => {
    const pr = imgProbe[side]
    if (pr && pr.date === d && (pr.st === 'missing' || pr.st === 'error')) return pr.st
    return imgStateRaw[side]
  }
  const imgState = { A: sideState('A', imageryDate), B: sideState('B', imageryDateB) }
  const compareMode: 'swipe' | 'overlay' = inv?.config.view.imagery_compare === 'overlay' ? 'overlay' : 'swipe'
  const imagerySwipe = inv?.config.view.imagery_swipe ?? 0.5
  const latestCheck = inv?.config.view.imagery_latest_check ?? null
  // Server-side tile probe whenever a date changes: distinguishes a 404 (missing) from a provider error;
  // map tile events then confirm 'loaded'. A missing date is never replaced by another date.
  useEffect(() => {
    if (!inv || !layers.imagery || !geometry) return
    const id = inv.id
    const [lon, lat] = geometry.type === 'bbox' ? [(geometry.west + geometry.east) / 2, (geometry.south + geometry.north) / 2] : [geometry.lon, geometry.lat]
    const z = 5, n = 2 ** z
    const x = Math.floor(((lon + 180) / 360) * n)
    const y = Math.floor(((1 - Math.log(Math.tan((lat * Math.PI) / 180) + 1 / Math.cos((lat * Math.PI) / 180)) / Math.PI) / 2) * n)
    const probe = (side: 'A' | 'B', d: string | null) => d && api.get<any>(`/api/imagery/check?date=${d}&z=${z}&x=${x}&y=${y}`)
      .then(r => { if (isActive(id)) setImgProbe(s => ({ ...s, [side]: { date: d, st: r.state === 'available' ? 'available' : r.state === 'missing' ? 'missing' : 'error' } })) })
      .catch(() => { if (isActive(id)) setImgProbe(s => ({ ...s, [side]: { date: d, st: 'error' } })) })
    probe('A', imageryDate)
    probe('B', imageryDateB)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inv?.id, layers.imagery, imageryDate, imageryDateB])
  const checkUpdates = async () => {
    try { const r = await api.get<any>('/api/imagery/latest'); patchView({ imagery_latest_check: { latest_date: r.latest_date, checked_at: r.checked_at } }) }
    catch (e: any) { patchView({ imagery_latest_check: { error: e.message, checked_at: new Date().toISOString() } }) }
  }
  // The one canonical focus every panel reads from.
  const focusState = inv ? {
    investigation: inv.id,
    revision: inv.current_revision_id,
    revisionSeq: inv.revisions.find(r => r.id === inv.current_revision_id)?.seq,
    claim: nodeId,
    observation: imageryDateB && compareMode === 'swipe' ? `${imageryDate} | B ${imageryDateB}` : imageryDateB && imageryMix >= 0.5 ? imageryDateB : imageryDate,
    observationLabel: imageryDateB ? (compareMode === 'swipe' ? 'A' : imageryMix >= 0.5 ? 'B' : 'A') : null,
    graph: match?.graph_version ?? null,
    matchRun: match?.id ?? null,
  } : null
  const defaultDateB = (a: string | null) => { if (!a) return null; const d = new Date(a + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - 14); return d.toISOString().slice(0, 10) }
  const hasResults = !!results?.batch
  const exportsDisabled = !inv ? 'Open an investigation first' : !hasResults ? 'Acquire NASA data first' : null

  const cmds: Cmd[] = useMemo(() => [
    { id: 'demo', label: 'Open demo investigation (Camp Fire 2018)', run: () => openDemo() },
    { id: 'new', label: 'Investigate another place…', run: () => setNewPlace(true) },
    ...cases.map(c => ({ id: 'case-' + c.id, label: `Open case file: ${c.display_name}`, run: () => openCase(c) })),
    ...invList.map(i => ({ id: 'inv-' + i.id, label: `Open investigation: ${i.title}`, run: () => openInv(i.id) })),
    { id: 'acq', label: 'Acquire / reuse NASA data', run: () => acquire(false), disabled: inv ? null : 'Open an investigation first' },
    { id: 'match', label: 'Find precedents (contextual match)', run: () => { switchTab('leads'); runMatch() }, disabled: inv ? null : 'Open an investigation first' },
    { id: 'trace', label: 'Trace top planning lead', run: () => match?.leads[0] && trace(match.leads[0].intervention_id), disabled: match?.leads.length ? null : 'No planning lead yet' },
    { id: 'cop', label: 'Open copilot', run: () => switchTab('copilot'), disabled: inv ? null : 'Open an investigation first' },
    { id: 'cmp', label: 'Compare cases…', run: () => setCompare(true) },
    { id: 'csv', label: 'Export normalized CSV', run: () => inv && (location.href = `/api/investigations/${inv.id}/export.csv`), disabled: exportsDisabled },
    { id: 'json', label: 'Export investigation JSON', run: () => inv && (location.href = `/api/investigations/${inv.id}/export.json`), disabled: exportsDisabled },
    { id: 'html', label: 'Export printable HTML report', run: () => inv && (location.href = `/api/investigations/${inv.id}/export.html`), disabled: exportsDisabled },
    { id: 'img', label: layers.imagery ? 'Hide NASA imagery layer' : 'Show NASA imagery layer', run: () => setLayer('imagery', !layers.imagery), disabled: inv ? null : 'Open an investigation first' },
    { id: 'dock', label: dockOpen ? 'Collapse layer dock' : 'Expand layer dock', run: () => setDockOpen(!dockOpen) },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [cases, invList, inv, match, exportsDisabled, layers.imagery, dockOpen])

  const searchCatalog = async (q: string) => { setCatQ(q); setCmr(null); try { setCat(await api.get<any[]>(`/api/catalog?q=${encodeURIComponent(q)}`)) } catch (e) { fail(e) } }
  const toggleVar = async (v: string) => {
    if (!inv) return
    const vars = inv.config.variables.includes(v) ? inv.config.variables.filter(x => x !== v) : [...inv.config.variables, v]
    if (!vars.length) return say('Keep at least one variable.', true)
    try { setInv(await api.patch<Investigation>(`/api/investigations/${inv.id}`, { variables: vars })); say('Variable family changed — acquire to run a new, separately labelled analysis.') } catch (e) { fail(e) }
  }
  const checkImagery = async () => {
    if (!imageryDate || !geometry) return
    const [lon, lat] = geometry.type === 'bbox' ? [(geometry.west + geometry.east) / 2, (geometry.south + geometry.north) / 2] : [geometry.lon, geometry.lat]
    const z = 5, n = 2 ** z
    const x = Math.floor(((lon + 180) / 360) * n)
    const y = Math.floor(((1 - Math.log(Math.tan((lat * Math.PI) / 180) + 1 / Math.cos((lat * Math.PI) / 180)) / Math.PI) / 2) * n)
    setImgCheck('Checking…')
    const one = async (label: string, d: string) => {
      try { const r = await api.get<any>(`/api/imagery/check?date=${d}&z=${z}&x=${x}&y=${y}`); return r.available ? `${label} ${d}: tile available` : `${label} ${d}: no imagery here (${r.reason || r.status}); not substituted` }
      catch (e: any) { return `${label} ${d}: ${e.message}` }
    }
    const parts = [await one('A', imageryDate)]
    if (imageryDateB) parts.push(await one('B', imageryDateB))
    setImgCheck(parts.join(' · '))
  }

  return (
    <div className={`app ${hasResults ? '' : 'no-time'}`}>
      {/* ---------------------------------------------- command bar */}
      <header className="cmdbar">
        <div className="brand"><Logo />EarthInspect <small>Inspect · Trace · Compare</small></div>
        <span className="bar-sep" />
        <div className="bar-title">{inv ? <><b>{inv.title}</b> · {inv.config.period.start} – {inv.config.period.end} · {inv.state.mechanism ? humanize(inv.state.mechanism) : 'mechanism not established'}</> : preview ? <><b>{preview.display_name}</b> · case file (read-only)</> : 'Select a case file or investigate another place'}</div>
        <span className="spacer" />
        <button className="btn" onClick={() => setNewPlace(true)}>+ New place</button>
        <button className="btn" onClick={() => setCompare(true)} disabled={!cases.length}>Compare</button>
        <details style={{ position: 'relative' }}>
          <summary className="btn" style={{ listStyle: 'none' }} aria-disabled={!!exportsDisabled} title={exportsDisabled || 'Download real work products'}>Export ▾</summary>
          <div className="modal" style={{ position: 'absolute', right: 0, top: 38, width: 240, zIndex: 40, padding: 6 }}>
            {exportsDisabled ? <p className="small muted" style={{ padding: 8 }}>{exportsDisabled}</p> : <>
              <a className="palette-item" href={`/api/investigations/${inv!.id}/export.csv`}>Normalized series (CSV)</a>
              <a className="palette-item" href={`/api/investigations/${inv!.id}/export.json`}>Investigation + provenance (JSON)</a>
              <a className="palette-item" href={`/api/investigations/${inv!.id}/export.html`}>Printable report (HTML)</a>
              <a className="palette-item" href={`/api/investigations/${inv!.id}/export.html?inline=1`} target="_blank" rel="noreferrer">Preview report ↗</a>
            </>}
          </div>
        </details>
        <button className="btn ghost" onClick={() => setPalette(true)} title="Command palette">Commands <span className="kbd">Ctrl K</span></button>
        <button className="btn ghost icon" onClick={() => setInspOpen(!inspOpen)} aria-label={inspOpen ? 'Collapse inspector' : 'Expand inspector'} aria-expanded={inspOpen}>{inspOpen ? '⟩' : '⟨'}</button>
      </header>

      {/* ---------------------------------------------- dock */}
      <nav className={`dock ${dockOpen ? 'pinned' : 'collapsed'}`} aria-label="Cases and layers">
        {!dockOpen ? (
          <div className="dock-collapsed-icons"><button className="btn icon ghost" onClick={() => setDockOpen(true)} aria-label="Expand dock">☰</button></div>
        ) : (
          <>
            <div className="dock-h"><span>Case files</span><button className="btn ghost sm" onClick={() => setDockOpen(false)} aria-label="Collapse dock">⟨</button></div>
            <div className="dock-sec">
              {cases.map(c => (
                <button key={c.id} className="case-item" aria-current={(inv?.config.place.case_id === c.id || preview?.id === c.id) ? 'true' : 'false'} onClick={() => openCase(c)}>
                  <span className="t">{c.display_name}</span><span className="s">{c.mechanism.label}</span>
                </button>
              ))}
            </div>
            <div className="dock-h"><span>My investigations</span><span className="num">{invList.length}</span></div>
            <div className="dock-sec">
              {invList.length === 0 && <p className="small muted" style={{ padding: '0 12px' }}>None yet. Open a case or a new place.</p>}
              {invList.map(i => <button key={i.id} className="case-item" aria-current={inv?.id === i.id ? 'true' : 'false'} onClick={() => openInv(i.id)}><span className="t">{i.title}</span><span className="s">{i.case_id ? 'From case file' : 'New place'} · {i.place}</span></button>)}
            </div>
            <div className="dock-h"><span>Layers</span></div>
            <div className="dock-sec">
              {([['footprint', 'Analysis footprint', 'var(--amber)', 'Requested geometry'], ['grid', 'POWER grid support', 'var(--teal)', r0 ? `${r0.spatial_support.cell_count} cells · ${r0.spatial_support.cell_size_deg.lat}°×${r0.spatial_support.cell_size_deg.lon}°` : 'Appears after acquisition'], ['event', 'Event reference point', 'var(--red)', 'Point marker, not a hazard extent'], ['basemap', 'Basemap', '#9aa5ad', 'NASA Blue Marble relief + labels (GIBS)']] as const).map(([k, l, c, m]) => (
                <label key={k} className="layer">
                  <input type="checkbox" checked={!!layers[k]} disabled={!inv && k !== 'basemap'} onChange={e => setLayer(k, e.target.checked)} style={{ accentColor: 'var(--teal)' }} />
                  <span className="row"><span className="swatch" style={{ borderColor: c }} />{l}</span><span />
                  <span className="meta">{m}</span>
                </label>
              ))}
              <label className="layer">
                <input type="checkbox" checked={layers.imagery} disabled={!inv} onChange={e => setLayer('imagery', e.target.checked)} style={{ accentColor: 'var(--teal)' }} />
                <span>NASA GIBS MODIS true colour</span><span />
                <span className="meta">Visual context; not numerical data</span>
              </label>
              {layers.imagery && inv && (
                <div style={{ padding: '0 12px 6px 34px' }}>
                  <p className="small" style={{ margin: '0 0 4px', color: 'var(--amber)' }}>Visual comparison only — no burned area, smoke extent or prediction is derived from colours.</p>
                  <div className="row"><span className="small muted" style={{ width: 14 }}>A</span><input type="date" className="input" value={imageryDate || ''} min="2000-02-24" max={today} onChange={e => { setImgCheck(null); patchView({ imagery_date: e.target.value }) }} aria-label="Imagery date A" /><span className={`img-state ${imgState.A}`} data-testid="img-state-A">{imgState.A}</span></div>
                  {imageryDateB ? (
                    <>
                      <div className="row" style={{ marginTop: 4 }}><span className="small muted" style={{ width: 14 }}>B</span><input type="date" className="input" value={imageryDateB} min="2000-02-24" max={today} onChange={e => { setImgCheck(null); patchView({ imagery_date_b: e.target.value }) }} aria-label="Imagery date B" /><span className={`img-state ${imgState.B}`} data-testid="img-state-B">{imgState.B}</span><button className="btn sm ghost" onClick={() => patchView({ imagery_date_b: null, imagery_mix: 0 })} aria-label="Remove comparison date">✕</button></div>
                      <div className="seg" role="group" aria-label="Comparison mode" style={{ marginTop: 6 }}>
                        <button aria-pressed={compareMode === 'swipe'} onClick={() => patchView({ imagery_compare: 'swipe' })}>Swipe</button>
                        <button aria-pressed={compareMode === 'overlay'} onClick={() => patchView({ imagery_compare: 'overlay' })}>Overlay</button>
                      </div>
                      {compareMode === 'overlay' && <label className="row small muted" style={{ marginTop: 6 }}>A <input type="range" min={0} max={1} step={0.05} value={imageryMix} onChange={e => patchView({ imagery_mix: +e.target.value })} aria-label="Crossfade between date A and date B" style={{ flex: 1 }} /> B</label>}
                      <div className="row wrap" style={{ marginTop: 4 }}>
                        {compareMode === 'overlay'
                          ? <button className="btn sm" onClick={() => patchView({ imagery_mix: imageryMix < 0.5 ? 1 : 0 })} title="Switch instantly between the two real observation dates">Flip to {imageryMix < 0.5 ? 'B' : 'A'}</button>
                          : <button className="btn sm" onClick={() => patchView({ imagery_swipe: 0.5 })}>Center swipe</button>}
                        <button className="btn sm" onClick={checkImagery}>Check both</button>
                      </div>
                    </>
                  ) : (
                    <div className="row" style={{ marginTop: 4 }}>
                      <button className="btn sm" onClick={() => patchView({ imagery_date_b: defaultDateB(imageryDate), imagery_mix: 0 })} disabled={!imageryDate}>+ Compare a second date</button>
                      <button className="btn sm" onClick={checkImagery}>Check</button>
                    </div>
                  )}
                  <label className="row small muted" style={{ marginTop: 4 }}>Opacity <input type="range" min={0.1} max={1} step={0.05} value={layers.imagery_opacity} onChange={e => setLayer('imagery_opacity', +e.target.value)} /></label>
                  {imgCheck && <p className="small muted" style={{ margin: '2px 0' }}>{imgCheck}</p>}
                  <div className="row wrap" style={{ marginTop: 4 }}>
                    <button className="btn sm" onClick={checkUpdates}>Check for updates</button>
                  </div>
                  {latestCheck && <p className="small muted" style={{ margin: '2px 0' }} data-testid="latest-check">{latestCheck.error ? `GIBS check failed: ${latestCheck.error}` : `Newest MODIS date on GIBS: ${latestCheck.latest_date}`} · checked {latestCheck.checked_at?.replace('T', ' ').replace('+00:00', ' UTC')} (manual check; no background monitoring)</p>}
                  <p className="small muted" style={{ margin: 0 }}>Real daily MODIS tiles only — no interpolated frames. Imagery dates are separate from the {inv.config.period.start.slice(0, 4)}–{inv.config.period.end.slice(0, 4)} monthly trend window.</p>
                </div>
              )}
            </div>
            <div className="dock-h"><span>NASA data catalog</span>{meta && <span className="num" title="Catalog entries vs implemented numerical adapters">{meta.catalog_counts.entries} entries · {meta.catalog_counts.analysis_ready_adapters} adapter</span>}</div>
            <div style={{ padding: '0 12px 12px' }}>
              <input className="input" placeholder="flood, fire, drought, soil moisture…" value={catQ} onChange={e => searchCatalog(e.target.value)} aria-label="Search catalog" />
              <div style={{ marginTop: 6 }}>
                {cat.slice(0, 8).map(e => (
                  <details key={e.id} style={{ borderBottom: '1px solid var(--line-soft)', padding: '4px 0' }}>
                    <summary style={{ cursor: 'pointer' }} className="small"><span className={`badge ${e.status === 'analysis_ready' ? 'b-computed' : e.status === 'imagery_view' ? 'b-source' : 'b-neutral'}`} style={{ marginRight: 4 }}>{humanize(e.status)}</span>{e.name}</summary>
                    <div className="small" style={{ color: 'var(--text-2)', padding: '4px 0 4px 4px' }}>
                      {e.relevance && <p style={{ margin: '2px 0' }}>{e.relevance}</p>}
                      <p style={{ margin: '2px 0' }} className="muted">{e.status_explanation}</p>
                      <p style={{ margin: '2px 0' }} className="muted">{e.short_name ? `${e.short_name} v${e.version}` : e.version} · {e.spatial} · {e.temporal} · {e.coverage} · auth: {e.auth}</p>
                      {e.caveats.map((c: string) => <p key={c} style={{ margin: '2px 0' }}>⚠ {c}</p>)}
                      {e.status === 'analysis_ready' && e.variables.map((v: any) => (
                        <label key={v.code} className="chk"><input type="checkbox" disabled={!inv} checked={!!inv?.config.variables.includes(v.code)} onChange={() => toggleVar(v.code)} /><span><code>{v.code}</code> {v.name} ({v.units}) — {v.definition}</span></label>
                      ))}
                      <a href={e.source_url} target="_blank" rel="noreferrer">Official metadata ↗</a>
                    </div>
                  </details>
                ))}
              </div>
              {catQ.length > 2 && <button className="btn sm" style={{ marginTop: 6 }} onClick={async () => { try { setCmr(await api.get<any[]>(`/api/catalog/cmr?q=${encodeURIComponent(catQ)}`)) } catch (e) { fail(e) } }}>Live NASA CMR search</button>}
              {cmr && <div className="small" style={{ marginTop: 6 }}>{cmr.length === 0 && <p className="muted">No CMR results.</p>}{cmr.map(c => <p key={c.concept_id} style={{ margin: '3px 0' }}><span className="badge b-neutral">metadata only</span> {c.title?.slice(0, 90)} <span className="muted">{c.data_center}</span></p>)}</div>}
            </div>
          </>
        )}
      </nav>

      {/* ---------------------------------------------- map */}
      <main className="mapwrap">
        <MapView geometry={geometry} support={r0?.spatial_support || null} cellCenters={r0?.cell_centers || []} eventPoint={eventPoint}
          layers={inv ? layers : { ...DEFAULT_LAYERS, grid: false }} imageryDate={imageryDate} imageryDateB={imageryDateB} imageryMix={imageryMix} flyKey={flyKey}
          compareMode={compareMode} swipe={imagerySwipe} onSwipe={v => patchView({ imagery_swipe: +v.toFixed(3) })}
          onImageryStatus={(side, st) => setImgState(s => (s[side] === st ? s : { ...s, [side]: st }))} highlight={highlight}
          center={inv?.config.view.center || [10, 20]} zoom={inv?.config.view.zoom || 1.6}
          onView={(c, z) => inv && (c[0] !== inv.config.view.center[0] || c[1] !== inv.config.view.center[1] || z !== inv.config.view.zoom) && patchView({ center: c, zoom: z, camera_saved: true })} />
        {health === 'down' && <div className="map-status" style={{ borderColor: 'var(--red)' }}>Backend unreachable — start the server (see README).</div>}
        {!inv && !preview && (
          <div className="map-status" style={{ top: 'auto', bottom: 70, right: '50%', transform: 'translateX(50%)', maxWidth: 520, padding: 14 }}>
            <b style={{ color: 'var(--text)' }}>What is changing here, which historical experiences are relevant, and what would change that assessment?</b>
            <p style={{ margin: '6px 0 0' }}>Open one of four source-backed case files on the left, or investigate a new place with the same NASA data and evidence pipeline.</p>
          </div>
        )}
        {traceId && inv && <TraceView key={traceId + inv.current_revision_id} invId={inv.id} interventionId={traceId} changed={changedNodes} initialSel={nodeId}
          onSelectClaim={id => { setNodeId(id); setTrail(t => [...t.filter(x => x !== id), id].slice(-10)); patchView({ selected_node: id }) }} onClose={closeTrace} onNode={id => { closeTrace(); showNode(id) }} onFocusFinding={focusFinding} />}
        {compare && <CompareView cases={cases} invs={invList} initialA={inv ? (inv.config.place.case_id ? `case:${inv.config.place.case_id}` : `inv:${inv.id}`) : `case:${cases[0]?.id}`} onClose={() => setCompare(false)} />}
      </main>

      {/* ---------------------------------------------- timeline */}
      {hasResults && inv && meta && (
        <section className="timeline" aria-label="Environmental time series">
          <Timeline results={results!.batch!.results} selected={selVar} onSelect={v => { setSelVar(v); patchView({ selected_variable: v }) }}
            events={caseOf ? [{ start: caseOf.event_start.slice(0, 7), end: caseOf.event_end.slice(0, 7), label: caseOf.event_name.split(',')[0] }] : []}
            period={inv.config.period} bounds={meta.period_bounds} onApplyWindow={applyWindow} busy={busy === 'acquire'} focus={focus}
            findingIdFor={v => results!.batch!.finding_ids.find(f => f.endsWith('-' + v))} onInspectFinding={showNode} />
        </section>
      )}

      {/* ---------------------------------------------- inspector */}
      <aside className={`inspector ${inspOpen ? '' : 'collapsed'}`} aria-label="Evidence inspector">
        <div className="tabs" role="tablist">
          {TABS.filter(([t]) => t === 'case' ? !!caseOf : !!inv).map(([t, l]) => (
            <button key={t} role="tab" className="tab" aria-selected={tab === t} onClick={() => switchTab(t)}>{l}{t === 'leads' && match ? ` (${match.leads.length})` : ''}</button>
          ))}
        </div>
        <div className="insp-body" key={tab}>
          {!inv && !preview && (
            <div className="empty">
              <h3>Start an investigation</h3>
              <p>Each case file opens its location, event, documented responses and original sources. NASA trend findings are computed only when you acquire data.</p>
              {meta && <p className="small muted">{meta.catalog_counts.entries} catalog entries · {meta.catalog_counts.analysis_ready_adapters} numerical adapter (NASA POWER) · {meta.catalog_counts.imagery_adapters} imagery layer (GIBS) · copilot: {meta.llm.available ? meta.llm.model : 'Guided analysis (no model key)'}</p>}
              <div className="row wrap">
                <button className="btn primary" onClick={openDemo} disabled={busy === 'open'}>{busy === 'open' ? 'Preparing…' : 'Open demo investigation'}</button>
                <button className="btn" onClick={() => setNewPlace(true)}>Investigate another place</button>
              </div>
              <p className="small muted">Demo: Camp Fire 2018 — real NASA trends, MODIS 2018-11-08 vs 2018-10-25, one labelled planning assumption that changes a planning lead.</p>
            </div>
          )}
          {tab === 'case' && caseOf && <CasePanel c={caseOf} busy={busy === 'open'} onOpen={() => inv ? switchTab('analysis') : createFromCase(caseOf)} onNode={id => inv ? showNode(id) : say('Open the investigation to inspect graph evidence.')} />}
          {inv && meta && tab === 'analysis' && <AnalysisPanel inv={inv} results={results} busy={busy === 'acquire'} onAcquire={acquire} selectedVar={selVar} onSelectVar={v => { setSelVar(v); patchView({ selected_variable: v }) }} onNode={showNode} acqEvents={acqEvents} />}
          {inv && meta && tab === 'leads' && <LeadsPanel inv={inv} meta={meta} match={match} busy={busy === 'match'} onRun={runMatch} onTrace={trace} onNode={id => showNode(id)} onRevise={revise} hasResults={hasResults}
            change={change} onDismissChange={() => { setChange(null); patchView({ last_change: null }) }} />}
          {inv && meta && tab === 'copilot' && <CopilotPanel key={inv.id} invId={inv.id} meta={meta} onNode={showNode} onTab={t => switchTab(t as Tab)} />}
          {inv && tab === 'evidence' && <EvidencePanel nodeId={nodeId} onNode={id => showNode(id)} disputed={inv.state.disputed} onFocusFinding={focusFinding}
            trail={trail} onTrail={id => showNode(id, true)}
            onShowInGraph={n => {
              const v = n.props?.variable
              const lead = match?.leads.find(l => l.features.some(f => f.feature === `signal:${v}` || f.evidence.includes(n.id))) || match?.leads.find(l => l.intervention_id === n.id) || match?.leads[0]
              if (lead) trace(n.type === 'Intervention' ? n.id : lead.intervention_id); else say('Find precedents first (Leads tab) to build an evidence graph.', true)
            }}
            onDispute={(id, on) => { const why = window.prompt(on ? 'Why is this claim disputed?' : 'Why remove the dispute?'); if (why) revise({ kind: on ? 'dispute' : 'undispute', node_id: id, rationale: why }) }} />}
          {inv && meta && tab === 'changes' && <ChangesPanel inv={inv} meta={meta} onRevise={revise} onActivate={activate} match={match} onNode={showNode} />}
        </div>
        <footer className="small muted" style={{ borderTop: '1px solid var(--line)', padding: '6px 12px' }} role="status" aria-live="polite">
          {busy ? <span className="row"><span className="spinner" />{busy === 'acquire' ? 'Acquiring / analysing…' : busy === 'match' ? 'Evaluating precedents…' : 'Working…'}</span>
            : health === 'down' ? 'Server unreachable' : focusState ? (
              <span className="focusbar" data-testid="focus-bar" title="Canonical focus shared by all panels">
                <span><b>{focusState.investigation}</b></span>
                <span>R{focusState.revisionSeq}</span>
                {focusState.observation && layers.imagery && <span>obs {focusState.observationLabel ? `${focusState.observationLabel} ` : ''}{focusState.observation}</span>}
                {focusState.claim && <button className="cite" onClick={() => showNode(focusState.claim!)} title="Selected claim">{focusState.claim.length > 22 ? focusState.claim.slice(0, 22) + '…' : focusState.claim}</button>}
                {focusState.graph && <span>graph {focusState.graph}</span>}
              </span>
            ) : health === 'ok' ? 'Server ok' : 'Connecting…'}
        </footer>
      </aside>

      {newPlace && meta && <NewPlaceDialog meta={meta} onClose={() => setNewPlace(false)} onCreate={async body => {
        const i = await api.post<Investigation>('/api/investigations', body)
        setNewPlace(false); await refreshList(); await openInv(i.id); say('Footprint confirmed. Acquiring NASA data…')
        setBusy('acquire')
        try { const b = await api.post<any>(`/api/investigations/${i.id}/analyze`, {}); setAcqEvents(b.events || []); await loadResults(i.id); setMatch(await api.get<MatchRun>(`/api/investigations/${i.id}/match`)) } catch (e) { fail(e) } finally { setBusy(null) }
      }} />}
      {palette && <Palette cmds={cmds} onClose={() => setPalette(false)} />}
      {toast && <div className={`toast ${toast.err ? 'err' : ''}`} role={toast.err ? 'alert' : 'status'}>{toast.msg}</div>}
    </div>
  )
}
