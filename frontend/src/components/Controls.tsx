import type { ConfigResponse, HealthResponse, RunResponse } from '../types'
import { fmtRelative } from '../format'
import { StatusBadge } from './Badge'

export type BusyAction = 'cycle' | 'dry' | 'reset' | 'forecast' | 'warmup' | null

interface Props {
  health: HealthResponse | null
  config: ConfigResponse | null
  lastUpdated: Date | null
  refreshing: boolean
  busy: BusyAction
  error: string | null
  notice: string | null
  onRefresh: () => void
  onRunCycle: (trade: boolean) => void
  onReset: () => void
}

/**
 * Header: identity, live system state and the actions.
 *
 * The run buttons are disabled when the model runtime is unavailable, with the reason shown in
 * the status strip. Letting a user click a button that is guaranteed to fail would hide the real
 * problem behind a generic error toast.
 */
export function Controls({
  health,
  config,
  lastUpdated,
  refreshing,
  busy,
  error,
  notice,
  onRefresh,
  onRunCycle,
  onReset,
}: Props) {
  const modelReady = health?.runtime_available ?? false
  const anyBusy = busy !== null
  const disabledReason = modelReady
    ? undefined
    : health?.detail ?? 'The Kronos runtime is unavailable on the server.'

  return (
    <header className="header">
      <div className="header-top">
        <div className="brand">
          <h1>JaiSadguru</h1>
          <p className="muted tiny">
            Kronos forecasts for indices, gold and silver · <strong>paper trading only</strong>
          </p>
        </div>

        <div className="actions">
          <button
            className="btn btn-ghost btn-sm"
            onClick={onRefresh}
            disabled={anyBusy || refreshing}
            title="Re-fetch market data, signals and portfolio"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onRunCycle(false)}
            disabled={anyBusy || !modelReady}
            title={disabledReason ?? 'Forecast and derive signals without touching the portfolio'}
          >
            {busy === 'dry' ? 'Running…' : 'Dry run'}
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => onRunCycle(true)}
            disabled={anyBusy || !modelReady}
            title={
              disabledReason ??
              'Fetch prices, forecast every symbol, derive signals and trade them on the paper portfolio'
            }
          >
            {busy === 'cycle' ? 'Running…' : 'Run cycle'}
          </button>
          <button
            className="btn btn-danger btn-sm"
            onClick={onReset}
            disabled={anyBusy}
            title="Clear positions, trades and snapshots and restore the starting cash"
          >
            {busy === 'reset' ? 'Resetting…' : 'Reset'}
          </button>
        </div>
      </div>

      <div className="status-strip">
        <span className={`status-dot ${health?.status === 'ok' ? 'dot-ok' : 'dot-warn'}`} />
        <span className="tiny">
          {health
            ? health.status === 'ok'
              ? 'Backend healthy'
              : 'Backend degraded'
            : 'Connecting…'}
        </span>
        {health && (
          <>
            <span className="sep" />
            <span className="tiny muted">
              model <span className="mono">{health.model}</span>
            </span>
            <span className="sep" />
            <span className="tiny muted">
              device <span className="mono">{health.device ?? 'not loaded'}</span>
            </span>
            <span className="sep" />
            <span className="tiny muted">
              {health.model_loaded ? 'weights in memory' : 'weights load on first forecast'}
            </span>
            <span className="sep" />
            <span className="tiny muted">
              {health.interval} bars · lookback <span className="mono">{config?.lookback ?? '—'}</span> ·
              horizon <span className="mono">{config?.pred_len ?? '—'}</span>
            </span>
            {config?.scheduler_enabled && (
              <>
                <span className="sep" />
                <span className="tiny muted">scheduler on</span>
              </>
            )}
          </>
        )}
        <span className="spacer" />
        <span className="tiny muted">updated {fmtRelative(lastUpdated)}</span>
      </div>

      {health && !health.runtime_available && (
        <div className="alert alert-warn">
          <strong>Model runtime unavailable.</strong> {health.detail} Install the backend
          dependencies with <code>pip install -r requirements.txt</code> and restart the API.
        </div>
      )}
      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}
    </header>
  )
}

/** Compact strip of the most recent runs, so a failing cycle is visible without opening /docs. */
export function RunsStrip({ runs }: { runs: RunResponse[] }) {
  if (runs.length === 0) return null
  return (
    <div className="runs-strip">
      <span className="tiny muted">recent runs</span>
      {runs.slice(0, 8).map((run) => (
        <span
          className="run-pill mono tiny"
          key={run.id}
          title={`${run.started_at} · ${run.duration_ms ?? '—'} ms${
            run.error ? ` · ${run.error}` : ''
          }`}
        >
          #{run.id} <StatusBadge status={run.status} />
        </span>
      ))}
    </div>
  )
}
