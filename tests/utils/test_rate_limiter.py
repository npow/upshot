"""Tests for rate limiter."""

import time

from upshot.utils.rate_limiter import TokenBucket


def test_token_bucket_immediate():
    """Acquiring within capacity should not block."""
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    start = time.monotonic()
    bucket.acquire(1.0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


def test_token_bucket_rate_limits():
    """Acquiring more than capacity should block."""
    bucket = TokenBucket(rate=10.0, capacity=1.0)
    bucket.acquire(1.0)  # use up capacity
    start = time.monotonic()
    bucket.acquire(1.0)  # should wait ~0.1s for refill
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05  # some delay expected
