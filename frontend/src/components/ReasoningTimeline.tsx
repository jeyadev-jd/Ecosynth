import { BookOpen, GitBranch, Shield, ArrowDown, AlertTriangle, Wrench, XCircle } from 'lucide-react'
import type { ReasoningStep } from '@/lib/api'

interface Props {
  steps: ReasoningStep[]
}

const EVENT_META: Record<string, {
  label: string
  icon: React.FC<{ size: number; className?: string; style?: React.CSSProperties }>
  iconColor: string
}> = {
  rag_retrieval:     { label: 'RAG Retrieval',          icon: BookOpen,       iconColor: '#60a5fa' },
  constraint_init:   { label: 'Constraint Init',         icon: GitBranch,      iconColor: '#a78bfa' },
  firewall_check:    { label: 'Firewall Check',          icon: Shield,         iconColor: '#22c55e' },
  constraint_update: { label: 'Constraint Update',       icon: ArrowDown,      iconColor: '#a78bfa' },
  repair_triggered:  { label: 'Repair Triggered',        icon: AlertTriangle,  iconColor: '#ef4444' },
  repair_success:    { label: 'Repair Succeeded',        icon: Wrench,         iconColor: '#7c3aed' },
  repair_failed:     { label: 'Repair Failed',           icon: XCircle,        iconColor: '#ef4444' },
}

function severityChipStyle(severity: string | null): { color: string; bg: string } {
  if (severity === 'block') return { color: '#ef4444', bg: '#450a0a' }
  if (severity === 'warn')  return { color: '#f59e0b', bg: '#422006' }
  if (severity === 'ok')    return { color: '#22c55e', bg: '#052e16' }
  return { color: '#71717a', bg: '#18181b' }
}

function iconColorForSeverity(event: string, severity: string | null): string {
  if (event === 'firewall_check') {
    if (severity === 'block') return '#ef4444'
    if (severity === 'warn')  return '#f59e0b'
    return '#22c55e'
  }
  return EVENT_META[event]?.iconColor ?? '#71717a'
}

export function ReasoningTimeline({ steps }: Props) {
  if (steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/20 p-8 text-zinc-700">
        <div className="h-2 w-2 rounded-full bg-zinc-800" />
        <p className="text-xs">No reasoning steps available for this route</p>
        <p className="text-[10px] text-zinc-800">Re-run synthesis to generate step-by-step trace</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="mb-3 flex items-center gap-2">
        <GitBranch size={11} className="text-violet-400" />
        <p className="text-[10px] font-semibold uppercase tracking-widest text-violet-400">
          Decision Trace · {steps.length} steps
        </p>
      </div>

      <div className="relative flex flex-col">
        {/* Vertical connecting line */}
        <div className="absolute left-[18px] top-0 bottom-0 w-px bg-zinc-800" />

        {steps.map((step, i) => {
          const meta = EVENT_META[step.event]
          const Icon = meta?.icon ?? Shield
          const iconColor = iconColorForSeverity(step.event, step.severity)
          const chip = severityChipStyle(step.severity)

          return (
            <div
              key={i}
              className="propagation-entry relative flex gap-3 pb-4"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              {/* Icon bubble */}
              <div
                className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border"
                style={{
                  background: iconColor + '14',
                  borderColor: iconColor + '44',
                }}
              >
                <Icon size={13} style={{ color: iconColor }} />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0 pt-1.5">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[11px] font-semibold text-zinc-300">
                    {meta?.label ?? step.event}
                  </span>
                  <span className="text-[9px] text-zinc-700">·</span>
                  <span className="text-[9px] text-zinc-700">step {step.step}</span>
                  {step.severity && step.severity !== 'ok' && (
                    <span
                      className="ml-auto rounded px-1.5 py-0.5 text-[9px] uppercase font-semibold"
                      style={{ color: chip.color, background: chip.bg }}
                    >
                      {step.severity}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-zinc-500 leading-relaxed">{step.detail}</p>
                {step.smiles && (
                  <code className="mt-1 block text-[9px] font-mono text-zinc-600 break-all bg-zinc-900/60 rounded px-2 py-0.5 border border-zinc-800">
                    {step.smiles.length > 60 ? step.smiles.slice(0, 58) + '…' : step.smiles}
                  </code>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
