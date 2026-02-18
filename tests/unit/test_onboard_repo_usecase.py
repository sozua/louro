"""Unit tests for the onboard_repo use case with mocked dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Repository, RepoStatus


@pytest.fixture
def repo():
    return Repository(full_name="acme/app", installation_id=1, default_branch="main")


def _make_response(content: str):
    return SimpleNamespace(
        content=content,
        metrics=SimpleNamespace(input_tokens=200),
    )


@patch("src.usecases.onboard_repo.set_repository_status", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.upsert_repository", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.gh")
@patch("src.usecases.onboard_repo.create_onboard_agent")
@patch("src.usecases.onboard_repo.create_evolution_agent")
@patch("src.usecases.onboard_repo.run_agent_with_retry")
@patch("src.usecases.onboard_repo.store_onboarding", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.store_evolution", new_callable=AsyncMock)
async def test_onboard_repo_happy_path(
    mock_store_evolution,
    mock_store_onboarding,
    mock_run_agent,
    mock_create_evolution,
    mock_create_onboard,
    mock_gh,
    mock_upsert,
    mock_set_status,
    repo,
):
    from src.usecases.onboard_repo import onboard_repo

    mock_gh.get_repo_tree = AsyncMock(return_value=["src/main.py", "pyproject.toml", "README.md"])
    mock_gh.get_file_content = AsyncMock(return_value="file content here")
    mock_gh.get_recent_commits = AsyncMock(
        return_value=[{"sha": "aaa"}, {"sha": "bbb"}],
    )
    mock_gh.get_commit_files = AsyncMock(return_value=["src/main.py"])
    mock_gh.get_recent_prs = AsyncMock(return_value=[{"number": 1, "title": "First PR"}])

    mock_run_agent.return_value = _make_response("Analysis complete")

    await onboard_repo(repo)

    mock_upsert.assert_awaited_once()
    mock_store_onboarding.assert_awaited_once()
    mock_store_evolution.assert_awaited_once()
    mock_set_status.assert_awaited_once_with("acme/app", RepoStatus.ACTIVE)


@patch("src.usecases.onboard_repo.set_repository_status", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.upsert_repository", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.gh")
async def test_onboard_repo_tree_failure_raises(mock_gh, mock_upsert, mock_set_status, repo):
    from src.usecases.onboard_repo import onboard_repo

    mock_gh.get_repo_tree = AsyncMock(side_effect=RuntimeError("API error"))

    with pytest.raises(RuntimeError, match="API error"):
        await onboard_repo(repo)

    mock_set_status.assert_awaited_once_with("acme/app", RepoStatus.PENDING)


@patch("src.usecases.onboard_repo.set_repository_status", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.upsert_repository", new_callable=AsyncMock)
@patch("src.usecases.onboard_repo.gh")
@patch("src.usecases.onboard_repo.create_onboard_agent")
@patch("src.usecases.onboard_repo.run_agent_with_retry")
@patch("src.usecases.onboard_repo.store_onboarding", new_callable=AsyncMock)
async def test_onboard_repo_no_recent_files_skips_evolution(
    mock_store_onboarding,
    mock_run_agent,
    mock_create_onboard,
    mock_gh,
    mock_upsert,
    mock_set_status,
    repo,
):
    from src.usecases.onboard_repo import onboard_repo

    mock_gh.get_repo_tree = AsyncMock(return_value=["README.md"])
    mock_gh.get_file_content = AsyncMock(return_value="content")
    mock_gh.get_recent_commits = AsyncMock(return_value=[])

    mock_run_agent.return_value = _make_response("Analysis")

    with patch("src.usecases.onboard_repo.store_evolution", new_callable=AsyncMock) as mock_store_evolution:
        await onboard_repo(repo)
        # No recent files = no evolution analysis
        mock_store_evolution.assert_not_awaited()


def test_is_code_file():
    from src.usecases.onboard_repo import _is_code_file

    assert _is_code_file("src/main.py") is True
    assert _is_code_file("src/app.ts") is True
    assert _is_code_file("src/index.jsx") is True
    assert _is_code_file("README.md") is False
    assert _is_code_file("Makefile") is False
    assert _is_code_file("data.json") is False
