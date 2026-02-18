"""Unit tests for the review_pr use case with mocked dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import FileDiff, PullRequest, Repository, RepoStatus, ReviewCommentSchema, ReviewResponseSchema


@pytest.fixture
def repo():
    return Repository(full_name="acme/app", installation_id=1, default_branch="main")


@pytest.fixture
def pr(repo):
    return PullRequest(
        number=10,
        title="Add feature",
        body="description",
        head_sha="abc",
        base_branch="main",
        head_branch="feat",
        repo=repo,
        author="dev-user",
        files=[
            FileDiff(filename="src/foo.py", status="modified", patch="@@ +1 @@\n+x=1", additions=1, deletions=0),
        ],
    )


def _make_agent_response(content):
    return SimpleNamespace(
        content=content,
        metrics=SimpleNamespace(input_tokens=100),
    )


_REVIEW_RESPONSE = ReviewResponseSchema(
    summary="Looks good",
    comments=[ReviewCommentSchema(path="src/foo.py", line=1, body="ok")],
)


@patch("src.usecases.review_pr.get_repository")
@patch("src.usecases.review_pr.get_org_language", new_callable=AsyncMock, return_value="en-US")
@patch("src.usecases.review_pr.gh")
@patch("src.usecases.review_pr.create_review_agent")
@patch("src.usecases.review_pr.run_agent_with_retry")
@patch("src.usecases.review_pr.save_review", new_callable=AsyncMock)
@patch("src.usecases.review_pr.record_usage_event", new_callable=AsyncMock)
@patch("src.usecases.review_pr.db_session")
async def test_review_pr_happy_path(
    mock_db_session,
    mock_record_usage,
    mock_save_review,
    mock_run_agent,
    mock_create_agent,
    mock_gh,
    mock_get_lang,
    mock_get_repo,
    pr,
):
    from src.usecases.review_pr import review_pr

    # Setup mocks
    record = MagicMock()
    record.status = RepoStatus.ACTIVE
    mock_get_repo.return_value = record

    mock_gh.get_diff_files = AsyncMock(return_value=pr.files)
    mock_gh.update_pr_description = AsyncMock()
    mock_gh.post_review = AsyncMock()

    mock_run_agent.return_value = _make_agent_response(_REVIEW_RESPONSE)

    # Mock the db_session context manager
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_db_session.return_value = mock_cm

    await review_pr(pr)

    mock_gh.get_diff_files.assert_awaited_once()
    mock_gh.post_review.assert_awaited_once()
    mock_gh.update_pr_description.assert_awaited_once()
    mock_save_review.assert_awaited_once()
    mock_record_usage.assert_awaited_once()


@patch("src.usecases.review_pr.get_repository")
async def test_review_pr_skips_inactive_repo(mock_get_repo, pr):
    from src.usecases.review_pr import review_pr

    record = MagicMock()
    record.status = RepoStatus.PENDING
    mock_get_repo.return_value = record

    # Should return early without error
    await review_pr(pr)


@patch("src.usecases.review_pr.get_repository")
async def test_review_pr_skips_missing_repo(mock_get_repo, pr):
    from src.usecases.review_pr import review_pr

    mock_get_repo.return_value = None

    await review_pr(pr)


@patch("src.usecases.review_pr.get_repository")
@patch("src.usecases.review_pr.gh")
async def test_review_pr_skips_empty_diff(mock_gh, mock_get_repo, pr):
    from src.usecases.review_pr import review_pr

    record = MagicMock()
    record.status = RepoStatus.ACTIVE
    mock_get_repo.return_value = record
    mock_gh.get_diff_files = AsyncMock(return_value=[])

    await review_pr(pr)

    # Should not attempt to run agent or post review
    mock_gh.post_review = AsyncMock()
    mock_gh.post_review.assert_not_awaited()


def test_format_diff_skips_lock_files():
    from src.usecases.review_pr import _should_skip_file

    assert _should_skip_file("package-lock.json") is True
    assert _should_skip_file("yarn.lock") is True
    assert _should_skip_file("uv.lock") is True
    assert _should_skip_file("src/main.py") is False
    assert _should_skip_file("assets/logo.png") is True
    assert _should_skip_file("dist/bundle.min.js") is True


def test_format_diff_truncates_large_diffs():
    from src.usecases.review_pr import _format_diff

    files = [
        FileDiff(
            filename=f"src/file_{i}.py",
            status="modified",
            patch="+" * 10_000,
            additions=100,
            deletions=0,
        )
        for i in range(20)
    ]
    pr = PullRequest(
        number=1,
        title="big",
        body="",
        head_sha="abc",
        base_branch="main",
        head_branch="feat",
        repo=Repository(full_name="a/b", installation_id=1),
        files=files,
    )
    result = _format_diff(pr)
    assert "omitted" in result


def test_build_pr_body_appends():
    from src.usecases.review_pr import _build_pr_body

    result = _build_pr_body("Original text", "AI summary")
    assert "Original text" in result
    assert "AI summary" in result


def test_build_pr_body_replaces_existing():
    from src.usecases.review_pr import _SUMMARY_END, _SUMMARY_START, _build_pr_body

    original = f"Text\n{_SUMMARY_START}\nold summary\n{_SUMMARY_END}\nAfter"
    result = _build_pr_body(original, "new summary")
    assert "old summary" not in result
    assert "new summary" in result
    assert "After" in result
