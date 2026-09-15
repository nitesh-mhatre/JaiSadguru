"""Kronos forecasting service.

Wraps the vendored Kronos predictor (``backend/vendor/kronos``) behind a service that:

* loads weights lazily and exactly once, guarded by a lock, so an idle API does not pay the
  download cost and concurrent requests cannot double-load a model;
* degrades cleanly when ``torch`` is unavailable — the API still boots and reports why;
* always records the context window a forecast came from, so the prediction can never be
  attributed to the wrong bars (``doc/objective.md`` rule R6).

The forecast itself is a **statistical sample** from a generative model. It is not a price
target and must never be presented as advice.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..config import ALLOWED_INTERVALS, INTRADAY_INTERVALS, INTRADAY_MAX_LOOKBACK, Settings
from ..config import settings as default_settings
from .market_data import MarketDataResult, MarketDataService, future_timestamps, market_data

logger = logging.getLogger(__name__)

#: Bare minimum bars we will ask the model to condition on. Below this the forecast is not
#: meaningful, so we refuse rather than return confident-looking noise.
MIN_CONTEXT_BARS = 64

#: Columns handed to the predictor, in the order it expects.
FEATURE_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]


class ForecastError(RuntimeError):
    """Raised when a forecast cannot be produced for one symbol."""

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(f"{symbol}: {reason}")
        self.symbol = symbol
        self.reason = reason


@dataclass
class ForecastOutcome:
    """A completed forecast plus the context it was derived from."""

    symbol: str
    name: str
    asset_class: str
    interval: str
    model: str
    horizon: int
    sample_count: int
    created_at: str
    data_start: str
    data_end: str
    last_close: float
    target_close: float
    points: list[dict[str, Any]]
    history: list[dict[str, Any]]
    forecast_id: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def expected_return(self) -> float:
        """Fractional move from the last actual close to the final forecasted close."""
        if self.last_close == 0:
            return 0.0
        return (self.target_close - self.last_close) / self.last_close

    @property
    def expected_return_pct(self) -> float:
        return self.expected_return * 100.0

    @property
    def closes(self) -> list[float]:
        """Forecasted closes in horizon order — the input to the signal engine."""
        return [float(point["close"]) for point in self.points]


# ------------------------------------------------------------------------------------
# Model runtime
# ------------------------------------------------------------------------------------


class KronosRuntime:
    """Owns the loaded Kronos tokenizer, model and predictor.

    Importing ``torch`` and the vendored model is deferred to :meth:`ensure_loaded` so that a
    machine without the ML stack can still run the API and be told what is missing.
    """

    def __init__(self, config: Settings | None = None) -> None:
        self.settings = config or default_settings
        self._lock = threading.Lock()
        self._predictor: Any | None = None
        self._import_error: str | None = None
        self._device: str | None = None

    # ------------------------------------------------------------------ probes

    def import_error(self) -> str | None:
        """Populate and return any import failure, or ``None`` when the stack is importable."""
        if self._predictor is not None:
            return None
        if self._import_error is not None:
            return self._import_error
        try:
            import torch  # noqa: F401  (probe only)

            from vendor.kronos import Kronos, KronosPredictor, KronosTokenizer  # noqa: F401
        except ImportError as exc:
            self._import_error = str(exc)
            return self._import_error
        return None

    def available(self) -> bool:
        """True when ``torch`` and the vendored model can be imported."""
        return self.import_error() is None

    @property
    def loaded(self) -> bool:
        return self._predictor is not None

    @property
    def device(self) -> str | None:
        return self._device

    # ------------------------------------------------------------------ loading

    def ensure_loaded(self) -> Any:
        """Load the model once and return the predictor. Raises :class:`ForecastError` on failure."""
        if self._predictor is not None:
            return self._predictor

        with self._lock:
            # Another thread may have finished loading while we waited on the lock.
            if self._predictor is not None:
                return self._predictor

            import_error = self.import_error()
            if import_error is not None:
                raise ForecastError(
                    "-",
                    "the Kronos runtime is unavailable ("
                    f"{import_error}). Install the backend dependencies with "
                    "`pip install -r requirements.txt`.",
                )

            from vendor.kronos import Kronos, KronosPredictor, KronosTokenizer

            spec = self.settings.model_spec
            logger.info(
                "Loading Kronos model %s (%s params, max_context=%d)",
                spec.model_id,
                spec.params,
                spec.max_context,
            )
            try:
                tokenizer = KronosTokenizer.from_pretrained(spec.tokenizer_id)
                model = Kronos.from_pretrained(spec.model_id)
            except Exception as exc:  # network, hub auth, disk, corrupt weights...
                raise ForecastError(
                    spec.model_id,
                    f"could not load weights from Hugging Face: {exc}",
                ) from exc

            # ``auto`` lets KronosPredictor pick cuda/mps/cpu for itself.
            device = None if self.settings.device.lower() == "auto" else self.settings.device
            try:
                self._predictor = KronosPredictor(
                    model, tokenizer, device=device, max_context=spec.max_context
                )
            except Exception as exc:
                raise ForecastError(spec.model_id, f"could not construct the predictor: {exc}") from exc

            self._device = str(self._predictor.device)
            logger.info("Kronos ready on %s", self._device)
            return self._predictor

    def unload(self) -> None:
        """Drop the loaded model, freeing memory. The next forecast reloads it."""
        with self._lock:
            self._predictor = None
            self._device = None


# ------------------------------------------------------------------------------------
# Forecasting
# ------------------------------------------------------------------------------------


class ForecastService:
    """Turns stored bars into Kronos forecasts."""

    def __init__(
        self,
        config: Settings | None = None,
        runtime: KronosRuntime | None = None,
        data_service: MarketDataService | None = None,
    ) -> None:
        self.settings = config or default_settings
        self.runtime = runtime or KronosRuntime(self.settings)
        self.data = data_service or market_data

    # ------------------------------------------------------------------ helpers

    def _prepare_inputs(
        self, result: MarketDataResult, lookback: int, horizon: int
    ) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str]]:
        """Build ``(x_df, x_timestamp, y_timestamp, notes)`` for the predictor."""
        notes: list[str] = []
        frame = result.frame

        if len(frame) < MIN_CONTEXT_BARS:
            raise ForecastError(
                result.symbol,
                f"only {len(frame)} bars available; need at least {MIN_CONTEXT_BARS} for a "
                "meaningful forecast on interval "
                f"{result.interval!r}",
            )

        if len(frame) > lookback:
            frame = frame.tail(lookback)
        elif len(frame) < lookback:
            notes.append(
                f"context truncated to {len(frame)} bars (configured lookback is {lookback})"
            )

        if frame[FEATURE_COLUMNS].isnull().values.any():
            raise ForecastError(result.symbol, "context window contains missing values")

        # ``calc_time_stamps`` inside Kronos uses the pandas ``.dt`` accessor, so this must be a
        # Series rather than a DatetimeIndex or a plain list.
        x_timestamp = pd.Series(frame.index, name="timestamps")
        y_index = future_timestamps(frame.index, horizon, result.interval, result.asset_class)
        if len(y_index) != horizon:
            raise ForecastError(
                result.symbol, f"could not build {horizon} future timestamps for {result.interval!r}"
            )
        y_timestamp = pd.Series(y_index, name="timestamps")

        return frame[FEATURE_COLUMNS].copy(), x_timestamp, y_timestamp, notes

    # ------------------------------------------------------------------ public API

    def forecast(
        self,
        symbol: str,
        *,
        refresh: bool = False,
        interval: str | None = None,
        lookback: int | None = None,
        pred_len: int | None = None,
        sample_count: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> ForecastOutcome:
        """Forecast ``symbol``. Raises :class:`ForecastError` — never returns a partial result.

        ``interval`` selects the bar size the forecast runs on: ``"5m"`` feeds the model
        5-minute candles and returns a horizon of 5-minute bars. ``None`` uses the configured
        default (daily).
        """
        settings = self.settings
        lookback = lookback or settings.lookback
        horizon = pred_len or settings.pred_len
        samples = sample_count or settings.sample_count
        interval = interval or settings.interval

        if interval not in ALLOWED_INTERVALS:
            raise ForecastError(
                symbol, f"unsupported interval {interval!r} (allowed: {sorted(ALLOWED_INTERVALS)})"
            )

        notes: list[str] = []
        # Intraday history is capped by the data provider, so intraday contexts must stay small
        # enough to actually be satisfiable (``INTRADAY_MAX_LOOKBACK`` in config). The configured
        # daily LOOKBACK (400) cannot be satisfied on intraday bars — clamp and say so rather
        # than refuse: the user asked for a 5m forecast and a 240-bar 5m context is a meaningful
        # one. The note travels into the forecast and signal rationale, so the clamped context is
        # visible in the UI, never silent (``doc/objective.md`` rule R6).
        if interval in INTRADAY_INTERVALS and lookback > INTRADAY_MAX_LOOKBACK:
            notes.append(
                f"context clamped from {lookback} to {INTRADAY_MAX_LOOKBACK} bars for intraday "
                f"interval {interval!r} (free intraday history is capped)"
            )
            lookback = INTRADAY_MAX_LOOKBACK

        data = self.data.fetch(symbol, interval=interval, refresh=refresh)
        x_df, x_timestamp, y_timestamp, prep_notes = self._prepare_inputs(data, lookback, horizon)
        notes.extend(prep_notes)

        predictor = self.runtime.ensure_loaded()

        try:
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=horizon,
                T=settings.temperature if temperature is None else temperature,
                top_p=settings.top_p if top_p is None else top_p,
                sample_count=samples,
                verbose=False,  # no tqdm progress bar in a server process
            )
        except Exception as exc:
            raise ForecastError(symbol, f"inference failed: {exc}") from exc

        if pred_df is None or len(pred_df) != horizon:
            raise ForecastError(
                symbol, f"model returned {0 if pred_df is None else len(pred_df)} rows, expected {horizon}"
            )
        if pred_df[["open", "high", "low", "close"]].isnull().values.any():
            raise ForecastError(symbol, "model returned NaN prices")

        points = [
            {
                "timestamp": index.isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
                "amount": float(row.get("amount", 0.0)),
            }
            for index, row in pred_df.iterrows()
        ]

        notes.extend(data.notes)
        if data.stale:
            notes.append("forecast used stale market data")

        return ForecastOutcome(
            symbol=data.symbol,
            name=data.name,
            asset_class=data.asset_class,
            interval=interval,
            model=settings.kronos_model,
            horizon=horizon,
            sample_count=samples,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            data_start=data.frame.index[0].isoformat(),
            data_end=data.frame.index[-1].isoformat(),
            last_close=float(x_df["close"].iloc[-1]),
            target_close=float(points[-1]["close"]),
            points=points,
            history=data.to_candles(),
            notes=notes,
        )

    def forecast_many(
        self, symbols: list[str] | tuple[str, ...], **kwargs: Any
    ) -> tuple[dict[str, ForecastOutcome], dict[str, str]]:
        """Forecast several symbols, isolating per-symbol failures as ``(outcomes, errors)``."""
        outcomes: dict[str, ForecastOutcome] = {}
        errors: dict[str, str] = {}
        for symbol in symbols:
            try:
                outcome = self.forecast(symbol, **kwargs)
                outcomes[outcome.symbol] = outcome
            except ForecastError as exc:
                logger.warning("Forecast failed for %s: %s", symbol, exc.reason)
                errors[symbol.upper()] = exc.reason
        return outcomes, errors

    def warmup(self) -> str:
        """Load the model eagerly and return the device it landed on."""
        predictor = self.runtime.ensure_loaded()
        return str(predictor.device)
