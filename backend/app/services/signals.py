"""Signal derivation — turning a forecast into a decision.

The engine is deliberately **rule-based and fully explainable**. A generative model's sampled
path is noisy, so the raw forecast return is normalised by the asset's own recent realised
volatility before it is compared against a threshold. That is the whole trick: a 1% forecast move
means something very different for silver than for the S&P 500.

Four independent checks feed the confidence score, and every one of them is written into the
signal's ``rationale`` so a decision can be audited after the fact rather than trusted:

1. **Magnitude** — the volatility-normalised score, squashed into 0-1.
2. **Trend agreement** — does the forecast direction match the recent trend?
3. **Monotonicity** — is the forecasted path consistent, or does it thrash?
4. **Smoothness** — how deep is the drawdown inside the forecasted move?

Thresholds, volatility window and the sizing rules all come from configuration. Nothing here is
tuned inside the function, so behaviour can be changed and re-tested without editing logic.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ..config import Settings
from ..config import settings as default_settings
from .forecast import ForecastOutcome

logger = logging.getLogger(__name__)

#: Used when there is not enough history to measure volatility. 1% daily is a deliberately
#: unaggressive placeholder; the signal is flagged in its rationale whenever it is used.
DEFAULT_DAILY_VOL = 0.01

#: Score that saturates the magnitude component of confidence.
SCORE_SATURATION = 2.0

#: Confidence component weights. They sum to 1.0.
WEIGHT_MAGNITUDE = 0.45
WEIGHT_AGREEMENT = 0.25
WEIGHT_MONOTONICITY = 0.20
WEIGHT_SMOOTHNESS = 0.10

#: Number of trailing bars used for the trend comparison.
TREND_FAST = 5
TREND_SLOW = 20


@dataclass
class Signal:
    """A trading decision with its full supporting evidence."""

    symbol: str
    name: str
    asset_class: str
    action: str  # BUY | SELL | HOLD
    confidence: float
    score: float
    expected_return: float
    horizon: int
    last_close: float
    suggested_qty: float
    suggested_notional: float
    rationale: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @property
    def expected_return_pct(self) -> float:
        return self.expected_return * 100.0


class SignalEngine:
    """Applies the configured rules to a :class:`ForecastOutcome`."""

    def __init__(self, config: Settings | None = None) -> None:
        self.settings = config or default_settings

    # ------------------------------------------------------------------ volatility

    def _realised_daily_vol(self, history: list[dict[str, Any]]) -> tuple[float, str]:
        """Standard deviation of recent log returns, plus a note on how it was obtained."""
        if not history or len(history) < 3:
            return DEFAULT_DAILY_VOL, "default (no usable history)"

        closes = pd.Series([float(bar["close"]) for bar in history], dtype="float64")
        closes = closes[closes > 0]
        if len(closes) < 3:
            return DEFAULT_DAILY_VOL, "default (no positive closes)"

        window = closes.tail(self.settings.vol_lookback + 1)
        log_returns = np.log(window / window.shift(1)).dropna()
        # Guard against a flat or one-bar series producing a meaningless 0-volatility reading,
        # which would blow the score up to infinity.
        if len(log_returns) < 2 or not math.isfinite(float(log_returns.std())):
            return DEFAULT_DAILY_VOL, "default (insufficient returns)"

        volatility = float(log_returns.std())
        if volatility <= 1e-6:
            return DEFAULT_DAILY_VOL, "default (zero measured volatility)"
        return volatility, f"realised over {len(log_returns)} bars"

    # ------------------------------------------------------------------ path shape

    @staticmethod
    def _monotonicity(closes: list[float]) -> float:
        """Fraction of steps moving in the same direction as the overall path, in 0-1.

        A clean 20-bar rally scores near 1.0; a path that whipsaws scores near 0.5.
        """
        if len(closes) < 3:
            return 0.5
        delta = closes[-1] - closes[0]
        if delta == 0:
            # A path that ends where it started has no direction to be consistent with.
            return 0.5
        direction = 1.0 if delta > 0 else -1.0
        steps = np.diff(np.asarray(closes, dtype="float64"))
        if steps.size == 0:
            return 0.5
        aligned = int(np.sum(np.sign(steps) == direction))
        return aligned / steps.size

    @staticmethod
    def _path_drawdown(closes: list[float]) -> float:
        """Worst peak-to-trough move *against* the overall direction, as a fraction."""
        if len(closes) < 2:
            return 0.0
        series = np.asarray(closes, dtype="float64")
        if series[0] == 0:
            return 0.0
        # A flat path (end == start) is treated as upward, so the reported drawdown is the
        # downside excursion of a move that went nowhere — the conservative reading.
        direction = 1.0 if series[-1] - series[0] >= 0 else -1.0
        worst = 0.0
        running_extreme = series[0]
        for value in series:
            if direction > 0:
                running_extreme = max(running_extreme, value)
                adverse = (running_extreme - value) / running_extreme if running_extreme else 0.0
            else:
                running_extreme = min(running_extreme, value)
                adverse = (value - running_extreme) / running_extreme if running_extreme else 0.0
            worst = max(worst, adverse)
        return worst

    @staticmethod
    def _trend(closes: list[float]) -> int:
        """+1 / 0 / -1 from a short versus long moving average of recent closes."""
        if len(closes) < TREND_SLOW:
            return 0
        recent = np.asarray(closes, dtype="float64")
        fast = float(recent[-TREND_FAST:].mean())
        slow = float(recent[-TREND_SLOW:].mean())
        if slow == 0:
            return 0
        relative = (fast - slow) / slow
        if relative > 0.002:
            return 1
        if relative < -0.002:
            return -1
        return 0

    # ------------------------------------------------------------------ sizing

    def _size_position(self, price: float, equity: float) -> dict[str, float]:
        """Notional-and-quantity sizing, clamped by the configured risk limits."""
        settings = self.settings
        if price <= 0 or equity <= 0:
            return {"notional": 0.0, "qty": 0.0, "stop_distance": 0.0, "risk_amount": 0.0}

        # The engine never allocates more than the smaller of the per-trade and per-position caps.
        fraction = min(settings.position_pct, settings.max_position_pct)
        notional = equity * fraction
        qty = round(notional / price, 4)
        stop_distance = price * settings.stop_loss_pct
        return {
            "notional": round(qty * price, 2),
            "qty": qty,
            "stop_distance": round(stop_distance, 4),
            "risk_amount": round(qty * stop_distance, 2),
            "target_fraction": fraction,
        }

    # ------------------------------------------------------------------ public API

    def evaluate(self, outcome: ForecastOutcome, *, equity: float) -> Signal:
        """Derive a signal for one forecast.

        ``equity`` is the current portfolio equity, used only to size the suggestion — it does not
        influence the direction of the call.
        """
        settings = self.settings
        closes = outcome.closes
        expected_return = outcome.expected_return

        daily_vol, vol_source = self._realised_daily_vol(outcome.history)
        horizon_vol = daily_vol * math.sqrt(max(outcome.horizon, 1))

        # The score: forecast return expressed in units of its own expected volatility.
        score = expected_return / horizon_vol if horizon_vol > 0 else 0.0
        magnitude = min(abs(score) / SCORE_SATURATION, 1.0)

        trend = self._trend([float(bar["close"]) for bar in outcome.history])
        forecast_direction = 1 if expected_return > 0 else (-1 if expected_return < 0 else 0)
        if trend == 0 or forecast_direction == 0:
            agreement_component = 0.5
            agreement_label = "no trend"
        elif trend == forecast_direction:
            agreement_component = 1.0
            agreement_label = "agrees"
        else:
            agreement_component = 0.2
            agreement_label = "conflicts"

        monotonicity = self._monotonicity(closes)
        monotonicity_component = max(0.0, min(1.0, (monotonicity - 0.5) * 2.0))

        drawdown = self._path_drawdown(closes)
        move = abs(expected_return)
        if move <= 1e-9:
            smoothness_component = 0.0
        else:
            smoothness_component = max(0.0, min(1.0, 1.0 - (drawdown / move)))

        confidence = (
            WEIGHT_MAGNITUDE * magnitude
            + WEIGHT_AGREEMENT * agreement_component
            + WEIGHT_MONOTONICITY * monotonicity_component
            + WEIGHT_SMOOTHNESS * smoothness_component
        )
        confidence = round(max(0.0, min(1.0, confidence)), 4)

        if score >= settings.signal_buy_threshold and confidence >= settings.min_confidence:
            action = "BUY"
        elif score <= settings.signal_sell_threshold and confidence >= settings.min_confidence:
            action = "SELL"
        else:
            action = "HOLD"

        sizing = self._size_position(outcome.last_close, equity)
        # Only surface a quantity we actually want acted on; a HOLD reports zero so it cannot be
        # read as a suggestion to open a position.
        suggested_qty = sizing["qty"] if action != "HOLD" else 0.0
        suggested_notional = sizing["notional"] if action != "HOLD" else 0.0

        rationale: dict[str, Any] = {
            "score": round(score, 4),
            "expected_return_pct": round(outcome.expected_return_pct, 4),
            "horizon_bars": outcome.horizon,
            "volatility": {
                "daily_pct": round(daily_vol * 100, 4),
                "horizon_pct": round(horizon_vol * 100, 4),
                "source": vol_source,
                "window": settings.vol_lookback,
            },
            "components": {
                "magnitude": round(magnitude, 4),
                "agreement": round(agreement_component, 4),
                "monotonicity": round(monotonicity, 4),
                "smoothness": round(smoothness_component, 4),
                "weights": {
                    "magnitude": WEIGHT_MAGNITUDE,
                    "agreement": WEIGHT_AGREEMENT,
                    "monotonicity": WEIGHT_MONOTONICITY,
                    "smoothness": WEIGHT_SMOOTHNESS,
                },
            },
            "trend": {"direction": trend, "agreement": agreement_label},
            "path": {
                "max_adverse_move_pct": round(drawdown * 100, 4),
                "forecast_move_pct": round(move * 100, 4),
            },
            "thresholds": {
                "buy": settings.signal_buy_threshold,
                "sell": settings.signal_sell_threshold,
                "min_confidence": settings.min_confidence,
            },
            "sizing": {
                **sizing,
                "equity": round(equity, 2),
                "stop_loss_pct": settings.stop_loss_pct,
                "take_profit_pct": settings.take_profit_pct,
            },
            "model": {
                "name": outcome.model,
                "sample_count": outcome.sample_count,
                "interval": outcome.interval,
            },
        }
        if outcome.notes:
            rationale["notes"] = list(outcome.notes)

        return Signal(
            symbol=outcome.symbol,
            name=outcome.name,
            asset_class=outcome.asset_class,
            action=action,
            confidence=confidence,
            score=round(score, 4),
            expected_return=expected_return,
            horizon=outcome.horizon,
            last_close=outcome.last_close,
            suggested_qty=suggested_qty,
            suggested_notional=suggested_notional,
            rationale=rationale,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def evaluate_many(
        self, outcomes: dict[str, ForecastOutcome], *, equity: float
    ) -> list[Signal]:
        """Evaluate several forecasts, ordered by descending conviction."""
        signals = [self.evaluate(outcome, equity=equity) for outcome in outcomes.values()]
        signals.sort(key=lambda s: abs(s.score), reverse=True)
        return signals
