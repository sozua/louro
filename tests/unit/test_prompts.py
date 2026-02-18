"""Unit tests for prompt lookup functions in src/agent/prompts.py."""

from __future__ import annotations

from src.agent.prompts import get_comment_prompt, get_review_prompt


class TestGetReviewPrompt:
    def test_pt_br_has_portuguese_labels(self):
        prompt = get_review_prompt("pt-BR")
        assert "elogio:" in prompt
        assert "sugestao:" in prompt
        assert "problema:" in prompt
        assert "(nao-bloqueante)" in prompt
        assert "(bloqueante)" in prompt
        assert "**Confianca:**" in prompt

    def test_en_us_has_english_labels(self):
        prompt = get_review_prompt("en-US")
        assert "praise:" in prompt
        assert "suggestion:" in prompt
        assert "issue:" in prompt
        assert "(non-blocking)" in prompt
        assert "(blocking)" in prompt
        assert "**Confidence:**" in prompt

    def test_unknown_language_falls_back_to_pt_br(self):
        assert get_review_prompt("fr-FR") == get_review_prompt("pt-BR")
        assert get_review_prompt("") == get_review_prompt("pt-BR")

    def test_shared_structure(self):
        pt = get_review_prompt("pt-BR")
        en = get_review_prompt("en-US")
        # Both are rendered from the same template
        assert "evolving codebases" in pt
        assert "evolving codebases" in en


class TestGetCommentPrompt:
    def test_pt_br_has_portuguese_labels(self):
        prompt = get_comment_prompt("pt-BR")
        assert "sugestao:" in prompt
        assert "problema:" in prompt

    def test_en_us_has_english_labels(self):
        prompt = get_comment_prompt("en-US")
        assert "suggestion:" in prompt
        assert "issue:" in prompt

    def test_unknown_language_falls_back_to_pt_br(self):
        assert get_comment_prompt("ja-JP") == get_comment_prompt("pt-BR")

    def test_shared_structure(self):
        pt = get_comment_prompt("pt-BR")
        en = get_comment_prompt("en-US")
        assert "Be helpful and collaborative" in pt
        assert "Be helpful and collaborative" in en
