// Thin typed client. All field names mirror the Python JSON contracts (snake_case).
export type Geometry =
  | { type: 'bbox'; west: number; south: number; east: number; north: number }
  | { type: 'point'; lon: number; lat: number }

export interface SourceRecord {
  id: string; url: string; publisher: string; title: string; published: string | null
  retrieved: string; locator: string; status: string
}
export interface Intervention {
  id: string; title: string; category: string; objective: string; status: string
  prerequisites?: string[]; requirements?: { id: string; decisive?: boolean; why?: string }[]
  scale: string; time_horizon?: string; constraints?: string[]; reported_outcome: string | null
  outcome_type: string; limitations?: string[]; source_id: string; locator: string; published?: string
  signals?: { variable: string; direction: string; note?: string }[]
}
export interface CaseFile {
  id: string; display_name: string; event_name: string; event_start: string; event_end: string
  event_point?: { lon: number; lat: number; label: string }
  hazard_mechanism: string; summary: string; sources: SourceRecord[]
  event_facts: { claim: string; source_id: string; locator?: string; excerpt?: string | null }[]
  interventions: Intervention[]
  analysis_geometry: Geometry; geometry_origin: string; scale: string; questions: string[]
  variables: string[]; mechanism: { id: string; label: string; family: string; definition: string }
  computed_findings?: GNode[]
}
export interface Place {
  name: string; case_id: string | null; node_id: string; geometry: Geometry; geometry_origin?: string
  scale?: string | null; event_point?: { lon: number; lat: number; label: string }
}
export interface ReqState { state: string; basis: string; note: string; via?: string; source_id?: string; locator?: string; revision_id?: string }
export interface Revision { id: string; prior_id: string | null; seq: number; kind: string; changes: any; rationale: string; created_at: string }
export interface Investigation {
  id: string; title: string; current_revision_id: string
  config: {
    place: Place; question: string; variables: string[]; period: { start: string; end: string }
    view: {
      center: [number, number]; zoom: number; layers: Record<string, any>; imagery_date: string | null; inspector_tab: string; selected_variable?: string
      imagery_date_b?: string | null; imagery_mix?: number; selected_node?: string | null; evidence_trail?: string[]
      last_change?: { from: string; to: string } | null
    }
    current_batch?: string
  }
  state: { mechanism: string | null; scale: string | null; requirements: Record<string, ReqState>; disputed: string[] }
  revisions: Revision[]
}
export interface SeriesPt { date: string; value: number | null; anomaly: number | null; monthly_total_mm?: number | null }
export interface TrendResult {
  variable: string; longname: string; units: string; period: { start: string; end: string }
  n_months_requested: number; n_valid: number; n_missing: number; coverage: number
  baseline: { start: string; end: string; definition: string }
  series: SeriesPt[]; method: any; mode: 'inferential' | 'descriptive'
  slope_per_decade?: number; ci95_per_decade?: [number, number]; se_per_decade?: number
  p_value?: number; q_value?: number | null; significant_at_0_05?: boolean; significant_bh?: boolean; statement?: string
  trend_line?: { date: string; value: number }[]; sensitivity?: any; diagnostics?: any
  limitation?: string; suggested_interval?: { start: string; end: string; months: number } | null; descriptive?: any
  artifact_id: string; artifact_sha256: string; spatial_support: any; cell_centers: [number, number][]; conversions: string[]
  family?: any
}
export interface Artifact {
  id: string; cache_key: string; version: number; variable: string; sha256: string; retrieved_at: string; origin: string
  manifest: any
}
export interface Results {
  batch: { id: string; results: TrendResult[]; artifact_ids: string[]; finding_ids: string[]; created_at: string } | null
  artifacts?: Artifact[]; association?: any
}
export interface GNode {
  id: string; type: string; label: string; status: string; props: any; event_time?: string | null
  published_time?: string | null; ingested_at?: string; scope?: string; provenance?: any[]; bundles?: Bundle[]
  layer?: number; assessment?: { state: string; detail: string } | null
}
export interface GEdge { id: string; src: string; dst: string; type: string; status: string; props: any }
export interface Bundle { id: string; assertion_type: string; evidence_status: string; label: string; version: number; time_scope: string | null; props: any; members: { node_id: string; role: string; type: string; label: string; status: string }[] }
export interface Feature { feature: string; state: string; weight: number; detail: string; evidence: string[]; kind: string }
export interface Evaluation {
  intervention_id: string; title: string; source_case: string; source_place: string; implementation_status: string
  category: string; scale: string; outcome_evidence_type: string; outcomes: { id: string; label: string; type: string }[]
  conflicts: { id: string; label: string }[]; source_id: string; locator: string; features: Feature[]
  matched: Feature[]; mismatches: Feature[]; unknowns: Feature[]; match_score: number; coverage: number
  eligibility: string; exclusion_reasons: string[]; next_evidence: string[]; score_note: string
}
export interface MatchRun {
  id: string; reused: boolean; investigation_id: string; revision_id: string; graph_version: string; rule_version: string
  context: any; leads: Evaluation[]; other_candidates: Evaluation[]; excluded: Evaluation[]; insufficient_context: boolean
  query: { description: string; interventions_considered: number; edge_types: string[] }
}
export interface Meta {
  mechanisms: Record<string, { label: string; family: string; definition: string; typical_scale: string }>
  requirements: Record<string, { label: string; definition: string }>
  variables: Record<string, string>; period_bounds: { start: string; end: string }
  llm: { available: boolean; model: string; reason: string | null }
  catalog_counts: { entries: number; analysis_ready_adapters: number; imagery_adapters: number }
  graph: any
}
export interface CopilotEvent { seq: number; type: string; label: string; payload: any; duration_ms: number | null; at: string }
export interface CopilotRun {
  id: string; status: string; mode: string; question: string
  answer: null | { findings: Cite[]; precedents: Cite[]; mismatches_unknowns: Cite[]; next_evidence: Cite[]; removed_claims: any[]; label: string; mode: string }
  error: any; events: CopilotEvent[]
}
export interface Cite { text: string; cites: string[] }

export class ApiErr extends Error {
  code: string
  constructor(code: string, message: string) { super(message); this.code = code }
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  let r: Response
  try {
    r = await fetch(url, {
      method, credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiErr('network', 'Cannot reach the EarthInspect server.')
  }
  const text = await r.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { /* non-JSON */ }
  if (!r.ok) {
    const e = data?.error
    throw new ApiErr(e?.code || `http_${r.status}`, e?.message || `Request failed (${r.status}).`)
  }
  return data as T
}

export const api = {
  get: <T,>(u: string) => req<T>('GET', u),
  post: <T,>(u: string, b?: unknown) => req<T>('POST', u, b ?? {}),
  patch: <T,>(u: string, b: unknown) => req<T>('PATCH', u, b),
}

export const fmt = (n: number | null | undefined, d = 3) =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d)
export const fmtP = (p: number | null | undefined) =>
  p === null || p === undefined ? '—' : p < 0.0001 ? '<0.0001' : p.toFixed(4)
export const humanize = (s: string | null | undefined) => (s || '').replace(/_/g, ' ')
