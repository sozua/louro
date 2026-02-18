from __future__ import annotations

import json
import logging

import httpx

from src.agent.factory import create_review_agent
from src.agent.retry import run_agent_with_retry
from src.db.engine import db_session
from src.db.queries import get_org_language, get_repository, record_usage_event, save_review
from src.github import client as gh
from src.models import PullRequest, RepoStatus, Review, ReviewComment, ReviewResponseSchema, extract_org

logger = logging.getLogger(__name__)

_SUMMARY_START = "<!-- louro-summary-start -->"
_SUMMARY_END = "<!-- louro-summary-end -->"

# Diff size limits — prevents exceeding model context windows
_MAX_DIFF_CHARS = 100_000  # ~25k tokens

# File patterns to skip (generated/vendored/binary-like)
_SKIP_EXTENSIONS = frozenset(
    {
        ".lock",
        ".min.js",
        ".min.css",
        ".map",
        ".snap",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
    }
)

_SKIP_PATTERNS = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "composer.lock",
        "Gemfile.lock",
        "Cargo.lock",
        "go.sum",
    }
)


async def review_pr(pr: PullRequest) -> None:
    repo = pr.repo

    # Only review PRs for activated repos
    record = await get_repository(repo.full_name)
    if not record or record.status != RepoStatus.ACTIVE:
        logger.info("Skipping PR #%d on %s (repo not active)", pr.number, repo.full_name)
        return

    logger.info("Reviewing PR #%d on %s", pr.number, repo.full_name)

    # Fetch diff files
    pr.files = await gh.get_diff_files(repo.installation_id, repo.full_name, pr.number)
    if not pr.files:
        logger.info("No files changed in PR #%d, skipping", pr.number)
        return

    # Build diff text for the agent
    diff_text = _format_diff(pr)

    # Look up org language preference
    org_language = await get_org_language(extract_org(repo.full_name))

    # Create agent and run review
    agent = create_review_agent(repo.full_name, repo.installation_id, pr.head_sha, language=org_language)
    prompt = (
        f"Review this pull request:\n\n"
        f"**Title:** {pr.title}\n"
        f"**Description:** {pr.body}\n"
        f"**Branch:** {pr.head_branch} → {pr.base_branch}\n\n"
        f"**Changed files:**\n{diff_text}"
    )
    response = await run_agent_with_retry(agent, prompt=prompt)
    result = _extract_review(response.content)

    # Append the AI summary to the original PR description (preserving the author's text).
    # Non-fatal: the review can still be posted even if the description update fails
    # (e.g. due to permissions), so we log and continue.
    try:
        updated_body = _build_pr_body(pr.body, result.body)
        await gh.update_pr_description(repo.installation_id, repo.full_name, pr.number, updated_body)
    except (httpx.HTTPStatusError, TimeoutError) as exc:
        logger.warning("Failed to update PR #%d description on %s: %s", pr.number, repo.full_name, exc)

    # Post review with inline comments only
    review_for_github = Review(
        body="",
        comments=result.comments,
    )
    try:
        await gh.post_review(repo.installation_id, repo.full_name, pr.number, review_for_github)
    except (httpx.HTTPStatusError, TimeoutError):
        logger.exception("Failed to post review on PR #%d on %s", pr.number, repo.full_name)
        raise

    org = extract_org(repo.full_name)
    async with db_session() as session:
        await save_review(repo.full_name, pr.number, result.body, len(result.comments), session=session)
        await record_usage_event(org, repo.full_name, pr.number, pr.author, session=session)
        await session.commit()
    logger.info(
        "Posted review on PR #%d with %d comments",
        pr.number,
        len(result.comments),
    )


def _build_pr_body(original: str, summary: str) -> str:
    """Append (or replace) the AI summary while preserving the author's description."""
    block = f"{_SUMMARY_START}\n\n---\n\n{summary}\n\n{_SUMMARY_END}"
    if _SUMMARY_START in original:
        start = original.find(_SUMMARY_START)
        end = original.find(_SUMMARY_END)
        if start != -1 and end != -1:
            end += len(_SUMMARY_END)
            return original[:start] + block + original[end:]
        # Corrupted markers — strip the orphan start marker and append fresh
        original = original.replace(_SUMMARY_START, "").strip()
    if original.strip():
        return f"{original}\n\n{block}"
    return block


def _should_skip_file(filename: str) -> bool:
    """Skip generated, vendored, and binary files."""
    basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
    if basename in _SKIP_PATTERNS:
        return True
    lower = filename.lower()
    # Check compound extensions like .min.js, .min.css
    return any(lower.endswith(ext) for ext in _SKIP_EXTENSIONS)


def _format_diff(pr: PullRequest) -> str:
    parts: list[str] = []
    total_chars = 0
    skipped = 0
    for f in pr.files:
        if _should_skip_file(f.filename):
            skipped += 1
            continue
        if not f.patch:
            continue
        header = f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions})"
        block = f"{header}\n```diff\n{f.patch}\n```"
        if total_chars + len(block) > _MAX_DIFF_CHARS:
            remaining = len(pr.files) - len(parts) - skipped
            parts.append(f"\n*... {remaining} more file(s) omitted (diff too large)*")
            break
        parts.append(block)
        total_chars += len(block)
    if skipped:
        parts.append(f"\n*{skipped} generated/lock file(s) excluded from review.*")
    return "\n\n".join(parts)


def _extract_review(content) -> Review:
    """Convert the agent response content into a domain Review.

    When ``output_schema`` is set on the agent, *content* is already a
    ``ReviewResponseSchema`` instance.  If structured output failed for any
    reason (or a raw string slipped through), we attempt a JSON parse as a
    fallback.
    """
    if isinstance(content, ReviewResponseSchema):
        return Review(
            body=content.summary,
            comments=[ReviewComment(path=c.path, line=c.line, body=c.body) for c in content.comments],
        )

    # Fallback: try to parse a raw string as JSON
    raw = content if isinstance(content, str) else str(content)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse review response as JSON, using raw text")
        return Review(body=raw)

    comments: list[ReviewComment] = []
    for c in data.get("comments", []):
        try:
            comments.append(ReviewComment(path=c["path"], line=c["line"], body=c["body"]))
        except (KeyError, TypeError):
            logger.warning("Skipping malformed comment in review response: %s", c)
    return Review(
        body=data.get("summary", "Code review complete."),
        comments=comments,
    )
