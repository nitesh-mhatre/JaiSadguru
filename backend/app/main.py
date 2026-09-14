"""FastAPI application entrypoint.

Run it from the ``backend`` directory:

    uvicorn app.main:app --reload --port 8000

Interactive API docs are then at ``http://localhost:8000/docs``.

The vendored Kronos package lives in ``backend/vendor``, a sibling of ``backend/app``. ``vendor``
is put on ``sys.path`` here, at import time, before any request can trigger the lazy model import.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Must happen before `vendor.kronos` is imported, which `ForecastService` does lazily.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from . import __version__  # noqa: E402
from .api.routes import router  # noqa: E402
from .config import settings  # noqa: E402
from .services.cycle import BotCycle  # noqa: E402
from .services.scheduler import CycleScheduler  # noqa: E402
from .store import Store  # noqa: E402

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("jaisadguru")

DESCRIPTION = """
Free, self-hosted forecasting and **paper** trading bot.

Market data comes from `yfinance` (no keys, no paid feed) and forecasts come from
[Kronos](https://github.com/shiyu-coder/Kronos), an open-source foundation model for financial
candlesticks. Signals are executed against a simulated portfolio.

**No real orders are ever placed.** There is no broker client in this codebase, and no API keys are
required or read anywhere.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the object graph once, and tear the scheduler down cleanly on exit."""
    store = Store(settings.db_path)
    store.init_schema()
    store.ensure_account(settings.initial_capital)

    cycle = BotCycle(store, settings)
    # The scheduler always exists so manual and scheduled runs share one lock; it only
    # self-starts when SCHEDULER_ENABLED is set.
    scheduler = CycleScheduler(
        cycle,
        settings.scheduler_interval_minutes,
        enabled=settings.scheduler_enabled,
    )

    app.state.store = store
    app.state.cycle = cycle
    app.state.scheduler = scheduler

    logger.info(
        "JaiSadguru %s ready | interval=%s lookback=%d horizon=%d model=%s watchlist=%s db=%s",
        __version__,
        settings.interval,
        settings.lookback,
        settings.pred_len,
        settings.kronos_model,
        ",".join(settings.symbols),
        store.db_path,
    )
    if settings.scheduler_enabled:
        logger.warning(
            "Scheduler enabled: a cycle runs every %d minute(s)",
            settings.scheduler_interval_minutes,
        )

    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(
    title="JaiSadguru Forecast & Paper Trading API",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Point a human who opened the base URL at the docs and the dashboard."""
    return {
        "name": "JaiSadguru Forecast & Paper Trading API",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
        "dashboard": "http://localhost:5173",
    }
