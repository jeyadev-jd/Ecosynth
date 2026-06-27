import * as SliderPrimitive from '@radix-ui/react-slider'
import { Leaf, Zap, ShoppingCart } from 'lucide-react'
import type { Preferences } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  preferences: Preferences
  onChange: (p: Preferences) => void
  disabled?: boolean
}

interface SliderRowProps {
  label: string
  icon: React.ReactNode
  value: number
  onChange: (v: number) => void
  disabled?: boolean
  color: string
}

function SliderRow({ label, icon, value, onChange, disabled, color }: SliderRowProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
          {icon}
          {label}
        </span>
        <span className="text-xs tabular-nums text-zinc-300">{Math.round(value * 100)}%</span>
      </div>
      <SliderPrimitive.Root
        className={cn('relative flex h-5 w-full touch-none select-none items-center', disabled && 'opacity-50')}
        min={0}
        max={1}
        step={0.05}
        value={[value]}
        onValueChange={([v]) => onChange(v)}
        disabled={disabled}
      >
        <SliderPrimitive.Track className="relative h-1.5 w-full grow rounded-full bg-zinc-700">
          <SliderPrimitive.Range className={cn('absolute h-full rounded-full', color)} />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border-2 border-zinc-500 bg-zinc-200 shadow-md transition-transform focus:outline-none focus:ring-2 focus:ring-zinc-400 hover:scale-110" />
      </SliderPrimitive.Root>
    </div>
  )
}

function normalise(p: Preferences): Preferences {
  const total = p.greenness + p.steps + p.commercial || 1
  return {
    greenness: p.greenness / total,
    steps: p.steps / total,
    commercial: p.commercial / total,
  }
}

export function PreferenceSliders({ preferences, onChange, disabled }: Props) {
  const update = (key: keyof Preferences) => (v: number) => {
    onChange(normalise({ ...preferences, [key]: v }))
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Route Preferences</p>
      <SliderRow
        label="Greenness"
        icon={<Leaf size={13} className="text-green-400" />}
        value={preferences.greenness}
        onChange={update('greenness')}
        disabled={disabled}
        color="bg-green-500"
      />
      <SliderRow
        label="Step Count"
        icon={<Zap size={13} className="text-amber-400" />}
        value={preferences.steps}
        onChange={update('steps')}
        disabled={disabled}
        color="bg-amber-500"
      />
      <SliderRow
        label="Commercial Availability"
        icon={<ShoppingCart size={13} className="text-sky-400" />}
        value={preferences.commercial}
        onChange={update('commercial')}
        disabled={disabled}
        color="bg-sky-500"
      />
    </div>
  )
}
