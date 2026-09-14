# JaiSadguru — Kronos Forecast & Paper Trading Bot

A **free, self-hosted** forecasting and paper-trading bot. It pulls market data from
[`yfinance`](https://github.com/ranaroussi/yfinance) (no paid data feed, no API keys) and uses
[**Kronos**](https://github.com/shiyu-coder/Kronos) — the first open-source foundation model for
financial candlesticks — to forecast prices for **index stocks, gold and silver**.

Forecasts are converted into `BUY` / `SELL` / `HOLD` signals by a rule-based signal engine, and
those signals are executed against a **simulated portfolio** (virtual cash, positions, P&L,
trade log). **No real orders are ever placed and no broker credentials are required.**

## Watchlist

| Symbol   | Asset              | Class     |
| -------- | ------------------ | --------- |
| `^GSPC`  | S&P 500            | index     |
| `^NDX`   | Nasdaq 100         | index     |
| `^DJI`   | Dow Jones 30       | index     |
| `GC=F`   | Gold futures       | commodity |
| `SI=F`   | Silver futures     | commodity |

Add more symbols in `backend/app/config.py` — any ticker `yfinance` supports works.

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

### 1. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On first forecast the Kronos weights download from Hugging Face into `~/.cache/huggingface`
(~100 MB for `Kronos-small`). Set `KRONOS_MODEL=kronos-mini` in `.env` for a lighter 4.1M-param model.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

### 3. Run a bot cycle

From the dashboard click **Run cycle**, or:

```bash
curl -X POST http://localhost:8000/api/paper/step
```

That fetches data → forecasts every watchlist symbol → derives signals → applies them to the
paper portfolio → records a snapshot.

> **Warning — read before doing anything else.** This is an educational forecasting and
> simulation project. Kronos output is a *statistical sample*, not investment advice. Results on
> historical data do not transfer to live markets. Nothing here is wired to a real broker, and it
> should stay that way until the backtest and risk controls are validated.

## Licence

MIT. Vendored Kronos code is MIT-licensed, © the Kronos authors — see `backend/vendor/kronos/LICENSE`.
