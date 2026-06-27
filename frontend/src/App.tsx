import { useState, useCallback } from 'react'
import { Search, Loader2, AlertCircle, FlaskConical, Pin, CircleX, GitCompare, FileText, GitBranch, AlertTriangle, ChevronDown, ChevronUp, ListOrdered } from 'lucide-react'
import { synthesize, steer, type RouteResult, type RouteNode, type Preferences, type ConstraintState, type ReasoningStep } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { RouteCard } from '@/components/RouteCard'
import { ExplanationPanel } from '@/components/ExplanationPanel'
import { PreferenceSliders } from '@/components/PreferenceSliders'
import { SynthesisTree } from '@/components/SynthesisTree'
import { ConstraintTimeline } from '@/components/ConstraintTimeline'
import { FailureConsole } from '@/components/FailureConsole'
import { ReasoningTimeline } from '@/components/ReasoningTimeline'
import type { Precedent } from '@/lib/api'

const DEFAULT_PREFS: Preferences = { greenness: 0.5, steps: 0.3, commercial: 0.2 }

type Tab = 'explanation' | 'reasoning' | 'constraints' | 'failures'

/**
 * Builds visualization forest using annotated trees from backend.
 * Backend already injected c_score, node_status, ht_type, route_rank per node.
 * Merges routes at shared target root.
 */
function buildAnnotatedForest(routes: RouteResult[]): RouteNode | null {
  if (routes.length === 0) return null

  const primaryTree = routes[0].tree
  if (!primaryTree || !primaryTree.smiles) return null

  // Root = annotated target node from top-ranked route
  const root: RouteNode = {
    ...primaryTree,
    node_status: 'target',
    c_score: routes[0].c_score,
    route_rank: 1,
    children: [],
  }

  // Merge each route's subtree children under shared root
  routes.forEach((route, i) => {
    const routeTree = route.tree
    if (!routeTree) return
    const children = (routeTree.children ?? []).map((child: RouteNode) =>
      tagRouteRank(child, i + 1)
    )
    root.children.push(...children)
  })

  return root
}

function tagRouteRank(node: RouteNode, rank: number): RouteNode {
  return {
    ...node,
    route_rank: node.route_rank ?? rank,
    children: (node.children ?? []).map(c => tagRouteRank(c, rank)),
  }
}

export default function App() {
  const [smiles, setSmiles] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [routes, setRoutes] = useState<RouteResult[]>([])
  const [precedents, setPrecedents] = useState<Precedent[]>([])
  const [selected, setSelected] = useState<RouteResult | null>(null)
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS)
  const [pinned, setPinned] = useState<string[]>([])
  const [blacklisted, setBlacklisted] = useState<string[]>([])
  const [canonical, setCanonical] = useState('')
  const [constraintState, setConstraintState] = useState<ConstraintState | undefined>()
  const [constraintHistory, setConstraintHistory] = useState<ConstraintState[]>([])
  const [compareMode, setCompareMode] = useState(false)
  const [compareRoute, setCompareRoute] = useState<RouteResult | undefined>()
  const [activeTab, setActiveTab] = useState<Tab>('explanation')
  const [treeCollapsed, setTreeCollapsed] = useState(false)

  const run = useCallback(async (smi: string, pins: string[], blacks: string[]) => {
    if (!smi.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await synthesize(smi, prefs, pins, blacks)
      if (res.error) setError(res.error)
      setRoutes(res.routes)
      setPrecedents(res.precedents)
      setCanonical(res.canonical_smiles)
      setSelected(res.routes[0] ?? null)
      if (res.constraint_state) {
        setConstraintState(res.constraint_state)
        setConstraintHistory(h => [...h, res.constraint_state!])
      }
      setCompareRoute(undefined)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [prefs])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPinned([])
    setBlacklisted([])
    setConstraintHistory([])
    run(smiles, [], [])
  }

  const handleNodeAction = useCallback(async (nodeSmi: string, action: 'pin' | 'reject') => {
    if (!smiles) return
    setLoading(true)
    setError(null)
    try {
      const res = await steer(smiles, action, nodeSmi, pinned, blacklisted, prefs)
      if (action === 'pin') setPinned(res.pinned)
      else setBlacklisted(res.blacklisted)
      if (res.error) setError(res.error)
      setRoutes(res.routes)
      setPrecedents(res.precedents)
      setSelected(res.routes[0] ?? null)
      if (res.constraint_state) {
        setConstraintState(res.constraint_state)
        setConstraintHistory(h => [...h, res.constraint_state!])
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [smiles, pinned, blacklisted, prefs])

  const handleRouteSelect = (route: RouteResult) => {
    if (compareMode && selected && route.route_id !== selected.route_id) {
      setCompareRoute(selected)
      setSelected(route)
    } else {
      setSelected(route)
    }
  }

  const flaggedCount = routes.filter(r =>
    r.hallucination_type || r.repaired ||
    ((r as any).hallucination_reports ?? []).some((x: any) => x.severity !== 'ok')
  ).length

  const intermediates = selected?.intermediates ?? []

  // Build annotated forest from backend-enriched trees
  const forestTree = routes.length > 0 ? buildAnnotatedForest(routes) : null
  const reasoningSteps: ReasoningStep[] = selected?.reasoning_steps ?? []

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-950 px-6 py-3">
        <FlaskConical size={18} className="text-green-400 shrink-0" />
        <div className="flex flex-col leading-none">
          <span className="text-sm font-semibold text-zinc-100">EcoSynth</span>
          <span className="text-[10px] text-zinc-600">Neuro-Symbolic Green Retrosynthesis</span>
        </div>

        {constraintState && (
          <div className="ml-4 hidden items-center gap-2 lg:flex">
            <span className="text-[10px] text-zinc-600 uppercase tracking-wider">G_C^(k)</span>
            <Badge variant="outline" className="text-[10px] text-violet-400 border-violet-800/50">
              {constraintState.rxn_types.length} rxn types
            </Badge>
            <Badge variant="outline" className="text-[10px] text-blue-400 border-blue-800/50">
              {constraintState.solvents.length} solvents
            </Badge>
            {constraintState.excluded_count > 0 && (
              <Badge variant="danger" className="text-[10px]">
                {constraintState.excluded_count} excluded
              </Badge>
            )}
            {constraintHistory.length > 1 && (
              <Badge variant="outline" className="text-[10px] text-zinc-500">
                {constraintHistory.length} steps
              </Badge>
            )}
          </div>
        )}

        {canonical && (
          <Badge variant="outline" className="ml-auto font-mono text-[10px]">
            {canonical.slice(0, 36)}{canonical.length > 36 ? '…' : ''}
          </Badge>
        )}
      </header>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="flex gap-2 border-b border-zinc-800 bg-zinc-950 px-6 py-3">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            className="w-full rounded-lg border border-zinc-700 bg-zinc-800 py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder-zinc-500 focus:border-green-600 focus:outline-none transition-colors"
            placeholder="Target molecule SMILES — e.g. CC(=O)Oc1ccccc1C(=O)O (aspirin)"
            value={smiles}
            onChange={e => setSmiles(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={loading || !smiles.trim()} size="md">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
          {loading ? 'Planning…' : 'Synthesize'}
        </Button>
      </form>

      {/* Constraint chips */}
      {(pinned.length > 0 || blacklisted.length > 0) && (
        <div className="flex flex-wrap gap-2 border-b border-zinc-800 bg-zinc-950 px-6 py-2">
          {pinned.map(s => (
            <Badge key={s} variant="success" className="gap-1">
              <Pin size={9} />
              <span className="font-mono text-[10px]">{s.slice(0, 18)}</span>
              <button onClick={() => { const p = pinned.filter(x => x !== s); setPinned(p); run(smiles, p, blacklisted) }}
                className="ml-0.5 opacity-60 hover:opacity-100">×</button>
            </Badge>
          ))}
          {blacklisted.map(s => (
            <Badge key={s} variant="danger" className="gap-1">
              <CircleX size={9} />
              <span className="font-mono text-[10px]">{s.slice(0, 18)}</span>
              <button onClick={() => { const b = blacklisted.filter(x => x !== s); setBlacklisted(b); run(smiles, pinned, b) }}
                className="ml-0.5 opacity-60 hover:opacity-100">×</button>
            </Badge>
          ))}
        </div>
      )}

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto border-r border-zinc-800 p-4">
          <PreferenceSliders preferences={prefs} onChange={setPrefs} disabled={loading} />

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}

          {routes.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
                  {routes.length} Route{routes.length !== 1 ? 's' : ''} Found
                </p>
                {routes.length > 1 && (
                  <button
                    onClick={() => { setCompareMode(x => !x); setCompareRoute(undefined) }}
                    className={`flex items-center gap-1 rounded px-2 py-0.5 text-[10px] transition-colors ${compareMode ? 'bg-blue-900/50 text-blue-300' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    <GitCompare size={10} />
                    {compareMode ? 'Exit compare' : 'Compare'}
                  </button>
                )}
              </div>
              {compareMode && (
                <p className="rounded-lg bg-blue-950/30 border border-blue-800/30 px-2 py-1.5 text-[10px] text-blue-400">
                  Click two routes to compare them side by side.
                </p>
              )}
              {routes.map((r, i) => (
                <RouteCard
                  key={r.route_id}
                  route={r}
                  rank={i + 1}
                  selected={selected?.route_id === r.route_id}
                  onSelect={handleRouteSelect}
                  compareRoute={compareMode ? compareRoute : undefined}
                />
              ))}
            </div>
          )}

          {!loading && routes.length === 0 && smiles && !error && (
            <p className="text-center text-xs text-zinc-600">No routes returned.</p>
          )}
        </aside>

        {/* Main area */}
        <main className="flex flex-1 flex-col overflow-hidden">
          {selected && forestTree ? (
            <>
              {/* Synthesis tree — collapsible */}
              <div className="shrink-0 border-b border-zinc-800">
                <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-950">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
                    Retrosynthesis Routes · {routes.length} found
                  </span>
                  <button
                    onClick={() => setTreeCollapsed(x => !x)}
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    {treeCollapsed ? <><ChevronDown size={11} /> Expand</> : <><ChevronUp size={11} /> Collapse</>}
                  </button>
                </div>
                {!treeCollapsed && (
                  <SynthesisTree
                    tree={forestTree}
                    routes={routes}
                    gScore={selected.g_score}
                    vScore={selected.v_score}
                    pinned={pinned}
                    blacklisted={blacklisted}
                    constraintState={constraintState}
                    constraintHistory={constraintHistory}
                    onNodeAction={handleNodeAction}
                  />
                )}
              </div>

              {/* Tab bar */}
              <div className="flex shrink-0 items-center gap-1 border-b border-zinc-800 bg-zinc-950 px-4">
                {([
                  { id: 'explanation' as Tab, label: 'Explanation', icon: FileText, badge: null },
                  { id: 'reasoning' as Tab, label: 'Reasoning', icon: ListOrdered, badge: reasoningSteps.length > 0 ? reasoningSteps.length : null },
                  { id: 'constraints' as Tab, label: 'Constraint Graph', icon: GitBranch, badge: constraintHistory.length > 0 ? constraintHistory.length : null },
                  { id: 'failures' as Tab, label: 'Failure Console', icon: AlertTriangle, badge: flaggedCount > 0 ? flaggedCount : null },
                ] as const).map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[11px] font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'border-violet-500 text-violet-300'
                        : 'border-transparent text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    <tab.icon size={11} />
                    {tab.label}
                    {tab.badge !== null && (
                      <span className={`rounded-full px-1.5 py-px text-[9px] font-semibold ${
                        tab.id === 'failures'
                          ? 'bg-orange-900/60 text-orange-400'
                          : 'bg-violet-900/60 text-violet-400'
                      }`}>
                        {tab.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {/* Tab content — scrollable */}
              <div className="flex-1 overflow-y-auto">
                {activeTab === 'explanation' && (
                  <div className="p-4 panel-appear">
                    <ExplanationPanel route={selected} precedents={precedents} />
                  </div>
                )}
                {activeTab === 'reasoning' && (
                  <div className="p-4 panel-appear">
                    <ReasoningTimeline steps={reasoningSteps} />
                  </div>
                )}
                {activeTab === 'constraints' && (
                  <div className="p-4 panel-appear">
                    <ConstraintTimeline
                      current={constraintState}
                      intermediates={intermediates}
                      constraintHistory={constraintHistory.length > 0 ? constraintHistory : undefined}
                    />
                  </div>
                )}
                {activeTab === 'failures' && (
                  <div className="p-4 panel-appear">
                    <FailureConsole routes={routes} />
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 text-zinc-600 p-4">
              <FlaskConical size={48} strokeWidth={1} />
              <div className="text-center">
                <p className="text-sm font-medium text-zinc-500">Green Retrosynthesis Workstation</p>
                <p className="mt-1 text-xs text-zinc-700">Enter a SMILES string to plan a synthesis route</p>
                <p className="mt-0.5 text-xs text-zinc-800">Try: CC(=O)Oc1ccccc1C(=O)O (aspirin)</p>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3 max-w-sm w-full">
                {[
                  ['Dynamic Constraints', 'G_C^(k) updates every step'],
                  ['HT Classification', 'HT-01..HT-05 taxonomy'],
                  ['RouteScore', 'αG + βV + γC + δH'],
                  ['Branch Repair', 'Local subtree regeneration'],
                ].map(([title, desc]) => (
                  <div key={title} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                    <p className="text-[10px] font-semibold text-zinc-400">{title}</p>
                    <p className="text-[9px] text-zinc-600 mt-0.5">{desc}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
