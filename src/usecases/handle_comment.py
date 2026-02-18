from __future__ import annotations

import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError

from src.agent.classifier import classify_comment
from src.agent.factory import create_comment_agent
from src.agent.retry import run_agent_with_retry
from src.db.queries import get_org_language, get_repository, save_feedback
from src.github import client as gh
from src.knowledge.store import store_evolution, store_feedback
from src.models import CommentEvent, RepoStatus, extract_org

logger = logging.getLogger(__name__)


async def handle_comment(event: CommentEvent) -> None:
    repo = event.repo

    # Only handle comments for activated repos
    record = await get_repository(repo.full_name)
    if not record or record.status != RepoStatus.ACTIVE:
        logger.info("Skipping comment %d on %s (repo not active)", event.comment_id, repo.full_name)
        return

    logger.info(
        "Handling comment %d on PR #%d in %s",
        event.comment_id,
        event.pr_number,
        repo.full_name,
    )

    # Build context for the agent
    context_parts = [f"**Developer replied to a review comment:**\n{event.body}"]
    if event.diff_hunk:
        context_parts.append(f"**Diff context:**\n```diff\n{event.diff_hunk}\n```")
    if event.path:
        context_parts.append(f"**File:** {event.path}, **Line:** {event.line}")

    # Get thread context if this is a reply
    original_comment_body = ""
    if event.in_reply_to_id:
        comments = await gh.get_review_comments(repo.installation_id, repo.full_name, event.pr_number)
        original = next((c for c in comments if c["id"] == event.in_reply_to_id), None)
        if original:
            original_comment_body = original.get("body", "")
        thread = [
            c for c in comments if c["id"] == event.in_reply_to_id or c.get("in_reply_to_id") == event.in_reply_to_id
        ]
        if thread:
            thread_text = "\n".join(f"**{c['user']['login']}:** {c['body']}" for c in thread)
            context_parts.append(f"**Thread context:**\n{thread_text}")

    # Look up org language preference
    org_language = await get_org_language(extract_org(repo.full_name))

    # Create agent and generate reply
    agent = create_comment_agent(repo.full_name, repo.installation_id, language=org_language)
    response = await run_agent_with_retry(agent, prompt="\n\n".join(context_parts))
    reply_body = response.content

    # Post reply
    try:
        await gh.reply_comment(
            repo.installation_id,
            repo.full_name,
            event.pr_number,
            event.comment_id,
            reply_body,
        )
    except (httpx.HTTPStatusError, TimeoutError):
        logger.exception("Failed to reply to comment %d on PR #%d", event.comment_id, event.pr_number)
        raise

    # Classify comment and store feedback.  Wrapped in try/except so a failure
    # here doesn't cause GitHub to retry and produce a duplicate reply.
    try:
        classification = await classify_comment(event.body)
        sentiment = classification.sentiment
        await save_feedback(repo.full_name, original_comment_body, event.body, sentiment)
        await store_feedback(repo.full_name, original_comment_body, event.body, sentiment)

        # If the developer is correcting us about patterns/architecture, store
        # that as evolution knowledge so future reviews respect it
        if classification.is_pattern_correction:
            await store_evolution(
                repo.full_name,
                f"Developer correction (from PR #{event.pr_number}):\n"
                f"File: {event.path or 'N/A'}\n"
                f"Developer said: {event.body}\n"
                f"Context: {event.diff_hunk}",
            )
            logger.info("Stored pattern correction from comment %d", event.comment_id)

        logger.info("Replied to comment %d (sentiment: %s)", event.comment_id, sentiment)
    except (httpx.HTTPStatusError, SQLAlchemyError, TimeoutError, ValueError) as exc:
        logger.exception("Failed to classify/store feedback for comment %d: %s", event.comment_id, exc)
    except Exception:
        logger.exception("Unexpected error classifying/storing feedback for comment %d", event.comment_id)
