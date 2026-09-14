/**
 * Typed API client.
 *
 * In development `VITE_API_BASE` is empty and requests go to `/api/...` on the Vite dev server,
 * which proxies them to the backend. That keeps the browser on a single origin, so the dashboard
 * never needs to deal with CORS.
 */

import type {
  CandleSeries,
  ConfigResponse,
  CycleResponse,
  ForecastBundle,
  ForecastResponse,
  HealthResponse,
  MessageResponse,
  PortfolioResponse,
  RunResponse,
  SignalResponse,
  TradeResponse,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    // A thrown fetch means the request never completed — usually the backend is not running.
    throw new ApiError(
      `Cannot reach the API at ${BASE || window.location.origin}. Is the backend running on port 8000?`,
      0,
    )
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body?.detail)) {
        detail = body.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
      }
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

/** Symbols contain `^` and `=`, which need encoding to survive a URL path. */
const enc = (symbol: string) => encodeURIComponent(symbol)

export const api = {
  health: () => request<HealthResponse>('/api/health'),

  config: () => request<ConfigResponse>('/api/config'),

  /** Omitting `symbols` makes the backend use its configured watchlist. */
  market: (rows: number, symbols?: string[]) =>
    request<CandleSeries[]>(
      symbols && symbols.length > 0
        ? `/api/market?symbols=${encodeURIComponent(symbols.join(','))}&rows=${rows}`
        : `/api/market?rows=${rows}`,
    ),

  latestSignals: () => request<SignalResponse[]>('/api/signals/latest'),

  latestForecasts: () => request<ForecastResponse[]>('/api/forecast/latest'),

  portfolio: () => request<PortfolioResponse>('/api/portfolio'),

  trades: (limit = 100) => request<TradeResponse[]>(`/api/trades?limit=${limit}`),

  runs: (limit = 10) => request<RunResponse[]>(`/api/runs?limit=${limit}`),

  forecastSymbol: (symbol: string, refresh = false) =>
    request<ForecastBundle>(`/api/forecast/${enc(symbol)}`, {
      method: 'POST',
      body: JSON.stringify({ refresh }),
    }),

  runCycle: (trade = true, refresh = false) =>
    request<CycleResponse>(`/api/paper/step?trade=${trade}&refresh=${refresh}`, { method: 'POST' }),

  resetPortfolio: (initialCapital?: number) =>
    request<PortfolioResponse>('/api/paper/reset', {
      method: 'POST',
      body: JSON.stringify({ initial_capital: initialCapital ?? null }),
    }),

  warmup: () => request<MessageResponse>('/api/system/warmup', { method: 'POST' }),
}

/** Everything the dashboard renders, fetched together so one poll is one consistent snapshot. */
export interface DashboardData {
  health: HealthResponse
  config: ConfigResponse
  market: CandleSeries[]
  signals: SignalResponse[]
  forecasts: ForecastResponse[]
  portfolio: PortfolioResponse
  trades: TradeResponse[]
  runs: RunResponse[]
}

/** Bars of history the chart requests; enough to show context without a heavy payload. */
const CHART_BARS = 180

export async function loadDashboard(): Promise<DashboardData> {
  // Config supplies the watchlist to the UI; the market call relies on the backend's own
  // configured watchlist, so everything can be fetched in parallel in one round trip.
  const [health, config, market, signals, forecasts, portfolio, trades, runs] = await Promise.all([
    api.health(),
    api.config(),
    api.market(CHART_BARS),
    api.latestSignals(),
    api.latestForecasts(),
    api.portfolio(),
    api.trades(100),
    api.runs(10),
  ])

  return { health, config, market, signals, forecasts, portfolio, trades, runs }
}
