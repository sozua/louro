"""Tests for config validation in src/config.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings

# Common valid kwargs to satisfy all validators
_VALID = {
    "github_app_id": "123",
    "github_private_key": "test-key",
    "github_webhook_secret": "secret",
    "ai_gateway_api_key": "gw-key",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_VALID, **overrides}, _env_file=None)


class TestConfigValidation:
    def test_valid_config(self):
        s = _settings()
        assert s.github_app_id == "123"

    def test_missing_private_key_raises(self):
        with pytest.raises(ValidationError, match="GITHUB_PRIVATE_KEY"):
            _settings(github_private_key="", github_private_key_path="")

    def test_private_key_path_is_accepted(self):
        s = _settings(github_private_key="", github_private_key_path="/tmp/key.pem")
        assert s.github_private_key_path == "/tmp/key.pem"

    def test_missing_ai_gateway_api_key_raises(self):
        kwargs = {**_VALID}
        del kwargs["ai_gateway_api_key"]
        with pytest.raises(ValidationError):
            Settings(**kwargs, _env_file=None)


class TestPgvectorUrl:
    def test_replaces_asyncpg_with_psycopg(self):
        s = _settings(database_url="postgresql+asyncpg://u:p@host/db")
        assert s.pgvector_url == "postgresql+psycopg://u:p@host/db"


class TestGetGithubPrivateKeyBytes:
    def test_from_string(self):
        s = _settings()
        assert s.get_github_private_key_bytes() == b"test-key"

    def test_from_file(self, tmp_path):
        key_file = tmp_path / "key.pem"
        key_file.write_bytes(b"file-key-content")
        s = _settings(github_private_key="", github_private_key_path=str(key_file))
        assert s.get_github_private_key_bytes() == b"file-key-content"
