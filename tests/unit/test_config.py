"""Tests for config validation in src/config.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import ModelProvider, Settings

# Common valid kwargs to satisfy all validators
_VALID = {
    "github_app_id": "123",
    "github_private_key": "test-key",
    "github_webhook_secret": "secret",
    "anthropic_api_key": "sk-ant-test",
}


class TestConfigValidation:
    def test_valid_config(self):
        s = Settings(**_VALID)
        assert s.github_app_id == "123"

    def test_missing_private_key_raises(self):
        kwargs = {**_VALID, "github_private_key": "", "github_private_key_path": ""}
        with pytest.raises(ValidationError, match="GITHUB_PRIVATE_KEY"):
            Settings(**kwargs)

    def test_private_key_path_is_accepted(self):
        kwargs = {**_VALID, "github_private_key": "", "github_private_key_path": "/tmp/key.pem"}
        s = Settings(**kwargs)
        assert s.github_private_key_path == "/tmp/key.pem"

    def test_anthropic_requires_api_key(self):
        kwargs = {**_VALID, "model_provider": ModelProvider.ANTHROPIC, "anthropic_api_key": ""}
        with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
            Settings(**kwargs)

    def test_gemini_requires_api_key(self):
        kwargs = {**_VALID, "model_provider": ModelProvider.GEMINI, "google_api_key": ""}
        with pytest.raises(ValidationError, match="GOOGLE_API_KEY"):
            Settings(**kwargs)

    def test_gemini_with_key_succeeds(self):
        kwargs = {**_VALID, "model_provider": ModelProvider.GEMINI, "google_api_key": "gkey"}
        s = Settings(**kwargs)
        assert s.model_provider == ModelProvider.GEMINI

    def test_bedrock_without_api_key_succeeds(self):
        kwargs = {**_VALID, "model_provider": ModelProvider.BEDROCK, "anthropic_api_key": ""}
        s = Settings(**kwargs)
        assert s.model_provider == ModelProvider.BEDROCK


class TestPgvectorUrl:
    def test_replaces_asyncpg_with_psycopg(self):
        s = Settings(**{**_VALID, "database_url": "postgresql+asyncpg://u:p@host/db"})
        assert s.pgvector_url == "postgresql+psycopg://u:p@host/db"


class TestGetGithubPrivateKeyBytes:
    def test_from_string(self):
        s = Settings(**_VALID)
        assert s.get_github_private_key_bytes() == b"test-key"

    def test_from_file(self, tmp_path):
        key_file = tmp_path / "key.pem"
        key_file.write_bytes(b"file-key-content")
        kwargs = {**_VALID, "github_private_key": "", "github_private_key_path": str(key_file)}
        s = Settings(**kwargs)
        assert s.get_github_private_key_bytes() == b"file-key-content"
