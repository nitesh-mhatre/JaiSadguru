# Objective — JaiSadguru Forecast & Paper Trading Bot

> **This document is the contract for the project.** It defines what we are building, what we are
> explicitly *not* building, and the working rules every contributor (human or agent) must follow.
> Task-level tracking lives in [`plan.md`](./plan.md). If the two disagree, this file wins —
> and then `plan.md` must be updated to match.

---

## 1. Mission

Build a **free, self-hosted forecasting and paper-trading bot** that uses the Kronos foundation
model to predict short-horizon price paths for **index stocks, gold and silver**, derives
actionable `BUY` / `SELL` / `HOLD` signals, and executes them against a **simulated portfolio** so
that strategy behaviour can be observed and measured over time without risking capital.

## 2. Primary targets

| # | Target | Success criterion |
|---|--------|-------------------|
| T1 | Free data ingestion | Daily OHLCV for `^GSPC`, `^NDX`, `^DJI`, `GC=F`, `SI=F` pulled via `yfinance` with **no API keys and no paid feed** |
| T2 | Working forecasts | Kronos produces an OHLCV forecast path per symbol for a configurable horizon |
| T3 | Deterministic signal layer | Every forecast maps to exactly one `BUY`/`SELL`/`HOLD` with a numeric confidence and machine-readable rationale |
| T4 | Realistic paper portfolio | Virtual cash, positions, average cost, realised/unrealised P&L, fees, equity snapshots, full trade log |
| T5 | Observable dashboard | React UI shows prices, forecast vs actual, signals, portfolio and trade log without page reloads |
| T6 | Reproducible setup | A clean clone runs with `pip install -r requirements.txt` + `npm install` and needs **no secrets** |
| T7 | Auditable history | Forecasts, signals, trades and run outcomes persist in SQLite and survive restarts |

## 3. Explicit non-goals

- ❌ **No live order execution.** No broker integration, no API keys, no real money, ever, in this phase.
- ❌ **No paid data.** If a data source needs a card, it is out of scope.
- ❌ **No claims of profit.** This is an engineering and research exercise, not an investment product.
- ❌ **No intraday-centric design.** Free intraday history is capped by `yfinance` (7d for 5m, 60d for
  1h); daily bars are the supported default. Intraday is best-effort and must never be presented as
  equivalent.
- ❌ **No fine-tuning in the first milestone.** Use the pretrained Kronos checkpoints. Fine-tuning is a
  later, separate milestone.

## 4. Working rules (the process contract)

These rules are mandatory. They are the ones the project owner asked to be recorded here.

### R1 — Keep a written record in `doc/plan.md`
- Every task that is started, changed, completed or abandoned is reflected in `plan.md`.
- Every bug found gets an entry in the **Bug log** section with: ID, symptom, root cause, fix, status.
- Every non-obvious technical decision gets a line in the **Decision log** with the date and the reason.
- Progress is tracked by moving tasks between `Todo → In progress → Done` and appending to the
  **Progress log**. A task is never marked `Done` without its verification evidence recorded.
- `plan.md` is updated **in the same commit** as the work it describes — never in a later "docs" pass.

### R2 — Commit after each build
- Every completed, self-consistent unit of work ends in a commit. No long-lived uncommitted trees.
- A commit must leave the repo in a state that builds: backend byte-compiles / imports, frontend
  typechecks and builds.
- Commit messages follow Conventional Commits with a scope, e.g.
  `feat(signals): add volatility-normalised confidence score`. The body explains **why**.
- Never commit: `.env`, caches, market data dumps, `*.db`, build output. These are git-ignored —
  check `git status` before staging and stage files explicitly rather than `git add -A` blindly.
- Never commit or push anything until the verification step for that unit has passed.

### R3 — One branch per feature
- Branch naming: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- One feature per branch. Do not mix unrelated changes; a stray fix rides along only if the feature
  cannot be verified without it, and then it is called out in the commit body.
- Work lands on `main` **only** via a merge (`git merge --no-ff`) after verification passes.
- `main` must always be in a working state. If a branch is abandoned, it is deleted and the reason
  recorded in the Decision log.
- Never rewrite shared history (`push --force`, `rebase` on `main`).

### R4 — Verify before declaring done
- Backend: `python -m compileall backend/app` (and `pytest` once tests exist) must pass.
- Frontend: `npm run typecheck` (`tsc --noEmit`) and `npm run build` must pass.
- A change that cannot be executed in the current environment (e.g. no GPU/`torch` available) must
  say so explicitly in the commit body and in `plan.md`, and must ship with the exact command the
  user can run to verify it. **Never claim a green result that was not observed.**

### R5 — Safety rails are code, not comments
- Paper trading only. Any code path that could place a real order must not exist.
- Risk limits (max positions, position size, stop-loss, take-profit, fees) are configuration values
  with safe defaults, enforced in the engine — not advice in a docstring.
- The bot must fail loudly and never silently widen risk: on missing data or a failed forecast, the
  symbol is skipped and the run is marked degraded, never guessed.

### R6 — Data honesty
- A stale or partial dataset must be detectable. Every stored forecast records the data window it
  was derived from, so a forecast can never be silently attributed to the wrong bars.
- Forecasts are stored as **predictions**, and are never overwritten by later actuals — comparison is
  an explicit join, so we can measure forecast error over time instead of retro-fitting it.

## 5. Technical decisions (fixed for this phase)

| Area | Decision | Why |
|------|----------|-----|
| Frontend | React + TypeScript on Vite | Requested; fast dev server, trivial proxy to backend |
| Charts | Hand-rolled SVG components | Zero chart deps → no version drift, no licence questions, tiny install |
| Backend | Python 3.10+ with FastAPI + Uvicorn | Requested language; async HTTP, automatic OpenAPI at `/docs` |
| Model | Vendored Kronos code in `backend/vendor/kronos/` | Repo stays self-contained and reproducible; upstream is only MIT-licensed source, not a dependency to be resolved at runtime |
| Weights | Downloaded at runtime from Hugging Face | Keeps the repo small; `Kronos-mini` confirms CPU-only smoke tests |
| Data | `yfinance`, daily bars default | Free, keyless, broad coverage of indices and futures |
| Storage | `sqlite3` from the stdlib | No ORM/service needed; single file; inspectable with any SQLite client |
| Execution | Simulated portfolio in-process | No broker, no keys, no money — see non-goals |

## 6. Configuration surface

All runtime knobs live in `backend/app/config.py` and are overridable by environment variables
(see `backend/.env.example`). Safe defaults are mandatory:

- `WATCHLIST` — symbols to track.
- `INTERVAL` (`1d`) / `LOOKBACK` (400 bars) / `PRED_LEN` (forecast horizon in bars).
- `KRONOS_MODEL` (`kronos-small`) / `DEVICE` (`auto`).
- Risk: `INITIAL_CAPITAL`, `POSITION_PCT`, `MAX_POSITIONS`, `MAX_POSITION_PCT`, `STOP_LOSS_PCT`,
  `TAKE_PROFIT_PCT`, `COMMISSION_BPS`, `SLIPPAGE_BPS`.
- Signals: `SIGNAL_BUY_THRESHOLD`, `SIGNAL_SELL_THRESHOLD`, `MIN_CONFIDENCE`.

## 7. Definition of Done

A task is Done only when **all** of these hold:

1. Code implements the described behaviour, matching existing project conventions.
2. `plan.md` is updated in the same commit (R1).
3. Verification for that layer passed — or, where the environment cannot run it, the limitation and
   the exact user-side command are recorded (R4).
4. No new secret, dataset, build artifact or `.db` file entered git.
5. The change is on a correctly named branch and merged to `main` per R3.

## 8. Milestones

| Milestone | Content | Status |
|-----------|---------|--------|
| **M0 — Foundation** | Docs, repo scaffold, vendored Kronos | ✅ built |
| **M1 — Forecast core** | Data layer, Kronos inference, API | ✅ built · ⚠️ not yet executed end to end |
| **M2 — Signal + paper trading** | Signal rules, portfolio engine, persistence | ✅ built · ⚠️ not yet executed end to end |
| **M3 — Dashboard** | React UI for prices, forecast, signals, portfolio, trades | ✅ built and verified (`tsc` + `vite build`) |
| **M4 — Proof** | Backend end-to-end run, backtest harness, accuracy tracking, tests | ⬜ next |
| **M5 — Hardening** | Retries, structured logging, Docker | ⬜ later — scheduler done early in M3's API work |

> **"Built" is not "working".** The backend was developed in an environment with no `torch`, no
> `pip` and no GPU, so it has only been statically verified (see bug B-01 in `plan.md`). Running it
> end to end and recording the result is the first task of M4 — task **P-00**. No claim about
> forecast quality may be made before that, and none is.

## 9. Risk register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Kronos accuracy is far weaker in practice than papers suggest | Misleading signals | Track forecast error vs actuals from day one; never present forecasts as advice |
| `yfinance` rate limits / schema changes | Stale or failed runs | On-disk cache with TTL; per-symbol failure isolation; run marked degraded rather than guessed |
| CPU-only inference is slow | Poor UX | Default to `kronos-small`; document `kronos-mini`; cache forecasts per bar |
| Overfitting the signal thresholds to the paper portfolio | False confidence | Thresholds live in config; M4 backtest must evaluate on a held-out window |
| Index/futures tickers have different sessions & gaps | Bad timestamps to the model | Timestamps normalised and timezone-stripped in the data layer; gaps documented |

## 10. Glossary

- **Kronos** — open-source decoder-only foundation model for OHLCV candlesticks (AAAI 2026).
- **K-line / candle** — one OHLCV bar.
- **LOOKBACK** — number of historical bars fed to the model as context (≤ 512 for small/base).
- **PRED_LEN / horizon** — number of future bars the model samples.
- **sample_count** — parallel sampled forecast paths, averaged to reduce noise.
- **Paper trading** — simulated execution against real prices; no real money.
- **Mark to market** — revaluing open positions at the latest price to get equity.
