"""Symbol search — find crypto and Indian stock tickers by name.

Backed by Yahoo Finance's public search endpoint, the same keyless service ``yfinance``
resolves symbols through, so no API key or paid feed is introduced (``doc/objective.md``
non-goals). Results are cached in SQLite for ``SEARCH_CACHE_TTL_MINUTES`` because the symbol
universe changes at human speed, not market speed.

If the network call fails, one fallback remains: a query that *is* a valid ticker (e.g.
``BTC-USD`` or ``RELIANCE.NS``) still resolves through :data:`KNOWN_ASSETS` and the
ticker-shape classifier, so the common "paste a symbol" path works offline.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from ..config import Settings, classify_symbol
from ..config import settings as default_settings
from ..store import Store

logger = logging.getLogger(__name__)

#: Yahoo's keyless symbol-search endpoint. Untyped JSON on purpose: the schema is simple and
#: unstable, and a hard contract would turn an upstream tweak into our outage.
_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"

#: User agent — Yahoo's edge rejects requests without one.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JaiSadguruPaperBot/1.0)", "Accept": "application/json"}


class SearchError(RuntimeError):
    """Raised when a search cannot be completed at all (network down and no fallback)."""


class SearchResult:
    """One search hit, normalised to what the watchlist service can consume."""

    def __init__(self, symbol: str, name: str, asset_class: str, exchange: str, on_watchlist: bool) -> None:
        self.symbol = symbol
        self.name = name
        self.asset_class = asset_class
        self.exchange = exchange
        self.on_watchlist = on_watchlist

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class,
            "exchange": self.exchange,
            "on_watchlist": self.on_watchlist,
        }


def _classify_hit(symbol: str, quote_type: str) -> str | None:
    """Map a Yahoo quote type to one of our asset classes, or ``None`` to hide the hit.

    Yahoo types that make no sense for a candlestick forecaster (options, mutual funds,
    currencies) are filtered here rather than shown and rejected at add-time.
    """
    quote_type = (quote_type or "").upper()
    if quote_type == "CRYPTOCURRENCY":
        return "crypto"
    if quote_type == "EQUITY":
        return classify_symbol(symbol)
    if quote_type == "INDEX":
        return "index"
    if quote_type == "FUTURE":
        return "commodity"
    return None


class SymbolSearchService:
    """Searches for tradeable symbols and remembers results in SQLite."""

    def __init__(self, store: Store, config: Settings | None = None) -> None:
        self.store = store
        self.settings = config or default_settings

    # ------------------------------------------------------------------ helpers

    def _tracked_symbols(self) -> set[str]:
        return set(self.store.watchlist_symbols())

    @staticmethod
    def _local_hits(query: str, tracked: set[str]) -> list[SearchResult]:
        """Offline fallback: exact and prefix matches over the built-in asset table."""
        query = query.strip().upper()
        from ..config import KNOWN_ASSETS

        hits: list[SearchResult] = []
        for symbol, asset in KNOWN_ASSETS.items():
            if query in symbol or query in asset.name.upper():
                hits.append(
                    SearchResult(
                        symbol=asset.symbol,
                        name=asset.name,
                        asset_class=asset.asset_class,
                        exchange="—",
                        on_watchlist=asset.symbol in tracked,
                    )
                )
        # An exact ticker that is not in the table still resolves by shape.
        if query and not hits:
            hits.append(
                SearchResult(
                    symbol=query,
                    name=query,
                    asset_class=classify_symbol(query),
                    exchange="—",
                    on_watchlist=query in tracked,
                )
            )
        return hits

    def _remote_hits(self, query: str) -> list[SearchResult] | None:
        """Live Yahoo search, or ``None`` when the network layer fails."""
        url = f"{_SEARCH_URL}?{urllib.parse.urlencode({'q': query, 'quotesCount': 12, 'newsCount': 0})}"
        request = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # urllib.error.*, timeouts, bad JSON — all one bucket
            logger.warning("Symbol search failed, falling back to local table: %s", exc)
            return None

        tracked = self._tracked_symbols()
        hits: list[SearchResult] = []
        for quote in payload.get("quotes", []):
            symbol = str(quote.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            asset_class = _classify_hit(symbol, str(quote.get("quoteType") or ""))
            if asset_class is None:
                continue
            hits.append(
                SearchResult(
                    symbol=symbol,
                    name=str(quote.get("shortname") or quote.get("longname") or symbol),
                    asset_class=asset_class,
                    exchange=str(quote.get("exchDisp") or quote.get("exchange") or "—"),
                    on_watchlist=symbol in tracked,
                )
            )
        return hits

    # ------------------------------------------------------------------ public API

    def search(self, query: str, limit: int = 10) -> list[dict[str, str | bool]]:
        """Search symbols by name or ticker, newest cache permitting."""
        query = query.strip()
        if not query:
            return []
        limit = max(1, min(limit, 25))

        cached = self.store.get_search_cache(query, self.settings.search_cache_ttl_minutes)
        if cached is not None:
            return cached[:limit]

        hits = self._remote_hits(query)
        if hits is None:
            hits = self._local_hits(query, self._tracked_symbols())
        if not hits:
            return []

        results = [hit.to_dict() for hit in hits]
        self.store.put_search_cache(query, results)
        return results[:limit]
