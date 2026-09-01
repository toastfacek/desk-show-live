"""Spend meter (§2): wraps every fal call, refuses to submit past the cap."""
from __future__ import annotations


class SpendCapReached(Exception):
    pass


class SpendMeter:
    def __init__(self, rate_per_s: float, cap_usd: float, already_spent: float = 0.0):
        self.rate_per_s = float(rate_per_s)
        self.cap_usd = float(cap_usd)
        self.spent = float(already_spent)

    def cost_of(self, seconds: float) -> float:
        return round(seconds * self.rate_per_s, 6)

    def can_afford(self, seconds: float) -> bool:
        return self.spent + self.cost_of(seconds) <= self.cap_usd

    def authorize(self, seconds: float) -> None:
        """Call BEFORE submitting a generation. Raises past the cap."""
        if not self.can_afford(seconds):
            raise SpendCapReached(
                f"spend cap: ${self.spent:.2f} spent + ${self.cost_of(seconds):.2f} next "
                f"> ${self.cap_usd:.2f} cap"
            )

    def charge(self, seconds: float) -> tuple[float, float]:
        """Record billed output-seconds. Returns (cost, cumulative). Charged even for
        dropped/failed takes — the bill doesn't care (§5)."""
        cost = self.cost_of(seconds)
        self.spent = round(self.spent + cost, 6)
        return cost, self.spent
