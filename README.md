# JaiSadguru — Kronos Forecast & Paper Trading Bot

A **free, self-hosted** forecasting and paper-trading bot. It pulls market data from
[`yfinance`](https://github.com/ranaroussi/yfinance) (no paid data feed, no API keys) and uses
[**Kronos**](https://github.com/shiyu-coder/Kronos) — the first open-source foundation model for
financial candlesticks — to forecast prices for **US indices, gold and silver, crypto, and
Indian stocks**.

Forecasts are converted into `BUY` / `SELL` / `HOLD` signals by a rule-based signal engine, and
those signals are executed against a **simulated portfolio** (virtual cash, positions, P&L,
trade log). **No real orders are ever placed and no broker credentials are required.**

## Watchlist

| Symbol        | Asset                     | Class     |
| ------------- | ------------------------- | --------- |
| `^GSPC`       | S&P 500                   | index     |
| `^NDX`        | Nasdaq 100                | index     |
| `^DJI`        | Dow Jones 30              | index     |
| `GC=F`        | Gold futures              | commodity |
| `SI=F`        | Silver futures            | commodity |
| `BTC-USD`     | Bitcoin                   | crypto    |
| `ETH-USD`     | Ethereum                  | crypto    |
| `^NSEI`       | Nifty 50                  | index     |
| `RELIANCE.NS` | Reliance Industries (NSE) | stock     |
| `TCS.NS`      | Tata Consultancy (NSE)    | stock     |

Any ticker `yfinance` supports works — including other crypto pairs (`SOL-USD`) and other
NSE/BSE stocks (`INFY.NS`, `HDFCBANK.NS`).

### Search and the live watchlist

The dashboard has a **search box** above the watchlist table: type a name or ticker
(`bitcoin`, `reliance`, `^NSEI`, `SOL-USD`) and add a hit to start tracking it. The live
watchlist is stored in SQLite and survives restarts; the `WATCHLIST` environment variable is
only the *seed* for a fresh database. A symbol is validated at add-time by actually fetching a
bar, so a typo is rejected once instead of skipped by every future cycle; a symbol with an open
paper position cannot be removed.

Programmatically: `GET /api/search?q=…`, `GET/POST/DELETE /api/watchlist` (see `/docs`).

> Crypto note: crypto trades 24/7, so daily bars include weekends and forecasts step calendar
> days. Session-traded assets (indices, futures, NSE/BSE stocks) step business days. Exchange
> holidays are not modelled.

## Architecture

```
React (Vite + TS)  ──HTTP/JSON──▶  FastAPI (Python)  ──▶  yfinance (market data)
       dashboard                    │                 ──▶  Kronos (forecast model)
                                    ├── signal engine (rules)
                                    ├── paper trading engine (virtual portfolio)
                                    └── SQLite (forecasts, signals, trades, snapshots)
```

- `backend/` — Python 3.10+ FastAPI service. Vendored Kronos model in `backend/vendor/kronos/`.
- `frontend/` — React + TypeScript dashboard (Vite), zero chart dependencies (hand-rolled SVG).
- `doc/objective.md` — goals, rules and working agreements for this project. **Read this first.**
- `doc/plan.md` — live task list, progress log and bug tracker.

## Quickstart

```bash
./setup.sh    # once: backend venv + frontend npm install (nothing installed globally)
./dev.sh      # backend + dashboard together; Ctrl-C stops both
```

> Run them as `./setup.sh`, **not** `. setup.sh` or `source setup.sh`. Sourcing makes `$0`
> resolve to your shell rather than the script, so relative paths point at the wrong directory.
> The scripts detect this and refuse, rather than half-installing somewhere unexpected.

| Service | URL |
|---------|-----|
| Dashboard | <http://localhost:5173> |
| API + interactive docs | <http://localhost:8000/docs> |

The first forecast downloads the Kronos weights from Hugging Face into `~/.cache/huggingface`
(~100 MB for `kronos-small`). Set `KRONOS_MODEL=kronos-mini` in `backend/.env` for the lighter
4.1M-parameter model.

On a CPU-only machine, install torch from the CPU wheel index so pip does not pull a
multi-gigabyte CUDA build:

```bash
TORCH_INDEX=https://download.pytorch.org/whl/cpu ./setup.sh
```

### Running one side only

```bash
./backend/run.sh     # API only      -> http://localhost:8000
./frontend/run.sh    # dashboard only -> http://localhost:5173
```

Both scripts accept an optional `PORT`, forward extra arguments to the underlying server, and
refuse to start with a clear message if their dependencies are missing.

### Manual setup (no scripts)

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend, in a second terminal
cd frontend && npm install && npm run dev
```

### Run a bot cycle

From the dashboard click **Run cycle**, or:

```bash
curl -X POST http://localhost:8000/api/paper/step
```

Search for symbols and manage the watchlist:

```bash
curl -s 'http://localhost:8000/api/search?q=bitcoin' | python3 -m json.tool
curl -s -X POST http://localhost:8000/api/watchlist \
     -H 'Content-Type: application/json' -d '{"symbol": "SOL-USD", "name": "Solana"}' \
     | python3 -m json.tool
```

That fetches data → forecasts every watchlist symbol → derives signals → applies them to the
paper portfolio → records a snapshot.

> **Warning — read before doing anything else.** This is an educational forecasting and
> simulation project. Kronos output is a *statistical sample*, not investment advice. Results on
> historical data do not transfer to live markets. Nothing here is wired to a real broker, and it
> should stay that way until the backtest and risk controls are validated.

## Licence

MIT. Vendored Kronos code is MIT-licensed, © the Kronos authors — see `backend/vendor/kronos/LICENSE`.
