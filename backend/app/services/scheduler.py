"""Optional in-process cycle scheduler.

Runs the bot cycle on a fixed interval inside the API process, so the bot can be left running
without an external cron. Disabled by default — enable it with ``SCHEDULER_ENABLED=true``.

Two safety properties matter more than the timing itself:

1. **Cycles never overlap.** A manual ``POST /api/paper/step`` and a scheduled tick share the same
   lock, so a fast interval or an impatient click cannot start two cycles against the same book.
2. **The cycle runs off the event loop.** Fetching and inference are blocking, so the cycle is
   dispatched to a worker thread; otherwise a cycle would freeze every HTTP request, including the
   dashboard's own status polling.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

from .cycle import BotCycle, CycleResult

logger = logging.getLogger(__name__)


class CycleScheduler:
    """Owns the single lock every cycle run must pass through."""

    def __init__(self, cycle: BotCycle, interval_minutes: int, enabled: bool = False) -> None:
        self.cycle = cycle
        self.interval_minutes = max(1, interval_minutes)
        self.enabled = enabled
        self.last_run_at: str | None = None
        self.last_status: str | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ state

    @property
    def active(self) -> bool:
        """True when the background loop is currently running."""
        return self._task is not None and not self._task.done()

    @property
    def busy(self) -> bool:
        """True when a cycle is executing right now, scheduled or manual."""
        return self._lock.locked()

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self.active or not self.enabled:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="jaisadguru-cycle-scheduler")
        logger.info("Cycle scheduler started, every %d minute(s)", self.interval_minutes)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("Cycle scheduler stopped")

    # ------------------------------------------------------------------ running

    async def run_once(self, **kwargs) -> CycleResult:
        """Run one cycle under the shared lock. Blocks until any in-flight cycle finishes."""
        async with self._lock:
            # ``to_thread`` keeps blocking network and inference work off the event loop.
            result = await asyncio.to_thread(self.cycle.run, **kwargs)
            self.last_run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.last_status = result.status
            return result

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failing cycle must not kill the loop; the run row already records the failure.
                logger.exception("Scheduled cycle raised")

            # Sleep interruptibly so shutdown does not wait out the full interval.
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_minutes * 60)
