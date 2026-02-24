"""Tests for the model router, fallback provider, and budget tracker."""

from __future__ import annotations

import pytest

from harness.providers.budget import (
    BudgetExhaustedError,
    BudgetSnapshot,
    TokenBudgetTracker,
)
from harness.providers.fallback import FallbackProvider
from harness.providers.router import ModelRouter, RoutingStrategy

from tests.conftest import FailingMockProvider, MockProvider, MockTurn


# ---------------------------------------------------------------------------
# TokenBudgetTracker tests
# ---------------------------------------------------------------------------


class TestTokenBudgetTracker:
    def test_tracks_usage(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=1000, max_cost=1.0)
        snap = tracker.record_usage(input_tokens=100, output_tokens=50, cost=0.1)

        assert snap.input_tokens_used == 100
        assert snap.output_tokens_used == 50
        assert snap.total_tokens_used == 150
        assert snap.cost_used == pytest.approx(0.1)

    def test_accumulates_usage(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=1000)
        tracker.record_usage(input_tokens=100)
        tracker.record_usage(input_tokens=200)
        snap = tracker.snapshot()
        assert snap.total_tokens_used == 300

    def test_is_exhausted_by_tokens(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=100)
        tracker.record_usage(input_tokens=100)
        assert tracker.is_exhausted()

    def test_is_exhausted_by_cost(self) -> None:
        tracker = TokenBudgetTracker(max_cost=0.5)
        tracker.record_usage(cost=0.5)
        assert tracker.is_exhausted()

    def test_not_exhausted_under_limit(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=1000, max_cost=1.0)
        tracker.record_usage(input_tokens=100, cost=0.1)
        assert not tracker.is_exhausted()

    def test_unlimited_never_exhausted(self) -> None:
        tracker = TokenBudgetTracker()  # 0 = unlimited
        tracker.record_usage(input_tokens=1_000_000, cost=100.0)
        assert not tracker.is_exhausted()

    def test_check_budget_raises(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=100)
        tracker.record_usage(input_tokens=100)
        with pytest.raises(BudgetExhaustedError) as exc_info:
            tracker.check_budget()
        assert exc_info.value.snapshot.total_tokens_used == 100

    def test_reset(self) -> None:
        tracker = TokenBudgetTracker(max_tokens=100)
        tracker.record_usage(input_tokens=100)
        assert tracker.is_exhausted()
        tracker.reset()
        assert not tracker.is_exhausted()
        assert tracker.total_tokens == 0


# ---------------------------------------------------------------------------
# FallbackProvider tests
# ---------------------------------------------------------------------------


class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_primary_success(self) -> None:
        primary = MockProvider(turns=[MockTurn(text="Hello")])
        fb = FallbackProvider([primary])

        events = []
        async for event in fb.chat_completion_stream([], [], "", 100):
            events.append(event)

        assert any(e.text == "Hello" for e in events)

    @pytest.mark.asyncio
    async def test_fallback_on_connection_error(self) -> None:
        failing = FailingMockProvider(
            turns=[MockTurn(text="Should not see this")],
            fail_count=100,  # Always fail
        )
        backup = MockProvider(turns=[MockTurn(text="Backup works")])

        fb = FallbackProvider([failing, backup])

        events = []
        async for event in fb.chat_completion_stream([], [], "", 100):
            events.append(event)

        assert any(e.text == "Backup works" for e in events)

    @pytest.mark.asyncio
    async def test_all_providers_fail(self) -> None:
        fail1 = FailingMockProvider(turns=[], fail_count=100)
        fail2 = FailingMockProvider(turns=[], fail_count=100)

        fb = FallbackProvider([fail1, fail2])

        with pytest.raises(ConnectionError):
            async for _ in fb.chat_completion_stream([], [], "", 100):
                pass

    def test_requires_at_least_one_provider(self) -> None:
        with pytest.raises(ValueError):
            FallbackProvider([])

    def test_model_id_from_active(self) -> None:
        p1 = MockProvider(turns=[], model="model-a")
        p2 = MockProvider(turns=[], model="model-b")
        fb = FallbackProvider([p1, p2])
        assert fb.model_id == "model-a"

    def test_format_delegation(self) -> None:
        primary = MockProvider(turns=[])
        fb = FallbackProvider([primary])

        result = fb.format_tool_use("tu1", "Read", {"file_path": "test.py"})
        assert result["name"] == "Read"


# ---------------------------------------------------------------------------
# ModelRouter tests
# ---------------------------------------------------------------------------


class TestModelRouter:
    @pytest.mark.asyncio
    async def test_manual_passthrough(self) -> None:
        primary = MockProvider(turns=[MockTurn(text="Primary response")])
        router = ModelRouter(primary, strategy=RoutingStrategy.MANUAL)

        events = []
        async for event in router.chat_completion_stream([], [], "", 100):
            events.append(event)

        assert any(e.text == "Primary response" for e in events)

    @pytest.mark.asyncio
    async def test_cost_optimized_uses_simple_for_short_convos(self) -> None:
        primary = MockProvider(turns=[MockTurn(text="Primary")], model="primary")
        simple = MockProvider(turns=[MockTurn(text="Simple")], model="simple")

        router = ModelRouter(
            primary,
            strategy=RoutingStrategy.COST_OPTIMIZED,
            simple_task_provider=simple,
        )

        # Short conversation (<=4 messages) should use simple
        events = []
        async for event in router.chat_completion_stream(
            [{"role": "user", "content": "hi"}], [], "", 100,
        ):
            events.append(event)

        assert any(e.text == "Simple" for e in events)

    @pytest.mark.asyncio
    async def test_budget_exhaustion_raises(self) -> None:
        primary = MockProvider(turns=[MockTurn(text="Response")])
        budget = TokenBudgetTracker(max_tokens=10)
        budget.record_usage(input_tokens=10)  # Already exhausted

        router = ModelRouter(primary, budget=budget)

        with pytest.raises(BudgetExhaustedError):
            async for _ in router.chat_completion_stream([], [], "", 100):
                pass

    def test_model_id(self) -> None:
        primary = MockProvider(turns=[], model="test-model")
        router = ModelRouter(primary)
        assert router.model_id == "test-model"
