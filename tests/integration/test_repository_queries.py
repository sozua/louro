"""Integration tests for repository CRUD queries in src/db/queries.py."""

from __future__ import annotations

import pytest

from src.db.queries import (
    delete_repository,
    get_repository,
    list_repositories,
    set_repository_status,
    upsert_repository,
)

pytestmark = pytest.mark.integration


class TestUpsertRepository:
    async def test_creates_new(self):
        repo = await upsert_repository("acme/new-repo", 100, "main")
        assert repo.full_name == "acme/new-repo"
        assert repo.installation_id == 100
        assert repo.default_branch == "main"
        assert repo.status == "pending"
        assert repo.id is not None

    async def test_updates_existing(self):
        await upsert_repository("acme/repo", 100, "main")
        updated = await upsert_repository("acme/repo", 200, "develop")
        assert updated.installation_id == 200
        assert updated.default_branch == "develop"


class TestGetRepository:
    async def test_found(self):
        await upsert_repository("acme/found", 100)
        repo = await get_repository("acme/found")
        assert repo is not None
        assert repo.full_name == "acme/found"

    async def test_not_found(self):
        repo = await get_repository("nonexistent/repo")
        assert repo is None


class TestListRepositories:
    async def test_ordered_by_full_name(self):
        await upsert_repository("zeta/repo", 1)
        await upsert_repository("alpha/repo", 2)
        await upsert_repository("mid/repo", 3)
        repos = await list_repositories()
        names = [r.full_name for r in repos]
        assert names == sorted(names)


class TestSetRepositoryStatus:
    async def test_updates_status(self):
        await upsert_repository("acme/status-test", 100)
        result = await set_repository_status("acme/status-test", "active")
        assert result is not None
        assert result.status == "active"

    async def test_not_found_returns_none(self):
        result = await set_repository_status("nonexistent/repo", "active")
        assert result is None


class TestDeleteRepository:
    async def test_deletes_existing(self):
        await upsert_repository("acme/to-delete", 100)
        assert await delete_repository("acme/to-delete") is True
        assert await get_repository("acme/to-delete") is None

    async def test_not_found_returns_false(self):
        assert await delete_repository("nonexistent/repo") is False
