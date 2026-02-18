"""Integration tests for save_review and save_feedback in src/db/queries.py."""

from __future__ import annotations

import pytest

from src.db.queries import save_feedback, save_review, upsert_repository

pytestmark = pytest.mark.integration

REPO_NAME = "acme/repo"
INSTALLATION_ID = 1


@pytest.fixture(autouse=True)
async def _create_repo():
    """Ensure the parent repository exists so FK constraints are satisfied."""
    await upsert_repository(REPO_NAME, INSTALLATION_ID)


class TestSaveReview:
    async def test_correct_fields(self):
        review = await save_review(REPO_NAME, 42, "LGTM", 3)
        assert review.repo_full_name == REPO_NAME
        assert review.pr_number == 42
        assert review.body == "LGTM"
        assert review.comment_count == 3

    async def test_auto_generated_id_and_timestamp(self):
        review = await save_review(REPO_NAME, 1, "body", 0)
        assert review.id is not None
        assert review.created_at is not None


class TestSaveFeedback:
    async def test_correct_fields(self):
        fb = await save_feedback(REPO_NAME, "original", "response", "positive")
        assert fb.repo_full_name == REPO_NAME
        assert fb.original_comment == "original"
        assert fb.user_response == "response"
        assert fb.sentiment == "positive"

    async def test_default_sentiment(self):
        fb = await save_feedback(REPO_NAME, "orig", "resp")
        assert fb.sentiment == "neutral"

    async def test_auto_generated_id_and_timestamp(self):
        fb = await save_feedback(REPO_NAME, "o", "r")
        assert fb.id is not None
        assert fb.created_at is not None
