import type { Interval, IntervalOption } from './types'

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

/** Clock time for intraday axis labels, e.g. "14:05". */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** Date or clock time, depending on the bar size the chart is drawn at. */
export function fmtBarTime(iso: string | null | undefined, intraday: boolean): string {
  return intraday ? fmtTime(iso) : fmtDate(iso)
}

/** Date + clock time, for tooltips like "12 Feb 14:05" — intraday bars need both. */
export function fmtBarDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.toLocaleDateString(undefined, { month: 'short', day: '2-digit' })} ${fmtTime(iso)}`
}

/**
 * Chart intervals the dashboard offers, in trader-reading order.
 *
 * `3m` is absent because the data provider does not offer it. `intraday` switches the chart's
 * time axis from dates to clock times — the whole point is that the user can see *which* bar
 * size they are looking at, on the chart and on the forecast.
 */
export const INTERVAL_OPTIONS: IntervalOption[] = [
  { value: '1m', label: '1m', intraday: true },
  { value: '5m', label: '5m', intraday: true },
  { value: '15m', label: '15m', intraday: true },
  { value: '30m', label: '30m', intraday: true },
  { value: '1h', label: '1h', intraday: true },
  { value: '1d', label: '1d', intraday: false },
  { value: '1wk', label: '1wk', intraday: false },
]

/** True for every intraday interval; drives time-axis labels and horizon wording. */
export function isIntraday(interval: string | null | undefined): boolean {
  return INTERVAL_OPTIONS.find((option) => option.value === interval)?.intraday ?? false
}

/** Narrow label like "5m" / "1d"; falls back to the raw string for unknown values. */
export function intervalLabel(interval: string | null | undefined): string {
  if (!interval) return ''
  return INTERVAL_OPTIONS.find((option) => option.value === interval)?.label ?? interval
}

/** Guard narrowing a raw string to a known interval value. */
export function asInterval(value: string | null | undefined): Interval | undefined {
  return INTERVAL_OPTIONS.find((option) => option.value === value)?.value
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
