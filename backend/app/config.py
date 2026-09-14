"""Runtime configuration for the JaiSadguru forecast and paper-trading bot.

Every knob is overridable by environment variable (see ``backend/.env.example``).

Defaults are deliberately conservative. The risk limits defined here are *enforced by the
paper-trading engine*, not advice in a docstring, per ``doc/objective.md`` rule R5. Nothing in
this module can cause a real order to be placed — the project has no broker integration by design.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
CACHE_DIR = BACKEND_DIR / ".cache"
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "jaisadguru.db"


def _load_dotenv() -> None:
    """Populate ``os.environ`` from ``backend/.env`` or ``./.env``.

    Real environment variables always win, so a container or shell export is never
    shadowed by a stale local file. Implemented by hand to avoid a dependency for the
    ~15 lines it takes.
    """
    for candidate in (BACKEND_DIR / ".env", PROJECT_ROOT / ".env"):
        if not candidate.is_file():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


# --------------------------------------------------------------------------------------
# Environment coercion helpers
# --------------------------------------------------------------------------------------


def _env(key: str, default: str) -> str:
    value = os.environ.get(key)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    return _env(key, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Asset:
    """One tradeable symbol the bot tracks."""

    symbol: str
    name: str
    asset_class: str  # "index" | "commodity" | "custom"


#: Nice display names for the symbols we ship with. Overriding ``WATCHLIST`` in the
#: environment is fine — unknown symbols simply fall back to their ticker as the name.
KNOWN_ASSETS: dict[str, Asset] = {
    "^GSPC": Asset("^GSPC", "S&P 500", "index"),
    "^NDX": Asset("^NDX", "Nasdaq 100", "index"),
    "^DJI": Asset("^DJI", "Dow Jones Industrial Average", "index"),
    "GC=F": Asset("GC=F", "Gold Futures", "commodity"),
    "SI=F": Asset("SI=F", "Silver Futures", "commodity"),
}

#: Default targets: index stocks, gold and silver (see ``doc/objective.md`` target T1).
DEFAULT_WATCHLIST: tuple[str, ...] = ("^GSPC", "^NDX", "^DJI", "GC=F", "SI=F")


def _parse_watchlist() -> tuple[Asset, ...]:
    raw = _env("WATCHLIST", ",".join(DEFAULT_WATCHLIST))
    assets: list[Asset] = []
    seen: set[str] = set()
    for token in raw.split(","):
        symbol = token.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        assets.append(KNOWN_ASSETS.get(symbol, Asset(symbol, symbol, "custom")))
    return tuple(assets)


# --------------------------------------------------------------------------------------
# Kronos model registry
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSpec:
    """A downloadable Kronos checkpoint pair and its context limit."""

    key: str
    model_id: str
    tokenizer_id: str
    max_context: int
    params: str


#: ``Kronos-large`` is not open-source, so it is intentionally absent.
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "kronos-mini": ModelSpec(
        key="kronos-mini",
        model_id="NeoQuasar/Kronos-mini",
        tokenizer_id="NeoQuasar/Kronos-Tokenizer-2k",
        max_context=2048,
        params="4.1M",
    ),
    "kronos-small": ModelSpec(
        key="kronos-small",
        model_id="NeoQuasar/Kronos-small",
        tokenizer_id="NeoQuasar/Kronos-Tokenizer-base",
        max_context=512,
        params="24.7M",
    ),
    "kronos-base": ModelSpec(
        key="kronos-base",
        model_id="NeoQuasar/Kronos-base",
        tokenizer_id="NeoQuasar/Kronos-Tokenizer-base",
        max_context=512,
        params="102.3M",
    ),
}

#: Intervals we allow. Free ``yfinance`` intraday history is capped (7 days at 5m, 60 days at
#: 1h), which is far shorter than a useful Kronos context, so daily bars are the default and
#: intraday is explicitly a best-effort convenience — see ``doc/objective.md`` non-goals.
ALLOWED_INTERVALS: dict[str, str] = {
    "1d": "5y",
    "1h": "60d",
    "1wk": "10y",
}

#: Cache lifetimes in minutes, per interval. Daily bars only change once a day, so a long TTL
#: is safe and keeps us well inside ``yfinance``'s rate limits.
CACHE_TTL_MINUTES: dict[str, int] = {"1d": 360, "1wk": 1440, "1h": 30}


# --------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Resolved application settings."""

    # ---- data ----
    interval: str = "1d"
    lookback: int = 400
    cache_enabled: bool = True

    # ---- forecast ----
    kronos_model: str = "kronos-small"
    device: str = "auto"
    pred_len: int = 10
    sample_count: int = 3
    temperature: float = 1.0
    top_p: float = 0.9

    # ---- signal thresholds ----
    signal_buy_threshold: float = 0.55
    signal_sell_threshold: float = -0.55
    min_confidence: float = 0.35
    vol_lookback: int = 60

    # ---- paper-trading risk limits (enforced, not advisory) ----
    initial_capital: float = 100_000.0
    position_pct: float = 0.20
    max_positions: int = 5
    max_position_pct: float = 0.30
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    commission_bps: float = 1.0
    slippage_bps: float = 2.0

    # ---- misc ----
    db_path: Path = DB_PATH
    cache_dir: Path = CACHE_DIR
    cors_origins: tuple[str, ...] = ()
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 60

    watchlist: tuple[Asset, ...] = field(default_factory=_parse_watchlist)

    def __post_init__(self) -> None:
        if self.interval not in ALLOWED_INTERVALS:
            raise ValueError(
                f"INTERVAL must be one of {sorted(ALLOWED_INTERVALS)}, got {self.interval!r}"
            )
        if self.kronos_model not in MODEL_REGISTRY:
            raise ValueError(
                f"KRONOS_MODEL must be one of {sorted(MODEL_REGISTRY)}, got {self.kronos_model!r}"
            )
        spec = MODEL_REGISTRY[self.kronos_model]
        if self.lookback > spec.max_context:
            raise ValueError(
                f"LOOKBACK={self.lookback} exceeds max_context={spec.max_context} for "
                f"{self.kronos_model}. Lower LOOKBACK or pick a larger-context model."
            )
        if self.pred_len < 1:
            raise ValueError("PRED_LEN must be at least 1")
        if not 0.0 < self.position_pct <= 1.0:
            raise ValueError("POSITION_PCT must be in (0, 1]")
        if not 0.0 < self.max_position_pct <= 1.0:
            raise ValueError("MAX_POSITION_PCT must be in (0, 1]")
        if self.signal_sell_threshold >= self.signal_buy_threshold:
            raise ValueError("SIGNAL_SELL_THRESHOLD must be below SIGNAL_BUY_THRESHOLD")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("MIN_CONFIDENCE must be in [0, 1]")

    # ---- derived helpers ----

    @property
    def model_spec(self) -> ModelSpec:
        return MODEL_REGISTRY[self.kronos_model]

    @property
    def history_period(self) -> str:
        """How far back to pull from ``yfinance`` for the configured interval."""
        return ALLOWED_INTERVALS[self.interval]

    @property
    def cache_ttl_minutes(self) -> int:
        return CACHE_TTL_MINUTES.get(self.interval, 60)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(asset.symbol for asset in self.watchlist)

    def asset(self, symbol: str) -> Asset | None:
        symbol = symbol.upper()
        for asset in self.watchlist:
            if asset.symbol == symbol:
                return asset
        return KNOWN_ASSETS.get(symbol)


def load_settings() -> Settings:
    """Build :class:`Settings` from the current environment."""
    origins_raw = _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        interval=_env("INTERVAL", "1d"),
        lookback=_env_int("LOOKBACK", 400),
        cache_enabled=_env_bool("CACHE_ENABLED", True),
        kronos_model=_env("KRONOS_MODEL", "kronos-small"),
        device=_env("DEVICE", "auto"),
        pred_len=_env_int("PRED_LEN", 10),
        sample_count=_env_int("SAMPLE_COUNT", 3),
        temperature=_env_float("TEMPERATURE", 1.0),
        top_p=_env_float("TOP_P", 0.9),
        signal_buy_threshold=_env_float("SIGNAL_BUY_THRESHOLD", 0.55),
        signal_sell_threshold=_env_float("SIGNAL_SELL_THRESHOLD", -0.55),
        min_confidence=_env_float("MIN_CONFIDENCE", 0.35),
        vol_lookback=_env_int("VOL_LOOKBACK", 60),
        initial_capital=_env_float("INITIAL_CAPITAL", 100_000.0),
        position_pct=_env_float("POSITION_PCT", 0.20),
        max_positions=_env_int("MAX_POSITIONS", 5),
        max_position_pct=_env_float("MAX_POSITION_PCT", 0.30),
        stop_loss_pct=_env_float("STOP_LOSS_PCT", 0.05),
        take_profit_pct=_env_float("TAKE_PROFIT_PCT", 0.10),
        commission_bps=_env_float("COMMISSION_BPS", 1.0),
        slippage_bps=_env_float("SLIPPAGE_BPS", 2.0),
        db_path=Path(_env("DB_PATH", str(DB_PATH))).expanduser(),
        cache_dir=Path(_env("CACHE_DIR", str(CACHE_DIR))).expanduser(),
        cors_origins=tuple(o.strip() for o in origins_raw.split(",") if o.strip()),
        scheduler_enabled=_env_bool("SCHEDULER_ENABLED", False),
        scheduler_interval_minutes=_env_int("SCHEDULER_INTERVAL_MINUTES", 60),
    )


#: Process-wide settings. Import this rather than calling :func:`load_settings` ad hoc.
settings = load_settings()
