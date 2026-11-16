import { useEffect, useRef, useState } from 'react'
import type { Cite, CopilotRun, Meta } from './api'
import { api } from './api'

const SUGGEST = [
  'What is changing here, and which historical experiences are relevant?',
  'What can be learned from another flood case, and what does not transfer?',
  'Has precipitation changed since 2001?',
]

export default function CopilotPanel({ invId, meta, onNode, onTab }: { invId: string; meta: Meta; onNode: (id: string) => void; onTab: (t: string) => void }) {
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<'guided' | 'llm'>(meta.llm.available ? 'llm' : 'guided')
  const [runs, setRuns] = useState<CopilotRun[]>([])
  const [err, setErr] = useState<string | null>(null)
  const poll = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    api.get<any[]>(`/api/investigations/${invId}/copilot`).then(async list => {
      const full = await Promise.all(list.slice(-4).map(r => api.get<CopilotRun>(`/api/copilot/${r.id}`)))
      if (alive) setRuns(full)
    }).catch(() => {})
    return () => { alive = false; if (poll.current) window.clearInterval(poll.current) }
  }, [invId])

  const running = runs.find(r => r.status === 'running')
  const ask = async (question: string) => {
    setErr(null)
    try {
      const { run_id } = await api.post<{ run_id: string }>(`/api/investigations/${invId}/copilot`, { question, mode })
      setRuns(rs => [...rs, { id: run_id, status: 'running', mode, question, answer: null, error: null, events: [] }])
      setQ('')
      track(run_id)
    } catch (e: any) { setErr(e.message) }
  }
  const track = (rid: string) => {
    if (poll.current) window.clearInterval(poll.current)
    poll.current = window.setInterval(async () => {
      try {
        const r = await api.get<CopilotRun>(`/api/copilot/${rid}`)
        setRuns(rs => rs.map(x => (x.id === rid ? r : x)))
        if (r.status !== 'running' && poll.current) { window.clearInterval(poll.current); poll.current = null }
      } catch { /* keep polling */ }
    }, 450)
  }
  const openEvent = (e: CopilotRun['events'][0]) => {
    const p = e.payload || {}
    if (p.artifact_id) onNode(p.artifact_id)
    else if (p.finding_ids?.length) onNode(p.finding_ids[0])
    else if (p.bundle_id) onNode(p.bundle_id.replace(/^bnd-/, 'bnd-'))
    else if (p.analysis_id) onTab('analysis')
    else if (p.match_run_id) onTab('leads')
    else if (p.event_ids?.length) onNode(p.event_ids[0])
  }
  const clickable = (e: CopilotRun['events'][0]) => {
    const p = e.payload || {}
    return !!(p.artifact_id || p.finding_ids?.length || p.analysis_id || p.match_run_id || p.event_ids?.length)
  }

  return (
    <div>
      <div className="sheet" style={{ padding: 10 }}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
          <div className="seg" role="group" aria-label="Copilot mode" style={{ background: '#fff', borderColor: 'var(--paper-line)' }}>
            <button aria-pressed={mode === 'llm'} disabled={!meta.llm.available} onClick={() => setMode('llm')} title={meta.llm.available ? `Server-side model ${meta.llm.model}` : meta.llm.reason || ''} style={{ color: 'var(--paper-text)' }}>Copilot</button>
            <button aria-pressed={mode === 'guided'} onClick={() => setMode('guided')} title="Deterministic templates over the same tools; no language model" style={{ color: 'var(--paper-text)' }}>Guided analysis</button>
          </div>
          {!meta.llm.available && <span className="small muted" title={meta.llm.reason || ''}>Model key not configured</span>}
        </div>
        <textarea className="input" style={{ background: '#fff', color: 'var(--paper-text)', borderColor: 'var(--paper-line)' }} rows={2} value={q} placeholder="Ask about change, precedents, transfer…"
          onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && q.trim() && !running) { e.preventDefault(); ask(q.trim()) } }} aria-label="Question" />
        <div className="row wrap" style={{ marginTop: 6, justifyContent: 'space-between' }}>
          <div className="row wrap">{SUGGEST.map(s => <button key={s} className="btn sm" disabled={!!running} onClick={() => ask(s)} title={s}>{s.slice(0, 28)}…</button>)}</div>
          {running
            ? <button className="btn sm warn" onClick={() => api.post(`/api/copilot/${running.id}/cancel`)}>Cancel</button>
            : <button className="btn sm primary" disabled={!q.trim()} onClick={() => ask(q.trim())}>Ask</button>}
        </div>
        {err && <p className="small" style={{ color: 'var(--red-ink)' }}>{err}</p>}
      </div>

      {[...runs].reverse().map(r => (
        <div key={r.id} style={{ marginBottom: 14 }}>
          <p className="small" style={{ margin: '4px 0' }}><b>Q:</b> {r.question}</p>
          <details className="events on-dark" aria-label="Execution log" open={r.status === 'running' || undefined}>
            <summary className="small muted" style={{ cursor: 'pointer', padding: '2px 6px' }}>Execution log · {r.events.length} real events · {r.events.filter(e => e.type === 'tool_call').length} tool calls{r.events.some(e => e.type === 'cache_cached') ? ' · cache reused' : ''}</summary>
            {r.events.map(e => (
              <button key={e.seq} className="ev" disabled={!clickable(e)} onClick={() => openEvent(e)} title={clickable(e) ? 'Open result' : undefined}>
                <span className={`dot ${e.type.includes('fail') || e.type.includes('error') ? 'err' : e.type.includes('snapshot') || e.type === 'tool_call' ? 'warn' : 'ok'}`} />
                <span>{e.label}</span>
                <span className="d">{e.duration_ms != null ? `${e.duration_ms} ms` : ''}</span>
              </button>
            ))}
            {r.status === 'running' && <div className="ev" style={{ cursor: 'default' }}><span className="spinner" /><span>Running…</span><span /></div>}
          </details>
          {r.status === 'error' && <div className="empty"><h3>Run failed</h3><p>{r.error?.message || 'Error'}</p><button className="btn sm" onClick={() => ask(r.question)}>Retry</button></div>}
          {r.status === 'cancelled' && <p className="small muted">Cancelled. Completed tool results remain persisted; nothing is written twice on retry.</p>}
          {r.answer && <Answer a={r.answer} onNode={onNode} />}
        </div>
      ))}
    </div>
  )
}

function Answer({ a, onNode }: { a: NonNullable<CopilotRun['answer']>; onNode: (id: string) => void }) {
  const sec = (title: string, items: Cite[]) => items.length > 0 && (
    <>
      <h4>{title}</h4>
      <ul>{items.map((it, i) => <li key={i}>{it.text} {it.cites.map(c => <button key={c} className="cite" onClick={() => onNode(c)} title={`Open ${c}`}>{c.length > 22 ? c.slice(0, 22) + '…' : c}</button>)}</li>)}</ul>
    </>
  )
  return (
    <div className="sheet answer">
      <div className="row" style={{ justifyContent: 'space-between' }}><span className="small muted">{a.label}</span></div>
      {sec('Findings', a.findings)}
      {sec('Relevant precedents', a.precedents)}
      {sec('Mismatches / unknowns', a.mismatches_unknowns)}
      {sec('Next evidence', a.next_evidence)}
      {a.removed_claims?.length > 0 && <details className="small muted"><summary>{a.removed_claims.length} unsupported claim(s) removed before display</summary>{a.removed_claims.map((r: any, i: number) => <p key={i}>{r.reason}: “{r.text.slice(0, 120)}”</p>)}</details>}
    </div>
  )
}
