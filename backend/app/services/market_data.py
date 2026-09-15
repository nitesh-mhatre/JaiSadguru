"""Market data acquisition.

Pulls OHLCV bars from ``yfinance`` — free and keyless, which is a hard requirement of the project
(``doc/objective.md`` target T1). Three behaviours matter more than the download itself:

1. **Failure isolation.** A bad symbol or a rate-limited request raises :class:`MarketDataError`
   for *that symbol only*, so one broken ticker never kills a whole cycle (rule R5: fail loudly,
   never guess).
2. **Staleness is visible.** When the cache TTL has expired but the live refresh fails, the cached
   bars are returned with ``stale=True`` rather than silently presented as current.
3. **Timestamps are normalised.** Timezones are stripped so index sessions, futures sessions and
   any future source all hand the model comparable, gap-free timestamps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import CACHE_TTL_MINUTES, Settings
from ..config import settings as default_settings
from ..config import classify_symbol, period_for_interval

logger = logging.getLogger(__name__)

#: Columns the Kronos predictor requires. ``volume``/``amount`` are optional to the model but we
#: always synthesise them so downstream code has one consistent frame shape.
PRICE_COLUMNS = ("open", "high", "low", "close")
VALUE_COLUMNS = ("volume", "amount")
ALL_COLUMNS = PRICE_COLUMNS + VALUE_COLUMNS

#: Upper bound on retained rows. Generous enough for the largest context plus room to compute
#: realised volatility, small enough that memory stays flat.
MAX_ROWS = 3000

#: ``yfinance`` cannot be imported at module scope without making the whole app fail to boot on a
#: machine where it is missing. We import lazily and surface the problem through ``/api/health``.
_YFINANCE_IMPORT_ERROR: str | None = None


def _import_yfinance():
    """Return the ``yfinance`` module, or raise a clear :class:`MarketDataError`."""
    global _YFINANCE_IMPORT_ERROR
    try:
        import yfinance as yf

        _YFINANCE_IMPORT_ERROR = None
        return yf
    except ImportError as exc:  # pragma: no cover - depends on the host environment
        _YFINANCE_IMPORT_ERROR = str(exc)
        raise MarketDataError(
            "-",
            "yfinance is not installed. Install the backend dependencies with "
            "`pip install -r requirements.txt`.",
        ) from exc


def runtime_available() -> bool:
    """True when ``yfinance`` can actually be imported."""
    try:
        _import_yfinance()
        return True
    except MarketDataError:
        return False


class MarketDataError(RuntimeError):
    """Raised when bars for one symbol could not be obtained."""

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(f"{symbol}: {reason}")
        self.symbol = symbol
        self.reason = reason


@dataclass
class MarketDataResult:
    """Normalised bars for one symbol, plus provenance about how current they are."""

    symbol: str
    name: str
    asset_class: str
    interval: str
    frame: pd.DataFrame  # DatetimeIndex (tz-naive), columns: open high low close volume amount
    from_cache: bool
    stale: bool
    fetched_at: str
    notes: list[str] = field(default_factory=list)

    @property
    def last_close(self) -> float:
        return float(self.frame["close"].iloc[-1])

    @property
    def previous_close(self) -> float:
        return float(self.frame["close"].iloc[-2]) if len(self.frame) > 1 else self.last_close

    @property
    def change_pct(self) -> float:
        previous = self.previous_close
        if previous == 0:
            return 0.0
        return (self.last_close - previous) / previous * 100.0

    @property
    def data_start(self) -> str:
        return self.frame.index[0].isoformat()

    @property
    def data_end(self) -> str:
        return self.frame.index[-1].isoformat()

    def to_candles(self) -> list[dict[str, float | str]]:
        """Serialise bars for the API/dashboard."""
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
            for index, row in self.frame.iterrows()
        ]


# ------------------------------------------------------------------------------------
# Timestamp handling
# ------------------------------------------------------------------------------------


def _strip_timezone(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Drop tz info, converting to UTC first so the wall-clock order is preserved."""
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    return index


def future_timestamps(
    index: pd.DatetimeIndex, horizon: int, interval: str, asset_class: str = "index"
) -> pd.DatetimeIndex:
    """Build the timestamps the model should predict for.

    Naively stepping one day at a time would place forecasts on weekends, misaligning them with
    the actuals they are later scored against (bug B-03). Daily bars therefore step over business
    days for session-traded assets, which tracks the Mon-Fri sessions of the indices and metals
    futures in the watchlist. **Crypto trades every calendar day**, so its daily bars are stepped
    per calendar day instead — classifying crypto bars on business days would silently skip every
    weekend, exactly the misalignment B-03 fixed for the other side. NSE/BSE sessions are also
    Mon-Fri, so Indian equities share the business-day path.

    Intraday bars need the same care at a finer grain: stepping a fixed 5-minute delta would run
    the forecast straight through the overnight gap and the weekend. For session-traded assets
    the observed *times of day* of the last session are replayed across subsequent business days,
    so predicted bars land inside a real session. Crypto has no sessions — its bars step by the
    observed spacing continuously. Exchange holidays are not modelled — documented, and harmless
    because the scoring step joins on timestamps rather than assuming a fixed offset.

    Returns an empty index when the horizon is not positive.
    """
    if horizon < 1 or len(index) == 0:
        return pd.DatetimeIndex([])

    last = index[-1]

    if interval == "1d":
        if asset_class == "crypto":
            # 24/7 markets: step calendar days.
            return pd.date_range(start=last.normalize(), periods=horizon + 1, freq="D")[1:]
        # ``bdate_range`` excludes Saturdays and Sundays (indices, futures, NSE/BSE stocks).
        return pd.bdate_range(start=last.normalize(), periods=horizon + 1, freq="B")[1:]

    if interval == "1wk":
        return pd.date_range(start=last, periods=horizon + 1, freq="7D")[1:]

    spacing = _observed_spacing(index)

    if asset_class == "crypto":
        # 24/7: intraday bars are continuous, so plain spacing is exact.
        return pd.date_range(start=last, periods=horizon + 1, freq=spacing)[1:]

    # Session-traded intraday: replay the observed times of day over the next business days.
    return _session_forward_timestamps(index, horizon, spacing)


def _observed_spacing(index: pd.DatetimeIndex) -> pd.Timedelta:
    """Median gap between observed bars, with a safe fallback."""
    if len(index) >= 3:
        spacing = index.to_series().diff().dropna().median()
    else:
        spacing = pd.Timedelta(hours=1)
    if pd.isna(spacing) or spacing <= pd.Timedelta(0):
        spacing = pd.Timedelta(hours=1)
    return pd.Timedelta(spacing)


def _session_forward_timestamps(
    index: pd.DatetimeIndex, horizon: int, spacing: pd.Timedelta
) -> pd.DatetimeIndex:
    """Intraday timestamps for session-traded assets, kept inside real sessions.

    The times of day observed on the final trading day are treated as the session template and
    replayed on the following business days, so a 5m bar at 09:15 is followed by 09:20, 09:25…
    within the session instead of stepping a fixed delta through the overnight gap. When the
    last day has fewer than two bars there is no session shape to learn, and the function falls
    back to plain continuous spacing — the behaviour this replaces, made explicit.
    """
    last_date = index[-1].normalize()
    # All bars sharing the final bar's calendar day form the session template. The index is
    # sorted, so they are the contiguous tail of the series.
    template = index[index.normalize() == last_date]
    if len(template) < 2:
        return pd.date_range(start=index[-1], periods=horizon + 1, freq=spacing)[1:]

    times = template.time
    # Business days strictly after the last observed date. Starting from the day *after*
    # avoids the bdate_range off-by-one when the last bar itself fell on a weekend.
    upcoming = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=horizon + 2)

    generated: list[pd.Timestamp] = []
    for day in upcoming:
        for time_of_day in times:
            generated.append(pd.Timestamp.combine(day, time_of_day))
            if len(generated) == horizon:
                return pd.DatetimeIndex(generated)
    # Unreachable while ``upcoming`` has enough days, but keep the contract honest.
    return pd.DatetimeIndex(generated[:horizon])


# ------------------------------------------------------------------------------------
# Service
# ------------------------------------------------------------------------------------


class MarketDataService:
    """Fetches, normalises and caches OHLCV bars."""

    def __init__(self, config: Settings | None = None) -> None:
        self.settings = config or default_settings

    # -------------------------------------------------------------- cache helpers

    def _cache_path(self, symbol: str, interval: str) -> Path:
        # '^', '=' and '.' are legal in a filename on POSIX but are awkward in shells and URLs.
        safe = symbol.upper().replace("^", "IDX_").replace("=", "_").replace(".", "_")
        return self.settings.cache_dir / f"{safe}_{interval}.csv"

    def _read_cache(self, symbol: str, interval: str) -> tuple[pd.DataFrame | None, float | None]:
        path = self._cache_path(symbol, interval)
        if not path.is_file():
            return None, None
        try:
            frame = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            logger.warning("Ignoring unreadable market-data cache %s: %s", path, exc)
            return None, None
        if frame.empty or not set(ALL_COLUMNS).issubset(frame.columns):
            return None, None
        return frame, path.stat().st_mtime

    def _write_cache(self, symbol: str, interval: str, frame: pd.DataFrame) -> None:
        path = self._cache_path(symbol, interval)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index_label="timestamp")
        except OSError as exc:  # a cache that cannot be written must not fail the request
            logger.warning("Could not write market-data cache %s: %s", path, exc)

    def _cache_is_fresh(self, modified_at: float | None, interval: str | None = None) -> bool:
        if modified_at is None:
            return False
        # TTL follows the requested interval: a 1m bar is old news within a minute while daily
        # bars survive most of a day. Falls back to the configured default when unspecified.
        ttl = (
            CACHE_TTL_MINUTES.get(interval, self.settings.cache_ttl_minutes)
            if interval is not None
            else self.settings.cache_ttl_minutes
        )
        age_minutes = (datetime.now(timezone.utc).timestamp() - modified_at) / 60.0
        return age_minutes < ttl

    # -------------------------------------------------------------- normalisation

    @staticmethod
    def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
        """Collapse the MultiIndex that ``yfinance`` returns when given several tickers."""
        if isinstance(frame.columns, pd.MultiIndex):
            # Level 0 is the field name, level 1 the ticker (or vice versa depending on version).
            for level in range(frame.columns.nlevels):
                values = {str(v).lower() for v in frame.columns.get_level_values(level)}
                if {"open", "close"}.issubset(values):
                    frame = frame.copy()
                    frame.columns = frame.columns.get_level_values(level)
                    break
        return frame

    @classmethod
    def normalize(cls, raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Turn a raw ``yfinance`` frame into the canonical OHLCV shape.

        Drops non-price columns (notably ``Adj Close``), strips timezones, discards rows with a
        missing or nonsensical price, and derives ``amount`` when the source does not provide it.
        """
        if raw is None or raw.empty:
            raise MarketDataError(symbol, "no rows returned by the data provider")

        frame = cls._flatten_columns(raw)
        frame = frame.rename(columns={c: str(c).strip().lower().replace(" ", "_") for c in frame.columns})

        missing = [c for c in PRICE_COLUMNS if c not in frame.columns]
        if missing:
            raise MarketDataError(symbol, f"provider response is missing columns {missing}")

        frame = frame[list(PRICE_COLUMNS) + (["volume"] if "volume" in frame.columns else [])].copy()
        frame.index = _strip_timezone(pd.DatetimeIndex(frame.index))
        frame.index.name = "timestamp"

        for column in list(frame.columns):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame = frame.dropna(subset=list(PRICE_COLUMNS))
        # A zero or negative close is a data fault, not a price.
        frame = frame[frame["close"] > 0]
        if frame.empty:
            raise MarketDataError(symbol, "every returned row had a missing or non-positive price")

        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        frame["volume"] = frame["volume"].fillna(0.0).clip(lower=0.0)

        # Kronos accepts `volume` and is trained with a turnover-like `amount`; derive a
        # representative notional from the bar's typical price.
        typical = frame[list(PRICE_COLUMNS)].mean(axis=1)
        frame["amount"] = (frame["volume"] * typical).astype(float)

        frame = frame[list(ALL_COLUMNS)]
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        return frame.tail(MAX_ROWS)

    # -------------------------------------------------------------- public API

    def fetch(self, symbol: str, *, interval: str | None = None, refresh: bool = False) -> MarketDataResult:
        """Return bars for ``symbol``, preferring a fresh cache entry.

        Raises :class:`MarketDataError` if neither a fresh cache entry nor a live download is
        available. Never returns an invented or partially-filled series.
        """
        symbol = symbol.strip().upper()
        interval = interval or self.settings.interval
        asset = self.settings.asset(symbol)
        name = asset.name if asset else symbol
        asset_class = asset.asset_class if asset else classify_symbol(symbol)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        cached, modified_at = (None, None)
        if self.settings.cache_enabled:
            cached, modified_at = self._read_cache(symbol, interval)
            if cached is not None and not refresh and self._cache_is_fresh(modified_at, interval):
                return MarketDataResult(
                    symbol=symbol,
                    name=name,
                    asset_class=asset_class,
                    interval=interval,
                    frame=cached,
                    from_cache=True,
                    stale=False,
                    fetched_at=now,
                    notes=["served from cache"],
                )

        try:
            frame = self._download(symbol, interval)
        except MarketDataError as exc:
            if cached is not None and not cached.empty:
                # Prefer visibly-stale real data over no data. It is flagged, not hidden.
                logger.warning("Serving stale cache for %s: %s", symbol, exc.reason)
                return MarketDataResult(
                    symbol=symbol,
                    name=name,
                    asset_class=asset_class,
                    interval=interval,
                    frame=cached,
                    from_cache=True,
                    stale=True,
                    fetched_at=now,
                    notes=[f"live refresh failed ({exc.reason}); serving cached bars"],
                )
            raise

        if self.settings.cache_enabled:
            self._write_cache(symbol, interval, frame)

        return MarketDataResult(
            symbol=symbol,
            name=name,
            asset_class=asset_class,
            interval=interval,
            frame=frame,
            from_cache=False,
            stale=False,
            fetched_at=now,
            notes=[],
        )

    def _download(self, symbol: str, interval: str) -> pd.DataFrame:
        """Download and normalise bars straight from ``yfinance``."""
        yf = _import_yfinance()
        period = period_for_interval(interval)
        try:
            raw = yf.download(
                symbol,
                period=period,
                interval=interval,
                auto_adjust=False,  # keep raw OHLC so the model sees the traded price
                progress=False,
                threads=False,
            )
        except Exception as exc:  # yfinance raises a variety of transport errors
            raise MarketDataError(symbol, f"download failed: {exc}") from exc
        return self.normalize(raw, symbol)

    def history(
        self,
        symbol: str,
        *,
        rows: int | None = None,
        refresh: bool = False,
        interval: str | None = None,
    ) -> MarketDataResult:
        """Fetch bars and keep only the most recent ``rows`` (default: the configured lookback)."""
        limit = rows or self.settings.lookback
        result = self.fetch(symbol, interval=interval, refresh=refresh)
        if len(result.frame) > limit:
            result.frame = result.frame.tail(limit)
        return result

    def fetch_many(
        self, symbols: list[str] | tuple[str, ...], *, refresh: bool = False
    ) -> tuple[dict[str, MarketDataResult], dict[str, str]]:
        """Fetch several symbols, returning ``(results, errors)`` keyed by symbol.

        Errors are captured rather than raised so that one failing ticker cannot abort a cycle.
        """
        results: dict[str, MarketDataResult] = {}
        errors: dict[str, str] = {}
        for symbol in symbols:
            try:
                results[symbol.upper()] = self.fetch(symbol, refresh=refresh)
            except MarketDataError as exc:
                errors[symbol.upper()] = exc.reason
        return results, errors


#: Module-level default instance, matching the module-level ``settings`` in config.
market_data = MarketDataService()
