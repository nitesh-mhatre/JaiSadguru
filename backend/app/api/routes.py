"""HTTP routes.

Split by concern with tags so ``/docs`` reads as a usable map of the system: **system**, **market**,
**forecast**, **signals**, **trading**.

Routers stay thin. They validate input, call one service, and translate service dataclasses into the
response contract. Any trading logic living here would be logic the paper engine could not enforce,
which is exactly the split rule R5 exists to prevent.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import __version__
from ..config import ALLOWED_INTERVALS, Settings, classify_symbol, period_for_interval
from ..config import settings as default_settings
from ..schemas import (
    AssetInfo,
    CandleSeries,
    ConfigResponse,
    CycleResponse,
    ForecastBundle,
    ForecastRequest,
    ForecastResponse,
    HealthResponse,
    MessageResponse,
    PortfolioResponse,
    ResetRequest,
    RiskLimits,
    RunResponse,
    SearchResultModel,
    SignalResponse,
    SignalThresholds,
    StatsResponse,
    TradeResponse,
    WatchlistAddRequest,
    WatchlistEntryModel,
)
from ..services.cycle import CycleResult
from ..services.forecast import ForecastError, ForecastOutcome, ForecastService, KronosRuntime
from ..services.market_data import MarketDataError, MarketDataService
from ..services.paper_trading import Fill, PaperTradingEngine, PortfolioState
from ..services.scheduler import CycleScheduler
from ..services.signals import Signal
from ..services.symbol_search import SearchError, SymbolSearchService
from ..services.watchlist import WatchlistError, WatchlistService
from ..store import Store, utcnow
from .deps import (
    get_cycle,
    get_forecast_service,
    get_market_data,
    get_paper,
    get_runtime,
    get_scheduler,
    get_store,
    get_symbol_search,
    get_watchlist,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------------------------
# Dataclass -> response converters
# ------------------------------------------------------------------------------------


def _signal_response(signal: Signal) -> SignalResponse:
    return SignalResponse(
        symbol=signal.symbol,
        name=signal.name,
        asset_class=signal.asset_class,
        action=signal.action,  # type: ignore[arg-type]
        confidence=signal.confidence,
        score=signal.score,
        expected_return=signal.expected_return,
        expected_return_pct=signal.expected_return_pct,
        horizon=signal.horizon,
        last_close=signal.last_close,
        suggested_qty=signal.suggested_qty,
        suggested_notional=signal.suggested_notional,
        rationale=signal.rationale,
        created_at=signal.created_at,
    )


def _stored_signal_response(row: dict, config: Settings) -> SignalResponse:
    """Rehydrate a persisted signal, backfilling display fields that are not stored."""
    symbol = str(row["symbol"])
    asset = config.asset(symbol)
    last_close = float(row["last_close"])
    qty = float(row["suggested_qty"])
    return SignalResponse(
        symbol=symbol,
        name=asset.name if asset else symbol,
        asset_class=asset.asset_class if asset else classify_symbol(symbol),
        action=str(row["action"]),  # type: ignore[arg-type]
        confidence=float(row["confidence"]),
        score=float(row["score"]),
        expected_return=float(row["expected_return"]),
        expected_return_pct=float(row["expected_return"]) * 100.0,
        horizon=int(row["horizon"]),
        last_close=last_close,
        suggested_qty=qty,
        suggested_notional=round(qty * last_close, 2),
        rationale=row.get("rationale") or {},
        created_at=str(row["created_at"]),
    )


def _forecast_response(outcome: ForecastOutcome) -> ForecastResponse:
    return ForecastResponse(
        symbol=outcome.symbol,
        interval=outcome.interval,
        created_at=outcome.created_at,
        model=outcome.model,
        horizon=outcome.horizon,
        sample_count=outcome.sample_count,
        data_start=outcome.data_start,
        data_end=outcome.data_end,
        last_close=outcome.last_close,
        target_close=outcome.target_close,
        expected_return=outcome.expected_return,
        expected_return_pct=outcome.expected_return_pct,
        points=outcome.points,  # type: ignore[arg-type]
        history=outcome.history,  # type: ignore[arg-type]
    )


def _portfolio_response(state: PortfolioState, config: Settings) -> PortfolioResponse:
    return PortfolioResponse(
        initial_capital=state.initial_capital,
        cash=state.cash,
        positions_value=state.positions_value,
        equity=state.equity,
        total_return=round(state.total_return, 2),
        total_return_pct=round(state.total_return_pct, 4),
        realized_pnl=state.realized_pnl,
        unrealized_pnl=state.unrealized_pnl,
        open_positions=len(state.positions),
        max_positions=config.max_positions,
        positions=state.positions,  # type: ignore[arg-type]
        equity_curve=state.equity_curve,  # type: ignore[arg-type]
        updated_at=state.updated_at,
    )


def _cycle_response(result: CycleResult, store: Store, config: Settings) -> CycleResponse:
    run_row = store.get_run(result.run_id)
    if run_row is None:  # pragma: no cover - the row is written before the cycle returns
        raise HTTPException(status_code=500, detail="run record disappeared during the cycle")
    return CycleResponse(
        run=RunResponse.model_validate(run_row),
        signals=[_signal_response(s) for s in result.signals],
        trades=[_fill_response(f) for f in result.fills],
        portfolio=_portfolio_response(result.portfolio, config),
        skipped=result.skipped,
        notes=result.notes,
    )


def _fill_response(fill: Fill) -> TradeResponse:
    return TradeResponse.model_validate(fill.to_dict())


def _candles(frame) -> list[dict]:
    return [
        {
            "timestamp": index.isoformat(),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
            "amount": float(row.amount),
        }
        for index, row in frame.iterrows()
    ]


def _market_series(result, rows: int) -> CandleSeries:
    frame = result.frame.tail(rows) if rows and rows > 0 else result.frame
    return CandleSeries(
        symbol=result.symbol,
        name=result.name,
        asset_class=result.asset_class,
        interval=result.interval,
        candles=_candles(frame),
        last_close=result.last_close,
        change_pct=round(result.change_pct, 4),
        rows=len(frame),
        from_cache=result.from_cache,
        stale=result.stale,
        fetched_at=result.fetched_at,
    )


# ------------------------------------------------------------------------------------
# System
# ------------------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(
    runtime: KronosRuntime = Depends(get_runtime),
    store: Store = Depends(get_store),
    watchlist: WatchlistService = Depends(get_watchlist),
) -> HealthResponse:
    """Liveness plus an honest statement of what the backend can actually do right now."""
    import_error = runtime.import_error()
    return HealthResponse(
        status="degraded" if import_error else "ok",
        version=__version__,
        time=utcnow(),
        interval=default_settings.interval,
        watchlist=watchlist.symbols(),
        db_path=str(store.db_path),
        model=default_settings.kronos_model,
        model_id=default_settings.model_spec.model_id,
        runtime_available=import_error is None,
        model_loaded=runtime.loaded,
        device=runtime.device,
        detail=import_error,
    )


@router.get("/config", response_model=ConfigResponse, tags=["system"])
def get_config(watchlist: WatchlistService = Depends(get_watchlist)) -> ConfigResponse:
    """Everything the dashboard needs to render its static chrome."""
    config = default_settings
    live_assets = watchlist.assets()
    return ConfigResponse(
        interval=config.interval,
        lookback=config.lookback,
        pred_len=config.pred_len,
        sample_count=config.sample_count,
        kronos_model=config.kronos_model,
        model_id=config.model_spec.model_id,
        max_context=config.model_spec.max_context,
        watchlist=[
            AssetInfo(symbol=a.symbol, name=a.name, asset_class=a.asset_class)
            for a in live_assets
        ],
        risk=RiskLimits(
            initial_capital=config.initial_capital,
            position_pct=config.position_pct,
            max_positions=config.max_positions,
            max_position_pct=config.max_position_pct,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            commission_bps=config.commission_bps,
            slippage_bps=config.slippage_bps,
        ),
        thresholds=SignalThresholds(
            buy=config.signal_buy_threshold,
            sell=config.signal_sell_threshold,
            min_confidence=config.min_confidence,
        ),
        allowed_intervals=sorted(ALLOWED_INTERVALS),
        scheduler_enabled=config.scheduler_enabled,
    )


@router.post("/system/warmup", response_model=MessageResponse, tags=["system"])
def warmup(runtime: KronosRuntime = Depends(get_runtime)) -> MessageResponse:
    """Load the Kronos weights now rather than on the first forecast request."""
    try:
        device = runtime.ensure_loaded()
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=exc.reason) from exc
    return MessageResponse(
        ok=True, message=f"{default_settings.kronos_model} loaded on {device}"
    )


@router.get("/system/stats", response_model=StatsResponse, tags=["system"])
def stats(store: Store = Depends(get_store)) -> StatsResponse:
    return StatsResponse(**store.stats())


# ------------------------------------------------------------------------------------
# Market data
# ------------------------------------------------------------------------------------


def _default_rows() -> int:
    return default_settings.lookback


def _validate_interval(interval: str | None) -> str | None:
    """Reject an unknown interval with a 422 naming the supported set."""
    if interval is None:
        return None
    try:
        period_for_interval(interval)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return interval


@router.get("/market/{symbol}", response_model=CandleSeries, tags=["market"])
def market_symbol(
    symbol: str,
    interval: str | None = Query(default=None, description="Bar size: 1m 5m 15m 30m 1h 1d 1wk."),
    rows: int = Query(default=0, ge=0, le=10_000, description="0 returns every cached bar."),
    refresh: bool = Query(default=False),
    data: MarketDataService = Depends(get_market_data),
) -> CandleSeries:
    """Historical bars for one symbol.

    Symbols containing ``^`` or ``=`` should be percent-encoded by the client; the dashboard uses
    ``encodeURIComponent`` for exactly this reason.
    """
    try:
        result = data.fetch(symbol, interval=_validate_interval(interval), refresh=refresh)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=exc.reason) from exc
    return _market_series(result, rows or _default_rows())


@router.get("/market", response_model=list[CandleSeries], tags=["market"])
def market_watchlist(
    symbols: str | None = Query(default=None, description="Comma-separated; defaults to the live watchlist."),
    interval: str | None = Query(default=None, description="Bar size: 1m 5m 15m 30m 1h 1d 1wk."),
    rows: int = Query(default=0, ge=0, le=10_000),
    refresh: bool = Query(default=False),
    data: MarketDataService = Depends(get_market_data),
    watchlist: WatchlistService = Depends(get_watchlist),
) -> list[CandleSeries]:
    """Historical bars for several symbols. Symbols that fail are omitted rather than guessed."""
    validated_interval = _validate_interval(interval)
    requested = (
        [s.strip() for s in symbols.split(",") if s.strip()]
        if symbols
        else watchlist.symbols()
    )
    series: list[CandleSeries] = []
    for symbol in requested:
        try:
            result = data.fetch(symbol, interval=validated_interval, refresh=refresh)
        except MarketDataError as exc:
            logger.warning("Skipping %s: %s", symbol, exc.reason)
            continue
        series.append(_market_series(result, rows or _default_rows()))
    if not series:
        raise HTTPException(status_code=502, detail="no market data available for any requested symbol")
    return series


# ------------------------------------------------------------------------------------
# Forecasts
# ------------------------------------------------------------------------------------


@router.post("/forecast/{symbol}", response_model=ForecastBundle, tags=["forecast"])
def forecast_symbol(
    symbol: str,
    request: ForecastRequest | None = None,
    cycle=Depends(get_cycle),
    store: Store = Depends(get_store),
) -> ForecastBundle:
    """Forecast one symbol and derive its signal.

    Slow on the first call: the Kronos weights download from Hugging Face and load into memory.
    """
    options = request or ForecastRequest()
    forecast_service: ForecastService = cycle.forecasts

    run_id = store.create_run("forecast")
    started = time.perf_counter()
    try:
        outcome, signal = cycle.forecast_symbol(
            symbol,
            refresh=options.refresh,
            interval=_validate_interval(options.interval),
            lookback=options.lookback,
            pred_len=options.pred_len,
            sample_count=options.sample_count,
            temperature=options.temperature,
            top_p=options.top_p,
        )
    except ForecastError as exc:
        store.finish_run(
            run_id,
            status="failed",
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=exc.reason,
        )
        status = 503 if not forecast_service.runtime.available() else 502
        raise HTTPException(status_code=status, detail=f"{symbol}: {exc.reason}") from exc

    cycle.persist(outcome, signal, run_id=run_id)
    store.finish_run(
        run_id,
        status="ok",
        symbols_ok=1,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return ForecastBundle(forecast=_forecast_response(outcome), signal=_signal_response(signal))


@router.get("/forecast/latest", tags=["forecast"], response_model=list[ForecastResponse])
def latest_forecasts(
    limit: int = Query(default=20, ge=1, le=200),
    store: Store = Depends(get_store),
    watchlist: WatchlistService = Depends(get_watchlist),
) -> list[ForecastResponse]:
    """Most recent stored forecast per symbol (metadata only — points are on ``/forecast/{symbol}``)."""
    responses: list[ForecastResponse] = []
    for symbol in watchlist.symbols():
        row = store.latest_forecast(symbol)
        if row is None:
            continue
        points = row.get("points") or []
        responses.append(
            ForecastResponse(
                symbol=str(row["symbol"]),
                interval=str(row["interval"]),
                created_at=str(row["created_at"]),
                model=str(row["model"]),
                horizon=int(row["horizon"]),
                sample_count=int(row["sample_count"]),
                data_start=str(row["data_start"]),
                data_end=str(row["data_end"]),
                last_close=float(row["last_close"]),
                target_close=float(row["target_close"]),
                expected_return=(
                    (float(row["target_close"]) - float(row["last_close"])) / float(row["last_close"])
                    if float(row["last_close"])
                    else 0.0
                ),
                expected_return_pct=(
                    (float(row["target_close"]) - float(row["last_close"]))
                    / float(row["last_close"])
                    * 100.0
                    if float(row["last_close"])
                    else 0.0
                ),
                points=points,
                history=[],
                from_cache=True,
            )
        )
    return responses[:limit]


# ------------------------------------------------------------------------------------
# Signals
# ------------------------------------------------------------------------------------


@router.get("/signals/latest", response_model=list[SignalResponse], tags=["signals"])
def latest_signals(store: Store = Depends(get_store)) -> list[SignalResponse]:
    """The most recent signal per symbol."""
    return [_stored_signal_response(row, default_settings) for row in store.latest_signals()]


@router.get("/signals", response_model=list[SignalResponse], tags=["signals"])
def recent_signals(
    limit: int = Query(default=50, ge=1, le=500),
    store: Store = Depends(get_store),
) -> list[SignalResponse]:
    """Signal history, newest first."""
    return [_stored_signal_response(row, default_settings) for row in store.recent_signals(limit)]


# ------------------------------------------------------------------------------------
# Search and watchlist
# ------------------------------------------------------------------------------------


@router.get("/search", response_model=list[SearchResultModel], tags=["watchlist"])
def search_symbols(
    q: str = Query(min_length=1, max_length=64, description="Name or ticker, e.g. bitcoin, reliance, BTC-USD."),
    limit: int = Query(default=10, ge=1, le=25),
    search: SymbolSearchService = Depends(get_symbol_search),
) -> list[SearchResultModel]:
    """Find tradeable symbols by name — crypto, Indian equities, indices and futures.

    Keyless: backed by the same public Yahoo endpoint ``yfinance`` resolves symbols through.
    Cached in SQLite; on network failure it falls back to the built-in asset table.
    """
    try:
        return [SearchResultModel(**hit) for hit in search.search(q, limit=limit)]
    except SearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/watchlist", response_model=list[WatchlistEntryModel], tags=["watchlist"])
def get_watchlist_entries(
    watchlist: WatchlistService = Depends(get_watchlist),
) -> list[WatchlistEntryModel]:
    """The symbols being tracked, in insertion order."""
    return [
        WatchlistEntryModel(
            symbol=e.symbol,
            name=e.name,
            asset_class=e.asset_class,
            added_at=e.added_at,
            source=e.source,  # type: ignore[arg-type]
        )
        for e in watchlist.entries()
    ]


@router.post("/watchlist", response_model=WatchlistEntryModel, status_code=201, tags=["watchlist"])
def add_watchlist_entry(
    request: WatchlistAddRequest,
    watchlist: WatchlistService = Depends(get_watchlist),
) -> WatchlistEntryModel:
    """Start tracking a symbol.

    The symbol is validated by actually fetching one bar, so an unpriceable ticker is rejected
    here rather than silently skipped by every future cycle.
    """
    try:
        entry = watchlist.add(request.symbol, request.name, request.asset_class)
    except WatchlistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WatchlistEntryModel(
        symbol=entry.symbol,
        name=entry.name,
        asset_class=entry.asset_class,
        added_at=entry.added_at,
        source=entry.source,
    )


@router.delete("/watchlist/{symbol}", response_model=MessageResponse, tags=["watchlist"])
def remove_watchlist_entry(
    symbol: str,
    watchlist: WatchlistService = Depends(get_watchlist),
) -> MessageResponse:
    """Stop tracking a symbol. Refused while a paper position is open in it."""
    try:
        watchlist.remove(symbol)
    except WatchlistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageResponse(ok=True, message=f"{symbol.upper()} removed from the watchlist")


# ------------------------------------------------------------------------------------
# Trading
# ------------------------------------------------------------------------------------


@router.get("/portfolio", response_model=PortfolioResponse, tags=["trading"])
def portfolio(
    paper: PaperTradingEngine = Depends(get_paper),
) -> PortfolioResponse:
    """Current simulated account, marked against the latest observed closes."""
    return _portfolio_response(paper.portfolio(paper.latest_prices()), default_settings)


@router.get("/trades", response_model=list[TradeResponse], tags=["trading"])
def trades(
    limit: int = Query(default=100, ge=1, le=1000),
    store: Store = Depends(get_store),
) -> list[TradeResponse]:
    return [TradeResponse.model_validate(row) for row in store.recent_trades(limit)]


@router.post("/paper/step", response_model=CycleResponse, tags=["trading"])
async def paper_step(
    trade: bool = Query(default=True, description="False previews signals without trading."),
    refresh: bool = Query(default=False, description="Bypass the market-data cache."),
    scheduler: CycleScheduler = Depends(get_scheduler),
) -> CycleResponse:
    """Run one full bot cycle.

    Routed through the scheduler's lock, so this can never overlap a scheduled tick or another
    manual run against the same portfolio.
    """
    result = await scheduler.run_once(trade=trade, refresh=refresh)
    return _cycle_response(result, scheduler.cycle.store, default_settings)


@router.post("/paper/reset", response_model=PortfolioResponse, tags=["trading"])
def paper_reset(
    request: ResetRequest | None = None,
    paper: PaperTradingEngine = Depends(get_paper),
) -> PortfolioResponse:
    """Reset the simulated portfolio. Forecast and signal history is deliberately retained."""
    capital = (request or ResetRequest()).initial_capital
    return _portfolio_response(paper.reset(capital), default_settings)


# ------------------------------------------------------------------------------------
# Runs
# ------------------------------------------------------------------------------------


@router.get("/runs", response_model=list[RunResponse], tags=["system"])
def runs(
    limit: int = Query(default=20, ge=1, le=200),
    store: Store = Depends(get_store),
) -> list[RunResponse]:
    return [RunResponse.model_validate(row) for row in store.recent_runs(limit)]


@router.get("/runs/{run_id}", response_model=RunResponse, tags=["system"])
def run_detail(run_id: int, store: Store = Depends(get_store)) -> RunResponse:
    row = store.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return RunResponse.model_validate(row)
