import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function scoreColor(score: number): string {
  if (score >= 0.75) return '#22c55e'
  if (score >= 0.5)  return '#84cc16'
  if (score >= 0.35) return '#eab308'
  if (score >= 0.2)  return '#f97316'
  return '#ef4444'
}

export function scoreLabel(score: number): string {
  if (score >= 0.75) return 'Excellent'
  if (score >= 0.5)  return 'Good'
  if (score >= 0.35) return 'Fair'
  return 'Poor'
}

export function htColor(htType: string | null): string {
  if (!htType) return '#22c55e'
  switch (htType) {
    case 'HT-01': return '#ef4444'
    case 'HT-02': return '#f97316'
    case 'HT-03': return '#eab308'
    case 'HT-04': return '#f97316'
    case 'HT-05': return '#8b5cf6'
    default: return '#71717a'
  }
}

export function htLabel(htType: string | null): string {
  if (!htType) return 'Valid'
  switch (htType) {
    case 'HT-01': return 'Valence Violation'
    case 'HT-02': return 'Stereo Impossible'
    case 'HT-03': return 'No Precedent'
    case 'HT-04': return 'Reagent Incompatibility'
    case 'HT-05': return 'Constraint Violation'
    default: return htType
  }
}

export function severityColor(severity: string): string {
  if (severity === 'ok') return '#22c55e'
  if (severity === 'warn') return '#eab308'
  return '#ef4444'
}
