"""Integration tests for repos API endpoints in src/api/repos.py."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.db.queries import upsert_repository

pytestmark = pytest.mark.integration


class TestListRepos:
    async def test_empty_list(self, client: AsyncClient):
        resp = await client.get("/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repos"] == []
        assert data["total"] == 0

    async def test_populated_list(self, client: AsyncClient):
        await upsert_repository("acme/repo-a", 100)
        await upsert_repository("acme/repo-b", 200)
        resp = await client.get("/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["repos"]) == 2
        names = [r["full_name"] for r in data["repos"]]
        assert "acme/repo-a" in names
        assert "acme/repo-b" in names

    async def test_pagination(self, client: AsyncClient):
        await upsert_repository("acme/repo-a", 100)
        await upsert_repository("acme/repo-b", 200)
        await upsert_repository("acme/repo-c", 300)
        resp = await client.get("/repos?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["repos"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

        resp2 = await client.get("/repos?limit=2&offset=2")
        data2 = resp2.json()
        assert data2["total"] == 3
        assert len(data2["repos"]) == 1


class TestGetRepo:
    async def test_200(self, client: AsyncClient):
        await upsert_repository("acme/my-repo", 100, "main")
        resp = await client.get("/repos/acme/my-repo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "acme/my-repo"
        assert data["installation_id"] == 100

    async def test_404(self, client: AsyncClient):
        resp = await client.get("/repos/no/repo")
        assert resp.status_code == 404


class TestDeactivateRepo:
    async def test_sets_status_to_pending(self, client: AsyncClient):
        await upsert_repository("acme/deact", 100)
        from src.db.queries import set_repository_status

        await set_repository_status("acme/deact", "active")

        resp = await client.post("/repos/acme/deact/deactivate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"

    async def test_404_if_missing(self, client: AsyncClient):
        resp = await client.post("/repos/no/repo/deactivate")
        assert resp.status_code == 404


class TestDeleteRepo:
    async def test_204(self, client: AsyncClient):
        await upsert_repository("acme/del-repo", 100)
        resp = await client.delete("/repos/acme/del-repo")
        assert resp.status_code == 204

    async def test_404(self, client: AsyncClient):
        resp = await client.delete("/repos/no/repo")
        assert resp.status_code == 404
