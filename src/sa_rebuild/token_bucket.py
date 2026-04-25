"""Local mirror of Keepa's token bucket — gates calls so we never overspend.

Keepa returns `tokensLeft` and `refillRate` in every response. We update from
those authoritative numbers and use the local mirror only to predict waits
between observations.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    tokens_left: int = 0
    refill_rate_per_min: float = 1.0
    last_observed_at: float = 0.0

    def update(self, tokens_left: int, refill_rate_per_min: float | None = None) -> None:
        self.tokens_left = max(0, int(tokens_left))
        if refill_rate_per_min is not None and refill_rate_per_min > 0:
            self.refill_rate_per_min = float(refill_rate_per_min)
        self.last_observed_at = time.time()

    def predicted_now(self) -> int:
        """Tokens available right now, accounting for time since last observation."""
        if self.last_observed_at == 0:
            return self.tokens_left
        elapsed_min = (time.time() - self.last_observed_at) / 60.0
        return int(self.tokens_left + elapsed_min * self.refill_rate_per_min)

    def seconds_until(self, target_tokens: int) -> float:
        """Seconds to wait until at least `target_tokens` are available."""
        have = self.predicted_now()
        if have >= target_tokens:
            return 0.0
        deficit = target_tokens - have
        return math.ceil(deficit / self.refill_rate_per_min) * 60.0

    def wait_for(self, target_tokens: int, max_wait_seconds: float) -> float:
        """Sleep until enough tokens, or return -1 if wait would exceed max.

        Returns actual seconds slept, or -1 to signal "checkpoint and exit".
        """
        wait = self.seconds_until(target_tokens)
        if wait <= 0:
            return 0.0
        if wait > max_wait_seconds:
            return -1.0
        time.sleep(wait)
        return wait
