"""Generic async rate limiter.

Enforces per-second, per-minute, and per-day request caps using a simple
sliding-window counter per bucket. Used by broker adapters (starting with
Fyers) to stay within exchange/broker-imposed API rate limits, since a burst
of concurrent scans/orders could otherwise exceed a per-second cap even
though daily volume is nowhere near the ceiling.

Thread-unsafe by design (asyncio-only) — one instance is meant to be shared
at module level within a single event loop, not across processes.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Deque, Optional

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a non-blocking rate-limit check fails."""


class RateLimiter:
    """Sliding-window rate limiter supporting per-second/minute/day caps.

    All limits are optional; pass None to skip that window.
    """

    def __init__(
        self,
        per_second: Optional[int] = None,
        per_minute: Optional[int] = None,
        per_day: Optional[int] = None,
        name: str = "default",
    ):
        self.per_second = per_second
        self.per_minute = per_minute
        self.per_day = per_day
        self.name = name
        self._events: Deque[float] = deque()
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        # Keep only what's needed for the largest configured window (day).
        horizon = 86400 if self.per_day else (60 if self.per_minute else 1)
        while self._events and now - self._events[0] > horizon:
            self._events.popleft()

    def _count_within(self, now: float, seconds: float) -> int:
        return sum(1 for t in self._events if now - t <= seconds)

    def _next_free_slot(self, now: float) -> float:
        """Seconds to wait until the tightest violated window frees up."""
        wait = 0.0
        if self.per_second and self._count_within(now, 1) >= self.per_second:
            oldest = min(t for t in self._events if now - t <= 1)
            wait = max(wait, 1 - (now - oldest) + 0.01)
        if self.per_minute and self._count_within(now, 60) >= self.per_minute:
            oldest = min(t for t in self._events if now - t <= 60)
            wait = max(wait, 60 - (now - oldest) + 0.01)
        return wait

    async def acquire(self, timeout: Optional[float] = 30.0) -> None:
        """Block until a request slot is available, or raise RateLimitExceeded.

        Daily limits are never waited out (would mean sleeping for hours) —
        exceeding the daily cap raises immediately so the caller can surface
        a clear error instead of silently hanging.
        """
        start = time.monotonic()
        async with self._lock:
            while True:
                now = time.time()
                self._prune(now)

                if self.per_day and self._count_within(now, 86400) >= self.per_day:
                    raise RateLimitExceeded(
                        f"[{self.name}] daily rate limit of {self.per_day} requests reached"
                    )

                wait = self._next_free_slot(now)
                if wait <= 0:
                    self._events.append(now)
                    return

                if timeout is not None and (time.monotonic() - start) + wait > timeout:
                    raise RateLimitExceeded(
                        f"[{self.name}] rate limit wait exceeded {timeout}s timeout"
                    )

                logger.debug("[%s] rate limit hit, waiting %.2fs", self.name, wait)
                await asyncio.sleep(wait)

    def status(self) -> dict:
        now = time.time()
        self._prune(now)
        return {
            "name": self.name,
            "used_last_second": self._count_within(now, 1),
            "used_last_minute": self._count_within(now, 60),
            "used_last_day": self._count_within(now, 86400) if self.per_day else None,
            "limit_per_second": self.per_second,
            "limit_per_minute": self.per_minute,
            "limit_per_day": self.per_day,
        }
