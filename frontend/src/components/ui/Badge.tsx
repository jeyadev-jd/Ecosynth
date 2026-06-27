import { cn } from '@/lib/utils'
import type { HTMLAttributes } from 'react'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'outline' | 'success' | 'warn' | 'danger'
}

const variants = {
  default:  'bg-zinc-700 text-zinc-100',
  outline:  'border border-zinc-600 text-zinc-300',
  success:  'bg-green-900/60 text-green-300 border border-green-700',
  warn:     'bg-amber-900/60 text-amber-300 border border-amber-700',
  danger:   'bg-red-900/60 text-red-300 border border-red-700',
}

export function Badge({ variant = 'default', className, ...props }: BadgeProps) {
  return (
    <span
      className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', variants[variant], className)}
      {...props}
    />
  )
}
