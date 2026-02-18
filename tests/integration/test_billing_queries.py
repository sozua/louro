"""Integration tests for billing queries in src/db/queries.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from src.db.queries import (
    count_usage_events_for_period,
    get_active_users_for_period,
    get_billing_history,
    get_billing_summary,
    get_or_create_billing_period,
    get_usage_events_for_period,
    record_usage_event,
    track_active_user,
)

pytestmark = pytest.mark.integration


class TestGetOrCreateBillingPeriod:
    async def test_creates_period(self):
        ref = datetime(2025, 3, 15, tzinfo=UTC)
        period = await get_or_create_billing_period("acme", ref)
        assert period.org == "acme"
        assert period.period_start == datetime(2025, 3, 1, tzinfo=UTC)
        assert period.period_end == datetime(2025, 4, 1, tzinfo=UTC)
        assert period.review_count == 0
        assert period.active_user_count == 0

    async def test_idempotent(self):
        ref = datetime(2025, 6, 10, tzinfo=UTC)
        p1 = await get_or_create_billing_period("acme", ref)
        p2 = await get_or_create_billing_period("acme", ref)
        assert p1.id == p2.id

    async def test_december_boundary(self):
        ref = datetime(2025, 12, 20, tzinfo=UTC)
        period = await get_or_create_billing_period("acme", ref)
        assert period.period_start == datetime(2025, 12, 1, tzinfo=UTC)
        assert period.period_end == datetime(2026, 1, 1, tzinfo=UTC)

    async def test_concurrent_race(self):
        ref = datetime(2025, 9, 5, tzinfo=UTC)
        results = await asyncio.gather(
            get_or_create_billing_period("race-org", ref),
            get_or_create_billing_period("race-org", ref),
        )
        assert results[0].id == results[1].id


class TestTrackActiveUser:
    async def test_new_user_returns_true(self):
        result = await track_active_user("acme", "user1")
        assert result is True

    async def test_duplicate_returns_false(self):
        await track_active_user("acme", "user1")
        result = await track_active_user("acme", "user1")
        assert result is False

    async def test_count_increments(self):
        now = datetime.now(UTC)
        await track_active_user("count-org", "u1")
        await track_active_user("count-org", "u2")
        await track_active_user("count-org", "u3")
        period = await get_or_create_billing_period("count-org", now)
        assert period.active_user_count == 3


class TestRecordUsageEvent:
    async def test_creates_event(self):
        event = await record_usage_event("acme", "acme/repo", 42, "dev")
        assert event.repo_full_name == "acme/repo"
        assert event.pr_number == 42
        assert event.pr_author == "dev"
        assert event.event_type == "review"
        assert event.id is not None

    async def test_increments_review_count(self):
        now = datetime.now(UTC)
        await record_usage_event("rev-org", "rev-org/r", 1, "a")
        await record_usage_event("rev-org", "rev-org/r", 2, "b")
        period = await get_or_create_billing_period("rev-org", now)
        assert period.review_count == 2

    async def test_over_soft_cap(self):
        now = datetime.now(UTC)
        # 1 user, default cap 60 reviews per seat
        await track_active_user("cap-org", "solo")
        # Record 61 events to exceed cap
        for i in range(61):
            await record_usage_event("cap-org", "cap-org/r", i, "solo")
        period = await get_or_create_billing_period("cap-org", now)
        assert period.over_soft_cap is True


class TestGetBillingSummary:
    async def test_returns_current_month(self):
        now = datetime.now(UTC)
        await get_or_create_billing_period("sum-org", now)
        summary = await get_billing_summary("sum-org")
        assert summary is not None
        assert summary.org == "sum-org"

    async def test_returns_none_when_missing(self):
        summary = await get_billing_summary("nonexistent-org")
        assert summary is None


class TestGetBillingHistory:
    async def test_descending_order(self):
        for month in [1, 3, 5]:
            ref = datetime(2025, month, 1, tzinfo=UTC)
            await get_or_create_billing_period("hist-org", ref)
        periods = await get_billing_history("hist-org")
        starts = [p.period_start for p in periods]
        assert starts == sorted(starts, reverse=True)

    async def test_respects_limit(self):
        for month in range(1, 6):
            ref = datetime(2025, month, 1, tzinfo=UTC)
            await get_or_create_billing_period("lim-org", ref)
        periods = await get_billing_history("lim-org", limit=2)
        assert len(periods) == 2


class TestGetActiveUsersForPeriod:
    async def test_correct_filtering(self):
        now = datetime.now(UTC)
        await track_active_user("au-org", "alice")
        await track_active_user("au-org", "bob")
        period = await get_or_create_billing_period("au-org", now)
        users = await get_active_users_for_period(period.id)
        usernames = {u.github_username for u in users}
        assert usernames == {"alice", "bob"}


class TestGetUsageEventsForPeriod:
    async def test_correct_filtering(self):
        now = datetime.now(UTC)
        await record_usage_event("ue-org", "ue-org/r", 1, "dev")
        await record_usage_event("ue-org", "ue-org/r", 2, "dev")
        period = await get_or_create_billing_period("ue-org", now)
        events = await get_usage_events_for_period(period.id)
        assert len(events) == 2


class TestCountUsageEventsForPeriod:
    async def test_correct_count(self):
        now = datetime.now(UTC)
        await record_usage_event("cnt-org", "cnt-org/r", 1, "a")
        await record_usage_event("cnt-org", "cnt-org/r", 2, "b")
        await record_usage_event("cnt-org", "cnt-org/r", 3, "c")
        period = await get_or_create_billing_period("cnt-org", now)
        count = await count_usage_events_for_period(period.id)
        assert count == 3
