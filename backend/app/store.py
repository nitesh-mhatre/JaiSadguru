"""SQLite persistence.

Deliberately built on the stdlib ``sqlite3`` module rather than an ORM: the schema is small, a
single file is easy to inspect and back up, and there is no service to run (see the Decision log
in ``doc/plan.md``).

Two invariants this module exists to protect (``doc/objective.md`` rule R6):

* A stored forecast carries the exact data window it was derived from, so it can never be
  silently attributed to the wrong bars.
* Forecasts are *never* overwritten by later actuals. Comparing a forecast against what really
  happened is an explicit join, so forecast error can be measured instead of retro-fitted.

Connections are opened per operation. SQLite connection objects are not safe to share across
threads, and FastAPI serves requests from a thread pool, so per-call connections are the simplest
correct choice here.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'running',
    started_at     TEXT    NOT NULL,
    finished_at    TEXT,
    duration_ms    INTEGER,
    symbols_ok     INTEGER NOT NULL DEFAULT 0,
    symbols_failed INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);

CREATE TABLE IF NOT EXISTS forecasts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    symbol        TEXT    NOT NULL,
    interval      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    data_start    TEXT    NOT NULL,
    data_end      TEXT    NOT NULL,
    last_close    REAL    NOT NULL,
    target_close  REAL    NOT NULL,
    model         TEXT    NOT NULL,
    horizon       INTEGER NOT NULL,
    sample_count  INTEGER NOT NULL,
    points_json   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_forecasts_symbol_created
    ON forecasts(symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    forecast_id       INTEGER REFERENCES forecasts(id) ON DELETE SET NULL,
    symbol            TEXT    NOT NULL,
    created_at        TEXT    NOT NULL,
    action            TEXT    NOT NULL,
    confidence        REAL    NOT NULL,
    score             REAL    NOT NULL,
    expected_return   REAL    NOT NULL,
    horizon           INTEGER NOT NULL,
    last_close        REAL    NOT NULL,
    suggested_qty     REAL    NOT NULL,
    rationale_json    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_created
    ON signals(symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS account (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    initial_capital REAL NOT NULL,
    cash            REAL NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    symbol            TEXT PRIMARY KEY,
    qty               REAL NOT NULL,
    avg_price         REAL NOT NULL,
    opened_at         TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    stop_price        REAL,
    take_profit_price REAL,
    signal_id         INTEGER REFERENCES signals(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    signal_id    INTEGER REFERENCES signals(id) ON DELETE SET NULL,
    symbol       TEXT    NOT NULL,
    side         TEXT    NOT NULL,
    qty          REAL    NOT NULL,
    price        REAL    NOT NULL,
    gross        REAL    NOT NULL,
    fee          REAL    NOT NULL,
    realized_pnl REAL,
    executed_at  TEXT    NOT NULL,
    reason       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_executed ON trades(executed_at DESC);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    cash            REAL    NOT NULL,
    positions_value REAL    NOT NULL,
    equity          REAL    NOT NULL,
    realized_pnl    REAL    NOT NULL,
    unrealized_pnl  REAL    NOT NULL,
    open_positions  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON snapshots(created_at DESC);
"""


def utcnow() -> str:
    """Current UTC time as an ISO-8601 string, second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value: Any) -> str:
    """JSON-encode a value, stringifying anything exotic (dates, numpy scalars)."""
    return json.dumps(value, default=str, separators=(",", ":"))


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


class Store:
    """All persistence for the bot. Construct once and share; it holds no connection."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    # ------------------------------------------------------------------ plumbing

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, committing on success and rolling back on any exception."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create tables and indexes if they do not exist. Safe to call on every startup."""
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ------------------------------------------------------------------ runs

    def create_run(self, kind: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (kind, status, started_at) VALUES (?, 'running', ?)",
                (kind, utcnow()),
            )
            return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        symbols_ok: int = 0,
        symbols_failed: int = 0,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE runs
                   SET status = ?, finished_at = ?, duration_ms = ?,
                       symbols_ok = ?, symbols_failed = ?, error = ?
                 WHERE id = ?
                """,
                (status, utcnow(), duration_ms, symbols_ok, symbols_failed, error, run_id),
            )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ forecasts

    def save_forecast(
        self,
        *,
        run_id: int | None,
        symbol: str,
        interval: str,
        data_start: str,
        data_end: str,
        last_close: float,
        target_close: float,
        model: str,
        horizon: int,
        sample_count: int,
        points: list[dict[str, Any]],
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO forecasts (
                    run_id, symbol, interval, created_at, data_start, data_end,
                    last_close, target_close, model, horizon, sample_count, points_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    symbol,
                    interval,
                    utcnow(),
                    data_start,
                    data_end,
                    last_close,
                    target_close,
                    model,
                    horizon,
                    sample_count,
                    _dumps(points),
                ),
            )
            return int(cur.lastrowid)

    def get_forecast(self, forecast_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM forecasts WHERE id = ?", (forecast_id,)
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        record["points"] = _loads(record.pop("points_json")) or []
        return record

    def latest_forecast(self, symbol: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM forecasts WHERE symbol = ? ORDER BY id DESC LIMIT 1",
                (symbol.upper(),),
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        record["points"] = _loads(record.pop("points_json")) or []
        return record

    def recent_forecasts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Recent forecast headers, without the bulky point arrays."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, symbol, interval, created_at, data_start, data_end,
                       last_close, target_close, model, horizon, sample_count
                  FROM forecasts
                 ORDER BY id DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ signals

    def save_signal(
        self,
        *,
        run_id: int | None,
        forecast_id: int | None,
        symbol: str,
        action: str,
        confidence: float,
        score: float,
        expected_return: float,
        horizon: int,
        last_close: float,
        suggested_qty: float,
        rationale: dict[str, Any],
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals (
                    run_id, forecast_id, symbol, created_at, action, confidence, score,
                    expected_return, horizon, last_close, suggested_qty, rationale_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    forecast_id,
                    symbol,
                    utcnow(),
                    action,
                    confidence,
                    score,
                    expected_return,
                    horizon,
                    last_close,
                    suggested_qty,
                    _dumps(rationale),
                ),
            )
            return int(cur.lastrowid)

    def get_signal(self, signal_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        return self._decode_signal(row)

    def latest_signals(self) -> list[dict[str, Any]]:
        """The most recent signal per symbol."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM signals
                 WHERE id IN (SELECT MAX(id) FROM signals GROUP BY symbol)
                 ORDER BY symbol
                """
            ).fetchall()
        return [s for s in (self._decode_signal(r) for r in rows) if s]

    def recent_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [s for s in (self._decode_signal(r) for r in rows) if s]

    @staticmethod
    def _decode_signal(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        record = dict(row)
        record["rationale"] = _loads(record.pop("rationale_json")) or {}
        return record

    # ------------------------------------------------------------------ account

    def ensure_account(self, initial_capital: float) -> dict[str, Any]:
        """Return the single account row, creating it on first use."""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
            if row is None:
                now = utcnow()
                conn.execute(
                    """
                    INSERT INTO account (id, initial_capital, cash, created_at, updated_at)
                    VALUES (1, ?, ?, ?, ?)
                    """,
                    (initial_capital, initial_capital, now, now),
                )
                row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
        return dict(row)

    def get_account(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
        return dict(row) if row else None

    def set_cash(self, cash: float) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE account SET cash = ?, updated_at = ? WHERE id = 1",
                (cash, utcnow()),
            )

    # ------------------------------------------------------------------ positions

    def get_positions(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        return [dict(r) for r in rows]

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),)
            ).fetchone()
        return dict(row) if row else None

    def upsert_position(
        self,
        *,
        symbol: str,
        qty: float,
        avg_price: float,
        opened_at: str,
        stop_price: float | None,
        take_profit_price: float | None,
        signal_id: int | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO positions (
                    symbol, qty, avg_price, opened_at, updated_at,
                    stop_price, take_profit_price, signal_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    qty               = excluded.qty,
                    avg_price         = excluded.avg_price,
                    updated_at        = excluded.updated_at,
                    stop_price        = excluded.stop_price,
                    take_profit_price = excluded.take_profit_price,
                    signal_id         = excluded.signal_id
                """,
                (
                    symbol.upper(),
                    qty,
                    avg_price,
                    opened_at,
                    utcnow(),
                    stop_price,
                    take_profit_price,
                    signal_id,
                ),
            )

    def delete_position(self, symbol: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol.upper(),))

    # ------------------------------------------------------------------ trades

    def insert_trade(
        self,
        *,
        run_id: int | None,
        signal_id: int | None,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        gross: float,
        fee: float,
        realized_pnl: float | None,
        reason: str,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades (
                    run_id, signal_id, symbol, side, qty, price,
                    gross, fee, realized_pnl, executed_at, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    signal_id,
                    symbol.upper(),
                    side,
                    qty,
                    price,
                    gross,
                    fee,
                    realized_pnl,
                    utcnow(),
                    reason,
                ),
            )
            return int(cur.lastrowid)

    def recent_trades(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def realized_pnl(self) -> float:
        """Total realised P&L over all closed trades.

        Derived from the trade log rather than stored on the account, so the two can never
        drift apart.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(realized_pnl), 0.0) AS total FROM trades"
            ).fetchone()
        return float(row["total"])

    # ------------------------------------------------------------------ snapshots

    def insert_snapshot(
        self,
        *,
        cash: float,
        positions_value: float,
        equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
        open_positions: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    created_at, cash, positions_value, equity,
                    realized_pnl, unrealized_pnl, open_positions
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utcnow(),
                    cash,
                    positions_value,
                    equity,
                    realized_pnl,
                    unrealized_pnl,
                    open_positions,
                ),
            )

    def recent_snapshots(self, limit: int = 500) -> list[dict[str, Any]]:
        """Snapshots oldest-first, so the client can plot an equity curve directly."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------------ maintenance

    def reset_portfolio(self, initial_capital: float) -> None:
        """Clear the simulated account.

        Positions, trades and snapshots are removed and cash is restored. Forecasts, signals and
        run history are **kept** on purpose: they are the audit trail of what the bot decided,
        and deleting them would make past behaviour unexplainable.
        """
        now = utcnow()
        with self.connect() as conn:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM snapshots")
            conn.execute(
                """
                INSERT INTO account (id, initial_capital, cash, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    initial_capital = excluded.initial_capital,
                    cash            = excluded.cash,
                    updated_at      = excluded.updated_at
                """,
                (initial_capital, initial_capital, now, now),
            )

    def stats(self) -> dict[str, int]:
        """Row counts per table — handy for the health endpoint and manual inspection."""
        tables = ("runs", "forecasts", "signals", "positions", "trades", "snapshots")
        with self.connect() as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
                for table in tables
            }
