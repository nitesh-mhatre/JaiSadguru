import { useCallback, useMemo, useState } from 'react'

import { ApiError, api, loadDashboard } from './api'
import { fmtMoney, fmtPct } from './format'
import { usePolling } from './hooks/usePolling'
import { Controls, RunsStrip, type BusyAction } from './components/Controls'
import { ForecastChart } from './components/ForecastChart'
import { MarketTable } from './components/MarketTable'
import { PortfolioPanel } from './components/PortfolioPanel'
import { SignalPanel } from './components/SignalPanel'
import { TradeLog } from './components/TradeLog'
import type { ForecastBundle } from './types'

/** How often the dashboard re-reads the backend. A cycle itself takes far longer than this. */
const POLL_MS = 20_000

export default function App() {
  const { data, error, loading, refreshing, lastUpdated, refresh } = usePolling(
    loadDashboard,
    POLL_MS,
  )

  const [selected, setSelected] = useState<string | null>(null)
  const [freshForecast, setFreshForecast] = useState<ForecastBundle | null>(null)
  const [busy, setBusy] = useState<BusyAction>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const activeSymbol = selected ?? data?.config.watchlist[0]?.symbol ?? null

  /** Run a button action with shared busy/error/notice bookkeeping. */
  const runAction = useCallback(
    async (kind: BusyAction, action: () => Promise<string>) => {
      setBusy(kind)
      setActionError(null)
      setNotice(null)
      try {
        setNotice(await action())
      } catch (err) {
        setActionError(
          err instanceof ApiError || err instanceof Error ? err.message : String(err),
        )
        // Refresh anyway so the UI reflects whatever the backend actually did.
        await refresh()
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  const handleRunCycle = useCallback(
    (trade: boolean) =>
      runAction(trade ? 'cycle' : 'dry', async () => {
        const result = await api.runCycle(trade)
        await refresh()

        const parts = [
          `Run #${result.run.id} ${result.run.status}`,
          `${result.signals.length} signal${result.signals.length === 1 ? '' : 's'}`,
          trade
            ? `${result.trades.length} trade${result.trades.length === 1 ? '' : 's'}`
            : 'no trades (dry run)',
        ]
        const skippedCount = Object.keys(result.skipped).length
        if (skippedCount > 0) parts.push(`${skippedCount} skipped`)
        if (result.run.error) parts.push(result.run.error)
        return parts.join(' · ')
      }),
    [runAction, refresh],
  )

  const handleReset = useCallback(
    () =>
      runAction('reset', async () => {
        const portfolio = await api.resetPortfolio()
        setFreshForecast(null)
        await refresh()
        return `Paper portfolio reset to ${fmtMoney(portfolio.initial_capital)}`
      }),
    [runAction, refresh],
  )

  const handleForecast = useCallback(() => {
    if (!activeSymbol) return Promise.resolve()
    return runAction('forecast', async () => {
      const bundle = await api.forecastSymbol(activeSymbol)
      setFreshForecast(bundle)
      await refresh()
      return `${activeSymbol}: ${bundle.signal.action} · score ${bundle.signal.score.toFixed(
        2,
      )} · confidence ${fmtPct(bundle.signal.confidence * 100, 0)}`
    })
  }, [activeSymbol, runAction, refresh])

  const series = useMemo(
    () => data?.market.find((item) => item.symbol === activeSymbol) ?? null,
    [data, activeSymbol],
  )

  const signal = useMemo(
    () => data?.signals.find((item) => item.symbol === activeSymbol) ?? null,
    [data, activeSymbol],
  )

  // A freshly run forecast wins over the stored one, but only for the symbol it belongs to.
  const forecast = useMemo(() => {
    if (freshForecast && freshForecast.forecast.symbol === activeSymbol) {
      return freshForecast.forecast
    }
    return data?.forecasts.find((item) => item.symbol === activeSymbol) ?? null
  }, [freshForecast, data, activeSymbol])

  const displayError = actionError ?? error

  return (
    <div className="app">
      <Controls
        health={data?.health ?? null}
        config={data?.config ?? null}
        lastUpdated={lastUpdated}
        refreshing={refreshing}
        busy={busy}
        error={displayError}
        notice={notice}
        onRefresh={() => void refresh()}
        onRunCycle={(trade) => void handleRunCycle(trade)}
        onReset={() => void handleReset()}
      />

      {data && <RunsStrip runs={data.runs} />}

      <section className="card">
        <div className="card-head">
          <h2>Watchlist</h2>
          <span className="tiny muted">
            {data ? `${data.market.length} symbols · click a row to chart it` : 'loading…'}
          </span>
        </div>
        {data ? (
          <MarketTable
            series={data.market}
            signals={data.signals}
            selected={activeSymbol}
            onSelect={(symbol) => setSelected(symbol)}
          />
        ) : (
          <div className="empty">{loading ? 'Loading market data…' : 'No data available.'}</div>
        )}
      </section>

      <div className="grid-2">
        <section className="card">
          <div className="card-head">
            <h2>Forecast — {activeSymbol ?? '—'}</h2>
            {series?.stale && <span className="tiny warn-text">prices may be stale</span>}
          </div>
          <ForecastChart series={series} forecast={forecast} />
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Signal</h2>
            <span className="tiny muted">full rationale, including the evidence against</span>
          </div>
          <SignalPanel
            signal={signal}
            symbol={activeSymbol}
            config={data?.config ?? null}
            busy={busy === 'forecast'}
            onRunForecast={() => void handleForecast()}
          />
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="card-head">
            <h2>Paper portfolio</h2>
            <span className="tag tag-sim">simulated</span>
          </div>
          <PortfolioPanel portfolio={data?.portfolio ?? null} config={data?.config ?? null} />
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Trade log</h2>
            <span className="tiny muted">{data?.trades.length ?? 0} fills</span>
          </div>
          <TradeLog trades={data?.trades ?? []} />
        </section>
      </div>

      <footer className="footer">
        <strong>Simulation only.</strong> No orders are placed and no broker is connected. Kronos
        output is a statistical sample, not investment advice, and historical behaviour does not
        transfer to live markets.
      </footer>
    </div>
  )
}
