import type { Action, RunStatus } from '../types'

/** Coloured pill for a BUY / SELL / HOLD decision. */
export function ActionBadge({ action }: { action: Action }) {
  return <span className={`badge badge-${action.toLowerCase()}`}>{action}</span>
}

/** Coloured pill for a run status. */
export function StatusBadge({ status }: { status: RunStatus }) {
  const label: Record<RunStatus, string> = {
    running: 'Running',
    ok: 'OK',
    degraded: 'Degraded',
    failed: 'Failed',
  }
  return <span className={`badge badge-status-${status}`}>{label[status]}</span>
}

/** Horizontal 0-1 meter used for signal confidence. */
export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="meter" title={`${pct.toFixed(1)}%`}>
      <div className="meter-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}

/** Small inline label for the asset class. */
export function ClassTag({ value }: { value: string }) {
  return <span className={`tag tag-${value}`}>{value}</span>
}
