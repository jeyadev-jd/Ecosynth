/**
 * Constraint Propagation Timeline
 * Shows G_C^(0) → G_C^(1) → G_C^(k) evolution as each intermediate is accepted.
 * Visualises which reaction types were pruned, which solvents were blocked.
 */
import { useEffect, useRef } from 'react'
import { ArrowDown, CheckCircle, XCircle, MinusCircle } from 'lucide-react'
import type { ConstraintState } from '@/lib/api'

interface PropagationStep {
  label: string              // e.g. "Target" or "Intermediate 1"
  smiles: string
  rxn_types: string[]
  solvents: string[]
  excluded_count: number
  pruned_rxn?: string[]      // types removed vs previous step
  pruned_solvents?: string[] // solvents removed vs previous step
  added_excluded?: string[]
}

interface Props {
  current: ConstraintState | undefined
  intermediates: string[]
  constraintHistory?: ConstraintState[]  // one per intermediate accepted
}

function diff<T>(before: T[], after: T[]): T[] {
  const a = new Set(after)
  return before.filter(x => !a.has(x))
}

function buildSteps(
  intermediates: string[],
  history: ConstraintState[] | undefined,
  current: ConstraintState | undefined,
): PropagationStep[] {
  if (!current) return []

  // If no history, synthesise a single "current" state entry
  if (!history || history.length === 0) {
    return [{
      label: 'Current state',
      smiles: intermediates[0] ?? '',
      rxn_types: current.rxn_types,
      solvents: current.solvents,
      excluded_count: current.excluded_count,
    }]
  }

  return history.map((state, i) => {
    const prev = history[i - 1]
    return {
      label: i === 0 ? 'Initial (target)' : `Step ${i}`,
      smiles: intermediates[i] ?? '',
      rxn_types: state.rxn_types,
      solvents: state.solvents,
      excluded_count: state.excluded_count,
      pruned_rxn: prev ? diff(prev.rxn_types, state.rxn_types) : [],
      pruned_solvents: prev ? diff(prev.solvents, state.solvents) : [],
      added_excluded: prev && state.excluded_count > prev.excluded_count
        ? state.excluded_sample.slice(prev.excluded_count)
        : [],
    }
  })
}

const RXN_COLORS: Record<string, string> = {
  oxidation:       '#f97316',
  reduction:       '#60a5fa',
  esterification:  '#22c55e',
  amide_formation: '#a78bfa',
  cross_coupling:  '#f59e0b',
  hydrogenation:   '#06b6d4',
  halogenation:    '#ec4899',
  grignard:        '#84cc16',
  aldol:           '#fb923c',
  michael:         '#818cf8',
  wittig:          '#34d399',
  suzuki:          '#fbbf24',
  buchwald_hartwig:'#c084fc',
  heck:            '#f87171',
  sonogashira:     '#38bdf8',
  epoxidation:     '#4ade80',
}

function rxnColor(t: string): string {
  return RXN_COLORS[t] ?? '#71717a'
}

function RxnChip({ type, faded }: { type: string; faded?: boolean }) {
  const color = rxnColor(type)
  return (
    <span
      className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-medium border transition-opacity duration-500"
      style={{
        color: faded ? '#52525b' : color,
        borderColor: faded ? '#27272a' : color + '44',
        background: faded ? 'transparent' : color + '0f',
        opacity: faded ? 0.4 : 1,
        textDecoration: faded ? 'line-through' : 'none',
      }}
    >
      {type.replace(/_/g, ' ')}
    </span>
  )
}

function SolventChip({ name, faded }: { name: string; faded?: boolean }) {
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[9px] border transition-opacity duration-500"
      style={{
        color: faded ? '#52525b' : '#60a5fa',
        borderColor: faded ? '#27272a' : '#1d4ed844',
        background: faded ? 'transparent' : '#1e3a5f22',
        opacity: faded ? 0.4 : 1,
        textDecoration: faded ? 'line-through' : 'none',
      }}
    >
      {name}
    </span>
  )
}

export function ConstraintTimeline({ current, intermediates, constraintHistory }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new steps appear
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [constraintHistory?.length])

  if (!current) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 p-8 text-zinc-700">
        <p className="text-xs">Run synthesis to see constraint propagation</p>
      </div>
    )
  }

  const steps = buildSteps(intermediates, constraintHistory, current)

  // Collect all types/solvents ever seen (union) for "grayed out" rendering
  const allRxnTypes = Array.from(new Set([
    ...(constraintHistory?.[0]?.rxn_types ?? current.rxn_types),
    ...current.rxn_types,
  ]))
  const allSolvents = Array.from(new Set([
    ...(constraintHistory?.[0]?.solvents ?? current.solvents),
    ...current.solvents,
  ]))

  const currentRxnSet = new Set(current.rxn_types)
  const currentSolventSet = new Set(current.solvents)

  return (
    <div ref={ref} className="flex flex-col gap-0 overflow-y-auto" style={{ maxHeight: 420 }}>
      {/* Current state: compact reaction matrix */}
      <div className="mb-3 rounded-xl border border-violet-800/30 bg-violet-950/10 p-3">
        <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-violet-400">
          G_C^(k) · Current Constraint State
        </p>

        {/* Reaction type matrix — all types, pruned shown faded */}
        <div className="mb-2">
          <p className="mb-1 text-[9px] text-zinc-600 uppercase tracking-wider">Reaction types</p>
          <div className="flex flex-wrap gap-1">
            {allRxnTypes.map(t => (
              <RxnChip key={t} type={t} faded={!currentRxnSet.has(t)} />
            ))}
          </div>
        </div>

        {/* Solvent list */}
        <div>
          <p className="mb-1 text-[9px] text-zinc-600 uppercase tracking-wider">Solvents</p>
          <div className="flex flex-wrap gap-1">
            {allSolvents.map(s => (
              <SolventChip key={s} name={s} faded={!currentSolventSet.has(s)} />
            ))}
          </div>
        </div>

        {/* Excluded */}
        {current.excluded_count > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            <p className="w-full text-[9px] text-zinc-600 uppercase tracking-wider">Excluded ({current.excluded_count})</p>
            {current.excluded_sample.map(e => (
              <span key={e} className="rounded bg-red-950/40 px-1.5 py-0.5 text-[9px] font-mono text-red-400 border border-red-800/30">
                {e.slice(0, 24)}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Propagation steps (if history available) */}
      {steps.length > 1 && (
        <div className="flex flex-col">
          {steps.map((step, i) => (
            <div key={i} className="propagation-entry" style={{ animationDelay: `${i * 60}ms` }}>
              {/* Step header */}
              <div className="flex items-center gap-2 py-1.5">
                <div className="h-px flex-1 bg-zinc-800" />
                <div className="flex items-center gap-1.5 rounded-full bg-zinc-900 border border-zinc-800 px-2 py-0.5">
                  <div className="h-1.5 w-1.5 rounded-full"
                    style={{ background: i === 0 ? '#22c55e' : '#a78bfa' }} />
                  <span className="text-[9px] text-zinc-400">{step.label}</span>
                </div>
                <div className="h-px flex-1 bg-zinc-800" />
              </div>

              {/* Pruned this step */}
              {(step.pruned_rxn?.length ?? 0) > 0 && (
                <div className="mb-2 ml-2 rounded-lg border border-red-900/30 bg-red-950/10 p-2">
                  <div className="mb-1 flex items-center gap-1 text-[9px] text-red-400">
                    <XCircle size={9} />
                    Pruned reaction types
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {step.pruned_rxn!.map(t => (
                      <span key={t} className="rounded px-1.5 py-0.5 text-[9px] line-through text-red-600 border border-red-900/20">
                        {t.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(step.pruned_solvents?.length ?? 0) > 0 && (
                <div className="mb-2 ml-2 rounded-lg border border-orange-900/30 bg-orange-950/10 p-2">
                  <div className="mb-1 flex items-center gap-1 text-[9px] text-orange-400">
                    <MinusCircle size={9} />
                    Blocked solvents
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {step.pruned_solvents!.map(s => (
                      <span key={s} className="rounded px-1.5 py-0.5 text-[9px] line-through text-orange-600 border border-orange-900/20">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Remaining after this step */}
              <div className="mb-1 ml-2 flex flex-wrap gap-1">
                {step.rxn_types.slice(0, 5).map(t => (
                  <RxnChip key={t} type={t} />
                ))}
                {step.rxn_types.length > 5 && (
                  <span className="text-[9px] text-zinc-600">+{step.rxn_types.length - 5}</span>
                )}
              </div>

              {/* Arrow connector */}
              {i < steps.length - 1 && (
                <div className="flex justify-center py-1 text-zinc-700">
                  <ArrowDown size={12} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Search space shrinkage summary */}
      {constraintHistory && constraintHistory.length > 1 && (
        <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
          <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-zinc-500">
            Search Space Reduction
          </p>
          <div className="flex flex-col gap-1.5">
            <SpaceDelta
              label="Reaction types"
              before={constraintHistory[0].rxn_types.length}
              after={current.rxn_types.length}
            />
            <SpaceDelta
              label="Solvents"
              before={constraintHistory[0].solvents.length}
              after={current.solvents.length}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function SpaceDelta({ label, before, after }: { label: string; before: number; after: number }) {
  const pct = before > 0 ? Math.round((1 - after / before) * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 text-[9px] text-zinc-500">{label}</span>
      <div className="relative flex-1 h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div className="absolute left-0 top-0 h-full rounded-full bg-violet-600"
          style={{ width: `${(after / Math.max(before, 1)) * 100}%` }} />
      </div>
      <span className="w-20 text-right text-[9px] tabular-nums text-zinc-500">
        {after}/{before} {pct > 0 ? <span className="text-red-400">−{pct}%</span> : null}
      </span>
    </div>
  )
}
