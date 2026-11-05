"""WP-423: bounded exponential backoff, jitter and provider cooldowns.

Deterministic by construction: the jitter source is an injectable ``random.Random``
so tests can assert exact delays. ``retry_after`` always wins over computed
backoff, and a cooldown is a hard gate — the orchestrator will not call a provider
whose cooldown has not elapsed.
"""

import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff: ``min(cap, base * factor**attempt)``."""

    max_attempts: int = 3
    base_seconds: float = 1.0
    factor: float = 2.0
    cap_seconds: float = 60.0
    jitter_ratio: float = 0.25

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_seconds < 0 or self.cap_seconds < 0:
            raise ValueError("delays must be >= 0")
        if not 0.0 <= self.jitter_ratio < 1.0:
            raise ValueError("jitter_ratio must be in [0, 1)")

    def raw_delay(self, attempt: int) -> float:
        """Delay for a 1-based attempt number, before jitter."""
        attempt = max(1, int(attempt))
        delay = self.base_seconds * (self.factor ** (attempt - 1))
        return min(self.cap_seconds, delay)

    def delay_for(
        self,
        attempt: int,
        retry_after: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> float:
        if retry_after is not None:
            return max(0.0, float(retry_after))
        base = self.raw_delay(attempt)
        if base <= 0 or self.jitter_ratio == 0:
            return base
        rng = rng or random.Random()
        spread = base * self.jitter_ratio
        return max(0.0, base + rng.uniform(-spread, spread))

    def can_retry(self, attempt: int) -> bool:
        return 1 <= attempt < self.max_attempts


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date).

    Returns seconds to wait, or ``None`` when absent/unparseable.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None
        now = time.time() if now is None else now
        return max(0.0, dt.timestamp() - now)
    except Exception:
        return None


class CooldownGate:
    """Hard gate on a provider's availability window, persisted by the caller."""

    def __init__(self, clock=None):
        self._clock = clock or time.time

    def is_open(self, cooldown_until: Optional[float]) -> bool:
        """True when the provider may be called."""
        if not cooldown_until:
            return True
        return self._clock() >= float(cooldown_until)

    def remaining(self, cooldown_until: Optional[float]) -> float:
        if not cooldown_until:
            return 0.0
        return max(0.0, float(cooldown_until) - self._clock())

    def until(self, delay_seconds: float) -> float:
        return self._clock() + max(0.0, float(delay_seconds))


class RetryBudget:
    """Bounded attempt counter for one unit of work (e.g. one delivery)."""

    def __init__(self, policy: RetryPolicy, used: int = 0):
        self.policy = policy
        self.used = int(used)

    @property
    def remaining(self) -> int:
        return max(0, self.policy.max_attempts - self.used)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    def consume(self) -> int:
        if self.exhausted:
            raise RuntimeError("retry budget exhausted")
        self.used += 1
        return self.used

    def to_dict(self) -> dict:
        return {
            "max_attempts": self.policy.max_attempts,
            "used": self.used,
            "remaining": self.remaining,
            "exhausted": self.exhausted,
        }
