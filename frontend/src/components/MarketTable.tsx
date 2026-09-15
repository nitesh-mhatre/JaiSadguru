import type { CandleSeries, SignalResponse } from '../types'
import { fmtFractionPct, fmtPct, fmtPrice, fmtRelative, signClass } from '../format'
import { ActionBadge, ClassTag, ConfidenceBar } from './Badge'

interface Props {
  series: CandleSeries[]
  signals: SignalResponse[]
  selected: string | null
  onSelect: (symbol: string) => void
  onRemove?: (symbol: string) => void
  busy?: boolean
}

/**
 * The watchlist. Clicking a row selects that symbol for the chart and signal panel.
 *
 * A symbol with no stored signal shows a dash rather than a HOLD — "we have not evaluated this
 * yet" is a different statement from "we evaluated it and there is no edge". The remove button
 * stops tracking a symbol; the backend refuses while a paper position is open in it.
 */
export function MarketTable({ series, signals, selected, onSelect, onRemove, busy = false }: Props) {
  const signalBySymbol = new Map(signals.map((s) => [s.symbol, s]))

  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="col-hide-mobile">Name</th>
            <th className="num">Last</th>
            <th className="num">Change</th>
            <th className="num">Signal</th>
            <th className="num col-hide-mobile">Score</th>
            <th className="col-hide-mobile col-hide-narrow">Confidence</th>
            <th className="num">Exp. move</th>
            <th className="num col-hide-mobile">Signal age</th>
            {onRemove && <th aria-label="Remove" />}
          </tr>
        </thead>
        <tbody>
          {series.map((item) => {
            const signal = signalBySymbol.get(item.symbol)
            return (
              <tr
                key={item.symbol}
                className={item.symbol === selected ? 'row-selected' : undefined}
                onClick={() => onSelect(item.symbol)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(item.symbol)
                  }
                }}
                tabIndex={0}
                role="button"
                aria-pressed={item.symbol === selected}
              >
                <td>
                  <div className="symbol">
                    <span className="symbol-ticker">{item.symbol}</span>
                    {item.stale && <span className="warn-dot" title="Prices may be stale" />}
                  </div>
                </td>
                <td className="muted col-hide-mobile">
                  {item.name} <ClassTag value={item.asset_class} />
                </td>
                <td className="num mono">{fmtPrice(item.last_close)}</td>
                <td className={`num mono ${signClass(item.change_pct)}`}>
                  {fmtPct(item.change_pct)}
                </td>
                <td className="num">
                  {signal ? <ActionBadge action={signal.action} /> : <span className="muted">—</span>}
                </td>
                <td className={`num mono col-hide-mobile ${signal ? signClass(signal.score) : ''}`}>
                  {signal ? signal.score.toFixed(2) : '—'}
                </td>
                <td className="col-hide-mobile col-hide-narrow">
                  {signal ? (
                    <div className="confidence-cell">
                      <ConfidenceBar value={signal.confidence} />
                      <span className="mono tiny">{(signal.confidence * 100).toFixed(0)}%</span>
                    </div>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className={`num mono ${signal ? signClass(signal.expected_return) : ''}`}>
                  {signal ? fmtFractionPct(signal.expected_return) : '—'}
                </td>
                <td className="num muted tiny col-hide-mobile">
                  {signal ? fmtRelative(new Date(signal.created_at)) : 'never'}
                </td>
                <td className="num">
                  {onRemove && (
                    <button
                      className="btn btn-ghost btn-sm row-remove"
                      onClick={(event) => {
                        event.stopPropagation()
                        onRemove(item.symbol)
                      }}
                      onKeyDown={(event) => event.stopPropagation()}
                      disabled={busy}
                      title={`Stop tracking ${item.symbol}`}
                    >
                      ✕
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
