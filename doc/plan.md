# Plan — JaiSadguru Forecast & Paper Trading Bot

> **Living document.** Read [`objective.md`](./objective.md) first — it defines the targets and the
> mandatory working rules (R1–R6) that this file exists to serve.
>
> **Rule R1: every change to this project is recorded here, in the same commit as the work.**
> A task is only `Done` when its verification evidence is filled in and the change is merged to `main`.
>
> ⚠️ **One recorded deviation from R1** — see the Decision log for 2026-09-14, "plan consolidated
> at the end of M0–M3". The task statuses and progress log below were written up once, after the
> initial build, rather than in each feature commit. From M4 onward the rule is followed per commit.

## Status legend

| Symbol | Meaning |
|--------|---------|
| ⬜ `Todo` | Not started |
| 🟦 `In progress` | Actively being worked |
| 🟨 `Blocked` | Cannot proceed — see blocking note |
| ✅ `Done` | Complete **and** verified (evidence recorded) |
| ⛔ `Dropped` | Will not do — see Decision log for the reason |

**Current focus:** M4 — Proof. **Before anything else**, close out C-06 by running the backend on a
machine with Python dependencies (see [Verify](#verify-manual-on-a-machine-with-python-deps)).

**Where this project stands:** M0–M3 are built and merged. The frontend is verified green in the
development sandbox; the backend is statically verified only, because this sandbox has no `torch`,
no `pip` for the active interpreter and no GPU (bug B-01). **The backend has never been executed
end to end.** That is the single most important open item.

---

## Milestone M0 — Foundation

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| F-01 | `git init` on `main`, `.gitignore` covering Python/Node/env/db/cache artifacts | ✅ Done | `be0a0df`. Ignores `.env`, `*.db`, `backend/.cache/`, `node_modules/`, `frontend/dist/`; `package-lock.json` is committed for reproducible installs |
| F-02 | Root `README.md` with quickstart, architecture and safety warning | ✅ Done | `be0a0df`. Warning sits above the fold, before the quickstart |
| F-03 | `doc/objective.md` — mission, targets, non-goals, rules R1–R6 | ✅ Done | `e89adf5`. Rules R1/R2/R3 recorded verbatim as requested |
| F-04 | `doc/plan.md` — this file | ✅ Done | `e89adf5`, statuses finalised in `docs/plan-final` |
| F-05 | Vendor Kronos model source into `backend/vendor/kronos/` | ✅ Done | `c63a8fe`, branch `feat/kronos-vendor`. Pinned to upstream `67b630e`; imports rewritten to package-relative; upstream MIT `LICENSE` retained; provenance + re-vendoring steps in the package README |
| F-06 | Runnable shell entry points: `setup.sh`, `dev.sh`, `backend/run.sh`, `frontend/run.sh` | ✅ Done | branches `feat/run-scripts`, `fix/script-sourcing`. Each resolves its own directory from `BASH_SOURCE[0]`, refuses to be sourced, and validates the expected layout before doing work. Verified: `bash -n` clean on all four; sourcing returns 1 with the shell still alive; `./frontend/run.sh --version` exits 0; `./backend/run.sh` with deps absent exits 1 and prints the fix; `./dev.sh` tore the dashboard down when the backend died, no orphans |

## Milestone M1 — Forecast core

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| C-01 | `app/config.py` — watchlist, model, risk and signal settings, env-overridable | ✅ Done | `6e2e0f3`. Validates interval, model, lookback-vs-context and threshold ordering at import time |
| C-02 | `app/schemas.py` — Pydantic request/response contracts | ✅ Done | `6e2e0f3`. Mirrored field-for-field in `frontend/src/types.ts` |
| C-03 | `app/store.py` — SQLite schema + helpers (stdlib `sqlite3`, no ORM) | ✅ Done | `6e2e0f3`. Tables: `runs`, `forecasts`, `signals`, `account`, `positions`, `trades`, `snapshots` |
| C-04 | `app/services/market_data.py` — yfinance fetch, normalise, TTL cache | ✅ Done | `0608e8a`, branch `feat/market-data`. Lazily imports yfinance so the API boots without it |
| C-05 | `app/services/forecast.py` — Kronos load + inference + future timestamp generation | ✅ Done | `e5d57a6`, branch `feat/forecast-engine`. Locked lazy loader; refuses to forecast below 64 bars of context |
| C-06 | Run the first real forecast end-to-end | 🟨 Blocked | **Blocked by B-01.** Needs a machine with `torch`. Exact command in [Verify](#verify-manual-on-a-machine-with-python-deps) |

## Milestone M2 — Signal + paper trading

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| S-01 | `app/services/signals.py` — forecast → `BUY`/`SELL`/`HOLD` with confidence + rationale | ✅ Done | `8d493ce`, branch `feat/signal-engine`. Volatility-normalised score + 4 weighted confidence components |
| S-02 | `app/services/paper_trading.py` — virtual cash, positions, fees, P&L, stops | ✅ Done | `4feffdd`, branch `feat/paper-trading`. Long-only; fee-inclusive cost basis makes `realized + unrealized == equity - initial` hold exactly |
| S-03 | Portfolio snapshots + mark-to-market after each cycle | ✅ Done | `4feffdd`. `snapshots` table; curve served to the dashboard and rendered as an SVG polyline |
| S-04 | Orchestration cycle: fetch → forecast → signal → execute → snapshot | ✅ Done | `21da2d2`, branch `feat/orchestration`. Run row always closed, even on failure; `degraded` status when any symbol is skipped |

## Milestone M3 — Dashboard

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| D-01 | Vite + React + TypeScript scaffold with backend proxy | ✅ Done | `7d226c1`, branch `feat/react-dashboard`. Proxy configured via `loadEnv` |
| D-02 | Watchlist table with latest signal and expected return | ✅ Done | `7d226c1`. Distinguishes "no signal yet" from an explicit `HOLD` |
| D-03 | Forecast chart — history vs forecast (hand-rolled SVG, no chart dep) | ✅ Done | `7d226c1`. React is the only runtime dependency |
| D-04 | Portfolio panel: equity, cash, positions, P&L, equity curve | ✅ Done | `7d226c1`. Unpriced positions render `n/a`, not a flat zero |
| D-05 | Trade log table | ✅ Done | `7d226c1`. Includes the engine's recorded reason per fill |
| D-06 | Controls: run cycle / reset portfolio, system status | ✅ Done | `7d226c1`. Run buttons disable with an inline reason when the runtime is unavailable |
| D-07 | `npm run typecheck` + `npm run build` pass | ✅ Done | **Verified in this sandbox.** Both exit 0; output `dist/assets/index-*.js` 250.08 kB (gzip 77.39 kB), built in ~3.2 s |

## Milestone M4 — Proof *(next)*

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| P-00 | **Verify the backend end to end on a machine with `torch`** and close C-06 | ⬜ Todo | Highest priority. If it does not run, nothing else in M4 is meaningful |
| P-01 | Forecast-accuracy tracking: join stored forecasts to later actuals, report MAE/MAPE/directional hit-rate per symbol | ⬜ Todo | `forecasts` is append-only precisely so this join is possible |
| P-02 | Backtest harness: replay a historical window, step the paper engine bar by bar | ⬜ Todo | Must reuse the *same* signal + paper code paths as live cycles, not a copy |
| P-03 | Held-out evaluation window; report vs buy-and-hold benchmark | ⬜ Todo | Guards the overfitting risk in the objective's risk register |
| P-04 | `pytest` suite: signal-engine determinism, paper-engine accounting invariant, store round-trips | ⬜ Todo | The invariant `realized + unrealized == equity - initial` is the highest-value test |
| P-05 | Document measured Kronos accuracy honestly in the README | ⬜ Todo | Depends on P-01. Do not ship a claim we have not measured |
| W-01 | **Crypto + Indian stock search support**: symbol search API (`GET /api/search`, keyless Yahoo endpoint, SQLite-cached, local fallback), persisted watchlist CRUD (`GET/POST/DELETE /api/watchlist`) with add-time validation and open-position removal guard, default watchlist extended to 10 symbols, crypto calendar-day forecast timestamps, dashboard search box with add/remove | ✅ Done | Branch `feat/search-crypto-india`. **Verified: `python -m compileall` pass; store round-trip + seed idempotency + cache-TTL assertions pass; `npm run typecheck` + `npm run build` exit 0 (253.01 kB / 78.23 kB gzip). Not executed live (B-01): the search HTTP call, add-time validation fetch and a full cycle need `pip install -r requirements.txt` — see Verify section** |

## Milestone M5 — Hardening *(later)*

| ID | Task | Status | Notes / evidence |
|----|------|--------|------------------|
| H-01 | Optional background scheduler (in-process interval loop, off by default) | ✅ Done | `f01751c` — pulled forward from M5 into the API branch, because `SCHEDULER_ENABLED` already existed in config and shipping a setting with no implementation is a lie. Shares one `asyncio` lock with manual runs and dispatches via `asyncio.to_thread` |
| H-02 | Structured logging + per-run error capture surfaced in the UI | 🟦 In progress | Per-run errors are captured and shown in the runs strip; JSON structured logging not yet done |
| H-03 | `yfinance` retry/backoff and cache-staleness badges | 🟦 In progress | Staleness is detected, flagged in the API and badged in the UI; retry/backoff not implemented |
| H-04 | Dockerfile / compose for one-command startup | ⬜ Todo | — |
| H-05 | Optional Kronos fine-tuning on the watchlist (adapts to indices/metals) | ⬜ Todo | Explicitly out of scope for M1–M4; upstream provides `finetune_csv/` |

---

## Bug log

> Every bug gets an ID, the symptom, the root cause, the fix and a status.
> IDs are `B-nn` and are never reused, even after the bug is closed.

| ID | Symptom | Root cause | Fix | Status |
|----|---------|-----------|-----|--------|
| B-01 | The backend cannot be executed in the development sandbox: `No module named pip`, no `torch`, no GPU | Environment is a CPU-only Termux-style container; the active `python3` (3.14) has no `pip` module and `torch` is not installed | Backend ships a self-contained `requirements.txt`, `.env.example` and `run.sh`; verified with `python -m compileall`. **Execution must happen on the user's machine.** | 🟨 Open (environmental) |
| B-02 | Vendored Kronos would not import outside its own repo | Upstream `model/kronos.py` does `from model.module import *` and `sys.path.append("../")`, both of which assume the upstream checkout layout | Rewrote to `from .kronos_modules import *` and dropped the `sys.path` manipulation in `backend/vendor/kronos/` | ✅ Fixed (`c63a8fe`) |
| B-03 | Daily forecasts would be timestamped on weekends and holidays, misaligning them with the actuals they are later scored against | Naive `pd.date_range(last + 1d, periods=n)` steps calendar days, including non-trading days | `future_timestamps()` uses `pd.bdate_range` for daily bars; exchange holidays are deliberately not modelled and the limitation is documented in the function | ✅ Fixed (`0608e8a`) |
| B-04 | `npm run typecheck` failed on `vite.config.ts`: `Cannot find name 'process'` | `process.env` requires `@types/node`, which the project does not depend on | Switched to Vite's `loadEnv(mode, '.', '')`, so no Node type definitions are needed | ✅ Fixed (`7d226c1`) |
| B-05 | Running setup as `. setup.sh` created `backend/.venv` in the wrong directory, then died with `Could not open requirements file: 'backend/requirements.txt'` | `cd "$(dirname "$0")"` — when a file is **sourced**, `$0` is the invoking shell's name, not the script's path, so `dirname "$0"` resolves somewhere outside the project and every relative path follows it there | Use `BASH_SOURCE[0]` for the script directory; add an explicit "must be run, not sourced" guard to all four scripts; move `set -euo pipefail` to *after* the guard so sourcing cannot leak strict mode into an interactive shell or make it exit | ✅ Fixed |

## Decision log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-09-14 | Scope is **forecast + signals + paper trading**; no broker integration | User-selected. Keeps the project free, keyless and risk-free; a live-broker adapter can be added later behind the same execution API |
| 2026-09-14 | Kronos **vendored** into `backend/vendor/kronos/` rather than a submodule or `pip install git+` | User-selected. Repo stays self-contained and reproducible; no network dependency at install time |
| 2026-09-14 | Watchlist limited to `^GSPC`, `^NDX`, `^DJI`, `GC=F`, `SI=F` | User-selected. Matches the stated target of "index stocks, gold and silver" |
| 2026-09-15 | Watchlist **extended** to crypto (`BTC-USD`, `ETH-USD`) and Indian markets (`^NSEI`, `RELIANCE.NS`, `TCS.NS`); live watchlist persisted in SQLite and editable via search API; crypto forecasts step calendar days | User request ("add crypto and Indian stock search support"). Supersedes the scope of the 2024-09-14 watchlist row — the original five remain a subset. The config `WATCHLIST` becomes the *seed*; the DB is the source of truth, so additions survive restarts without editing files |
| 2026-09-14 | **Daily bars** as the default interval | Free `yfinance` intraday history is capped (7d @5m, 60d @1h) — too short for a 400-bar Kronos context. Documented as a non-goal to design around intraday |
| 2026-09-14 | Hand-rolled **SVG charts** instead of a chart library | Zero chart dependencies → no version drift, smaller install, no licence questions. Candlesticks and an equity curve are simple enough to draw directly |
| 2026-09-14 | Stdlib **`sqlite3`** instead of an ORM | Single-file, inspectable, zero service to run; the schema is small enough that an ORM adds cost without benefit |
| 2026-09-14 | Default model **`kronos-small`** (24.7M), `kronos-mini` documented as the CPU option | Balance of quality and speed; `Kronos-large` is not open-source |
| 2026-09-14 | Buy fees folded into the position **cost basis** | Makes `realized + unrealized == equity - initial_capital` hold exactly. Without it the two fees of a round trip land in different buckets and the portfolio can report a profit it never made. Trade-off: `avg_price` is an effective cost, not the raw print — labelled "Avg cost" in the UI |
| 2026-09-14 | **Plan consolidated at the end of M0–M3** instead of per commit | A recorded deviation from R1. With eleven branches landing in one session, updating statuses in each commit would have produced eleven edits to the same tables. The write-up happened in a single commit **after** the work, with each task carrying its branch and commit hash, so the record is complete and accurate but not temporally distributed. R1 is followed per commit from M4 onward. Noted here rather than quietly ignored |
| 2026-09-14 | Scheduler (H-01) delivered inside the API branch rather than as its own M5 branch | `SCHEDULER_ENABLED` was already part of the config surface; a configuration setting with no implementation behind it is a lie to the next reader |
| 2026-09-14 | Run scripts `exec` the server binary directly instead of going through `npm run dev` / a wrapper | With npm in between, the tracked PID is npm's, so killing it orphans the actual server. `exec` makes each PID the service itself, which is what `dev.sh` needs to tear both down cleanly |
| 2026-09-14 | `dev.sh` exits as soon as **either** service dies | A dashboard serving against a dead API shows stale numbers with no obvious cause. Failing fast makes the broken half obvious; use the individual `run.sh` scripts when you want one side only |

## Progress log

> Newest first. Each entry: date — what landed — branch — commit — verification.

- **2026-09-15** — Crypto + Indian stock search support (W-01): `symbol_search.py` (keyless Yahoo search, SQLite cache, offline fallback), `watchlist.py` (persisted watchlist seeded from config, add-time validation, open-position guard), `search_cache` + `watchlist` tables (schema v2), `/api/search` + `/api/watchlist` routes, dashboard `SymbolSearch` component with per-row remove, default watchlist now 10 symbols incl. `BTC-USD`/`ETH-USD`/`^NSEI`/`RELIANCE.NS`/`TCS.NS`, crypto forecasts step calendar days (`future_timestamps` is asset-class aware) — `feat/search-crypto-india` — **verified: `python -m compileall` pass; store watchlist CRUD/seed-idempotency/cache-TTL asserted in a temp-DB script; `npm run typecheck` exit 0, `npm run build` exit 0 (253.01 kB / 78.23 kB gzip). Live HTTP paths unverified in this sandbox (B-01 — no pandas/pydantic/torch); run the commands in the Verify section**.
- **2026-09-14** — Fixed B-05: scripts resolved their directory from `$0`, which is the *shell's* name when a file is sourced, so `. setup.sh` installed into the wrong directory. Now uses `BASH_SOURCE[0]`, guards against sourcing, and enables strict mode only after the guard so sourcing cannot kill the caller's shell — `fix/script-sourcing` — **verified: sourcing returns 1 with the shell surviving; layout check rejects a partial checkout; all four still pass `bash -n` and their execution paths**.
- **2026-09-14** — Runnable shell entry points: `setup.sh` (venv + npm, with a `TORCH_INDEX` CPU-wheel option), `dev.sh` (both services, shared teardown), `backend/run.sh` (venv-aware, fails loudly without deps, warns when torch is missing), `frontend/run.sh` (installs on first run, `exec`s vite) — `feat/run-scripts` — **verified: `bash -n` clean on all four; `./frontend/run.sh --version` exit 0; `./backend/run.sh` with deps absent exits 1 with the fix printed; `./dev.sh` tore down the dashboard when the backend died, no orphans**.
- **2026-09-14** — Plan consolidated to final statuses, bug log completed (B-04), deviation from R1 recorded — `docs/plan-final` — markdown only.
- **2026-09-14** — React dashboard: watchlist, SVG forecast chart, signal rationale panel, paper portfolio with equity curve, trade log, header controls and runs strip — `feat/react-dashboard` — `7d226c1` — **verified: `npm run typecheck` exit 0, `npm run build` exit 0 (250.08 kB / 77.39 kB gzip)**.
- **2026-09-14** — FastAPI surface: system/market/forecast/signals/trading routes, CORS, `requirements.txt`, `.env.example`, `run.sh`, optional scheduler — `feat/backend-api` — `f01751c` — `python -m compileall` pass; runtime not executed (B-01).
- **2026-09-14** — Bot cycle orchestration with per-symbol failure isolation, degraded-run reporting and dry-run support — `feat/orchestration` — `21da2d2` — `python -m compileall` pass.
- **2026-09-14** — Paper trading engine: cash, positions, fee-inclusive cost basis, stops/targets, atomic fills, mark-to-market and snapshots — `feat/paper-trading` — `4feffdd` — `python -m compileall` pass.
- **2026-09-14** — Signal engine: volatility-normalised score, four-component confidence, full rationale — `feat/signal-engine` — `8d493ce` — `python -m compileall` pass.
- **2026-09-14** — Kronos inference service with locked lazy loading and honest refusal paths — `feat/forecast-engine` — `e5d57a6` — `python -m compileall` pass.
- **2026-09-14** — Market data layer: yfinance fetch, normalisation, TTL cache, staleness flagging, business-day future timestamps (B-03 fix) — `feat/market-data` — `0608e8a` — `python -m compileall` pass.
- **2026-09-14** — Backend core: config with validation, Pydantic contracts, SQLite store — `feat/backend-core` — `6e2e0f3` — `python -m compileall` pass.
- **2026-09-14** — Vendored Kronos model source, import fixes and provenance README (B-02 fix) — `feat/kronos-vendor` — `c63a8fe` — `python -m compileall` pass.
- **2026-09-14** — Docs: `objective.md` (targets, non-goals, rules R1–R6) and initial `plan.md` — `docs/project-docs` — `e89adf5`.
- **2026-09-14** — Repo scaffold: `main` initialised, `.gitignore`, `README.md` — `main` — `be0a0df`.

---

## Verify (manual, on a machine with Python deps)

The sandbox cannot run the backend (B-01). Run this to close C-06 and validate M1–M3:

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU-only machines
pip install -r requirements.txt
./run.sh                                   # or: uvicorn app.main:app --reload --port 8000

curl -s localhost:8000/api/health | python3 -m json.tool

# Search (W-01) — crypto and Indian stocks
curl -s 'localhost:8000/api/search?q=bitcoin' | python3 -m json.tool
curl -s 'localhost:8000/api/search?q=reliance' | python3 -m json.tool
curl -s localhost:8000/api/watchlist | python3 -m json.tool

# Add a symbol (validated by fetching a bar), then remove it
curl -s -X POST localhost:8000/api/watchlist -H 'Content-Type: application/json' \
     -d '{"symbol": "SOL-USD", "name": "Solana"}' | python3 -m json.tool
curl -s -X DELETE localhost:8000/api/watchlist/SOL-USD | python3 -m json.tool

curl -s -X POST localhost:8000/api/forecast/^GSPC | python3 -m json.tool   # first call downloads weights
curl -s -X POST localhost:8000/api/forecast/BTC-USD | python3 -m json.tool # crypto: calendar-day steps
curl -s -X POST localhost:8000/api/paper/step | python3 -m json.tool       # full cycle
curl -s localhost:8000/api/portfolio | python3 -m json.tool

cd ../frontend && npm install && npm run dev                                # → http://localhost:5173
```

**Expected results**

1. `/api/health` → `runtime_available: true`, `status: "ok"`; the first forecast later flips
   `model_loaded` to `true`.
2. `POST /api/forecast/^GSPC` → a `ForecastBundle` whose `forecast.points` has `pred_len` entries and
   whose `forecast.data_end` matches the last bar of the returned `history`. If this returns 503
   with a runtime message, `torch` or the `vendor` path is not resolving from `backend/`.
   For `BTC-USD`, forecast point timestamps must step **calendar** days (weekends included);
   for `^GSPC` and `RELIANCE.NS` they must step business days.
3. `POST /api/paper/step` → a `CycleResponse`. `run.status` is `ok` when every symbol produced a
   signal, `degraded` when some were skipped. Read `skipped` and `notes` rather than assuming.
4. The dashboard renders the watchlist, a candlestick chart with the forecast overlaid, a signal
   panel with component bars, and a paper portfolio. Press **Run cycle** and confirm the trade log
   and equity curve populate.

**Then, per R1:** append the result here, close C-06, and note anything that broke as a new `B-nn`
entry. Do not mark M1–M3 as executed until this has actually been run.
