"""Runtime watchlist management.

The configured ``WATCHLIST`` (see ``backend/.env.example``) is the *seed*; the ``watchlist``
table in SQLite is the *source of truth* once the app has started. That split means symbols
added through the dashboard's search survive a restart without anyone editing a file, while a
fresh clone still boots with sensible defaults.

Removal is guarded: a symbol with an open paper position is kept on the list, because dropping
it would leave the position unpriced and invisible (rule R5 — fail loudly, never silently
widen risk). Sell the position first, then remove the symbol.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Asset, Settings
from ..config import classify_symbol
from ..config import settings as default_settings
from ..store import Store

logger = logging.getLogger(__name__)


class WatchlistError(RuntimeError):
    """Raised when a watchlist change cannot be made. The message is user-facing."""


@dataclass(frozen=True)
class WatchlistEntry:
    """One tracked symbol as stored in the database."""

    symbol: str
    name: str
    asset_class: str
    added_at: str
    source: str  # "seed" | "search" | "manual"


class WatchlistService:
    """Reads and writes the persisted watchlist, seeding it from config on first use."""

    def __init__(self, store: Store, config: Settings | None = None) -> None:
        self.store = store
        self.settings = config or default_settings

    def seed(self) -> None:
        """Insert configured defaults that are not tracked yet. Never removes anything."""
        self.store.seed_watchlist(
            [
                {"symbol": a.symbol, "name": a.name, "asset_class": a.asset_class}
                for a in self.settings.watchlist
            ]
        )

    def entries(self) -> list[WatchlistEntry]:
        rows = self.store.get_watchlist()
        return [
            WatchlistEntry(
                symbol=str(row["symbol"]),
                name=str(row["name"]),
                asset_class=str(row["asset_class"]),
                added_at=str(row["added_at"]),
                source=str(row["source"]),
            )
            for row in rows
        ]

    def symbols(self) -> list[str]:
        """The tracked tickers, in insertion order. The cycle and market routes use this."""
        return self.store.watchlist_symbols()

    def assets(self) -> list[Asset]:
        return [
            Asset(entry.symbol, entry.name, entry.asset_class) for entry in self.entries()
        ]

    def add(self, symbol: str, name: str | None = None, asset_class: str | None = None) -> WatchlistEntry:
        """Start tracking a symbol, validating it can actually be priced.

        The fetch attempt is the whole validation: a ticker that returns no bars is worse than
        useless on a watchlist, because every cycle would pay a failed download for it and then
        skip it. Rejecting it at add-time turns a recurring silent failure into one loud error.
        """
        symbol = symbol.strip().upper()
        if not symbol:
            raise WatchlistError("symbol must not be empty")

        known = self.settings.asset(symbol)
        resolved_name = (name or known.name if known else name) or symbol
        resolved_class = asset_class or (known.asset_class if known else classify_symbol(symbol))

        if len(self.symbols()) >= self.settings.max_watchlist:
            raise WatchlistError(
                f"watchlist is full ({self.settings.max_watchlist} symbols); "
                "remove one before adding another"
            )

        # Lazy import avoids a hard yfinance dependency for tests and boot.
        from .market_data import MarketDataError, market_data

        try:
            market_data.fetch(symbol, refresh=True)
        except MarketDataError as exc:
            raise WatchlistError(
                f"{symbol}: not tradeable on the configured data source ({exc.reason})"
            ) from exc

        added = self.store.add_watchlist_entry(symbol, resolved_name, resolved_class, "search")
        if not added:
            raise WatchlistError(f"{symbol} is already on the watchlist")
        logger.info("Watchlist: added %s (%s, %s)", symbol, resolved_name, resolved_class)
        # Re-read so the caller gets the real ``added_at`` timestamp.
        for entry in self.entries():
            if entry.symbol == symbol:
                return entry
        return WatchlistEntry(symbol, resolved_name, resolved_class, "", "search")  # pragma: no cover

    def remove(self, symbol: str) -> None:
        """Stop tracking a symbol. Refuses while a paper position is open in it."""
        symbol = symbol.strip().upper()
        held = {row["symbol"] for row in self.store.get_positions()}
        if symbol in held:
            raise WatchlistError(
                f"{symbol} has an open paper position; close it before removing the symbol"
            )
        if not self.store.remove_watchlist_entry(symbol):
            raise WatchlistError(f"{symbol} is not on the watchlist")
        logger.info("Watchlist: removed %s", symbol)
