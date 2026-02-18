from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel


class RepoStatus(StrEnum):
    PENDING = "pending"
    ONBOARDING = "onboarding"
    ACTIVE = "active"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


def extract_org(repo_full_name: str) -> str:
    """Extract the org/owner from an 'owner/repo' string."""
    if "/" not in repo_full_name:
        raise ValueError(f"Invalid repo full name (expected 'owner/repo'): {repo_full_name!r}")
    return repo_full_name.split("/")[0]


@dataclass
class Repository:
    full_name: str  # "owner/repo"
    installation_id: int
    default_branch: str = "main"


@dataclass
class FileDiff:
    filename: str
    status: str  # added, modified, removed, renamed
    patch: str = ""
    additions: int = 0
    deletions: int = 0
    previous_filename: str | None = None


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    head_sha: str
    base_branch: str
    head_branch: str
    repo: Repository
    author: str = ""
    files: list[FileDiff] = field(default_factory=list)


@dataclass
class ReviewComment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"


@dataclass
class Review:
    body: str
    event: str = "COMMENT"  # APPROVE, REQUEST_CHANGES, COMMENT
    comments: list[ReviewComment] = field(default_factory=list)


@dataclass
class CommentEvent:
    repo: Repository
    pr_number: int
    comment_id: int
    body: str
    path: str | None = None
    line: int | None = None
    in_reply_to_id: int | None = None
    diff_hunk: str = ""


# ── Structured output schemas (used by agno agents) ──────────


class ReviewCommentSchema(BaseModel):
    path: str
    line: int
    body: str


class ReviewResponseSchema(BaseModel):
    summary: str
    comments: list[ReviewCommentSchema] = []
