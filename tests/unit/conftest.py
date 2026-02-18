"""Unit test fixtures — sample payloads and domain objects."""

from __future__ import annotations

import pytest

from src.models import FileDiff, PullRequest, Repository


@pytest.fixture
def sample_repo() -> Repository:
    return Repository(
        full_name="acme/web-app",
        installation_id=12345,
        default_branch="main",
    )


@pytest.fixture
def sample_pr(sample_repo: Repository) -> PullRequest:
    return PullRequest(
        number=42,
        title="Add login feature",
        body="Implements OAuth login flow",
        head_sha="abc123",
        base_branch="main",
        head_branch="feature/login",
        repo=sample_repo,
        author="dev-user",
        files=[
            FileDiff(
                filename="src/auth.py",
                status="added",
                patch="@@ -0,0 +1,10 @@\n+def login():\n+    pass",
                additions=10,
                deletions=0,
            ),
            FileDiff(
                filename="src/routes.py",
                status="modified",
                patch="@@ -5,3 +5,5 @@\n-# old\n+# new",
                additions=2,
                deletions=1,
            ),
        ],
    )


@pytest.fixture
def minimal_pr_payload() -> dict:
    return {
        "pull_request": {
            "number": 1,
            "title": "Test PR",
            "body": "description",
            "head": {"sha": "abc123", "ref": "feature"},
            "base": {"ref": "main"},
            "user": {"login": "dev"},
        },
        "repository": {
            "full_name": "acme/repo",
            "default_branch": "main",
        },
        "installation": {"id": 100},
    }


@pytest.fixture
def minimal_comment_payload() -> dict:
    return {
        "comment": {
            "id": 999,
            "body": "Looks good!",
            "path": "src/main.py",
            "line": 10,
            "original_line": 8,
            "diff_hunk": "@@ -1,5 +1,5 @@",
        },
        "repository": {
            "full_name": "acme/repo",
            "default_branch": "main",
        },
        "pull_request": {"number": 42},
        "installation": {"id": 100},
    }


@pytest.fixture
def minimal_installation_payload() -> dict:
    return {
        "installation": {"id": 200},
        "repositories": [
            {"full_name": "acme/repo-a"},
            {"full_name": "acme/repo-b"},
        ],
    }
