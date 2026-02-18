"""Tests for agent factory in src/agent/factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import Settings

# Common valid settings kwargs
_BASE = {
    "github_app_id": "123",
    "github_private_key": "test-key",
    "github_webhook_secret": "secret",
}


class TestBuildModelForProvider:
    def test_anthropic_creates_claude(self, monkeypatch):
        settings = Settings(**{**_BASE, "anthropic_api_key": "sk-ant", "model_provider": "anthropic"})
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import _build_model_for_id

        model = _build_model_for_id("claude-opus-4-20250514")
        assert type(model).__name__ == "Claude"

    def test_bedrock_creates_aws(self, monkeypatch):
        settings = Settings(**{**_BASE, "model_provider": "bedrock", "anthropic_api_key": ""})
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import _build_model_for_id

        model = _build_model_for_id("anthropic.claude-3-sonnet")
        assert type(model).__name__ == "AwsBedrock"

    def test_gemini_creates_gemini(self, monkeypatch):
        settings = Settings(**{**_BASE, "model_provider": "gemini", "google_api_key": "gkey", "anthropic_api_key": ""})
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import _build_model_for_id

        model = _build_model_for_id("gemini-2.0-flash")
        assert type(model).__name__ == "Gemini"


class TestCreateReviewAgent:
    def test_has_knowledge(self, monkeypatch):
        settings = Settings(**{**_BASE, "anthropic_api_key": "sk-ant"})
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import create_review_agent

        with patch("src.agent.factory.get_knowledge_base") as mock_kb:
            mock_kb.return_value = MagicMock()
            agent = create_review_agent("acme/repo", 1, "HEAD")
            assert agent.knowledge is not None


class TestCreateOnboardAgent:
    def test_has_no_knowledge(self, monkeypatch):
        settings = Settings(**{**_BASE, "anthropic_api_key": "sk-ant"})
        monkeypatch.setattr("src.agent.factory.get_settings", lambda: settings)

        from src.agent.factory import create_onboard_agent

        agent = create_onboard_agent("acme/repo", 1, "main")
        assert agent.knowledge is None
