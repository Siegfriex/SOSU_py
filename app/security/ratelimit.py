"""Per-instance token bucket.

THIS IS NOT A SHARED RATE LIMIT. On Vercel every function instance has its own memory, instances
scale horizontally and are recycled, so an attacker can exceed these numbers by a large factor.
It is a cheap backstop only. The enforceable limit must live at the edge (Vercel WAF rate-limit
rule) — see docs/SECURITY.md.
"""

from __future__ import annotations

import threading
import time

_MAX_KEYS = 10_000


class TokenBucketLimiter:
    def __init__(self, per_minute: int, *, burst: int | None = None) -> None:
        self.rate = max(per_minute, 0) / 60.0
        self.capacity = float(burst if burst is not None else max(per_minute, 1))
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        if self.rate <= 0:
            return False
        t = now if now is not None else time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, t))
            tokens = min(self.capacity, tokens + (t - last) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, t)
                return False
            if len(self._buckets) >= _MAX_KEYS and key not in self._buckets:
                self._buckets.clear()  # bounded memory; resets are acceptable for a backstop
            self._buckets[key] = (tokens - 1.0, t)
            return True
