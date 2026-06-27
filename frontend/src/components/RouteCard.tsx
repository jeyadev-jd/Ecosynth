import { ChevronDown, ChevronRight, FlaskConical, Layers, ShieldCheck, Brain, Heart, Leaf, Wrench } from 'lucide-react'
import { useState } from 'react'
import type { RouteResult } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { scoreColor, scoreLabel, htColor, htLabel } from '@/lib/utils'

interface Props {
  route: RouteResult
  rank: number
  onSelect: (route: RouteResult) => void
  selected: boolean
  compareRoute?: RouteResult   // for route delta comparison
}

function ScoreBar({ value, color, label }: { value: number; color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[10px] text-zinc-500">{label}</span>
      <div className="relative flex-1 h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(value * 100, 100)}%`, background: color }}
        />
      </div>
      <span className="w-8 shrink-0 text-right text-[10px] tabular-nums" style={{ color }}>
        {(value * 100).toFixed(0)}
      </span>
    </div>
  )
}

function Delta({ label, a, b, higherBetter = true }: { label: string; a: number; b: number; higherBetter?: boolean }) {
  const diff = a - b
  const pct = Math.abs(diff * 100).toFixed(0)
  const better = higherBetter ? diff > 0 : diff < 0
  const color = Math.abs(diff) < 0.01 ? '#71717a' : better ? '#22c55e' : '#ef4444'
  const sign = diff > 0.005 ? '+' : diff < -0.005 ? '' : '±'
  return (
    <div className="flex items-center justify-between text-[10px]">
      <span className="text-zinc-500">{label}</span>
      <span style={{ color }} className="tabular-nums">
        {Math.abs(diff) < 0.005 ? '—' : `${sign}${pct}%`}
      </span>
    </div>
  )
}

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between text-[10px]">
      <span className="text-zinc-500">{label}</span>
      <span className="tabular-nums text-zinc-300">{value}</span>
    </div>
  )
}

export function RouteCard({ route, rank, onSelect, selected, compareRoute }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [showDelta, setShowDelta] = useState(false)
  const bd = route.score_breakdown
  const rs = route.route_score ?? route.g_score
  const variant = rs >= 0.65 ? 'success' : rs >= 0.35 ? 'warn' : 'danger'

  return (
    <Card
      className={`cursor-pointer transition-all ${selected ? 'border-green-600 ring-1 ring-green-600/30' : 'hover:border-zinc-600'}`}
      onClick={() => onSelect(route)}
    >
      <CardHeader>
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-zinc-800 text-xs font-bold text-zinc-400">
            {rank}
          </span>
          <CardTitle className="truncate text-[11px] font-mono text-zinc-400">{route.route_id}</CardTitle>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="outline">
            <Layers size={10} />
            {route.n_steps}
          </Badge>
          {route.repaired && (
            <Badge variant="warn" title="Route was locally repaired">
              <Wrench size={10} />
              Repaired
            </Badge>
          )}
          <Badge variant={variant}>
            {scoreLabel(rs)}
          </Badge>
        </div>
      </CardHeader>

      {/* RouteScore composite bar */}
      <div className="mb-1 flex items-center gap-2">
        <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
            style={{ width: `${rs * 100}%`, background: scoreColor(rs) }}
          />
        </div>
        <span className="shrink-0 text-xs tabular-nums font-semibold" style={{ color: scoreColor(rs) }}>
          {(rs * 100).toFixed(1)}
        </span>
      </div>

      {/* HT badge */}
      {route.hallucination_type && (
        <div className="mb-2 flex items-center gap-1.5 rounded-md border px-2 py-1"
          style={{ borderColor: htColor(route.hallucination_type) + '55', background: htColor(route.hallucination_type) + '11' }}>
          <div className="h-1.5 w-1.5 rounded-full" style={{ background: htColor(route.hallucination_type) }} />
          <span className="text-[10px]" style={{ color: htColor(route.hallucination_type) }}>
            {route.hallucination_type} · {htLabel(route.hallucination_type)}
          </span>
        </div>
      )}

      {/* Component score bars: G V C H */}
      <div className="mb-2 flex flex-col gap-1">
        <ScoreBar value={route.g_score} color="#22c55e" label="G Greenness" />
        <ScoreBar value={route.v_score ?? 1} color="#60a5fa" label="V Validity" />
        <ScoreBar value={route.c_score ?? 0} color="#a78bfa" label="C Confidence" />
        <ScoreBar value={route.h_score ?? 0} color="#f59e0b" label="H Preference" />
      </div>

      {/* Weight display */}
      {bd.weights && (
        <div className="mb-2 flex items-center gap-1 text-[9px] text-zinc-600">
          <span>α{bd.weights.alpha}</span>
          <span className="text-zinc-700">·</span>
          <span>β{bd.weights.beta}</span>
          <span className="text-zinc-700">·</span>
          <span>γ{bd.weights.gamma}</span>
          <span className="text-zinc-700">·</span>
          <span>δ{bd.weights.delta}</span>
        </div>
      )}

      {/* Expand toggle */}
      <button
        className="flex w-full items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
        onClick={e => { e.stopPropagation(); setExpanded(x => !x) }}
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Green metrics
      </button>

      {expanded && (
        <div className="mt-2 flex flex-col gap-1.5 rounded-lg bg-zinc-800/50 p-3">
          <MetricRow label="Atom Economy" value={(bd.atom_economy * 100).toFixed(1) + '%'} />
          <MetricRow label="E-Factor" value={bd.e_factor.toFixed(2)} />
          <MetricRow label="PMI" value={bd.pmi.toFixed(2)} />
          <MetricRow label="CHEM21 Solvent" value={(bd.chem21_score * 10).toFixed(1) + '/10'} />
          <MetricRow label="Step Penalty" value={bd.step_penalty.toFixed(3)} />
          <div className="mt-1.5 flex items-center gap-1.5 border-t border-zinc-700 pt-2">
            <FlaskConical size={10} className="text-green-400 shrink-0" />
            <span className="text-[10px] text-zinc-500">{route.source}</span>
          </div>
        </div>
      )}

      {/* Route delta vs compareRoute */}
      {compareRoute && (
        <>
          <button
            className="mt-1 flex w-full items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
            onClick={e => { e.stopPropagation(); setShowDelta(x => !x) }}
          >
            {showDelta ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            vs route #{compareRoute.route_id.split('_')[1]}
          </button>
          {showDelta && (
            <div className="mt-2 flex flex-col gap-1 rounded-lg bg-zinc-800/50 p-3">
              <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-zinc-600">Delta</p>
              <Delta label="RouteScore" a={rs} b={compareRoute.route_score ?? compareRoute.g_score} />
              <Delta label="Greenness" a={route.g_score} b={compareRoute.g_score} />
              <Delta label="Confidence" a={route.c_score ?? 0} b={compareRoute.c_score ?? 0} />
              <Delta label="Steps" a={compareRoute.n_steps} b={route.n_steps} higherBetter={false} />
            </div>
          )}
        </>
      )}
    </Card>
  )
}
