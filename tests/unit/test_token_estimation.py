"""Tests for _estimate_tokens from src/agent/retry.py."""

from __future__ import annotations

from src.agent.retry import _CHARS_PER_TOKEN, _OVERHEAD_TOKENS, _estimate_tokens


class TestEstimateTokens:
    def test_empty_prompt(self):
        assert _estimate_tokens("") == _OVERHEAD_TOKENS

    def test_formula(self):
        prompt = "a" * 400  # 400 chars / 4 = 100 tokens
        assert _estimate_tokens(prompt) == _OVERHEAD_TOKENS + 100

    def test_short_prompt(self):
        prompt = "hello"
        expected = _OVERHEAD_TOKENS + len(prompt) // _CHARS_PER_TOKEN
        assert _estimate_tokens(prompt) == expected

    def test_long_prompt(self):
        prompt = "x" * 10_000
        assert _estimate_tokens(prompt) == _OVERHEAD_TOKENS + 2_500
