"""Small process-local fixed-window rate limiter.

The application is normally deployed as a single Flask/Gunicorn process for a
single scorekeeper. A process-local limiter is intentionally simple and has no
external dependency; for a multi-instance deployment use a shared Redis-backed
limiter instead (documented in the deployment guide).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> Decision:
        now = time.monotonic()
        with self._lock:
            started, count = self._buckets.get(key, (now, 0))
            if now - started >= window_seconds:
                started, count = now, 0
            count += 1
            self._buckets[key] = (started, count)
            remaining = max(limit - count, 0)
            retry_after = max(1, int(window_seconds - (now - started)))
            return Decision(count <= limit, remaining, retry_after)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
