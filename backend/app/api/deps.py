"""FastAPI dependencies.

Services are constructed once during application startup and hung off ``app.state``; these
helpers are the only way routers reach them. Keeping construction in one place means the DB path,
CORS settings and model configuration cannot diverge between endpoints.
"""

from __future__ import annotations

from fastapi import Request

from ..services.cycle import BotCycle
from ..services.forecast import ForecastService, KronosRuntime
from ..services.market_data import MarketDataService
from ..services.paper_trading import PaperTradingEngine
from ..services.scheduler import CycleScheduler
from ..services.signals import SignalEngine
from ..store import Store


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_cycle(request: Request) -> BotCycle:
    return request.app.state.cycle


def get_scheduler(request: Request) -> CycleScheduler:
    return request.app.state.scheduler


def get_paper(request: Request) -> PaperTradingEngine:
    return request.app.state.cycle.paper


def get_forecast_service(request: Request) -> ForecastService:
    return request.app.state.cycle.forecasts


def get_runtime(request: Request) -> KronosRuntime:
    return request.app.state.cycle.forecasts.runtime


def get_signal_engine(request: Request) -> SignalEngine:
    return request.app.state.cycle.signals


def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.cycle.data
