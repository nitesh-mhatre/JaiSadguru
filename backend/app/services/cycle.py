"""Bot cycle orchestration.

Chains the pipeline: **fetch marks -> forecast -> signal -> execute -> snapshot**, recording what
happened at every step.

The design goal is that a cycle always produces an honest answer. A symbol that cannot be priced,
forecast or traded is reported in ``skipped`` with the reason, and the run is marked ``degraded``
rather than ``ok``. Silently dropping a symbol would make an untraded signal indistinguishable
from a signal that never existed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..config import settings as default_settings
from ..store import Store
from .forecast import ForecastError, ForecastOutcome, ForecastService
from .market_data import MarketDataError, MarketDataService, market_data
from .paper_trading import Fill, PaperTradingEngine, PortfolioState
from .signals import Signal, SignalEngine
from .watchlist import WatchlistService

logger = logging.getLogger(__name__)

#: Run statuses recorded in the ``runs`` table.
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"


@dataclass
class CycleResult:
    """Everything one cycle did, in the order a human would want to read it."""

    run_id: int
    status: str
    duration_ms: int
    signals: list[Signal] = field(default_factory=list)
    signal_ids: dict[str, int] = field(default_factory=dict)
    forecast_ids: dict[str, int] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    portfolio: PortfolioState | None = None


class BotCycle:
    """Runs the full pipeline for a set of symbols."""

    def __init__(
        self,
        store: Store,
        config: Settings | None = None,
        *,
        data_service: MarketDataService | None = None,
        forecast_service: ForecastService | None = None,
        signal_engine: SignalEngine | None = None,
        paper: PaperTradingEngine | None = None,
        watchlist: WatchlistService | None = None,
    ) -> None:
        self.settings = config or default_settings
        self.store = store
        self.data = data_service or market_data
        self.forecasts = forecast_service or ForecastService(self.settings)
        self.signals = signal_engine or SignalEngine(self.settings)
        self.paper = paper or PaperTradingEngine(store, self.settings)
        self.watchlist = watchlist or WatchlistService(store, self.settings)

    # ------------------------------------------------------------------ marks

    def collect_marks(
        self, symbols: list[str], *, refresh: bool = False
    ) -> tuple[dict[str, float], dict[str, str], list[str]]:
        """Latest closes for every symbol we may need to value.

        Includes currently-held symbols as well as the requested set, so an existing position is
        never valued at cost basis merely because it left the watchlist.

        Returns ``(prices, errors, notes)``.
        """
        held = {row["symbol"] for row in self.store.get_positions()}
        wanted = sorted({s.upper() for s in symbols} | held)

        prices: dict[str, float] = {}
        errors: dict[str, str] = {}
        notes: list[str] = []

        for symbol in wanted:
            try:
                result = self.data.fetch(symbol, refresh=refresh)
            except MarketDataError as exc:
                errors[symbol] = f"market data unavailable ({exc.reason})"
                continue
            prices[symbol] = result.last_close
            if result.stale:
                notes.append(f"{symbol}: priced from stale cached data")

        return prices, errors, notes

    # ------------------------------------------------------------------ single symbol

    def forecast_symbol(
        self, symbol: str, *, refresh: bool = False, **kwargs: Any
    ) -> tuple[ForecastOutcome, Signal]:
        """Forecast and evaluate one symbol without persisting anything."""
        outcome = self.forecasts.forecast(symbol, refresh=refresh, **kwargs)
        prices, _, _ = self.collect_marks([symbol], refresh=refresh)
        prices.setdefault(outcome.symbol, outcome.last_close)
        equity = self.paper.portfolio(prices).equity
        return outcome, self.signals.evaluate(outcome, equity=equity)

    def persist(
        self, outcome: ForecastOutcome, signal: Signal, *, run_id: int
    ) -> tuple[int, int]:
        """Write a forecast and its signal. Returns ``(forecast_id, signal_id)``.

        The forecast is written with the exact ``data_start``/``data_end`` window it used, so it
        stays interpretable after the market moves on (rule R6).
        """
        forecast_id = self.store.save_forecast(
            run_id=run_id,
            symbol=outcome.symbol,
            interval=outcome.interval,
            data_start=outcome.data_start,
            data_end=outcome.data_end,
            last_close=outcome.last_close,
            target_close=outcome.target_close,
            model=outcome.model,
            horizon=outcome.horizon,
            sample_count=outcome.sample_count,
            points=outcome.points,
        )
        outcome.forecast_id = forecast_id

        signal_id = self.store.save_signal(
            run_id=run_id,
            forecast_id=forecast_id,
            symbol=signal.symbol,
            action=signal.action,
            confidence=signal.confidence,
            score=signal.score,
            expected_return=signal.expected_return,
            horizon=signal.horizon,
            last_close=signal.last_close,
            suggested_qty=signal.suggested_qty,
            rationale=signal.rationale,
        )
        return forecast_id, signal_id

    # ------------------------------------------------------------------ full cycle

    def run(
        self, *, refresh: bool = False, symbols: list[str] | None = None, trade: bool = True
    ) -> CycleResult:
        """Run one full cycle.

        ``trade=False`` performs forecasting and signal generation only, leaving the portfolio
        untouched — used by the dashboard's dry-run button.
        """
        target_symbols = [s.upper() for s in (symbols or self.watchlist.symbols())]
        run_id = self.store.create_run("cycle")
        started = time.perf_counter()

        skipped: dict[str, str] = {}
        notes: list[str] = []
        signals: list[Signal] = []
        signal_ids: dict[str, int] = {}
        forecast_ids: dict[str, int] = {}
        fills: list[Fill] = []

        try:
            # 1. Prices. Needed both as model context and to value the book.
            prices, mark_errors, mark_notes = self.collect_marks(target_symbols, refresh=refresh)
            skipped.update(mark_errors)
            notes.extend(mark_notes)
            if not prices:
                raise ForecastError(
                    "-", "no market data could be retrieved for any symbol in the watchlist"
                )

            # 2. Size against current equity, so allocations reflect the live book.
            equity = self.paper.portfolio(prices).equity

            # 3. Forecast and evaluate each symbol, isolating failures.
            for symbol in target_symbols:
                try:
                    outcome = self.forecasts.forecast(symbol, refresh=refresh)
                except ForecastError as exc:
                    logger.warning("Cycle: forecast failed for %s: %s", symbol, exc.reason)
                    skipped.setdefault(symbol, f"forecast failed ({exc.reason})")
                    continue

                signal = self.signals.evaluate(outcome, equity=equity)
                forecast_id, signal_id = self.persist(outcome, signal, run_id=run_id)
                signal_ids[symbol] = signal_id
                forecast_ids[symbol] = forecast_id
                signals.append(signal)

                if outcome.notes:
                    notes.extend(f"{symbol}: {note}" for note in outcome.notes)

            if not signals:
                raise ForecastError(
                    "-", "forecasting failed for every symbol in the watchlist"
                )

            # 4. Execute. Risk-reducing exits happen inside apply_signals, before entries.
            if trade:
                fills, trade_skips = self.paper.apply_signals(
                    signals, prices, run_id=run_id, signal_ids=signal_ids
                )
                for symbol, reason in trade_skips.items():
                    skipped.setdefault(symbol, reason)

            # 5. Mark to market and record an equity point.
            state = self.paper.snapshot(prices)

            status = STATUS_OK if not skipped else STATUS_DEGRADED
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.store.finish_run(
                run_id,
                status=status,
                symbols_ok=len(signals),
                symbols_failed=len(skipped),
                duration_ms=duration_ms,
            )

            return CycleResult(
                run_id=run_id,
                status=status,
                duration_ms=duration_ms,
                signals=signals,
                signal_ids=signal_ids,
                forecast_ids=forecast_ids,
                fills=fills,
                skipped=skipped,
                notes=notes,
                portfolio=state,
            )

        except Exception as exc:  # the run must be closed even when the cycle dies
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = getattr(exc, "reason", None) or str(exc)
            logger.exception("Cycle %s failed", run_id)
            self.store.finish_run(
                run_id,
                status=STATUS_FAILED,
                symbols_ok=len(signals),
                symbols_failed=len(skipped),
                duration_ms=duration_ms,
                error=message,
            )
            return CycleResult(
                run_id=run_id,
                status=STATUS_FAILED,
                duration_ms=duration_ms,
                signals=signals,
                signal_ids=signal_ids,
                forecast_ids=forecast_ids,
                fills=fills,
                skipped=skipped,
                notes=[*notes, f"cycle failed: {message}"],
                portfolio=self.paper.portfolio(self.paper.latest_prices()),
            )
