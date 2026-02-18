"""Tests for agent factory in src/agent/factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import Settings

# Common valid settings kwargs
_BASE = {
    "github_app_id": "123",
    "github_private_key": "test-key",
    "github_webhook_secret": "secret",
    "ai_gateway_api_key": "gw-key",
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_BASE, **overrides}, _env_file=None)


class TestBuildModelForId:
    def test_returns_openai_like_with_gateway_config(self, monkeypatch):
        settings = _settings(ai_gateway_base_url="https://gw.example.com/v1")
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import _build_model_for_id

        model = _build_model_for_id("anthropic/claude-sonnet-4-5-20250929")
        assert type(model).__name__ == "OpenAILike"
        assert model.api_key == "gw-key"
        assert model.base_url == "https://gw.example.com/v1"


class TestCreateReviewAgent:
    def test_has_knowledge(self, monkeypatch):
        settings = _settings()
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import create_review_agent

        with patch("src.agent.factory.get_knowledge_base") as mock_kb:
            mock_kb.return_value = MagicMock()
            agent = create_review_agent("acme/repo", 1, "HEAD")
            assert agent.knowledge is not None


class TestCreateOnboardAgent:
    def test_has_no_knowledge(self, monkeypatch):
        settings = _settings()
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import create_onboard_agent

        agent = create_onboard_agent("acme/repo", 1, "main")
        assert agent.knowledge is None
