from __future__ import annotations

import time
from collections import deque


class TokenBucket:
    def __init__(self, rate: int, per_seconds: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._per_seconds = per_seconds
        self._calls: deque[float] = deque()

    def wait(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self._per_seconds:
            self._calls.popleft()

        if len(self._calls) >= self._rate:
            sleep_for = self._per_seconds - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)

        self._calls.append(time.monotonic())
