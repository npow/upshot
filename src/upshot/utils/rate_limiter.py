"""Token bucket rate limiter for HTTP requests."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from urllib.parse import urlparse


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = rate  # tokens per second
        self.capacity = capacity or rate * 2
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until the requested tokens are available."""
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                wait = (tokens - self.tokens) / self.rate
            time.sleep(wait)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now


class RateLimiter:
    """Global + per-domain rate limiter."""

    def __init__(self, global_rate: float = 2.0, per_domain_rate: float = 1.0):
        self._global = TokenBucket(global_rate)
        self._per_domain: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(per_domain_rate)
        )
        self._lock = Lock()

    def acquire(self, url: str) -> None:
        """Wait for rate limit clearance for the given URL."""
        domain = urlparse(url).netloc
        self._global.acquire()
        with self._lock:
            bucket = self._per_domain[domain]
        bucket.acquire()


# Global singleton
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        from upshot.config import get_settings

        settings = get_settings()
        _rate_limiter = RateLimiter(
            global_rate=settings.extraction.requests_per_second,
            per_domain_rate=settings.extraction.per_domain_requests_per_second,
        )
    return _rate_limiter
