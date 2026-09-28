"""Source-specific rate limiting and exponential backoff retry management."""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("job_intelligence.scheduler.rate_limiter")


class SourceExhaustedError(Exception):
    """Raised when a job source repeatedly fails and all retry attempts are exhausted."""

    def __init__(self, source_name: str, attempts: int, last_error: Exception) -> None:
        self.source_name = source_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Source '{source_name}' repeatedly failed after {attempts} attempts. Last error: {last_error}"
        )


class SourceRateLimiter:
    """Enforces strict source-specific rate limits and handles exponential backoff retries.

    Guarantees:
    - Never exceeds configured requests-per-minute for any source.
    - Prevents unrestricted web crawling.
    - Isolates failures so one failing source does not halt the entire pipeline.
    """

    def __init__(
        self,
        rate_limits: dict[str, int] | None = None,
        default_rate_limit: int = 20,
    ) -> None:
        self._rate_limits = rate_limits or {}
        self._default_rate_limit = default_rate_limit
        self._request_history: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def get_rate_limit(self, source_name: str) -> int:
        """Return requests permitted per minute for the specified source."""
        return self._rate_limits.get(source_name.lower(), self._default_rate_limit)

    def set_rate_limit(self, source_name: str, limit_per_minute: int) -> None:
        """Dynamically update rate limit for a source."""
        with self._lock:
            self._rate_limits[source_name.lower()] = max(1, limit_per_minute)

    def acquire(self, source_name: str) -> float:
        """Acquire permission to execute a request against the source.

        Sleeps if necessary to stay within the source's rate limit window (sliding 60s).
        Returns the duration waited in seconds.
        """
        src = source_name.lower()
        limit = self.get_rate_limit(src)
        waited = 0.0

        with self._lock:
            if src not in self._request_history:
                self._request_history[src] = deque()

            history = self._request_history[src]
            now = time.time()
            cutoff = now - 60.0

            # Discard timestamps outside the 60s sliding window
            while history and history[0] < cutoff:
                history.popleft()

            if len(history) >= limit:
                oldest = history[0]
                sleep_needed = (oldest + 60.0) - now
                if sleep_needed > 0:
                    waited = sleep_needed

        if waited > 0:
            logger.debug(
                "Source '%s' rate limit (%d/min) reached. Pausing for %.2fs",
                src,
                limit,
                waited,
            )
            time.sleep(waited)

        with self._lock:
            self._request_history[src].append(time.time())

        return waited

    def execute_with_retry(
        self,
        source_name: str,
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        **kwargs: Any,
    ) -> tuple[Any, int]:
        """Execute a source query function respecting rate limits and exponential backoff retry.

        Args:
            source_name: Name of the job source.
            func: Callable that executes the source operation.
            max_retries: Number of retry attempts before marking source failure.
            backoff_base_seconds: Base delay multiplier (delay = base * 2^attempt).

        Returns:
            Tuple of (result, retries_attempted).

        Raises:
            SourceExhaustedError if all retry attempts fail.
        """
        attempt = 0
        last_exception: Exception | None = None

        while attempt <= max_retries:
            # Always throttle according to source policy
            self.acquire(source_name)

            try:
                result = func(*args, **kwargs)
                return result, attempt
            except Exception as exc:
                last_exception = exc
                attempt += 1

                if attempt > max_retries:
                    logger.error(
                        "Source '%s' exhausted all %d retry attempts. Final error: %s",
                        source_name,
                        max_retries,
                        exc,
                    )
                    break

                backoff_delay = backoff_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Source '%s' failed on attempt %d/%d (%s). Retrying with backoff in %.2fs...",
                    source_name,
                    attempt,
                    max_retries,
                    exc,
                    backoff_delay,
                )
                time.sleep(backoff_delay)

        raise SourceExhaustedError(
            source_name=source_name,
            attempts=attempt,
            last_error=last_exception or RuntimeError("Unknown source failure"),
        )
