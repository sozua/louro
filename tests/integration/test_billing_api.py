"""Integration tests for billing API endpoints in src/api/billing.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from src.db.queries import (
    get_or_create_billing_period,
    record_usage_event,
    track_active_user,
)

pytestmark = pytest.mark.integration


class TestCurrentPeriod:
    async def test_404_when_no_period(self, client: AsyncClient):
        resp = await client.get("/billing/no-such-org/current")
        assert resp.status_code == 404

    async def test_200_with_correct_shape(self, client: AsyncClient):
        now = datetime.now(UTC)
        await get_or_create_billing_period("api-org", now)
        await track_active_user("api-org", "alice")
        await record_usage_event("api-org", "api-org/repo", 1, "alice")

        resp = await client.get("/billing/api-org/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org"] == "api-org"
        assert data["active_user_count"] == 1
        assert data["review_count"] == 1
        assert "period_start" in data
        assert "period_end" in data
        assert "review_quota" in data
        assert "reviews_remaining" in data
        assert "users" in data
        assert len(data["users"]) == 1
        assert data["users"][0]["github_username"] == "alice"


class TestBillingPeriods:
    async def test_list(self, client: AsyncClient):
        for month in [1, 2, 3]:
            ref = datetime(2025, month, 1, tzinfo=UTC)
            await get_or_create_billing_period("periods-org", ref)
        resp = await client.get("/billing/periods-org/periods")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_respects_limit(self, client: AsyncClient):
        for month in [1, 2, 3, 4]:
            ref = datetime(2025, month, 1, tzinfo=UTC)
            await get_or_create_billing_period("lim-api-org", ref)
        resp = await client.get("/billing/lim-api-org/periods?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestUsageEvents:
    async def test_defaults_to_current_period(self, client: AsyncClient):
        now = datetime.now(UTC)
        await get_or_create_billing_period("ue-api-org", now)
        await record_usage_event("ue-api-org", "ue-api-org/r", 1, "dev")
        resp = await client.get("/billing/ue-api-org/usage-events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["events"]) == 1

    async def test_respects_period_id(self, client: AsyncClient):
        now = datetime.now(UTC)
        await record_usage_event("pid-org", "pid-org/r", 1, "a")
        period = await get_or_create_billing_period("pid-org", now)
        resp = await client.get(f"/billing/pid-org/usage-events?period_id={period.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    async def test_respects_limit_and_offset(self, client: AsyncClient):
        now = datetime.now(UTC)
        await get_or_create_billing_period("lo-org", now)
        for i in range(5):
            await record_usage_event("lo-org", "lo-org/r", i, "dev")
        resp = await client.get("/billing/lo-org/usage-events?limit=2&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 1

    async def test_404_when_no_period(self, client: AsyncClient):
        resp = await client.get("/billing/ghost-org/usage-events")
        assert resp.status_code == 404
