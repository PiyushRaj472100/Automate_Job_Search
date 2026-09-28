"""In-memory thread-safe Job Queue decoupling discovery cycles from downstream processing."""

import logging
import threading
from collections import deque
from typing import Any

from backend.discovery.models import RawJobPosting

logger = logging.getLogger("job_intelligence.scheduler.queue")


class JobQueueManager:
    """Thread-safe Queue buffering discovered jobs for batch processing and verification."""

    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: deque[RawJobPosting | dict[str, Any]] = deque(maxlen=maxsize)
        self._lock = threading.Lock()
        self._total_enqueued = 0
        self._total_dequeued = 0

    def enqueue(self, item: RawJobPosting | dict[str, Any]) -> None:
        """Enqueue a single discovered job posting."""
        with self._lock:
            self._queue.append(item)
            self._total_enqueued += 1

    def enqueue_batch(self, items: list[RawJobPosting | dict[str, Any]]) -> int:
        """Enqueue multiple discovered job postings in a single atomic operation."""
        with self._lock:
            for item in items:
                self._queue.append(item)
            count = len(items)
            self._total_enqueued += count
            logger.debug("Enqueued batch of %d jobs. Current queue size: %d", count, len(self._queue))
            return count

    def dequeue_batch(self, batch_size: int = 50) -> list[RawJobPosting | dict[str, Any]]:
        """Pop up to `batch_size` items from the queue for pipeline processing."""
        items: list[RawJobPosting | dict[str, Any]] = []
        with self._lock:
            count = min(batch_size, len(self._queue))
            for _ in range(count):
                items.append(self._queue.popleft())
            self._total_dequeued += len(items)
        return items

    def size(self) -> int:
        """Return the current number of queued jobs awaiting processing."""
        with self._lock:
            return len(self._queue)

    def is_empty(self) -> bool:
        """Check whether the queue is currently empty."""
        with self._lock:
            return len(self._queue) == 0

    def clear(self) -> None:
        """Empty the queue."""
        with self._lock:
            self._queue.clear()

    @property
    def metrics(self) -> dict[str, int]:
        """Telemetry snapshot of queue throughput."""
        with self._lock:
            return {
                "current_size": len(self._queue),
                "total_enqueued": self._total_enqueued,
                "total_dequeued": self._total_dequeued,
            }
