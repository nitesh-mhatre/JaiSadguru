/**
 * TypeScript mirrors of the backend Pydantic contracts in `backend/app/schemas.py`.
 *
 * These are the API's public shape. When a field changes on one side it must change on the
 * other in the same commit — see the note at the top of `schemas.py`.
 */

export type Action = 'BUY' | 'SELL' | 'HOLD'
export type RunStatus = 'running' | 'ok' | 'degraded' | 'failed'

/** Bar sizes the backend serves. Mirrors ALLOWED_INTERVALS in `backend/app/config.py`. */
export type Interval = '1m' | '5m' | '15m' | '30m' | '1h' | '1d' | '1wk'

export interface AssetInfo {
  symbol: string
  name: string
  asset_class: string
}

export interface RiskLimits {
  initial_capital: number
  position_pct: number
  max_positions: number
  max_position_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  commission_bps: number
  slippage_bps: number
}

export interface SignalThresholds {
  buy: number
  sell: number
  min_confidence: number
}

/** One symbol found by the search endpoint. */
export interface SearchResult {
  symbol: string
  name: string
  asset_class: string
  exchange: string
  on_watchlist: boolean
}

/** One tracked symbol with its provenance. */
export interface WatchlistEntry {
  symbol: string
  name: string
  asset_class: string
  added_at: string
  source: 'seed' | 'search' | 'manual'
}

export interface ConfigResponse {
  interval: string
  lookback: number
  pred_len: number
  sample_count: number
  kronos_model: string
  model_id: string
  max_context: number
  watchlist: AssetInfo[]
  risk: RiskLimits
  thresholds: SignalThresholds
  allowed_intervals: string[]
  scheduler_enabled: boolean
}

export interface Candle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
}

/** A forecasted bar. A model sample, never an actual. */
export interface ForecastPoint extends Candle {}

export interface CandleSeries {
  symbol: string
  name: string
  asset_class: string
  interval: string
  candles: Candle[]
  last_close: number
  change_pct: number
  rows: number
  from_cache: boolean
  /** True when the cache TTL expired and the live refresh failed. */
  stale: boolean
  fetched_at: string
}

export interface ForecastResponse {
  symbol: string
  interval: string
  created_at: string
  model: string
  horizon: number
  sample_count: number
  data_start: string
  data_end: string
  last_close: number
  target_close: number
  expected_return: number
  expected_return_pct: number
  points: ForecastPoint[]
  history: Candle[]
  from_cache: boolean
}

export interface SignalComponentBreakdown {
  magnitude: number
  agreement: number
  monotonicity: number
  smoothness: number
  weights: Record<string, number>
}

/** The `rationale` object the signal engine stores. Every field is evidence for the action. */
export interface SignalRationale {
  score?: number
  expected_return_pct?: number
  horizon_bars?: number
  volatility?: {
    daily_pct: number
    horizon_pct: number
    source: string
    window: number
  }
  components?: SignalComponentBreakdown
  trend?: { direction: number; agreement: string }
  path?: { max_adverse_move_pct: number; forecast_move_pct: number }
  thresholds?: { buy: number; sell: number; min_confidence: number }
  sizing?: {
    notional: number
    qty: number
    stop_distance: number
    risk_amount: number
    target_fraction: number
    equity?: number
    stop_loss_pct?: number
    take_profit_pct?: number
  }
  model?: { name: string; sample_count: number; interval: string }
  notes?: string[]
}

export interface SignalResponse {
  symbol: string
  name: string
  asset_class: string
  action: Action
  confidence: number
  /** Volatility-normalised forecast return being thresholded. */
  score: number
  expected_return: number
  expected_return_pct: number
  horizon: number
  last_close: number
  suggested_qty: number
  suggested_notional: number
  rationale: SignalRationale
  created_at: string
}

export interface PositionResponse {
  symbol: string
  name: string
  qty: number
  avg_price: number
  last_price: number
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  opened_at: string
  stop_price: number | null
  take_profit_price: number | null
  /** False when no mark price was available and the position was valued at cost basis. */
  priced: boolean
}

export interface TradeResponse {
  id: number
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  price: number
  gross: number
  fee: number
  realized_pnl: number | null
  executed_at: string
  reason: string
}

export interface EquityPoint {
  created_at: string
  equity: number
  cash: number
  positions_value: number
}

export interface PortfolioResponse {
  initial_capital: number
  cash: number
  positions_value: number
  equity: number
  total_return: number
  total_return_pct: number
  realized_pnl: number
  unrealized_pnl: number
  open_positions: number
  max_positions: number
  positions: PositionResponse[]
  equity_curve: EquityPoint[]
  updated_at: string
}

export interface RunResponse {
  id: number
  kind: string
  status: RunStatus
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  symbols_ok: number
  symbols_failed: number
  error: string | null
}

export interface CycleResponse {
  run: RunResponse
  signals: SignalResponse[]
  trades: TradeResponse[]
  portfolio: PortfolioResponse
  /** Symbol -> reason it was left alone. Explains a quiet cycle. */
  skipped: Record<string, string>
  notes: string[]
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  version: string
  time: string
  interval: string
  watchlist: string[]
  db_path: string
  model: string
  model_id: string
  runtime_available: boolean
  model_loaded: boolean
  device: string | null
  detail: string | null
}

export interface ForecastBundle {
  forecast: ForecastResponse
  signal: SignalResponse
}

/** Display metadata for one selectable chart interval. */
export interface IntervalOption {
  value: Interval
  label: string
  /** Chart time-axis labels switch to clock time on intraday bars. */
  intraday: boolean
}

export interface MessageResponse {
  ok: boolean
  message: string
}
