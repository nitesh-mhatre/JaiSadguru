# Plan — JaiSadguru Forecast & Paper Trading Bot

> **Living document.** Read [`objective.md`](./objective.md) first — it defines the targets and the
> mandatory working rules (R1–R6) that this file exists to serve.
>
> **Rule R1: every change to this project is recorded here, in the same commit as the work.**
> A task is only `Done` when its verification evidence is filled in and the change is merged to `main`.

## Status legend

| Symbol | Meaning |
|--------|---------|
| ⬜ `Todo` | Not started |
| 🟦 `In progress` | Actively being worked |
| 🟨 `Blocked` | Cannot proceed — see blocking note |
| ✅ `Done` | Complete **and** verified (evidence recorded) |
| ⛔ `Dropped` | Will not do — see Decision log for the reason |

**Current focus:** M0 — Foundation, then M1 — Forecast core.

---

## Milestone M0 — Foundation

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| F-01 | `git init` on `main`, `.gitignore` covering Python/Node/env/db/cache artifacts | ✅ Done | `.gitignore` ignores `.env`, `*.db`, `backend/.cache/`, `node_modules/`, `frontend/dist/` |
| F-02 | Root `README.md` with quickstart, architecture and safety warning | ✅ Done | Includes the "no real orders" warning above the fold |
| F-03 | `doc/objective.md` — mission, targets, non-goals, rules R1–R6 | ✅ Done | Rules R1 (record in plan.md), R2 (commit per build), R3 (branch per feature) recorded verbatim |
| F-04 | `doc/plan.md` — this file | ✅ Done | — |
| F-05 | Vendor Kronos model source into `backend/vendor/kronos/` | ⬜ Todo | Upstream is MIT; must rewrite `from model.module import *` and drop `sys.path` hacks |

## Milestone M1 — Forecast core

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| C-01 | `app/config.py` — watchlist, model, risk and signal settings, env-overridable | ⬜ Todo | Symbols: `^GSPC`, `^NDX`, `^DJI`, `GC=F`, `SI=F` |
| C-02 | `app/schemas.py` — Pydantic request/response contracts | ⬜ Todo | Stable JSON shapes for the dashboard |
| C-03 | `app/store.py` — SQLite schema + helpers (stdlib `sqlite3`, no ORM) | ⬜ Todo | Tables: `runs`, `forecasts`, `signals`, `account`, `positions`, `trades`, `snapshots` |
| C-04 | `app/services/market_data.py` — yfinance fetch, normalise, TTL cache | ⬜ Todo | tz stripped, `amount` derived, per-symbol failure isolation |
| C-05 | `app/services/forecast.py` — Kronos load + inference + future timestamp generation | ⬜ Todo | Lazy singleton loader, `pd.bdate_range` for daily horizons |
| C-06 | Run the first real forecast end-to-end | 🟨 Blocked | **Blocked by B-01** — no `torch`/`pip` in the dev sandbox. See "Verify" section for the user-side command |

## Milestone M2 — Signal + paper trading

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| S-01 | `app/services/signals.py` — forecast → `BUY`/`SELL`/`HOLD` with confidence + rationale | ⬜ Todo | Volatility-normalised score, trend agreement, monotonicity, dispersion penalty |
| S-02 | `app/services/paper_trading.py` — virtual cash, positions, fees, P&L, stops | ⬜ Todo | Long-only; commission + slippage in bps; max-position and max-count guards |
| S-03 | Portfolio snapshots + mark-to-market after each cycle | ⬜ Todo | `snapshots` table; equity curve served to the dashboard |
| S-04 | Orchestration cycle: fetch → forecast → signal → execute → snapshot | ⬜ Todo | `POST /api/paper/step`; per-symbol failures isolated, run marked degraded |

## Milestone M3 — Dashboard

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| D-01 | Vite + React + TypeScript scaffold with backend proxy | ⬜ Todo | — |
| D-02 | Watchlist table with latest signal and expected return | ⬜ Todo | — |
| D-03 | Forecast chart — history vs forecast (hand-rolled SVG, no chart dep) | ⬜ Todo | Zero runtime deps beyond React |
| D-04 | Portfolio panel: equity, cash, positions, P&L, equity curve | ⬜ Todo | — |
| D-05 | Trade log table | ⬜ Todo | — |
| D-06 | Controls: run cycle / reset portfolio, system status | ⬜ Todo | — |
| D-07 | `npm run typecheck` + `npm run build` pass | ⬜ Todo | — |

## Milestone M4 — Proof *(next)*

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| P-01 | Forecast-accuracy tracking: join stored forecasts to later actuals, report MAE/MAPE/directional hit-rate per symbol | ⬜ Todo | Depends on C-03's "forecasts are never overwritten" rule |
| P-02 | Backtest harness: replay a historical window, step the paper engine bar by bar | ⬜ Todo | Must reuse the *same* signal + paper code paths as live cycles, not a copy |
| P-03 | Held-out evaluation window; report vs buy-and-hold benchmark | ⬜ Todo | Guards against the overfitting risk in the objective's risk register |
| P-04 | `pytest` suite: signal engine determinism, paper-engine accounting invariants (cash + positions = equity), store round-trips | ⬜ Todo | Accounting invariants are the highest-value tests |
| P-05 | Document measured Kronos accuracy honestly in the README | ⬜ Todo | Depends on P-01 |

## Milestone M5 — Hardening *(later)*

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| H-01 | Optional background scheduler (in-process interval loop, off by default) | ⬜ Todo | Must not double-fire with manual cycles |
| H-02 | Structured logging + per-run error capture surfaced in the UI | ⬜ Todo | — |
| H-03 | `yfinance` retry/backoff and cache-staleness badges | ⬜ Todo | — |
| H-04 | Dockerfile / compose for one-command startup | ⬜ Todo | — |
| H-05 | Optional Kronos fine-tuning on the watchlist (adapts to indices/metals) | ⬜ Todo | Explicitly out of scope for M1–M4 |

---

## Bug log

> Every bug gets an ID, the symptom, the root cause, the fix and a status.
> IDs are `B-nn` and are never reused, even after the bug is closed.

| ID | Symptom | Root cause | Fix | Status |
|----|---------|-----------|-----|--------|
| B-01 | Backend cannot be executed in the development sandbox (`No module named pip`, no `torch`) | Environment is a CPU-only Termux-style container; the `torch`/FastAPI stack is not installed and the active `python3` (3.14) has no `pip` module | Backend ships a self-contained `requirements.txt` + `run.sh`; syntax verified with `python -m compileall`. **Execution happens on the user's machine.** | 🟨 Open (environmental) |
| B-02 | Vendored Kronos would not import | Upstream `model/kronos.py` does `from model.module import *` and `sys.path.append("../")` — only valid when run from inside its own repo | Rewrote imports to package-relative in `backend/vendor/kronos/`, dropped the `sys.path` manipulation | ✅ Fixed |
| B-03 | Daily forecast timestamps would land on weekends/holidays and misalign with actuals | Naive `pd.date_range(last + 1d, periods=n)` includes non-trading days | Generate daily horizons with `pd.bdate_range` over the symbol's known trading calendar | ✅ Fixed |

## Decision log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-09-14 | Scope is **forecast + signals + paper trading**; no broker integration | User-selected. Keeps the project free, keyless and risk-free; a live-broker adapter can be added later behind the same execution API |
| 2026-09-14 | Kronos **vendored** into `backend/vendor/kronos/` rather than a submodule or `pip install git+` | User-selected. Repo stays self-contained and reproducible; no network dependency at install time |
| 2026-09-14 | Watchlist limited to `^GSPC`, `^NDX`, `^DJI`, `GC=F`, `SI=F` | User-selected. Matches the stated target of "index stocks, gold and silver" |
| 2026-09-14 | **Daily bars** as the default interval | Free `yfinance` intraday history is capped (7d @5m, 60d @1h) — too short for a 400-bar Kronos context. Documented as a non-goal to design around intraday |
| 2026-09-14 | Hand-rolled **SVG charts** instead of a chart library | Zero chart dependencies → no version drift, smaller install, no licence questions. Candlesticks and an equity curve are simple enough to draw directly |
| 2026-09-14 | Stdlib **`sqlite3`** instead of an ORM | Single-file, inspectable, zero service to run; the schema is small enough that an ORM adds cost without benefit |
| 2026-09-14 | Default model **`kronos-small`** (24.7M), `kronos-mini` documented as the CPU option | Balance of quality and speed; `Kronos-large` is not open-source |

## Progress log

> Newest first. Each entry: date — what landed — branch — commit — verification.

- **2026-09-14** — Docs: `objective.md` (targets, non-goals, rules R1–R6) and `plan.md` — `docs/project-docs` — markdown only, no build step.
- **2026-09-14** — Repo scaffold: `main` initialised, `.gitignore`, `README.md` — `main`.

---

## Verify (manual, on a machine with Python deps)

The sandbox cannot run the backend (B-01). Run this on your own machine to confirm M1–M3:

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # → http://localhost:8000/docs

curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/forecast/^GSPC     # first call downloads Kronos weights
curl -s -X POST localhost:8000/api/paper/step         # full cycle: data → forecast → signal → trade
curl -s localhost:8000/api/portfolio

cd ../frontend && npm install && npm run dev          # → http://localhost:5173
```

Expected: `/api/health` reports the model as available; `/api/paper/step` returns a summary with a
signal per symbol; `/api/portfolio` shows virtual cash plus any opened positions; the dashboard
renders the forecast chart against history. Record the outcome here and close C-06.
