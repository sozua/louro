"""Tests for GitHub API client in src/github/client.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.github.client import close_client, get_diff_files, get_file_content


@pytest.fixture(autouse=True)
async def _clean_client():
    yield
    await close_client()


class TestGetDiffFiles:
    async def test_maps_response_to_file_diffs(self, monkeypatch):
        raw = [
            {
                "filename": "src/main.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-old\n+new",
                "additions": 1,
                "deletions": 1,
            },
            {
                "filename": "README.md",
                "status": "added",
                "additions": 5,
                "deletions": 0,
            },
        ]
        with patch("src.github.client._paginate", new_callable=AsyncMock, return_value=raw):
            files = await get_diff_files(1, "owner/repo", 42)

        assert len(files) == 2
        assert files[0].filename == "src/main.py"
        assert files[0].status == "modified"
        assert files[0].additions == 1
        assert files[1].patch == ""  # missing patch defaults to ""


class TestGetFileContent:
    async def test_404_returns_empty_string(self, monkeypatch):
        resp = httpx.Response(404, request=httpx.Request("GET", "http://test"))
        with patch("src.github.client._request", new_callable=AsyncMock, return_value=resp):
            result = await get_file_content(1, "owner/repo", "missing.py", "main")
        assert result == ""

    async def test_200_returns_text(self, monkeypatch):
        resp = httpx.Response(200, text="file content", request=httpx.Request("GET", "http://test"))
        with patch("src.github.client._request", new_callable=AsyncMock, return_value=resp):
            result = await get_file_content(1, "owner/repo", "src/main.py", "main")
        assert result == "file content"
