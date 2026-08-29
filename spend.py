"""Spend meter: wraps every fal call, refuses to submit past the cap."""

from __future__ import annotations

from dataclasses import dataclass, field


class SpendCapExceeded(Exception):
    """Raised when a submit would push cumulative spend past the cap."""


@dataclass
class SpendMeter:
    cap_usd: float
    rate_per_second: dict[str, float]
    cumulative_usd: float = field(default=0.0, init=False)

    def cost_for(self, resolution: str, duration_s: float) -> float:
        rate = self.rate_per_second[resolution]
        return round(rate * duration_s, 4)

    def check(self, resolution: str, duration_s: float) -> float:
        """Raise if submitting this take would exceed the cap; else return its cost."""
        cost = self.cost_for(resolution, duration_s)
        if self.cumulative_usd + cost > self.cap_usd:
            raise SpendCapExceeded(
                f"submitting would bring spend to ${self.cumulative_usd + cost:.2f}, "
                f"cap is ${self.cap_usd:.2f}"
            )
        return cost

    def record(self, cost_usd: float) -> float:
        """Record a completed (or dropped-but-billed) take. Returns new cumulative total."""
        self.cumulative_usd = round(self.cumulative_usd + cost_usd, 4)
        return self.cumulative_usd


def from_config(config: dict) -> SpendMeter:
    spend_cfg = config["spend"]
    return SpendMeter(
        cap_usd=spend_cfg["cap_usd"],
        rate_per_second={
            "768p": spend_cfg["rate_768p"],
            "480p": spend_cfg["rate_480p"],
        },
    )
