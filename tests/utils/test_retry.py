"""Tests for retry decorator."""

import pytest

from upshot.utils.retry import retry


def test_retry_succeeds_first_try():
    call_count = 0

    @retry(max_attempts=3, base_delay=0.01)
    def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    assert succeed() == "ok"
    assert call_count == 1


def test_retry_succeeds_after_failure():
    call_count = 0

    @retry(max_attempts=3, base_delay=0.01)
    def fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    assert fail_then_succeed() == "ok"
    assert call_count == 3


def test_retry_exhausted():
    @retry(max_attempts=2, base_delay=0.01, exceptions=(ValueError,))
    def always_fail():
        raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        always_fail()
