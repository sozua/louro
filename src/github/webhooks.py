from __future__ import annotations

import asyncio
import contextvars
import hashlib
import hmac
import json
import logging
import uuid

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from src.config import get_settings
from src.db.queries import (
    delete_repository,
    get_repository,
    is_delivery_processed,
    mark_delivery_processed,
    track_active_user,
    upsert_repository,
)
from src.github.mappers import map_comment_event, map_installation_event, map_pr_event
from src.models import extract_org
from src.usecases.handle_comment import handle_comment
from src.usecases.review_pr import review_pr

logger = logging.getLogger(__name__)
router = APIRouter()

# Correlation ID propagated through async context for log tracing
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

_MAX_PAYLOAD_BYTES = 1_000_000  # 1 MB


def _verify_signature(payload: bytes, signature: str) -> None:
    secret = get_settings().github_webhook_secret.encode()
    expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str = Header(...),
    x_github_delivery: str = Header(""),
):
    body = await request.body()
    if len(body) > _MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    _verify_signature(body, x_hub_signature_256)

    # Set correlation ID for log tracing throughout this request
    cid = x_github_delivery or uuid.uuid4().hex[:12]
    correlation_id.set(cid)

    if x_github_delivery and await is_delivery_processed(x_github_delivery):
        logger.info("Duplicate delivery %s, skipping", x_github_delivery)
        return {"ok": True}

    payload = json.loads(body)

    # Long-running handlers (PR review, comment reply) are enqueued to the
    # durable task queue. The delivery is marked as processed in the same
    # transaction as the enqueue to guarantee atomicity.
    # Short handlers (push, installation) run inline since they're fast.
    match x_github_event:
        case "pull_request":
            await _enqueue_pr(payload, x_github_delivery)
        case "pull_request_review_comment":
            await _enqueue_review_comment(payload, x_github_delivery)
        case "push":
            if x_github_delivery:
                await mark_delivery_processed(x_github_delivery)
            try:
                await _handle_push(payload)
            except (httpx.HTTPStatusError, SQLAlchemyError, ValueError) as exc:
                logger.exception("Push handler failed: %s", exc)
        case "installation" | "installation_repositories":
            if x_github_delivery:
                await mark_delivery_processed(x_github_delivery)
            try:
                await _handle_installation(payload)
            except (httpx.HTTPStatusError, SQLAlchemyError, ValueError) as exc:
                logger.exception("Installation handler failed: %s", exc)
        case _:
            if x_github_delivery:
                await mark_delivery_processed(x_github_delivery)
            logger.debug("Ignoring event: %s", x_github_event)

    return {"ok": True}


async def _enqueue_pr(payload: dict, delivery_id: str) -> None:
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        if delivery_id:
            await mark_delivery_processed(delivery_id)
        return
    pr = map_pr_event(payload)
    logger.info("PR %s #%d on %s", action, pr.number, pr.repo.full_name)

    if delivery_id:
        await mark_delivery_processed(delivery_id)
    asyncio.create_task(review_pr(pr))


async def _enqueue_review_comment(payload: dict, delivery_id: str) -> None:
    action = payload.get("action")
    if action != "created":
        if delivery_id:
            await mark_delivery_processed(delivery_id)
        return
    # Ignore comments from bots (including our own GitHub App)
    sender = payload.get("sender", {})
    if sender.get("type") == "Bot" or sender.get("login", "").endswith("[bot]"):
        if delivery_id:
            await mark_delivery_processed(delivery_id)
        return
    event = map_comment_event(payload)

    if delivery_id:
        await mark_delivery_processed(delivery_id)
    asyncio.create_task(handle_comment(event))


async def _handle_push(payload: dict) -> None:
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    if not repo_full_name:
        return
    # Only track billing for active repos
    record = await get_repository(repo_full_name)
    if not record or record.status != "active":
        return
    org = extract_org(repo_full_name)
    commits = payload.get("commits", [])
    seen: set[str] = set()
    for commit in commits:
        username = commit.get("author", {}).get("username")
        if not username or username in seen or username.endswith("[bot]"):
            continue
        seen.add(username)
        await track_active_user(org, username)
    if seen:
        logger.info("Tracked %d active user(s) from push to %s", len(seen), repo_full_name)


async def _handle_installation(payload: dict) -> None:
    action = payload.get("action")
    if action in ("created", "added"):
        repos = map_installation_event(payload)
        for repo in repos:
            await upsert_repository(repo.full_name, repo.installation_id, repo.default_branch)
            logger.info("Registered repository %s (pending activation)", repo.full_name)
    elif action == "deleted":
        # App uninstalled — clean up all repos for this installation
        repos = map_installation_event(payload)
        for repo in repos:
            deleted = await delete_repository(repo.full_name)
            if deleted:
                logger.info("Removed repository %s (app uninstalled)", repo.full_name)
    elif action == "removed":
        # Repos removed from an existing installation
        repos = map_installation_event(payload)
        for repo in repos:
            deleted = await delete_repository(repo.full_name)
            if deleted:
                logger.info("Removed repository %s (removed from installation)", repo.full_name)
