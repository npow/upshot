"""Exponential backoff retry decorator."""

from __future__ import annotations

import functools
import logging
import time
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator for exponential backoff retry.

    Args:
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay between retries.
        backoff_factor: Multiplier for delay after each retry.
        exceptions: Tuple of exception types to catch and retry on.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            "Function %s failed after %d attempts: %s",
                            func.__name__,
                            max_attempts,
                            e,
                        )
                        raise
                    logger.warning(
                        "Function %s attempt %d/%d failed: %s. Retrying in %.1fs...",
                        func.__name__,
                        attempt,
                        max_attempts,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exception  # unreachable, but satisfies type checker

        return wrapper  # type: ignore[return-value]

    return decorator
