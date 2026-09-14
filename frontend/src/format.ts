/** Formatting helpers. Kept in one place so every panel shows a number the same way. */

export function fmtMoney(value: number, decimals = 2): string {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Compact currency for axis labels and large figures: $1.2M, $98.5k. */
export function fmtMoneyCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `$${(value / 1_000).toFixed(1)}k`
  return fmtMoney(value, 0)
}

export function fmtPrice(value: number): string {
  const decimals = Math.abs(value) >= 100 ? 2 : 4
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function fmtPct(value: number, decimals = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`
}

/** Percent from a fraction, e.g. 0.05 -> "+5.00%". */
export function fmtFractionPct(value: number, decimals = 2): string {
  return fmtPct(value * 100, decimals)
}

export function fmtQty(value: number): string {
  if (value === 0) return '0'
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'short', day: '2-digit' })
}

export function fmtRelative(from: Date | null): string {
  if (!from) return 'never'
  const seconds = Math.round((Date.now() - from.getTime()) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.floor(minutes / 60)}h ago`
}

/** Tailwind-free class helper for positive/negative figures. */
export function signClass(value: number): string {
  if (value > 0) return 'pos'
  if (value < 0) return 'neg'
  return 'flat'
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}
