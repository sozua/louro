from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth import verify_api_key
from src.db.queries import (
    delete_repository,
    get_repository,
    list_repositories,
    set_repository_status,
    try_transition_repository_status,
)
from src.models import Repository, RepoStatus
from src.usecases.onboard_repo import onboard_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/repos", tags=["repos"], dependencies=[Depends(verify_api_key)])


# ── Response schemas ──────────────────────────────────────────────


class RepoOut(BaseModel):
    full_name: str
    installation_id: int
    default_branch: str
    status: str
    created_at: datetime
    updated_at: datetime


class RepoListOut(BaseModel):
    repos: list[RepoOut]
    total: int
    limit: int
    offset: int


class RepoActionOut(BaseModel):
    full_name: str
    status: str
    message: str


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("", response_model=RepoListOut)
async def list_repos(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    repos, total = await list_repositories(limit=limit, offset=offset)
    return RepoListOut(
        repos=[
            RepoOut(
                full_name=r.full_name,
                installation_id=r.installation_id,
                default_branch=r.default_branch,
                status=r.status,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in repos
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{owner}/{repo}", response_model=RepoOut)
async def get_repo(owner: str, repo: str):
    full_name = f"{owner}/{repo}"
    record = await get_repository(full_name)
    if not record:
        raise HTTPException(status_code=404, detail=f"Repository {full_name} not found")
    return RepoOut(
        full_name=record.full_name,
        installation_id=record.installation_id,
        default_branch=record.default_branch,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/{owner}/{repo}/activate", response_model=RepoActionOut)
async def activate_repo(owner: str, repo: str):
    full_name = f"{owner}/{repo}"
    record = await get_repository(full_name)
    if not record:
        raise HTTPException(status_code=404, detail=f"Repository {full_name} not found")
    if record.status == RepoStatus.ACTIVE:
        return RepoActionOut(full_name=full_name, status=RepoStatus.ACTIVE, message="Already active")
    if record.status == RepoStatus.ONBOARDING:
        return RepoActionOut(full_name=full_name, status=RepoStatus.ONBOARDING, message="Onboarding in progress")

    # Atomic transition: only one request wins the race from pending -> onboarding
    transitioned = await try_transition_repository_status(full_name, RepoStatus.PENDING, RepoStatus.ONBOARDING)
    if not transitioned:
        return RepoActionOut(full_name=full_name, status=record.status, message="Onboarding already in progress")

    repo_obj = Repository(
        full_name=record.full_name,
        installation_id=record.installation_id,
        default_branch=record.default_branch,
    )
    asyncio.create_task(onboard_repo(repo_obj))

    return RepoActionOut(full_name=full_name, status=RepoStatus.ONBOARDING, message="Onboarding started")


@router.post("/{owner}/{repo}/deactivate", response_model=RepoActionOut)
async def deactivate_repo(owner: str, repo: str):
    full_name = f"{owner}/{repo}"
    record = await get_repository(full_name)
    if not record:
        raise HTTPException(status_code=404, detail=f"Repository {full_name} not found")
    if record.status == RepoStatus.PENDING:
        return RepoActionOut(full_name=full_name, status=RepoStatus.PENDING, message="Already inactive")

    await set_repository_status(full_name, RepoStatus.PENDING)
    return RepoActionOut(full_name=full_name, status=RepoStatus.PENDING, message="Deactivated")


@router.delete("/{owner}/{repo}", status_code=204)
async def remove_repo(owner: str, repo: str):
    full_name = f"{owner}/{repo}"
    deleted = await delete_repository(full_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Repository {full_name} not found")
