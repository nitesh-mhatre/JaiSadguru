import type { ConfigResponse, EquityPoint, PortfolioResponse } from '../types'
import { fmtMoney, fmtPct, fmtPrice, fmtQty, signClass } from '../format'

interface Props {
  portfolio: PortfolioResponse | null
  config: ConfigResponse | null
}

const CURVE_W = 640
const CURVE_H = 150
const CURVE_PAD = 12

/** Equity against the starting capital, drawn as a plain SVG polyline. */
function EquityCurve({
  curve,
  initialCapital,
}: {
  curve: EquityPoint[]
  initialCapital: number
}) {
  if (curve.length < 2) {
    return (
      <div className="empty small">
        Not enough snapshots for a curve yet — each cycle records one equity point.
      </div>
    )
  }

  const values = curve.map((point) => point.equity)
  const min = Math.min(...values, initialCapital)
  const max = Math.max(...values, initialCapital)
  const span = max - min || 1

  const x = (index: number) =>
    CURVE_PAD + (index / (curve.length - 1)) * (CURVE_W - CURVE_PAD * 2)
  const y = (value: number) =>
    CURVE_PAD + ((max - value) / span) * (CURVE_H - CURVE_PAD * 2)

  const path = curve.map((point, index) => `${x(index)},${y(point.equity)}`).join(' ')
  const last = values[values.length - 1] ?? initialCapital
  const stroke = last >= initialCapital ? '#26a69a' : '#ef5350'

  return (
    <svg
      className="chart curve"
      viewBox={`0 0 ${CURVE_W} ${CURVE_H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Portfolio equity curve"
    >
      <line
        x1={CURVE_PAD}
        x2={CURVE_W - CURVE_PAD}
        y1={y(initialCapital)}
        y2={y(initialCapital)}
        stroke="#4b5563"
        strokeWidth={1}
        strokeDasharray="5 4"
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={path}
        fill="none"
        stroke={stroke}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

/**
 * The simulated account. Labelled "paper" throughout, because the single most dangerous thing
 * this dashboard could do is let a P&L figure be mistaken for real money.
 */
export function PortfolioPanel({ portfolio, config }: Props) {
  if (!portfolio) {
    return <div className="empty">Loading portfolio…</div>
  }

  return (
    <div className="portfolio">
      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Paper equity</span>
          <span className="stat-value mono">{fmtMoney(portfolio.equity)}</span>
          <span className={`tiny mono ${signClass(portfolio.total_return)}`}>
            {fmtMoney(portfolio.total_return)} ({fmtPct(portfolio.total_return_pct)})
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Cash</span>
          <span className="stat-value mono">{fmtMoney(portfolio.cash)}</span>
          <span className="tiny muted">
            of {fmtMoney(portfolio.initial_capital)} starting
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Realised</span>
          <span className={`stat-value mono ${signClass(portfolio.realized_pnl)}`}>
            {fmtMoney(portfolio.realized_pnl)}
          </span>
          <span className="tiny muted">closed trades</span>
        </div>
        <div className="stat">
          <span className="stat-label">Unrealised</span>
          <span className={`stat-value mono ${signClass(portfolio.unrealized_pnl)}`}>
            {fmtMoney(portfolio.unrealized_pnl)}
          </span>
          <span className="tiny muted">
            {portfolio.open_positions}/{portfolio.max_positions} positions open
          </span>
        </div>
      </div>

      <EquityCurve curve={portfolio.equity_curve} initialCapital={portfolio.initial_capital} />

      {portfolio.positions.length === 0 ? (
        <div className="empty small">
          No open positions. Signals only open a position when the score clears the threshold and
          confidence is high enough.
        </div>
      ) : (
        <div className="table-scroll">
          <table className="table compact">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Qty</th>
                <th className="num">Avg cost</th>
                <th className="num">Mark</th>
                <th className="num col-hide-mobile col-hide-narrow">Value</th>
                <th className="num">P&amp;L</th>
                <th className="num col-hide-mobile">Stop</th>
                <th className="num col-hide-mobile">Target</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map((position) => (
                <tr key={position.symbol}>
                  <td className="mono">{position.symbol}</td>
                  <td className="num mono">{fmtQty(position.qty)}</td>
                  <td className="num mono">{fmtPrice(position.avg_price)}</td>
                  <td className="num mono">
                    {position.priced ? (
                      fmtPrice(position.last_price)
                    ) : (
                      <span className="muted" title="No mark price observed; valued at cost basis">
                        n/a
                      </span>
                    )}
                  </td>
                  <td className="num mono col-hide-mobile col-hide-narrow">{fmtMoney(position.market_value)}</td>
                  <td className={`num mono ${signClass(position.unrealized_pnl)}`}>
                    {fmtMoney(position.unrealized_pnl)}
                    <span className="tiny"> ({fmtPct(position.unrealized_pnl_pct)})</span>
                  </td>
                  <td className="num mono muted col-hide-mobile">
                    {position.stop_price != null ? fmtPrice(position.stop_price) : '—'}
                  </td>
                  <td className="num mono muted col-hide-mobile">
                    {position.take_profit_price != null ? fmtPrice(position.take_profit_price) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {config && (
        <p className="tiny muted footnote">
          Sizing {fmtPct(config.risk.position_pct * 100)} of equity per entry, capped at{' '}
          {fmtPct(config.risk.max_position_pct * 100)} per position · stop{' '}
          {fmtPct(-config.risk.stop_loss_pct * 100)} · target{' '}
          {fmtPct(config.risk.take_profit_pct * 100)} · {config.risk.commission_bps} bps commission
          + {config.risk.slippage_bps} bps slippage
        </p>
      )}
    </div>
  )
}
