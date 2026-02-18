"""Unit tests for the handle_comment use case with mocked dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.classifier import CommentClassification
from src.models import CommentEvent, Repository, RepoStatus


@pytest.fixture
def repo():
    return Repository(full_name="acme/app", installation_id=1, default_branch="main")


@pytest.fixture
def comment_event(repo):
    return CommentEvent(
        repo=repo,
        pr_number=5,
        comment_id=100,
        body="I disagree, we use snake_case here",
        path="src/utils.py",
        line=10,
        in_reply_to_id=99,
        diff_hunk="@@ -1,5 +1,5 @@",
    )


def _make_repo_record(status: str = RepoStatus.ACTIVE):
    return SimpleNamespace(status=status)


@patch("src.usecases.handle_comment.get_repository", new_callable=AsyncMock, return_value=None)
@patch("src.usecases.handle_comment.gh")
async def test_handle_comment_skips_when_repo_not_found(mock_gh, mock_get_repo, comment_event):
    from src.usecases.handle_comment import handle_comment

    await handle_comment(comment_event)

    mock_gh.get_review_comments.assert_not_awaited() if hasattr(
        mock_gh.get_review_comments, "assert_not_awaited"
    ) else None
    mock_gh.reply_comment.assert_not_called()


@patch(
    "src.usecases.handle_comment.get_repository",
    new_callable=AsyncMock,
    return_value=_make_repo_record(RepoStatus.PENDING),
)
@patch("src.usecases.handle_comment.gh")
async def test_handle_comment_skips_when_repo_not_active(mock_gh, mock_get_repo, comment_event):
    from src.usecases.handle_comment import handle_comment

    await handle_comment(comment_event)

    mock_gh.reply_comment.assert_not_called()


def _make_response(content: str):
    return SimpleNamespace(
        content=content,
        metrics=SimpleNamespace(input_tokens=50),
    )


@patch("src.usecases.handle_comment.get_repository", new_callable=AsyncMock, return_value=_make_repo_record())
@patch("src.usecases.handle_comment.gh")
@patch("src.usecases.handle_comment.create_comment_agent")
@patch("src.usecases.handle_comment.run_agent_with_retry")
@patch("src.usecases.handle_comment.classify_comment")
@patch("src.usecases.handle_comment.save_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.store_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.store_evolution", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.get_org_language", new_callable=AsyncMock, return_value="en-US")
async def test_handle_comment_with_pattern_correction(
    mock_get_lang,
    mock_store_evolution,
    mock_store_feedback,
    mock_save_feedback,
    mock_classify,
    mock_run_agent,
    mock_create_agent,
    mock_gh,
    mock_get_repo,
    comment_event,
):
    from src.usecases.handle_comment import handle_comment

    # Thread context
    mock_gh.get_review_comments = AsyncMock(
        return_value=[
            {"id": 99, "body": "Use camelCase", "user": {"login": "louro[bot]"}},
            {"id": 100, "body": "We use snake_case", "in_reply_to_id": 99, "user": {"login": "dev"}},
        ]
    )
    mock_gh.reply_comment = AsyncMock()

    mock_run_agent.return_value = _make_response("Thanks for the clarification!")
    mock_classify.return_value = CommentClassification(sentiment="negative", is_pattern_correction=True)

    await handle_comment(comment_event)

    mock_gh.reply_comment.assert_awaited_once()
    mock_save_feedback.assert_awaited_once()
    mock_store_feedback.assert_awaited_once()
    # Pattern correction should trigger evolution storage
    mock_store_evolution.assert_awaited_once()


@patch("src.usecases.handle_comment.get_repository", new_callable=AsyncMock, return_value=_make_repo_record())
@patch("src.usecases.handle_comment.gh")
@patch("src.usecases.handle_comment.create_comment_agent")
@patch("src.usecases.handle_comment.run_agent_with_retry")
@patch("src.usecases.handle_comment.classify_comment")
@patch("src.usecases.handle_comment.save_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.store_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.store_evolution", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.get_org_language", new_callable=AsyncMock, return_value="pt-BR")
async def test_handle_comment_positive_no_evolution(
    mock_get_lang,
    mock_store_evolution,
    mock_store_feedback,
    mock_save_feedback,
    mock_classify,
    mock_run_agent,
    mock_create_agent,
    mock_gh,
    mock_get_repo,
    comment_event,
):
    from src.usecases.handle_comment import handle_comment

    mock_gh.get_review_comments = AsyncMock(return_value=[])
    mock_gh.reply_comment = AsyncMock()

    mock_run_agent.return_value = _make_response("Glad you agree!")
    mock_classify.return_value = CommentClassification(sentiment="positive", is_pattern_correction=False)

    await handle_comment(comment_event)

    mock_gh.reply_comment.assert_awaited_once()
    mock_save_feedback.assert_awaited_once()
    # Positive comment without correction should NOT store evolution
    mock_store_evolution.assert_not_awaited()


@patch("src.usecases.handle_comment.get_repository", new_callable=AsyncMock, return_value=_make_repo_record())
@patch("src.usecases.handle_comment.gh")
@patch("src.usecases.handle_comment.create_comment_agent")
@patch("src.usecases.handle_comment.run_agent_with_retry")
@patch("src.usecases.handle_comment.classify_comment")
@patch("src.usecases.handle_comment.save_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.store_feedback", new_callable=AsyncMock)
@patch("src.usecases.handle_comment.get_org_language", new_callable=AsyncMock, return_value="en-US")
async def test_handle_comment_classification_failure_does_not_crash(
    mock_get_lang,
    mock_store_feedback,
    mock_save_feedback,
    mock_classify,
    mock_run_agent,
    mock_create_agent,
    mock_gh,
    mock_get_repo,
    comment_event,
):
    from src.usecases.handle_comment import handle_comment

    mock_gh.get_review_comments = AsyncMock(return_value=[])
    mock_gh.reply_comment = AsyncMock()
    mock_run_agent.return_value = _make_response("Reply text")

    # Classification fails
    mock_classify.side_effect = RuntimeError("model down")

    # Should not raise — classification failure is non-fatal
    await handle_comment(comment_event)

    mock_gh.reply_comment.assert_awaited_once()
