"""TokenBudgetTracker — tracks usage against budget limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BudgetSnapshot:
    """Current budget state.

    The budget tracks *total* tokens (input + output combined), so
    ``tokens_remaining`` reflects the combined limit.
    """

    input_tokens_used: int = 0
    output_tokens_used: int = 0
    total_tokens_used: int = 0
    cost_used: float = 0.0
    tokens_remaining: int = 0
    cost_remaining: float = 0.0


class BudgetExhaustedError(Exception):
    """Raised when the token or cost budget is exceeded."""

    def __init__(self, message: str, snapshot: BudgetSnapshot) -> None:
        super().__init__(message)
        self.snapshot = snapshot


class TokenBudgetTracker:
    """Tracks token usage and cost against configured limits.

    A limit of 0 means unlimited.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 0,
        max_cost: float = 0.0,
    ) -> None:
        self._max_tokens = max_tokens
        self._max_cost = max_cost
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0

    @property
    def total_tokens(self) -> int:
        return self._input_tokens + self._output_tokens

    @property
    def total_cost(self) -> float:
        return self._cost

    def record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
    ) -> BudgetSnapshot:
        """Record usage and return current budget snapshot."""
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._cost += cost
        return self.snapshot()

    def snapshot(self) -> BudgetSnapshot:
        """Return current budget state."""
        total = self._input_tokens + self._output_tokens
        tokens_remaining = max(0, self._max_tokens - total) if self._max_tokens > 0 else 0
        cost_remaining = max(0.0, self._max_cost - self._cost) if self._max_cost > 0 else 0.0

        return BudgetSnapshot(
            input_tokens_used=self._input_tokens,
            output_tokens_used=self._output_tokens,
            total_tokens_used=total,
            cost_used=self._cost,
            tokens_remaining=tokens_remaining,
            cost_remaining=cost_remaining,
        )

    def is_exhausted(self) -> bool:
        """Check if any budget limit has been exceeded."""
        total = self._input_tokens + self._output_tokens
        if self._max_tokens > 0 and total >= self._max_tokens:
            return True
        if self._max_cost > 0 and self._cost >= self._max_cost:
            return True
        return False

    def check_budget(self) -> None:
        """Raise BudgetExhaustedError if budget is exceeded."""
        if self.is_exhausted():
            snap = self.snapshot()
            parts = []
            if self._max_tokens > 0:
                parts.append(f"tokens: {snap.total_tokens_used}/{self._max_tokens}")
            if self._max_cost > 0:
                parts.append(f"cost: ${snap.cost_used:.4f}/${self._max_cost:.2f}")
            raise BudgetExhaustedError(
                f"Budget exhausted ({', '.join(parts)})", snap,
            )

    def reset(self) -> None:
        """Reset all counters."""
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost = 0.0
