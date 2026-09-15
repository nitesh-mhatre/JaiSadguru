import { INTERVAL_OPTIONS } from '../format'
import type { Interval } from '../types'

interface Props {
  value: Interval
  onChange: (interval: Interval) => void
  disabled?: boolean
  /** Compact rendering for narrow screens. */
  compact?: boolean
}

/**
 * Bar-size selector for the chart: 1m / 5m / 15m / 30m / 1h / 1d / 1wk.
 *
 * The selection drives everything time-shaped on the dashboard — the candles drawn, the axis
 * labels (clock times for intraday, dates otherwise) and the bar size a new forecast runs on,
 * so picking 5m forecasts 5-minute bars. It renders as a segmented control because that reads
 * instantly on a phone, where a `<select>` would hide the options behind a tap.
 */
export function IntervalPicker({ value, onChange, disabled = false, compact = false }: Props) {
  return (
    <div className={`interval-picker${compact ? ' interval-picker-compact' : ''}`} role="group" aria-label="Chart bar size">
      {INTERVAL_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`interval-btn${option.value === value ? ' interval-btn-active' : ''}`}
          onClick={() => onChange(option.value)}
          disabled={disabled}
          aria-pressed={option.value === value}
          title={
            option.intraday
              ? `${option.label} candles — forecast runs on ${option.label} bars`
              : `${option.label} candles — forecast runs on ${option.label} bars`
          }
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
