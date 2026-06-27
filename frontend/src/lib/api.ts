const BASE = '/api'

export interface Preferences {
  greenness: number
  steps: number
  commercial: number
}

export interface ScoreBreakdown {
  g_score: number
  atom_economy: number
  e_factor: number
  pmi: number
  chem21_score: number
  step_penalty: number
  v_score?: number
  c_score?: number
  h_score?: number
  route_score?: number
  weights?: { alpha: number; beta: number; gamma: number; delta: number }
}

export interface HallucinationReport {
  smiles: string
  ht_type: string | null
  message: string
  severity: 'ok' | 'warn' | 'block'
  details: Record<string, unknown>
}

export interface ReasoningStep {
  step: number
  event: string
  detail: string
  smiles: string | null
  severity: 'ok' | 'warn' | 'block' | null
}

export interface RouteResult {
  route_id: string
  intermediates: string[]
  n_steps: number
  product: string
  reactants: string[]
  g_score: number
  v_score: number
  c_score: number
  h_score: number
  route_score: number
  hallucination_type: string | null
  score_breakdown: ScoreBreakdown
  explanation: string
  source: string
  tree: RouteNode
  repaired: boolean
  hallucination_reports?: HallucinationReport[]
  reasoning_steps?: ReasoningStep[]
}

export interface RouteNode {
  smiles: string
  type: 'mol' | 'reaction' | string
  depth: number
  children: RouteNode[]
  node_status?: 'accepted' | 'rejected' | 'repaired' | 'target'
  c_score?: number
  ht_type?: string | null
  route_id?: string
  route_rank?: number
  is_rejected_branch?: boolean
}

export interface Precedent {
  text: string
  reaction_class: string
  reactants: string
  product: string
  reaction_smiles: string
  similarity: number
  distance?: number
}

export interface ConstraintState {
  solvents: string[]
  rxn_types: string[]
  excluded_count: number
  excluded_sample: string[]
}

export interface SynthesizeResponse {
  target_smiles: string
  canonical_smiles: string
  routes: RouteResult[]
  precedents: Precedent[]
  constraint_state?: ConstraintState
  error?: string
}

export interface SteerResponse {
  target_smiles: string
  canonical_smiles: string
  routes: RouteResult[]
  precedents: Precedent[]
  constraint_state?: ConstraintState
  applied_action: string
  pinned: string[]
  blacklisted: string[]
  error?: string
}

export async function synthesize(
  smiles: string,
  preferences: Preferences,
  pinned?: string[],
  blacklisted?: string[],
): Promise<SynthesizeResponse> {
  const res = await fetch(`${BASE}/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smiles, preferences, pinned, blacklisted }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

export async function steer(
  target_smiles: string,
  action: 'pin' | 'reject',
  smiles: string,
  current_pinned: string[],
  current_blacklisted: string[],
  preferences: Preferences,
): Promise<SteerResponse> {
  const res = await fetch(`${BASE}/steer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_smiles,
      action,
      smiles,
      current_pinned,
      current_blacklisted,
      preferences,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

export async function getWeights() {
  const res = await fetch(`${BASE}/weights`)
  if (!res.ok) throw new Error('Failed to fetch weights')
  return res.json() as Promise<{ alpha: number; beta: number; gamma: number; delta: number }>
}

export async function setWeights(w: { alpha: number; beta: number; gamma: number; delta: number }) {
  const res = await fetch(`${BASE}/weights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(w),
  })
  if (!res.ok) throw new Error('Failed to set weights')
  return res.json()
}
