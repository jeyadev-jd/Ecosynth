/**
 * Failure Attribution Console
 * Shows rejected routes with HT type, reason, confidence, and repair action.
 */
import { AlertTriangle, Wrench, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { RouteResult } from '@/lib/api'
import { htColor, htLabel } from '@/lib/utils'

interface Props {
  routes: RouteResult[]
}

function FailureEntry({ route, rank }: { route: RouteResult; rank: number }) {
  const [open, setOpen] = useState(false)
  const htType = route.hallucination_type
  const reports = (route as any).hallucination_reports ?? []
  const flagged = reports.filter((r: any) => r.severity !== 'ok')

  if (!htType && flagged.length === 0 && !route.repaired) return null

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
      <button
        className="flex w-full items-center gap-3 p-3 text-left hover:bg-zinc-800/40 transition-colors"
        onClick={() => setOpen(x => !x)}
      >
        {/* Route indicator */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold"
          style={{
            background: htType ? htColor(htType) + '18' : route.repaired ? '#4c1d9520' : '#1c1c27',
            color: htType ? htColor(htType) : route.repaired ? '#a78bfa' : '#71717a',
            border: `1px solid ${htType ? htColor(htType) + '44' : route.repaired ? '#4c1d9544' : '#27272a'}`,
          }}>
          #{rank}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {htType && (
              <span className="text-[10px] font-semibold" style={{ color: htColor(htType) }}>
                {htType} · {htLabel(htType)}
              </span>
            )}
            {route.repaired && (
              <span className="flex items-center gap-1 text-[10px] text-violet-400">
                <Wrench size={9} />
                Repaired
              </span>
            )}
            {!htType && !route.repaired && flagged.length > 0 && (
              <span className="text-[10px] text-yellow-400">
                {flagged.length} warning{flagged.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          <p className="truncate text-[10px] text-zinc-500 font-mono mt-0.5">
            {route.route_id}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="text-right">
            <p className="text-[10px] tabular-nums text-zinc-400">{(route.route_score * 100).toFixed(0)}</p>
            <p className="text-[9px] text-zinc-600">score</p>
          </div>
          {open ? <ChevronDown size={12} className="text-zinc-600" /> : <ChevronRight size={12} className="text-zinc-600" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-zinc-800 p-3 flex flex-col gap-3">
          {flagged.map((r: any, i: number) => (
            <div key={i} className="rounded-lg p-3"
              style={{
                background: htColor(r.ht_type) + '0a',
                border: `1px solid ${htColor(r.ht_type)}33`,
              }}>
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <AlertTriangle size={10} style={{ color: htColor(r.ht_type) }} />
                  <span className="text-[10px] font-semibold" style={{ color: htColor(r.ht_type) }}>
                    {r.ht_type ?? 'Warning'}
                  </span>
                </div>
                <span className="rounded px-1.5 py-0.5 text-[9px] uppercase"
                  style={{
                    color: r.severity === 'block' ? '#ef4444' : '#eab308',
                    background: r.severity === 'block' ? '#450a0a' : '#422006',
                  }}>
                  {r.severity}
                </span>
              </div>
              <p className="text-[11px] text-zinc-300 leading-relaxed">{r.message}</p>
              {r.smiles && (
                <code className="mt-2 block text-[10px] text-zinc-500 font-mono break-all bg-zinc-900/60 rounded px-2 py-1">
                  {r.smiles}
                </code>
              )}
              {r.details && Object.keys(r.details).length > 0 && (
                <div className="mt-2 flex flex-col gap-0.5">
                  {Object.entries(r.details).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-[9px]">
                      <span className="text-zinc-600">{k}:</span>
                      <span className="text-zinc-400 font-mono">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {route.repaired && (
            <div className="rounded-lg border border-violet-800/30 bg-violet-950/10 p-3">
              <div className="mb-1 flex items-center gap-1.5">
                <Wrench size={10} className="text-violet-400" />
                <span className="text-[10px] font-semibold text-violet-400">Branch Repair Applied</span>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                Failed subtree was invalidated and regenerated via local constraint-guided search.
                Original intermediate excluded from session blacklist.
              </p>
            </div>
          )}

          {/* Confidence bar */}
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-zinc-600 w-20">Confidence</span>
            <div className="relative flex-1 h-1 overflow-hidden rounded-full bg-zinc-800">
              <div className="absolute left-0 top-0 h-full rounded-full bg-violet-600"
                style={{ width: `${(route.c_score ?? 0) * 100}%` }} />
            </div>
            <span className="text-[9px] tabular-nums text-zinc-500">
              {((route.c_score ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

export function FailureConsole({ routes }: Props) {
  const flaggedRoutes = routes.filter(r =>
    r.hallucination_type || r.repaired ||
    ((r as any).hallucination_reports ?? []).some((x: any) => x.severity !== 'ok')
  )

  if (flaggedRoutes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/20 p-6 text-zinc-700">
        <div className="h-2 w-2 rounded-full bg-green-800" />
        <p className="text-xs">No hallucinations detected in any route</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle size={11} className="text-orange-400" />
        <p className="text-[10px] font-semibold uppercase tracking-widest text-orange-400">
          Failure Console · {flaggedRoutes.length} flagged route{flaggedRoutes.length !== 1 ? 's' : ''}
        </p>
      </div>
      {flaggedRoutes.map((r, i) => (
        <FailureEntry key={r.route_id} route={r} rank={i + 1} />
      ))}
    </div>
  )
}
