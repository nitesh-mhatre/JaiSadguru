import type { TradeResponse } from '../types'
import { fmtDateTime, fmtMoney, fmtPrice, fmtQty, signClass } from '../format'

interface Props {
  trades: TradeResponse[]
}

/**
 * Every simulated fill, newest first, with the reason the engine recorded for it.
 *
 * The reason column is the point of this table: a P&L number tells you what happened, the reason
 * tells you why, and only the second one is actionable when the strategy misbehaves.
 */
export function TradeLog({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="empty small">
        No simulated trades yet. Signals only trade when they clear the score threshold and the
        risk limits allow it.
      </div>
    )
  }

  return (
    <div className="scroll-y table-scroll">
      <table className="table compact">
        <thead>
          <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>Side</th>
            <th className="num">Qty</th>
            <th className="num">Fill</th>
            <th className="num col-hide-mobile col-hide-narrow">Fee</th>
            <th className="num col-hide-mobile">Realised</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id}>
              <td className="muted tiny">{fmtDateTime(trade.executed_at)}</td>
              <td className="mono">{trade.symbol}</td>
              <td>
                <span className={`badge badge-${trade.side.toLowerCase()}`}>{trade.side}</span>
              </td>
              <td className="num mono">{fmtQty(trade.qty)}</td>
              <td className="num mono">{fmtPrice(trade.price)}</td>
              <td className="num mono muted col-hide-mobile col-hide-narrow">{fmtMoney(trade.fee)}</td>
              <td className={`num mono col-hide-mobile ${trade.realized_pnl == null ? 'muted' : signClass(trade.realized_pnl)}`}>
                {trade.realized_pnl == null ? '—' : fmtMoney(trade.realized_pnl)}
              </td>
              <td className="muted tiny reason">{trade.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
