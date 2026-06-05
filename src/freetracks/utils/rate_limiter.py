"""Rate limiter for respectful API/scraping requests.

Ensures we don't hammer platforms and risk getting blocked.
Default is 2 requests per second which is conservative and polite.
"""

import asyncio
import time
from collections import deque


class RateLimiter:
    """Sliding window rate limiter for async HTTP requests."""

    def __init__(self, requests_per_second: float = 2.0):
        self.min_interval = 1.0 / requests_per_second
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until we're clear to make the next request."""
        async with self._lock:
            now = time.monotonic()

            # Clean old timestamps outside our window
            while self._timestamps and now - self._timestamps[0] > 1.0:
                self._timestamps.popleft()

            if self._timestamps:
                elapsed = now - self._timestamps[-1]
                if elapsed < self.min_interval:
                    wait_time = self.min_interval - elapsed
                    await asyncio.sleep(wait_time)

            self._timestamps.append(time.monotonic())

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass


class MultiPlatformLimiter:
    """Manages separate rate limiters per platform so one slow platform
    doesn't block others."""

    def __init__(self, default_rps: float = 2.0):
        self._limiters: dict[str, RateLimiter] = {}
        self._default_rps = default_rps

    def get(self, platform: str) -> RateLimiter:
        if platform not in self._limiters:
            self._limiters[platform] = RateLimiter(self._default_rps)
        return self._limiters[platform]

    def set_rate(self, platform: str, requests_per_second: float) -> None:
        self._limiters[platform] = RateLimiter(requests_per_second)
