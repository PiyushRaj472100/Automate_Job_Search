import logging, time
import httpx
from tenacity import (retry, retry_if_exception, stop_after_attempt,
                       wait_exponential, before_sleep_log)

log = logging.getLogger("retry")


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        s = exc.response.status_code
        return s == 429 or 500 <= s < 600
    return False  # 400/401/403/404 and validation errors are never retried


def with_retry(attempts: int = 3):
    return retry(retry=retry_if_exception(_transient), stop=stop_after_attempt(attempts),
                 wait=wait_exponential(multiplier=1, min=1, max=10),
                 before_sleep=before_sleep_log(log, logging.WARNING), reraise=True)


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown: float = 300):
        self.threshold, self.cooldown = threshold, cooldown
        self.failures, self.opened_at, self.last_error = 0, None, None

    @property
    def open(self) -> bool:
        if self.opened_at is None:
            return False
        return time.time() - self.opened_at < self.cooldown  # after cooldown: half-open

    def success(self):
        self.failures, self.opened_at, self.last_error = 0, None, None

    def failure(self, err: str):
        self.failures += 1
        self.last_error = err
        if self.failures >= self.threshold:
            self.opened_at = time.time()
