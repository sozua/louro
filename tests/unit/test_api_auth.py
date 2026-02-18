"""Tests for API key authentication in src/api/auth.py."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.api.auth import verify_api_key


class TestVerifyApiKey:
    async def test_empty_configured_key_allows_all(self, monkeypatch):
        monkeypatch.setattr("src.api.auth.get_settings", lambda: type("S", (), {"api_key": ""})())
        await verify_api_key(None)  # should not raise
        await verify_api_key("anything")  # should not raise

    async def test_correct_key_passes(self, monkeypatch):
        monkeypatch.setattr("src.api.auth.get_settings", lambda: type("S", (), {"api_key": "secret123"})())
        await verify_api_key("secret123")  # should not raise

    async def test_wrong_key_raises_401(self, monkeypatch):
        monkeypatch.setattr("src.api.auth.get_settings", lambda: type("S", (), {"api_key": "secret123"})())
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key("wrong")
        assert exc_info.value.status_code == 401

    async def test_missing_key_raises_401(self, monkeypatch):
        monkeypatch.setattr("src.api.auth.get_settings", lambda: type("S", (), {"api_key": "secret123"})())
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(None)
        assert exc_info.value.status_code == 401
