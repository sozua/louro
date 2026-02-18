"""Integration tests for org settings API endpoints in src/api/orgs.py."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.db.queries import get_org_language, set_org_language

pytestmark = pytest.mark.integration


class TestGetOrgLanguage:
    async def test_default_for_unknown_org(self, client: AsyncClient):
        resp = await client.get("/orgs/unknown-org/language")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org"] == "unknown-org"
        assert data["language"] == "pt-BR"

    async def test_returns_stored_value(self, client: AsyncClient):
        await set_org_language("stored-org", "en-US")
        resp = await client.get("/orgs/stored-org/language")
        assert resp.status_code == 200
        assert resp.json()["language"] == "en-US"


class TestPutOrgLanguage:
    async def test_round_trip(self, client: AsyncClient):
        resp = await client.put("/orgs/rt-org/language", json={"language": "en-US"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["org"] == "rt-org"
        assert data["language"] == "en-US"

        # Verify via GET
        resp = await client.get("/orgs/rt-org/language")
        assert resp.json()["language"] == "en-US"

    async def test_upsert_updates_existing(self, client: AsyncClient):
        await client.put("/orgs/upsert-org/language", json={"language": "en-US"})
        resp = await client.put("/orgs/upsert-org/language", json={"language": "pt-BR"})
        assert resp.status_code == 200
        assert resp.json()["language"] == "pt-BR"

    async def test_unsupported_language_returns_422(self, client: AsyncClient):
        resp = await client.put("/orgs/bad-org/language", json={"language": "fr-FR"})
        assert resp.status_code == 422


class TestOrgLanguageQuery:
    async def test_get_org_language_default(self):
        lang = await get_org_language("no-such-org")
        assert lang == "pt-BR"

    async def test_set_then_get(self):
        await set_org_language("query-org", "en-US")
        lang = await get_org_language("query-org")
        assert lang == "en-US"
