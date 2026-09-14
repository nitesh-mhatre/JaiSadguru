"""Paper trading engine — a simulated long-only portfolio.

**No order ever leaves this process.** There is no broker client in this codebase by design
(``doc/objective.md`` §3). This engine exists to make strategy behaviour observable: what would
have been bought, at what price, and what that did to the account.

## The accounting invariant

`realized_pnl + unrealized_pnl == equity - initial_capital`, exactly.

That holds because buy fees are folded into the position's cost basis, so ``avg_price`` is a
*fee-inclusive effective cost* rather than the raw market price paid. Without that, the two fees
on a round trip would land in different buckets and the portfolio could quietly report a profit it
never made. ``tests`` in milestone M4 assert this invariant.

## Costs modelled

Both are configuration values, not defaults buried in the code:

* **Slippage** — buys fill above, sells fill below the reference price, so the simulator never
  assumes we get the mid-market print.
* **Commission** — charged in basis points of notional on both sides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..config import settings as default_settings
from ..store import Store, utcnow
from .signals import Signal

logger = logging.getLogger(__name__)

#: Positions and fills smaller than this are dust and are never traded.
MIN_QTY = 1e-6

#: Guards against float noise making an affordable order look unaffordable by 1e-13.
CASH_EPSILON = 1e-9


class PaperTradingError(RuntimeError):
    """Raised when a simulated order cannot be executed. Always a skip, never a partial fill."""


@dataclass
class Fill:
    """A completed simulated trade."""

    trade_id: int
    symbol: str
    side: str
    qty: float
    price: float
    gross: float
    fee: float
    realized_pnl: float | None
    reason: str
    executed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": round(self.qty, 6),
            "price": round(self.price, 4),
            "gross": round(self.gross, 2),
            "fee": round(self.fee, 2),
            "realized_pnl": None if self.realized_pnl is None else round(self.realized_pnl, 2),
            "reason": self.reason,
            "executed_at": self.executed_at,
        }


@dataclass
class PortfolioState:
    """A full mark-to-market view of the simulated account."""

    initial_capital: float
    cash: float
    positions_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    positions: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def total_return(self) -> float:
        return self.equity - self.initial_capital

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return self.total_return / self.initial_capital * 100.0


class PaperTradingEngine:
    """Executes signals against a virtual portfolio stored in SQLite."""

    def __init__(self, store: Store, config: Settings | None = None) -> None:
        self.store = store
        self.settings = config or default_settings

    # ------------------------------------------------------------------ cost model

    def _fill_price(self, side: str, reference_price: float) -> float:
        """Apply slippage: buys pay up, sells receive less."""
        slip = self.settings.slippage_bps / 10_000.0
        return reference_price * (1.0 + slip) if side == "BUY" else reference_price * (1.0 - slip)

    def _fee(self, gross: float) -> float:
        return abs(gross) * self.settings.commission_bps / 10_000.0

    # ------------------------------------------------------------------ reads

    def account(self) -> dict[str, Any]:
        return self.store.ensure_account(self.settings.initial_capital)

    def portfolio(self, prices: dict[str, float] | None = None) -> PortfolioState:
        """Mark the book to ``prices``.

        A position whose symbol is absent from ``prices`` is valued at its cost basis and flagged
        in ``notes`` — it is never silently dropped, and never marked to a price we did not
        actually observe (rule R5).
        """
        marks = prices or {}
        account = self.account()
        cash = float(account["cash"])

        positions: list[dict[str, Any]] = []
        positions_value = 0.0
        unrealized = 0.0
        notes: list[str] = []

        for row in self.store.get_positions():
            symbol = row["symbol"]
            qty = float(row["qty"])
            avg_price = float(row["avg_price"])
            mark = marks.get(symbol)
            priced = mark is not None and mark > 0
            if not priced:
                mark = avg_price
                notes.append(f"{symbol}: no mark price available; valued at cost basis")

            market_value = qty * mark
            pnl = qty * (mark - avg_price)
            positions_value += market_value
            unrealized += pnl

            asset = self.settings.asset(symbol)
            positions.append(
                {
                    "symbol": symbol,
                    "name": asset.name if asset else symbol,
                    "qty": round(qty, 6),
                    "avg_price": round(avg_price, 4),
                    "last_price": round(mark, 4),
                    "market_value": round(market_value, 2),
                    "unrealized_pnl": round(pnl, 2),
                    "unrealized_pnl_pct": round((mark / avg_price - 1.0) * 100.0, 4)
                    if avg_price
                    else 0.0,
                    "opened_at": row["opened_at"],
                    "stop_price": row["stop_price"],
                    "take_profit_price": row["take_profit_price"],
                    "priced": priced,
                }
            )

        equity = cash + positions_value
        curve = [
            {
                "created_at": snap["created_at"],
                "equity": round(float(snap["equity"]), 2),
                "cash": round(float(snap["cash"]), 2),
                "positions_value": round(float(snap["positions_value"]), 2),
            }
            for snap in self.store.recent_snapshots()
        ]

        return PortfolioState(
            initial_capital=float(account["initial_capital"]),
            cash=round(cash, 2),
            positions_value=round(positions_value, 2),
            equity=round(equity, 2),
            realized_pnl=round(self.store.realized_pnl(), 2),
            unrealized_pnl=round(unrealized, 2),
            positions=positions,
            equity_curve=curve,
            updated_at=account["updated_at"],
            notes=notes,
        )

    def latest_prices(self) -> dict[str, float]:
        """Mark prices for held positions, sourced from the stored signal history.

        Only used where a live fetch is unavailable; the caller should prefer passing fresh
        prices into :meth:`portfolio`.
        """
        prices: dict[str, float] = {}
        for signal in self.store.latest_signals():
            prices[str(signal["symbol"])] = float(signal["last_close"])
        return prices

    # ------------------------------------------------------------------ execution

    def execute(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        reference_price: float,
        reason: str,
        run_id: int | None = None,
        signal_id: int | None = None,
    ) -> Fill:
        """Execute a simulated order. Raises :class:`PaperTradingError` on any failed guard.

        Every guard fails the whole order. There are no partial fills, because a partially-applied
        order is exactly how a simulator starts lying about what it would have achieved.
        """
        symbol = symbol.strip().upper()
        side = side.strip().upper()

        if side not in {"BUY", "SELL"}:
            raise PaperTradingError(f"unsupported side {side!r}")
        if qty <= MIN_QTY:
            raise PaperTradingError(f"quantity {qty:.8f} is below the minimum tradeable size")
        if reference_price <= 0:
            raise PaperTradingError(f"reference price {reference_price} is not positive")

        cash = float(self.account()["cash"])
        existing = self.store.get_position(symbol)
        fill_price = self._fill_price(side, reference_price)
        gross = qty * fill_price
        fee = self._fee(gross)
        now = utcnow()

        if side == "BUY":
            cost = gross + fee
            if cost > cash + CASH_EPSILON:
                raise PaperTradingError(
                    f"insufficient cash: order costs {cost:,.2f}, available {cash:,.2f}"
                )

            held_qty = float(existing["qty"]) if existing else 0.0
            held_basis = held_qty * float(existing["avg_price"]) if existing else 0.0
            new_qty = held_qty + qty
            # Fee-inclusive cost basis — this is what makes the accounting invariant hold.
            new_avg = (held_basis + cost) / new_qty
            cash_after = cash - cost
            realized: float | None = None
            position_after: dict[str, Any] | None = {
                "qty": new_qty,
                "avg_price": new_avg,
                "opened_at": existing["opened_at"] if existing else now,
                "stop_price": fill_price * (1.0 - self.settings.stop_loss_pct),
                "take_profit_price": fill_price * (1.0 + self.settings.take_profit_pct),
                "signal_id": signal_id,
            }
        else:
            if existing is None:
                raise PaperTradingError(
                    "no position to sell — this engine is long-only and does not short"
                )
            held_qty = float(existing["qty"])
            if qty > held_qty + MIN_QTY:
                raise PaperTradingError(
                    f"cannot sell {qty:.6f} of {symbol}: only {held_qty:.6f} held"
                )

            proceeds = gross - fee
            avg_price = float(existing["avg_price"])
            realized = proceeds - avg_price * qty
            cash_after = cash + proceeds

            remaining = held_qty - qty
            if remaining <= MIN_QTY:
                position_after = None
            else:
                position_after = {
                    "qty": remaining,
                    "avg_price": avg_price,
                    "opened_at": existing["opened_at"],
                    "stop_price": existing["stop_price"],
                    "take_profit_price": existing["take_profit_price"],
                    "signal_id": existing["signal_id"],
                }

        trade_id = self.store.record_fill(
            run_id=run_id,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=fill_price,
            gross=gross,
            fee=fee,
            realized_pnl=realized,
            reason=reason,
            cash_after=cash_after,
            position_after=position_after,
        )

        logger.info(
            "Paper %s %s %.6f @ %.4f (fee %.2f) — %s", side, symbol, qty, fill_price, fee, reason
        )
        return Fill(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=fill_price,
            gross=gross,
            fee=fee,
            realized_pnl=realized,
            reason=reason,
            executed_at=now,
        )

    # ------------------------------------------------------------------ signal application

    def _max_affordable_qty(self, qty: float, reference_price: float, cash: float) -> float:
        """Largest quantity at or below ``qty`` that cash can cover, including fees."""
        per_unit = self._fill_price("BUY", reference_price) * (
            1.0 + self.settings.commission_bps / 10_000.0
        )
        if per_unit <= 0:
            return 0.0
        affordable = qty if qty * per_unit <= cash else cash / per_unit
        # Trim a hair so float error cannot push the order a cent over the balance.
        return max(0.0, min(qty, affordable) * (1.0 - 1e-9))

    def _check_exits(self, prices: dict[str, float], run_id: int | None) -> list[Fill]:
        """Close any position that has breached its stop or target.

        Run before new entries so the cycle reduces risk before it adds any.
        """
        fills: list[Fill] = []
        for row in self.store.get_positions():
            symbol = row["symbol"]
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            qty = float(row["qty"])
            stop = row["stop_price"]
            target = row["take_profit_price"]

            reason: str | None = None
            if stop is not None and price <= float(stop):
                reason = f"stop-loss triggered at {price:,.4f} (stop {float(stop):,.4f})"
            elif target is not None and price >= float(target):
                reason = f"take-profit triggered at {price:,.4f} (target {float(target):,.4f})"
            if reason is None:
                continue

            try:
                fills.append(
                    self.execute(
                        symbol=symbol,
                        side="SELL",
                        qty=qty,
                        reference_price=price,
                        reason=reason,
                        run_id=run_id,
                        signal_id=row["signal_id"],
                    )
                )
            except PaperTradingError as exc:
                logger.warning("Exit for %s failed: %s", symbol, exc)
        return fills

    def _open_position(
        self,
        signal: Signal,
        price: float,
        prices: dict[str, float],
        run_id: int | None,
        signal_id: int | None,
    ) -> Fill:
        """Size and execute an entry, or raise :class:`PaperTradingError` explaining the skip."""
        if self.store.get_position(signal.symbol) is not None:
            raise PaperTradingError("already holding this symbol (no pyramiding)")

        held = self.store.get_positions()
        if len(held) >= self.settings.max_positions:
            raise PaperTradingError(
                f"max_positions limit reached ({self.settings.max_positions}); "
                "close a position before opening another"
            )

        state = self.portfolio(prices)
        if state.equity <= 0:
            raise PaperTradingError("portfolio equity is non-positive")

        fraction = min(self.settings.position_pct, self.settings.max_position_pct)
        target_notional = state.equity * fraction
        qty = self._max_affordable_qty(target_notional / price, price, state.cash)
        if qty <= MIN_QTY:
            raise PaperTradingError(
                f"insufficient cash: {state.cash:,.2f} cannot fund the smallest position"
            )

        return self.execute(
            symbol=signal.symbol,
            side="BUY",
            qty=qty,
            reference_price=price,
            reason=f"{signal.action} signal (score {signal.score:+.2f}, confidence {signal.confidence:.0%})",
            run_id=run_id,
            signal_id=signal_id,
        )

    def _close_position(
        self, signal: Signal, price: float, run_id: int | None, signal_id: int | None
    ) -> Fill:
        """Liquidate an existing position in response to a SELL signal."""
        existing = self.store.get_position(signal.symbol)
        if existing is None:
            raise PaperTradingError("no position to sell")
        return self.execute(
            symbol=signal.symbol,
            side="SELL",
            qty=float(existing["qty"]),
            reference_price=price,
            reason=(
                f"SELL signal (score {signal.score:+.2f}, confidence {signal.confidence:.0%})"
            ),
            run_id=run_id,
            signal_id=signal_id,
        )

    def apply_signals(
        self,
        signals: list[Signal],
        prices: dict[str, float],
        *,
        run_id: int | None = None,
        signal_ids: dict[str, int] | None = None,
    ) -> tuple[list[Fill], dict[str, str]]:
        """Execute signals against the portfolio.

        Returns ``(fills, skipped)`` where ``skipped`` maps a symbol to the reason it was left
        alone, so a cycle can report *why* it did nothing instead of looking like it missed a
        signal.
        """
        signal_ids = signal_ids or {}
        skipped: dict[str, str] = {}

        # Protective exits first: reduce risk before adding it.
        fills = self._check_exits(prices, run_id)

        # Highest conviction first, so if capital runs out it goes to the strongest signal.
        for signal in sorted(signals, key=lambda s: abs(s.score), reverse=True):
            if signal.action == "HOLD":
                continue

            price = prices.get(signal.symbol)
            if price is None or price <= 0:
                skipped[signal.symbol] = "no mark price available for this symbol"
                continue

            try:
                if signal.action == "BUY":
                    fills.append(
                        self._open_position(
                            signal, price, prices, run_id, signal_ids.get(signal.symbol)
                        )
                    )
                else:
                    fills.append(
                        self._close_position(
                            signal, price, run_id, signal_ids.get(signal.symbol)
                        )
                    )
            except PaperTradingError as exc:
                skipped[signal.symbol] = str(exc)

        return fills, skipped

    # ------------------------------------------------------------------ snapshots

    def snapshot(self, prices: dict[str, float] | None = None) -> PortfolioState:
        """Mark to market and persist an equity point for the curve."""
        state = self.portfolio(prices)
        self.store.insert_snapshot(
            cash=state.cash,
            positions_value=state.positions_value,
            equity=state.equity,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=state.unrealized_pnl,
            open_positions=len(state.positions),
        )
        return self.portfolio(prices)

    def reset(self, initial_capital: float | None = None) -> PortfolioState:
        """Wipe the simulated book. Forecast and signal history is retained for audit."""
        capital = initial_capital if initial_capital is not None else self.settings.initial_capital
        self.store.reset_portfolio(capital)
        return self.portfolio()
