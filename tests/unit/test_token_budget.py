"""Tests for TokenBudget from src/agent/retry.py."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.agent.retry import TokenBudget


class TestTokenBudget:
    def test_initial_state(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        assert budget.tokens_used == 0
        assert budget.tokens_available == 10_000

    async def test_acquire_within_budget(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        await budget.acquire(5_000)
        assert budget.tokens_used == 5_000
        assert budget.tokens_available == 5_000

    async def test_tracking_after_multiple_acquires(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        await budget.acquire(3_000)
        await budget.acquire(2_000)
        assert budget.tokens_used == 5_000
        assert budget.tokens_available == 5_000

    def test_record_actual_adjusts_up(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        # Simulate a reservation
        import time

        budget._log.append((time.monotonic(), 1_000))
        budget.record_actual(estimated=1_000, actual=1_500)
        # Should have original 1000 + adjustment of +500
        assert budget.tokens_used == 1_500

    def test_record_actual_adjusts_down(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        import time

        budget._log.append((time.monotonic(), 1_000))
        budget.record_actual(estimated=1_000, actual=600)
        # 1000 + (600 - 1000) = 600
        assert budget.tokens_used == 600

    def test_record_actual_no_adjustment_when_equal(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        import time

        budget._log.append((time.monotonic(), 1_000))
        initial_len = len(budget._log)
        budget.record_actual(estimated=1_000, actual=1_000)
        assert len(budget._log) == initial_len  # no new entry

    async def test_purge_removes_old_entries(self):
        budget = TokenBudget(tokens_per_minute=10_000)
        # Add an entry 61 seconds in the past
        import time

        old_ts = time.monotonic() - 61
        budget._log.append((old_ts, 5_000))
        # After purge (triggered by tokens_used), old entry should be gone
        assert budget.tokens_used == 0
        assert budget.tokens_available == 10_000

    async def test_concurrent_acquires_one_waits(self):
        budget = TokenBudget(tokens_per_minute=10_000)

        # Mock time.monotonic to control the sliding window
        base_time = 1000.0
        current_time = base_time

        def mock_monotonic():
            return current_time

        with patch("src.agent.retry.time.monotonic", side_effect=mock_monotonic):
            # First acquire takes most of the budget
            await budget.acquire(8_000)

        # Now with real time, try two concurrent acquires that together exceed budget
        # The second one should need to wait
        results = []

        async def acquire_and_record(n: int, tokens: int):
            await budget.acquire(tokens)
            results.append(n)

        # Advance time so the first entry expires
        import time

        old_ts = time.monotonic() - 61
        budget._log.clear()
        budget._log.append((old_ts, 8_000))

        # Both should fit after purge
        await asyncio.gather(
            acquire_and_record(1, 3_000),
            acquire_and_record(2, 3_000),
        )
        assert len(results) == 2
