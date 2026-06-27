import { BookOpen, AlertTriangle, CheckCircle, Wrench, FlaskConical } from 'lucide-react'
import type { RouteResult, Precedent, HallucinationReport } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { htColor, htLabel, severityColor, scoreColor } from '@/lib/utils'

interface Props {
  route: RouteResult | null
  precedents: Precedent[]
}

function HTIcon({ severity }: { severity: string }) {
  if (severity === 'ok') return <CheckCircle size={12} className="text-green-400 shrink-0" />
  if (severity === 'warn') return <AlertTriangle size={12} className="text-yellow-400 shrink-0" />
  return <AlertTriangle size={12} className="text-red-400 shrink-0" />
}

function FailureAttribution({ reports }: { reports: HallucinationReport[] }) {
  const flagged = reports.filter(r => r.severity !== 'ok')
  if (flagged.length === 0) return null
  return (
    <div className="rounded-xl border border-orange-800/40 bg-orange-950/20 p-4">
      <p className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-orange-400">
        <AlertTriangle size={12} />
        Hallucination Reports
      </p>
      <div className="flex flex-col gap-3">
        {flagged.map((r, i) => (
          <div key={i} className="rounded-lg border p-3"
            style={{ borderColor: htColor(r.ht_type) + '44', background: htColor(r.ht_type) + '08' }}>
            <div className="mb-1 flex items-center gap-2">
              <HTIcon severity={r.severity} />
              <span className="text-[11px] font-semibold" style={{ color: htColor(r.ht_type) }}>
                {r.ht_type ?? 'Unknown'} · {htLabel(r.ht_type)}
              </span>
              <span className="ml-auto text-[9px] uppercase tracking-wider"
                style={{ color: severityColor(r.severity) }}>
                {r.severity}
              </span>
            </div>
            <p className="text-[11px] text-zinc-400">{r.message}</p>
            {r.smiles && (
              <code className="mt-1 block text-[10px] text-zinc-500 font-mono break-all">{r.smiles.slice(0, 60)}</code>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function RouteScoreBreakdown({ route }: { route: RouteResult }) {
  const bd = route.score_breakdown
  const rs = route.route_score ?? route.g_score
  const components = [
    { label: 'G · Greenness', value: route.g_score, weight: bd.weights?.alpha ?? 0.4, color: '#22c55e' },
    { label: 'V · Validity', value: route.v_score ?? 1, weight: bd.weights?.beta ?? 0.3, color: '#60a5fa' },
    { label: 'C · Confidence', value: route.c_score ?? 0, weight: bd.weights?.gamma ?? 0.2, color: '#a78bfa' },
    { label: 'H · Preference', value: route.h_score ?? 0, weight: bd.weights?.delta ?? 0.1, color: '#f59e0b' },
  ]
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">RouteScore = αG + βV + γC + δH</p>
        <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor(rs) }}>
          {(rs * 100).toFixed(1)}
        </span>
      </div>
      <div className="flex flex-col gap-2.5">
        {components.map(c => (
          <div key={c.label} className="flex items-center gap-3">
            <div className="w-28 shrink-0">
              <p className="text-[10px] text-zinc-400">{c.label}</p>
              <p className="text-[9px] text-zinc-600">weight {c.weight}</p>
            </div>
            <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-zinc-800">
              <div className="absolute left-0 top-0 h-full rounded-full"
                style={{ width: `${c.value * 100}%`, background: c.color }} />
            </div>
            <span className="w-10 shrink-0 text-right text-[10px] tabular-nums" style={{ color: c.color }}>
              {(c.value * 100).toFixed(0)}
            </span>
            <span className="w-14 shrink-0 text-right text-[9px] text-zinc-600 tabular-nums">
              +{(c.weight * c.value * 100).toFixed(1)} pts
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function IntermediateList({ route }: { route: RouteResult }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
        <FlaskConical size={11} />
        Synthesis Pathway
      </p>
      <div className="flex flex-col gap-2">
        {route.intermediates.map((smi, i) => (
          <div key={i} className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[9px] text-zinc-400">
                {i + 1}
              </div>
              <div className="flex flex-1 items-center gap-2 min-w-0">
                {/* Molecule structure thumbnail */}
                <img
                  src={`https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodeURIComponent(smi)}/PNG?record_type=2d&image_size=120x90`}
                  alt=""
                  className="h-[50px] w-[70px] shrink-0 rounded object-contain bg-white/5 border border-zinc-800"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
                <code className="flex-1 rounded-md bg-zinc-800/60 px-2 py-1 text-[10px] font-mono text-green-300 break-all self-stretch flex items-center">
                  {smi}
                </code>
              </div>
            </div>
            {i < route.intermediates.length - 1 && (
              <div className="ml-7 text-zinc-700 text-xs">↓</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ExplanationPanel({ route, precedents }: Props) {
  if (!route) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-600">
        Select a route to see details
      </div>
    )
  }

  const htReports: HallucinationReport[] = (route as any).hallucination_reports ?? []

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto pr-1 pb-4">
      {/* RouteScore breakdown */}
      <RouteScoreBreakdown route={route} />

      {/* Repaired notice */}
      {route.repaired && (
        <div className="flex items-start gap-2 rounded-xl border border-yellow-800/40 bg-yellow-950/20 p-3">
          <Wrench size={13} className="shrink-0 text-yellow-400 mt-0.5" />
          <div>
            <p className="text-xs font-semibold text-yellow-400">Local Branch Repair Applied</p>
            <p className="mt-0.5 text-[11px] text-zinc-400">
              A failed subtree was detected and locally repaired via constraint-guided regeneration.
              The route excludes the original failing intermediate.
            </p>
          </div>
        </div>
      )}

      {/* Failure attribution */}
      {htReports.length > 0 && <FailureAttribution reports={htReports} />}

      {/* LLM explanation */}
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-zinc-500">Route Explanation</p>
        <p className="text-sm leading-relaxed text-zinc-300 whitespace-pre-wrap">{route.explanation}</p>
      </div>

      {/* Intermediates */}
      {route.intermediates.length > 0 && <IntermediateList route={route} />}

      {/* USPTO precedents */}
      {precedents.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-zinc-500 flex items-center gap-1.5">
            <BookOpen size={11} />
            USPTO Precedents
          </p>
          <div className="flex flex-col gap-2">
            {precedents.slice(0, 5).map((p, i) => (
              <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">
                    [{i + 1}] {p.reaction_class || 'reaction'}
                  </Badge>
                  {/* Similarity bar */}
                  <div className="flex flex-1 items-center gap-2">
                    <div className="relative flex-1 h-1 overflow-hidden rounded-full bg-zinc-800">
                      <div className="absolute left-0 top-0 h-full rounded-full"
                        style={{ width: `${p.similarity * 100}%`, background: scoreColor(p.similarity) }} />
                    </div>
                    <span className="text-[9px] tabular-nums" style={{ color: scoreColor(p.similarity) }}>
                      {(p.similarity * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                {/* Reaction arrow layout */}
                {p.reaction_smiles.includes('>>') ? (
                  <div className="flex items-center gap-1.5 text-[10px]">
                    <code className="flex-1 rounded bg-zinc-800/60 px-1.5 py-1 text-zinc-400 font-mono break-all">
                      {p.reaction_smiles.split('>>')[0].slice(0, 40)}
                    </code>
                    <span className="shrink-0 text-zinc-600">→</span>
                    <code className="flex-1 rounded bg-zinc-800/60 px-1.5 py-1 text-green-400 font-mono break-all">
                      {p.reaction_smiles.split('>>')[1]?.slice(0, 40)}
                    </code>
                  </div>
                ) : (
                  <code className="text-[10px] text-zinc-400 font-mono break-all">{p.reaction_smiles.slice(0, 80)}</code>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
