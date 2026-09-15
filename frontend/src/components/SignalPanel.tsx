import type { ConfigResponse, SignalResponse, SignalRationale } from '../types'
import {
  fmtFractionPct,
  fmtMoney,
  fmtPrice,
  fmtRelative,
  intervalLabel,
  signClass,
} from '../format'
import { ActionBadge, ConfidenceBar } from './Badge'

interface Props {
  signal: SignalResponse | null
  symbol: string | null
  config: ConfigResponse | null
  busy: boolean
  onRunForecast: () => void
  /** Selected chart bar size, so the horizon can be shown in time units, not bare bars. */
  interval?: string
}

const COMPONENT_HELP: Record<string, string> = {
  magnitude: 'How large the forecast move is relative to the asset’s own volatility.',
  agreement: 'Whether the forecast direction matches the recent trend.',
  monotonicity: 'How consistently the forecasted path moves one way.',
  smoothness: 'How shallow the drawdown inside the forecasted move is.',
}

function ComponentBars({ rationale }: { rationale: SignalRationale }) {
  const components = rationale.components
  if (!components) return null
  const rows: [string, number][] = [
    ['magnitude', components.magnitude],
    ['agreement', components.agreement],
    ['monotonicity', components.monotonicity],
    ['smoothness', components.smoothness],
  ]
  return (
    <div className="components">
      {rows.map(([label, value]) => (
        <div className="component" key={label} title={COMPONENT_HELP[label]}>
          <span className="component-label">{label}</span>
          <ConfidenceBar value={value} />
          <span className="mono tiny">{value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * The evidence behind the selected symbol's decision.
 *
 * Everything the engine used is shown, including the parts that argue against the action. A
 * dashboard that only surfaced the verdict would make the signal impossible to judge.
 */
export function SignalPanel({ signal, symbol, config, busy, onRunForecast, interval }: Props) {
  if (!symbol) {
    return <div className="empty">Select a symbol to see its forecast and signal.</div>
  }
  if (!signal) {
    return (
      <div className="empty">
        No signal recorded for <strong>{symbol}</strong> yet.
        <button className="btn btn-primary btn-sm" onClick={onRunForecast} disabled={busy}>
          {busy ? 'Forecasting…' : 'Forecast now'}
        </button>
      </div>
    )
  }

  const rationale = signal.rationale
  const volatility = rationale.volatility
  const trend = rationale.trend
  const sizing = rationale.sizing

  return (
    <div className="signal">
      <header className="signal-head">
        <div>
          <h3>
            {signal.symbol} <ActionBadge action={signal.action} />
          </h3>
          <p className="muted tiny">
            {intervalLabel(interval ?? signal.rationale.model?.interval)} bars ahead ·{' '}
            evaluated {fmtRelative(new Date(signal.created_at))}
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onRunForecast} disabled={busy}>
          {busy ? 'Forecasting…' : 'Re-forecast'}
        </button>
      </header>

      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Confidence</span>
          <span className="stat-value mono">{(signal.confidence * 100).toFixed(0)}%</span>
          <ConfidenceBar value={signal.confidence} />
        </div>
        <div className="stat">
          <span className="stat-label">Score</span>
          <span className={`stat-value mono ${signClass(signal.score)}`}>
            {signal.score.toFixed(2)}
          </span>
          <span className="tiny muted">
            threshold ±{config?.thresholds.buy.toFixed(2) ?? '—'}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Expected move</span>
          <span className={`stat-value mono ${signClass(signal.expected_return)}`}>
            {fmtFractionPct(signal.expected_return)}
          </span>
          <span className="tiny muted">
            {fmtPrice(signal.last_close)} → {fmtPrice(signal.last_close * (1 + signal.expected_return))}
          </span>
        </div>
      </div>

      <ComponentBars rationale={rationale} />

      <dl className="kv">
        {volatility && (
          <>
            <dt>Realised volatility</dt>
            <dd className="mono">
              {volatility.daily_pct.toFixed(2)}%/bar · {volatility.horizon_pct.toFixed(2)}% over{' '}
              {rationale.horizon_bars} bars
            </dd>
            <dt>Volatility source</dt>
            <dd className="muted">{volatility.source}</dd>
          </>
        )}
        {trend && (
          <>
            <dt>Trend</dt>
            <dd className={trend.agreement === 'agrees' ? 'pos' : trend.agreement === 'conflicts' ? 'neg' : 'muted'}>
              {trend.agreement}
            </dd>
          </>
        )}
        {rationale.path && (
          <>
            <dt>Path shape</dt>
            <dd className="mono">
              max adverse {rationale.path.max_adverse_move_pct.toFixed(2)}% of a{' '}
              {rationale.path.forecast_move_pct.toFixed(2)}% move
            </dd>
          </>
        )}
        {sizing && (
          <>
            <dt>Suggested size</dt>
            <dd className="mono">
              {signal.suggested_qty > 0
                ? `${signal.suggested_qty} units · ${fmtMoney(signal.suggested_notional)}`
                : 'no position suggested'}
            </dd>
            <dt>Risk at stop</dt>
            <dd className="mono">{fmtMoney(sizing.risk_amount)}</dd>
          </>
        )}
        {rationale.model && (
          <>
            <dt>Model</dt>
            <dd className="muted">
              {rationale.model.name} · {rationale.model.sample_count} sampled paths
            </dd>
          </>
        )}
      </dl>

      {rationale.notes && rationale.notes.length > 0 && (
        <ul className="notes">
          {rationale.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
