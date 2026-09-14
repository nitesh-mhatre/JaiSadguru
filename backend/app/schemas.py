"""Pydantic contracts for the HTTP API.

These shapes are the contract between the FastAPI backend and the React dashboard. Changing a
field name here is a breaking change for the frontend — update ``frontend/src/types.ts`` in the
same commit and note it in ``doc/plan.md``.

All timestamps are ISO-8601 strings in UTC.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

#: The only actions the signal engine can emit. Long-only by design — there is no SHORT
#: action because the paper engine does not support shorting (see ``doc/objective.md`` §5).
Action = Literal["BUY", "SELL", "HOLD"]


# ------------------------------------------------------------------------------------
# Reference data
# ------------------------------------------------------------------------------------


class AssetInfo(BaseModel):
    """One tracked symbol."""

    symbol: str
    name: str
    asset_class: str


class RiskLimits(BaseModel):
    """Risk configuration currently enforced by the paper-trading engine."""

    initial_capital: float
    position_pct: float
    max_positions: int
    max_position_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    commission_bps: float
    slippage_bps: float


class SignalThresholds(BaseModel):
    """Score thresholds that separate BUY / HOLD / SELL."""

    buy: float
    sell: float
    min_confidence: float


class ConfigResponse(BaseModel):
    """Everything the dashboard needs to render its static chrome."""

    interval: str
    lookback: int
    pred_len: int
    sample_count: int
    kronos_model: str
    model_id: str
    max_context: int
    watchlist: list[AssetInfo]
    risk: RiskLimits
    thresholds: SignalThresholds
    allowed_intervals: list[str]
    scheduler_enabled: bool


# ------------------------------------------------------------------------------------
# Market data
# ------------------------------------------------------------------------------------


class Candle(BaseModel):
    """A single OHLCV bar."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class CandleSeries(BaseModel):
    """Historical bars for one symbol."""

    symbol: str
    name: str
    asset_class: str
    interval: str
    candles: list[Candle]
    last_close: float
    change_pct: float = Field(description="Close-over-close change of the last bar, in percent.")
    rows: int
    from_cache: bool
    stale: bool = Field(
        description="True when the cache TTL expired and a live refresh failed, so these bars "
        "may be behind the market."
    )
    fetched_at: str


# ------------------------------------------------------------------------------------
# Forecasts
# ------------------------------------------------------------------------------------


class ForecastPoint(BaseModel):
    """One forecasted bar. These are model samples, never actuals."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class ForecastResponse(BaseModel):
    """A Kronos forecast plus the exact context window it was derived from.

    ``data_start`` / ``data_end`` are recorded so a forecast can never be silently attributed
    to the wrong bars (``doc/objective.md`` rule R6).
    """

    symbol: str
    interval: str
    created_at: str
    model: str
    horizon: int
    sample_count: int
    data_start: str
    data_end: str
    last_close: float
    target_close: float = Field(description="Final forecasted close of the horizon.")
    expected_return: float = Field(description="target_close / last_close - 1, as a fraction.")
    expected_return_pct: float
    points: list[ForecastPoint]
    history: list[Candle] = Field(
        description="The lookback bars fed to the model, so the chart can plot context "
        "and forecast in one response."
    )
    from_cache: bool = False


# ------------------------------------------------------------------------------------
# Signals
# ------------------------------------------------------------------------------------


class SignalResponse(BaseModel):
    """The trading decision derived from one forecast, with its full rationale."""

    symbol: str
    name: str
    asset_class: str
    action: Action
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence in the action.")
    score: float = Field(description="Volatility-normalised forecast return being thresholded.")
    expected_return: float
    expected_return_pct: float
    horizon: int
    last_close: float
    suggested_qty: float = Field(description="Position size the risk limits permit, in units.")
    suggested_notional: float
    rationale: dict[str, Any] = Field(
        description="Machine-readable reasons behind the action, for auditability."
    )
    created_at: str


class ForecastBundle(BaseModel):
    """A forecast together with the signal derived from it.

    Defined after :class:`SignalResponse` so the reference resolves without a forward-ref
    rebuild step.
    """

    forecast: ForecastResponse
    signal: SignalResponse


# ------------------------------------------------------------------------------------
# Paper portfolio
# ------------------------------------------------------------------------------------


class PositionResponse(BaseModel):
    """An open simulated position, marked to the latest known price."""

    symbol: str
    name: str
    qty: float
    avg_price: float
    last_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: str
    stop_price: float | None
    take_profit_price: float | None
    priced: bool = Field(
        default=True,
        description="False when no mark price was available and the position was valued at its "
        "cost basis instead, so the UI can show it as unpriced rather than as a flat "
        "zero-P&L holding.",
    )


class TradeResponse(BaseModel):
    """A completed simulated fill."""

    id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float
    price: float = Field(description="Fill price, including modelled slippage.")
    gross: float
    fee: float
    realized_pnl: float | None
    executed_at: str
    reason: str


class EquityPoint(BaseModel):
    """One mark-to-market snapshot of the portfolio."""

    created_at: str
    equity: float
    cash: float
    positions_value: float


class PortfolioResponse(BaseModel):
    """The complete simulated account state."""

    initial_capital: float
    cash: float
    positions_value: float
    equity: float
    total_return: float
    total_return_pct: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: int
    max_positions: int
    positions: list[PositionResponse]
    equity_curve: list[EquityPoint]
    updated_at: str


# ------------------------------------------------------------------------------------
# Runs and orchestration
# ------------------------------------------------------------------------------------


class RunResponse(BaseModel):
    """The outcome record of one bot execution."""

    id: int
    kind: str
    status: Literal["running", "ok", "degraded", "failed"]
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    symbols_ok: int
    symbols_failed: int
    error: str | None


class CycleResponse(BaseModel):
    """Result of one full cycle: fetch -> forecast -> signal -> execute -> snapshot."""

    run: RunResponse
    signals: list[SignalResponse]
    trades: list[TradeResponse]
    portfolio: PortfolioResponse
    skipped: dict[str, str] = Field(
        default_factory=dict, description="Symbol -> reason it was excluded from this cycle."
    )
    notes: list[str] = Field(default_factory=list)


class ResetRequest(BaseModel):
    """Reset the simulated portfolio back to a clean account."""

    initial_capital: float | None = Field(
        default=None, description="Defaults to the configured INITIAL_CAPITAL."
    )


class ForecastRequest(BaseModel):
    """Optional per-request overrides for a forecast."""

    lookback: int | None = Field(default=None, gt=0)
    pred_len: int | None = Field(default=None, gt=0, le=120)
    sample_count: int | None = Field(default=None, gt=0, le=32)
    temperature: float | None = Field(default=None, gt=0.0, le=5.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    refresh: bool = Field(default=False, description="Bypass the market-data cache.")


# ------------------------------------------------------------------------------------
# System
# ------------------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness plus an honest statement of what the backend can actually do right now."""

    status: Literal["ok", "degraded"]
    version: str
    time: str
    interval: str
    watchlist: list[str]
    db_path: str
    model: str
    model_id: str
    runtime_available: bool = Field(description="True when torch and the vendored model import.")
    model_loaded: bool = Field(description="True once weights are resident in memory.")
    device: str | None
    detail: str | None = None


class MessageResponse(BaseModel):
    """Simple acknowledgement payload."""

    ok: bool
    message: str


class StatsResponse(BaseModel):
    """Row counts per table, for manual inspection and debugging."""

    runs: int
    forecasts: int
    signals: int
    positions: int
    trades: int
    snapshots: int
