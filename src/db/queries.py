from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete as sa_delete
from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Language
from src.db.engine import db_session
from src.db.tables import (
    BillingActiveUserRecord,
    BillingPeriodRecord,
    BillingUsageEventRecord,
    FeedbackRecord,
    OrgSettingsRecord,
    RepositoryRecord,
    ReviewRecord,
    WebhookDeliveryRecord,
)
from src.models import RepoStatus, Sentiment


@asynccontextmanager
async def _use_session(session: AsyncSession | None) -> AsyncIterator[tuple[AsyncSession, bool]]:
    """Yield ``(session, is_owner)``.

    When the caller provides a session, we yield it and let them handle commit.
    When ``None``, we create a fresh session and auto-commit on success.
    """
    if session is not None:
        yield session, False
    else:
        async with db_session() as s:
            yield s, True
            await s.commit()


async def upsert_repository(
    full_name: str,
    installation_id: int,
    default_branch: str = "main",
    *,
    session: AsyncSession | None = None,
) -> RepositoryRecord:
    async with _use_session(session) as (s, is_owner):
        result = await s.execute(select(RepositoryRecord).where(RepositoryRecord.full_name == full_name))
        repo = result.scalar_one_or_none()
        if repo:
            repo.installation_id = installation_id
            repo.default_branch = default_branch
        else:
            repo = RepositoryRecord(
                full_name=full_name,
                installation_id=installation_id,
                default_branch=default_branch,
            )
            s.add(repo)
        if is_owner:
            await s.flush()
            await s.refresh(repo)
        else:
            await s.flush()
        return repo


async def get_repository(
    full_name: str,
    *,
    session: AsyncSession | None = None,
) -> RepositoryRecord | None:
    async with _use_session(session) as (s, _):
        result = await s.execute(select(RepositoryRecord).where(RepositoryRecord.full_name == full_name))
        return result.scalar_one_or_none()


async def list_repositories(
    *,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> tuple[list[RepositoryRecord], int]:
    async with _use_session(session) as (s, _):
        total_result = await s.execute(select(sa_func.count()).select_from(RepositoryRecord))
        total = total_result.scalar_one()
        result = await s.execute(
            select(RepositoryRecord).order_by(RepositoryRecord.full_name).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total


async def set_repository_status(
    full_name: str,
    status: RepoStatus,
    *,
    session: AsyncSession | None = None,
) -> RepositoryRecord | None:
    async with _use_session(session) as (s, is_owner):
        result = await s.execute(select(RepositoryRecord).where(RepositoryRecord.full_name == full_name))
        repo = result.scalar_one_or_none()
        if repo:
            repo.status = status
            if is_owner:
                await s.flush()
                await s.refresh(repo)
            else:
                await s.flush()
        return repo


async def try_transition_repository_status(
    full_name: str,
    from_status: RepoStatus,
    to_status: RepoStatus,
    *,
    session: AsyncSession | None = None,
) -> bool:
    """Atomically transition repo status. Returns True if the row was updated."""
    async with _use_session(session) as (s, _):
        result = await s.execute(
            update(RepositoryRecord)
            .where(RepositoryRecord.full_name == full_name, RepositoryRecord.status == from_status)
            .values(status=to_status)
        )
        return result.rowcount > 0  # type: ignore[no-any-return,attr-defined]


async def delete_repository(
    full_name: str,
    *,
    session: AsyncSession | None = None,
) -> bool:
    async with _use_session(session) as (s, _):
        result = await s.execute(select(RepositoryRecord).where(RepositoryRecord.full_name == full_name))
        repo = result.scalar_one_or_none()
        if not repo:
            return False
        await s.delete(repo)

    # Clean up the per-repo knowledge vector table outside the session
    from src.knowledge.store import drop_knowledge_base

    try:
        await drop_knowledge_base(full_name)
    except Exception:
        logging.getLogger(__name__).warning("Failed to drop knowledge table for %s", full_name, exc_info=True)

    return True


async def save_review(
    repo_full_name: str,
    pr_number: int,
    body: str,
    comment_count: int,
    *,
    session: AsyncSession | None = None,
) -> ReviewRecord:
    record = ReviewRecord(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        body=body,
        comment_count=comment_count,
    )
    async with _use_session(session) as (s, is_owner):
        s.add(record)
        await s.flush()
        if is_owner:
            await s.refresh(record)
        return record


async def save_feedback(
    repo_full_name: str,
    original_comment: str,
    user_response: str,
    sentiment: str = Sentiment.NEUTRAL,
    *,
    session: AsyncSession | None = None,
) -> FeedbackRecord:
    record = FeedbackRecord(
        repo_full_name=repo_full_name,
        original_comment=original_comment,
        user_response=user_response,
        sentiment=sentiment,
    )
    async with _use_session(session) as (s, is_owner):
        s.add(record)
        await s.flush()
        if is_owner:
            await s.refresh(record)
        return record


# --- Org settings helpers ---


async def get_org_language(
    org: str,
    *,
    session: AsyncSession | None = None,
) -> str:
    async with _use_session(session) as (s, _):
        result = await s.execute(select(OrgSettingsRecord).where(OrgSettingsRecord.org == org))
        record = result.scalar_one_or_none()
        return record.language if record else Language.PT_BR


async def set_org_language(
    org: str,
    language: str,
    *,
    session: AsyncSession | None = None,
) -> OrgSettingsRecord:
    async with _use_session(session) as (s, is_owner):
        result = await s.execute(select(OrgSettingsRecord).where(OrgSettingsRecord.org == org))
        record = result.scalar_one_or_none()
        if record:
            record.language = language
        else:
            record = OrgSettingsRecord(org=org, language=language)
            s.add(record)
        if is_owner:
            await s.flush()
            await s.refresh(record)
        else:
            await s.flush()
        return record


# --- Billing helpers ---


async def get_or_create_billing_period(
    org: str,
    ref_date: datetime | None = None,
    *,
    session: AsyncSession | None = None,
) -> BillingPeriodRecord:
    if ref_date is None:
        ref_date = datetime.now(UTC)
    period_start = ref_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    async with _use_session(session) as (s, is_owner):
        result = await s.execute(
            select(BillingPeriodRecord).where(
                BillingPeriodRecord.org == org,
                BillingPeriodRecord.period_start == period_start,
            )
        )
        period = result.scalar_one_or_none()
        if period:
            return period

        period = BillingPeriodRecord(org=org, period_start=period_start, period_end=period_end)
        s.add(period)
        try:
            if is_owner:
                await s.commit()
                await s.refresh(period)
            else:
                await s.flush()
            return period
        except IntegrityError:
            await s.rollback()
            result = await s.execute(
                select(BillingPeriodRecord).where(
                    BillingPeriodRecord.org == org,
                    BillingPeriodRecord.period_start == period_start,
                )
            )
            return result.scalar_one()


async def track_active_user(
    org: str,
    github_username: str,
    *,
    session: AsyncSession | None = None,
) -> bool:
    async with _use_session(session) as (s, is_owner):
        period = await get_or_create_billing_period(org, session=s)
        result = await s.execute(
            select(BillingActiveUserRecord).where(
                BillingActiveUserRecord.billing_period_id == period.id,
                BillingActiveUserRecord.github_username == github_username,
            )
        )
        if result.scalar_one_or_none():
            return False

        user_record = BillingActiveUserRecord(billing_period_id=period.id, org=org, github_username=github_username)
        s.add(user_record)
        try:
            await s.flush()
        except IntegrityError:
            await s.rollback()
            return False

        # Increment active_user_count and recompute soft cap in same transaction
        new_count = BillingPeriodRecord.active_user_count + 1
        new_cap = new_count * BillingPeriodRecord.soft_cap_reviews_per_seat
        await s.execute(
            update(BillingPeriodRecord)
            .where(BillingPeriodRecord.id == period.id)
            .values(
                active_user_count=new_count,
                over_soft_cap=BillingPeriodRecord.review_count > new_cap,
            )
        )
        if is_owner:
            await s.commit()
        return True


async def record_usage_event(
    org: str,
    repo_full_name: str,
    pr_number: int,
    pr_author: str,
    *,
    session: AsyncSession | None = None,
) -> BillingUsageEventRecord:
    async with _use_session(session) as (s, is_owner):
        period = await get_or_create_billing_period(org, session=s)
        event = BillingUsageEventRecord(
            billing_period_id=period.id,
            org=org,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_author=pr_author,
        )
        s.add(event)
        await s.flush()
        # Increment review_count and recompute soft cap in same transaction
        new_count = BillingPeriodRecord.review_count + 1
        total_cap = BillingPeriodRecord.active_user_count * BillingPeriodRecord.soft_cap_reviews_per_seat
        await s.execute(
            update(BillingPeriodRecord)
            .where(BillingPeriodRecord.id == period.id)
            .values(
                review_count=new_count,
                over_soft_cap=new_count > total_cap,
            )
        )
        if is_owner:
            await s.refresh(event)
        return event


async def get_billing_period_by_id(
    period_id: int,
    *,
    session: AsyncSession | None = None,
) -> BillingPeriodRecord | None:
    async with _use_session(session) as (s, _):
        result = await s.execute(select(BillingPeriodRecord).where(BillingPeriodRecord.id == period_id))
        return result.scalar_one_or_none()


async def get_billing_summary(
    org: str,
    *,
    session: AsyncSession | None = None,
) -> BillingPeriodRecord | None:
    now = datetime.now(UTC)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with _use_session(session) as (s, _):
        result = await s.execute(
            select(BillingPeriodRecord).where(
                BillingPeriodRecord.org == org,
                BillingPeriodRecord.period_start == period_start,
            )
        )
        return result.scalar_one_or_none()


async def get_billing_history(
    org: str,
    limit: int = 12,
    *,
    session: AsyncSession | None = None,
) -> list[BillingPeriodRecord]:
    async with _use_session(session) as (s, _):
        result = await s.execute(
            select(BillingPeriodRecord)
            .where(BillingPeriodRecord.org == org)
            .order_by(BillingPeriodRecord.period_start.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_active_users_for_period(
    billing_period_id: int,
    *,
    session: AsyncSession | None = None,
) -> list[BillingActiveUserRecord]:
    async with _use_session(session) as (s, _):
        result = await s.execute(
            select(BillingActiveUserRecord).where(BillingActiveUserRecord.billing_period_id == billing_period_id)
        )
        return list(result.scalars().all())


async def get_usage_events_for_period(
    billing_period_id: int,
    limit: int = 50,
    offset: int = 0,
    *,
    session: AsyncSession | None = None,
) -> list[BillingUsageEventRecord]:
    async with _use_session(session) as (s, _):
        result = await s.execute(
            select(BillingUsageEventRecord)
            .where(BillingUsageEventRecord.billing_period_id == billing_period_id)
            .order_by(BillingUsageEventRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


async def count_usage_events_for_period(
    billing_period_id: int,
    *,
    session: AsyncSession | None = None,
) -> int:
    async with _use_session(session) as (s, _):
        result = await s.execute(
            select(sa_func.count())
            .select_from(BillingUsageEventRecord)
            .where(BillingUsageEventRecord.billing_period_id == billing_period_id)
        )
        return result.scalar_one()


# --- Webhook deduplication helpers ---


async def is_delivery_processed(
    delivery_id: str,
    *,
    session: AsyncSession | None = None,
) -> bool:
    async with _use_session(session) as (s, _):
        result = await s.execute(select(WebhookDeliveryRecord).where(WebhookDeliveryRecord.delivery_id == delivery_id))
        return result.scalar_one_or_none() is not None


async def mark_delivery_processed(
    delivery_id: str,
    *,
    session: AsyncSession | None = None,
) -> None:
    async with _use_session(session) as (s, _):
        record = WebhookDeliveryRecord(delivery_id=delivery_id)
        s.add(record)
        try:
            await s.flush()
        except IntegrityError:
            await s.rollback()


async def cleanup_old_deliveries(max_age_hours: int = 24) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    async with db_session() as session:
        result = await session.execute(
            sa_delete(WebhookDeliveryRecord).where(WebhookDeliveryRecord.processed_at < cutoff)
        )
        await session.commit()
        return result.rowcount  # type: ignore[no-any-return]
