"""Tests for classify_comment in src/agent/classifier.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.classifier import CommentClassification, classify_comment


@dataclass
class FakeModelResponse:
    content: Any = None
    parsed: Any = None


MOCK_PATH = "src.agent.classifier.build_classifier_model"


class TestClassifyComment:
    @pytest.mark.asyncio
    async def test_uses_parsed_structured_output(self):
        expected = CommentClassification(sentiment="positive", is_pattern_correction=False)
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(parsed=expected)

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("Thanks!")

        assert result == expected
        model.aresponse.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_json_text_parsing(self):
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(
            parsed=None,
            content='{"sentiment": "negative", "is_pattern_correction": true}',
        )

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("That's wrong")

        assert result.sentiment == "negative"
        assert result.is_pattern_correction is True

    @pytest.mark.asyncio
    async def test_handles_json_in_markdown_code_fence(self):
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(
            parsed=None,
            content='```json\n{"sentiment": "positive", "is_pattern_correction": false}\n```',
        )

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("Good point!")

        assert result.sentiment == "positive"
        assert result.is_pattern_correction is False

    @pytest.mark.asyncio
    async def test_returns_safe_defaults_on_api_error(self):
        model = AsyncMock()
        model.aresponse.side_effect = RuntimeError("API error")

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("some comment")

        assert result.sentiment == "neutral"
        assert result.is_pattern_correction is False

    @pytest.mark.asyncio
    async def test_returns_safe_defaults_on_empty_response(self):
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(parsed=None, content="")

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("some comment")

        assert result.sentiment == "neutral"
        assert result.is_pattern_correction is False

    @pytest.mark.asyncio
    async def test_sends_correct_message_structure(self):
        expected = CommentClassification(sentiment="neutral", is_pattern_correction=False)
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(parsed=expected)

        with patch(MOCK_PATH, return_value=model):
            await classify_comment("test body")

        call_kwargs = model.aresponse.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "test body"
        assert call_kwargs.kwargs["response_format"] is CommentClassification

    @pytest.mark.asyncio
    async def test_handles_list_content_in_response(self):
        model = AsyncMock()
        model.aresponse.return_value = FakeModelResponse(
            parsed=None,
            content=['{"sentiment": "positive",', ' "is_pattern_correction": false}'],
        )

        with patch(MOCK_PATH, return_value=model):
            result = await classify_comment("Thanks!")

        assert result.sentiment == "positive"
        assert result.is_pattern_correction is False
