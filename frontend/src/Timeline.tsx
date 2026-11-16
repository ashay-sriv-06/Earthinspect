import { useEffect, useMemo, useRef, useState } from 'react'
import type { TrendResult } from './api'
import { fmt } from './api'

interface Props {
  results: TrendResult[]
  selected: string | null
  onSelect: (v: string) => void
  events: { start: string; end: string; label: string }[]
  period: { start: string; end: string }
  bounds: { start: string; end: string }
  onApplyWindow: (start: string, end: string) => void
  busy: boolean
  focus: { start: string; end: string } | null
}

const mi = (d: string) => +d.slice(0, 4) * 12 + (+d.slice(5, 7) - 1)
const md = (i: number) => `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`

export default function Timeline(p: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(800)
  const [mode, setMode] = useState<'anomaly' | 'value'>('anomaly')
  const [brush, setBrush] = useState<[number, number] | null>(null)
  const drag = useRef<number | null>(null)
  const H = 140, padL = 44, padR = 12, padT = 10, padB = 20

  useEffect(() => {
    if (!wrap.current) return
    const ro = new ResizeObserver(e => setW(Math.max(300, e[0].contentRect.width)))
    ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  const r = p.results.find(x => x.variable === p.selected) || p.results[0]
  const a0 = mi(p.period.start), a1 = mi(p.period.end)
  const X = (i: number) => padL + ((w - padL - padR) * (i - a0)) / Math.max(1, a1 - a0)
  const inv = (x: number) => Math.round(a0 + ((x - padL) / (w - padL - padR)) * (a1 - a0))

  const { path, lo, hi, tl } = useMemo(() => {
    if (!r) return { path: '', lo: 0, hi: 1, tl: '' }
    const vals = r.series.map(s => (mode === 'anomaly' ? s.anomaly : s.value)).filter((v): v is number => v !== null)
    let lo = Math.min(...vals), hi = Math.max(...vals)
    if (!isFinite(lo)) { lo = 0; hi = 1 }
    if (hi === lo) hi = lo + 1
    const Y = (v: number) => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo))
    let d = '', pen = false
    r.series.forEach(s => {
      const v = mode === 'anomaly' ? s.anomaly : s.value
      if (v === null) { pen = false; return }
      d += `${pen ? 'L' : 'M'}${X(mi(s.date)).toFixed(1)},${Y(v).toFixed(1)}`
      pen = true
    })
    let tl = ''
    if (r.trend_line && mode === 'anomaly') {
      const f = r.trend_line[0], l = r.trend_line[r.trend_line.length - 1]
      tl = `M${X(mi(f.date)).toFixed(1)},${Y(f.value).toFixed(1)}L${X(mi(l.date)).toFixed(1)},${Y(l.value).toFixed(1)}`
    }
    return { path: d, lo, hi, tl }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [r, mode, w, p.period.start, p.period.end])

  if (!r) return null
  const Y = (v: number) => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo))
  const years: number[] = []
  for (let y = +p.period.start.slice(0, 4); y <= +p.period.end.slice(0, 4); y++) years.push(y)
  const step = Math.ceil(years.length / Math.max(4, Math.floor((w - 60) / 60)))
  const missing = r.series.filter(s => s.value === null).map(s => mi(s.date))

  const down = (e: React.PointerEvent<SVGSVGElement>) => {
    const x = e.clientX - (e.currentTarget.getBoundingClientRect().left)
    if (x < padL) return
    drag.current = Math.max(a0, Math.min(a1, inv(x)))
    setBrush([drag.current, drag.current])
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (drag.current === null) return
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left
    const v = Math.max(a0, Math.min(a1, inv(x)))
    setBrush([Math.min(drag.current, v), Math.max(drag.current, v)])
  }
  const up = () => { drag.current = null; if (brush && brush[1] - brush[0] < 2) setBrush(null) }
  const bMonths = brush ? brush[1] - brush[0] + 1 : 0

  return (
    <div ref={wrap}>
      <div className="tl-head">
        <span className="t">{r.longname} <span className="muted">({r.units}{mode === 'anomaly' ? ', anomaly' : ''})</span></span>
        <div className="seg" role="group" aria-label="Variable">
          {p.results.map(x => <button key={x.variable} aria-pressed={x.variable === r.variable} onClick={() => p.onSelect(x.variable)}>{x.variable}</button>)}
        </div>
        <div className="seg" role="group" aria-label="Series view">
          <button aria-pressed={mode === 'anomaly'} onClick={() => setMode('anomaly')} title={`Departure from the ${r.baseline.start}–${r.baseline.end} calendar-month mean`}>Anomaly</button>
          <button aria-pressed={mode === 'value'} onClick={() => setMode('value')} title="Area-weighted monthly value as returned">Raw</button>
        </div>
        <span className="spacer" />
        {r.mode === 'inferential'
          ? <span className="small num" title="Slope from OLS + HAC; CI is uncertainty about the fitted slope">Trend <b>{fmt(r.slope_per_decade)}</b> {r.units}/decade [{fmt(r.ci95_per_decade?.[0])}, {fmt(r.ci95_per_decade?.[1])}]</span>
          : <span className="small" style={{ color: 'var(--amber)' }}>Descriptive only</span>}
        {brush ? (
          <>
            <span className="small num">{md(brush[0])} → {md(brush[1])} ({bMonths} mo){bMonths < 120 && <span style={{ color: 'var(--amber)' }}> · &lt;120: descriptive only</span>}</span>
            <button className="btn sm primary" disabled={p.busy} onClick={() => { p.onApplyWindow(md(brush[0]), md(brush[1])); setBrush(null) }}>Apply window</button>
            <button className="btn sm ghost" onClick={() => setBrush(null)}>Clear</button>
          </>
        ) : (
          (p.period.start !== p.bounds.start || p.period.end !== p.bounds.end) &&
          <button className="btn sm" disabled={p.busy} onClick={() => p.onApplyWindow(p.bounds.start, p.bounds.end)} title="Return to the full 2001–2024 window">Reset to {p.bounds.start.slice(0, 4)}–{p.bounds.end.slice(0, 4)}</button>
        )}
      </div>
      <svg className="tl-svg" height={H} width={w} onPointerDown={down} onPointerMove={move} onPointerUp={up} role="img"
        aria-label={`${r.variable} monthly series ${p.period.start} to ${p.period.end}. Drag to preview a window, then Apply.`} style={{ cursor: 'crosshair', touchAction: 'none' }}>
        {p.events.map(e => {
          const s = Math.max(a0, mi(e.start)), en = Math.min(a1, mi(e.end))
          if (en < a0 || s > a1) return null
          return <g key={e.label}><rect x={X(s)} y={padT} width={Math.max(2, X(en) - X(s))} height={H - padT - padB} fill="rgba(213,122,108,.18)" /><text x={X(s) + 3} y={padT + 9} style={{ fill: 'var(--red)' }}>{e.label}</text></g>
        })}
        {p.focus && <rect x={X(Math.max(a0, mi(p.focus.start)))} y={padT} width={Math.max(2, X(Math.min(a1, mi(p.focus.end))) - X(Math.max(a0, mi(p.focus.start))))} height={H - padT - padB} fill="none" stroke="var(--teal)" strokeDasharray="3 3" />}
        {missing.map(i => <rect key={i} x={X(i) - 1} y={H - padB - 4} width={2} height={4} fill="var(--amber)"><title>Missing month {md(i)}</title></rect>)}
        {lo < 0 && hi > 0 && <line x1={padL} x2={w - padR} y1={Y(0)} y2={Y(0)} stroke="var(--line)" strokeDasharray="3 3" />}
        <text x={4} y={padT + 8}>{hi.toFixed(1)}</text>
        <text x={4} y={H - padB}>{lo.toFixed(1)}</text>
        {years.filter((_, i) => i % step === 0).map(y => <text key={y} x={X(y * 12)} y={H - 4}>{y}</text>)}
        <path d={path} fill="none" stroke="#8c9ba6" strokeWidth={1} />
        {tl && <path d={tl} stroke="var(--teal)" strokeWidth={2.2} />}
        {brush && <rect x={X(brush[0])} y={padT} width={Math.max(1, X(brush[1]) - X(brush[0]))} height={H - padT - padB} fill="var(--teal-dim)" stroke="var(--teal)" />}
      </svg>
    </div>
  )
}
