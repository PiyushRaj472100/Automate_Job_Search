import time
import random
import functools
import logging
from typing import Callable, Any, Tuple, Type

import requests

# Import prometheus metrics if available; fallback to no‑op counters when library missing
try:
    from backend.core.metrics import RETRY_ATTEMPTS, RETRY_SUCCESS, RETRY_FAILURE
except Exception:  # pragma: no cover
    class _NoOpCounter:
        def inc(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
    RETRY_ATTEMPTS = RETRY_SUCCESS = RETRY_FAILURE = _NoOpCounter()

logger = logging.getLogger("job_intelligence.retry")

# Types of exceptions considered transient by default
_DEFAULT_TRANSIENT_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    requests.exceptions.RequestException,
)

def _is_transient_exception(exc: BaseException, transient_exceptions: Tuple[Type[BaseException], ...]) -> bool:
    """Return True if *exc* is considered transient.

    - Direct subclass of one of *transient_exceptions*.
    - HTTP‑related exceptions with status 429 or 5xx.
    """
    if isinstance(exc, transient_exceptions):
        return True
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status == 429 or (status and 500 <= status < 600):
            return True
    return False

def retry(
    attempts: int = 3,
    backoff_factor: float = 0.5,
    jitter: float = 0.1,
    transient_exceptions: Tuple[Type[BaseException], ...] = _DEFAULT_TRANSIENT_EXCEPTIONS,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to retry a function on transient errors.

    Parameters
    ----------
    attempts: int
        Maximum number of attempts (initial call + retries).
    backoff_factor: float
        Base delay in seconds; actual sleep is ``backoff_factor * 2**(attempt-1)``.
    jitter: float
        Random jitter added to each sleep to avoid thundering‑herd.
    transient_exceptions: tuple
        Exception classes that are always considered transient.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # pylint: disable=broad-except
                    RETRY_ATTEMPTS.labels(function=func.__qualname__).inc()
                    if attempt == attempts or not _is_transient_exception(exc, transient_exceptions):
                        RETRY_FAILURE.labels(function=func.__qualname__).inc()
                        logger.exception(
                            "Function %s failed on attempt %d (non-transient or out of retries)",
                            func.__qualname__,
                            attempt,
                        )
                        raise
                    sleep_time = backoff_factor * (2 ** (attempt - 1)) + random.uniform(0, jitter)
                    logger.warning(
                        "Transient error in %s (attempt %d/%d). Retrying after %.2fs. Error: %s",
                        func.__qualname__,
                        attempt,
                        attempts,
                        sleep_time,
                        exc,
                    )
                    time.sleep(sleep_time)
            raise RuntimeError("Retry logic exhausted without returning or raising")
        return wrapper
    return decorator
