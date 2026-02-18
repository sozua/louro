"""Tests for GitHub App authentication in src/github/auth.py."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.github.auth import (
    _make_jwt,
    _token_cache,
    get_installation_token,
    invalidate_token,
    reset_token_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_token_cache()
    yield
    reset_token_cache()


class TestMakeJWT:
    def test_returns_string(self, monkeypatch):
        monkeypatch.setattr(
            "src.github.auth.get_settings",
            lambda: type(
                "S",
                (),
                {
                    "github_app_id": "12345",
                    "get_github_private_key_bytes": lambda self: _rsa_key(),
                },
            )(),
        )
        token = _make_jwt()
        assert isinstance(token, str)
        # JWT has three dot-separated parts
        assert len(token.split(".")) == 3


class TestTokenCache:
    def test_invalidate_removes_entry(self):
        _token_cache[42] = ("tok", time.time() + 9999)
        invalidate_token(42)
        assert 42 not in _token_cache

    def test_invalidate_missing_is_noop(self):
        invalidate_token(999)  # should not raise


class TestGetInstallationToken:
    async def test_returns_cached_token_when_valid(self):
        _token_cache[1] = ("cached-tok", time.time() + 600)
        token = await get_installation_token(1)
        assert token == "cached-tok"

    async def test_fetches_new_token_when_expired(self, monkeypatch):
        _token_cache[1] = ("old-tok", time.time() - 1)

        monkeypatch.setattr(
            "src.github.auth.get_settings",
            lambda: type(
                "S",
                (),
                {
                    "github_app_id": "12345",
                    "get_github_private_key_bytes": lambda self: _rsa_key(),
                },
            )(),
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"token": "new-tok"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_resp
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.github.auth.httpx.AsyncClient", return_value=mock_client_instance):
            token = await get_installation_token(1)

        assert token == "new-tok"
        assert _token_cache[1][0] == "new-tok"


def _rsa_key() -> bytes:
    """Generate a minimal RSA private key for JWT signing in tests."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
