"""GitHub REST API client with automatic retry and rate-limit handling.

All functions accept an installation_id and a repo in "owner/repo" format.
Retries are handled transparently for server errors (5xx) and rate limits (429).
"""

# mypy: disable-error-code="no-any-return"
from __future__ import annotations

import asyncio
import logging

import httpx

from src.github.auth import GITHUB_API, get_installation_token, invalidate_token
from src.models import FileDiff, Review

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_TIMEOUT = 30.0

# ── Shared HTTP client (connection pooling) ──────────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=GITHUB_API, timeout=_TIMEOUT)
    return _client


async def close_client() -> None:
    """Close the shared HTTP client (call during shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Core request helper ──────────────────────────────────────────


async def _request(
    installation_id: int,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    """Send an authenticated request to the GitHub API.

    Handles three retryable failure modes automatically:
      - 401 unauthorized   → refreshes the installation token once
      - 429 rate limits    → waits the Retry-After header value
      - 5xx server errors  → exponential backoff  (1s, 4s, 9s)
    """
    extra_headers = kwargs.pop("headers", {})
    token_refreshed = False
    client = _get_client()

    for attempt in range(_MAX_RETRIES + 1):
        token = await get_installation_token(installation_id)
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            **extra_headers,
        }

        resp = await client.request(method, path, headers=headers, **kwargs)

        # Token expired or revoked — clear cache and retry once
        if resp.status_code == 401 and not token_refreshed:
            logger.warning("Token rejected on %s %s, refreshing", method, path)
            invalidate_token(installation_id)
            token_refreshed = True
            continue

        # 2xx or 4xx (except 429) — return immediately, let the caller decide
        if resp.status_code < 500 and resp.status_code != 429:
            return resp

        # Last attempt — nothing left to retry, return as-is
        if attempt == _MAX_RETRIES:
            return resp

        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "60"))
            logger.warning("Rate limited on %s %s, waiting %ds", method, path, wait)
        else:
            wait = (attempt + 1) ** 2
            logger.warning(
                "Server error %d on %s %s, retrying in %ds",
                resp.status_code,
                method,
                path,
                wait,
            )

        await asyncio.sleep(wait)

    return resp  # type: ignore[return-value]  # unreachable, loop always returns


# ── Pagination helper ────────────────────────────────────────────


_DEFAULT_MAX_PAGES = 50


async def _paginate(
    installation_id: int,
    path: str,
    per_page: int = 100,
    extra_params: dict | None = None,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> list[dict]:
    """Fetch all pages from a paginated GitHub endpoint.

    ``max_pages`` caps the total number of requests to prevent unbounded
    pagination on very large resources (e.g. repos with thousands of files).
    """
    all_items: list[dict] = []
    page = 1
    params = extra_params or {}
    while page <= max_pages:
        resp = await _request(
            installation_id,
            "GET",
            path,
            params={"per_page": per_page, "page": page, **params},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    else:
        logger.warning("Pagination cap (%d pages) reached for %s, results truncated", max_pages, path)
    return all_items


# ── Read operations ──────────────────────────────────────────────


async def get_pr(installation_id: int, repo: str, pr_number: int) -> dict:
    resp = await _request(installation_id, "GET", f"/repos/{repo}/pulls/{pr_number}")
    resp.raise_for_status()
    return resp.json()


async def get_diff_files(installation_id: int, repo: str, pr_number: int) -> list[FileDiff]:
    """Fetch all changed files in a PR, paginated to handle large diffs."""
    raw = await _paginate(installation_id, f"/repos/{repo}/pulls/{pr_number}/files")
    return [
        FileDiff(
            filename=f["filename"],
            status=f["status"],
            patch=f.get("patch", ""),
            additions=f.get("additions", 0),
            deletions=f.get("deletions", 0),
            previous_filename=f.get("previous_filename"),
        )
        for f in raw
    ]


async def get_file_content(installation_id: int, repo: str, path: str, ref: str) -> str:
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/contents/{path}",
        params={"ref": ref},
        headers={"Accept": "application/vnd.github.raw+json"},
    )
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    return resp.text


async def get_repo_tree(installation_id: int, repo: str, ref: str = "HEAD") -> list[str]:
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/git/trees/{ref}",
        params={"recursive": "1"},
    )
    resp.raise_for_status()
    tree = resp.json().get("tree", [])
    return [item["path"] for item in tree if item["type"] == "blob"]


async def get_review_comments(installation_id: int, repo: str, pr_number: int) -> list[dict]:
    return await _paginate(installation_id, f"/repos/{repo}/pulls/{pr_number}/comments")


async def get_recent_commits(installation_id: int, repo: str, branch: str, count: int = 30) -> list[dict]:
    """Fetch recent commits on a branch."""
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/commits",
        params={"sha": branch, "per_page": count},
    )
    resp.raise_for_status()
    return resp.json()


async def get_commit_files(installation_id: int, repo: str, sha: str) -> list[str]:
    """Get the list of files changed in a specific commit."""
    resp = await _request(installation_id, "GET", f"/repos/{repo}/commits/{sha}")
    resp.raise_for_status()
    data = resp.json()
    return [f["filename"] for f in data.get("files", [])]


async def get_recent_prs(installation_id: int, repo: str, state: str = "closed", count: int = 10) -> list[dict]:
    """Fetch recently merged PRs to understand evolving patterns."""
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/pulls",
        params={"state": state, "sort": "updated", "direction": "desc", "per_page": count},
    )
    resp.raise_for_status()
    return [pr for pr in resp.json() if pr.get("merged_at")]


async def get_merged_prs_since(
    installation_id: int,
    repo: str,
    since: str,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> list[dict]:
    """Fetch merged PRs since a given ISO date, paginated.

    Unlike ``_paginate``, this needs early termination on date so it can't
    reuse the generic helper.  ``max_pages`` prevents runaway pagination on
    repos with very long histories.
    """
    all_prs: list[dict] = []
    page = 1
    while page <= max_pages:
        resp = await _request(
            installation_id,
            "GET",
            f"/repos/{repo}/pulls",
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for pr in batch:
            merged_at = pr.get("merged_at")
            if not merged_at:
                continue
            if merged_at < since:
                return all_prs
            all_prs.append(pr)
        if len(batch) < 100:
            break
        page += 1
    else:
        logger.warning(
            "Pagination cap (%d pages) reached for merged PRs on %s since %s, results truncated",
            max_pages,
            repo,
            since,
        )
    return all_prs


async def get_pr_reviews_list(installation_id: int, repo: str, pr_number: int) -> list[dict]:
    """Fetch review submissions for a PR."""
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/pulls/{pr_number}/reviews",
        params={"per_page": 100},
    )
    resp.raise_for_status()
    return resp.json()


async def get_pr_commits(installation_id: int, repo: str, pr_number: int) -> list[dict]:
    """Fetch commits on a PR branch."""
    resp = await _request(
        installation_id,
        "GET",
        f"/repos/{repo}/pulls/{pr_number}/commits",
        params={"per_page": 100},
    )
    resp.raise_for_status()
    return resp.json()


# ── Write operations ─────────────────────────────────────────────


async def update_pr_description(installation_id: int, repo: str, pr_number: int, body: str) -> dict:
    resp = await _request(
        installation_id,
        "PATCH",
        f"/repos/{repo}/pulls/{pr_number}",
        json={"body": body},
    )
    resp.raise_for_status()
    return resp.json()


async def post_review(installation_id: int, repo: str, pr_number: int, review: Review) -> dict:
    payload: dict = {
        "body": review.body,
        "event": review.event,
    }
    if review.comments:
        payload["comments"] = [
            {
                "path": c.path,
                "line": c.line,
                "side": c.side,
                "body": c.body,
            }
            for c in review.comments
        ]
    resp = await _request(
        installation_id,
        "POST",
        f"/repos/{repo}/pulls/{pr_number}/reviews",
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


async def reply_comment(installation_id: int, repo: str, pr_number: int, comment_id: int, body: str) -> dict:
    resp = await _request(
        installation_id,
        "POST",
        f"/repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
        json={"body": body},
    )
    resp.raise_for_status()
    return resp.json()
