from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth import verify_api_key
from src.db.queries import (
    count_usage_events_for_period,
    get_active_users_for_period,
    get_billing_history,
    get_billing_period_by_id,
    get_billing_summary,
    get_usage_events_for_period,
)

router = APIRouter(prefix="/billing", tags=["billing"], dependencies=[Depends(verify_api_key)])


# ── Response schemas ──────────────────────────────────────────────


class ActiveUserOut(BaseModel):
    github_username: str
    first_seen_at: datetime


class PeriodSummaryOut(BaseModel):
    period_id: int
    org: str
    period_start: datetime
    period_end: datetime
    active_user_count: int
    review_count: int
    review_quota: int
    reviews_remaining: int
    soft_cap_reviews_per_seat: int
    seat_price_cents: int
    total_cents: int
    over_soft_cap: bool
    users: list[ActiveUserOut]


class PeriodOut(BaseModel):
    period_id: int
    period_start: datetime
    period_end: datetime
    active_user_count: int
    review_count: int
    review_quota: int
    soft_cap_reviews_per_seat: int
    seat_price_cents: int
    total_cents: int
    over_soft_cap: bool


class UsageEventOut(BaseModel):
    id: int
    repo_full_name: str
    pr_number: int
    pr_author: str
    event_type: str
    created_at: datetime


class UsageEventsOut(BaseModel):
    events: list[UsageEventOut]
    total: int
    limit: int
    offset: int


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/{org}/current", response_model=PeriodSummaryOut)
async def current_period(org: str):
    period = await get_billing_summary(org)
    if not period:
        raise HTTPException(status_code=404, detail="No billing period found for this org")

    users = await get_active_users_for_period(period.id)
    review_quota = period.active_user_count * period.soft_cap_reviews_per_seat
    return PeriodSummaryOut(
        period_id=period.id,
        org=period.org,
        period_start=period.period_start,
        period_end=period.period_end,
        active_user_count=period.active_user_count,
        review_count=period.review_count,
        review_quota=review_quota,
        reviews_remaining=max(0, review_quota - period.review_count),
        soft_cap_reviews_per_seat=period.soft_cap_reviews_per_seat,
        seat_price_cents=period.seat_price_cents,
        total_cents=period.active_user_count * period.seat_price_cents,
        over_soft_cap=period.over_soft_cap,
        users=[
            ActiveUserOut(
                github_username=u.github_username,
                first_seen_at=u.first_seen_at,
            )
            for u in users
        ],
    )


@router.get("/{org}/periods", response_model=list[PeriodOut])
async def billing_periods(org: str, limit: int = Query(default=12, ge=1, le=120)):
    periods = await get_billing_history(org, limit=limit)
    return [
        PeriodOut(
            period_id=p.id,
            period_start=p.period_start,
            period_end=p.period_end,
            active_user_count=p.active_user_count,
            review_count=p.review_count,
            review_quota=p.active_user_count * p.soft_cap_reviews_per_seat,
            soft_cap_reviews_per_seat=p.soft_cap_reviews_per_seat,
            seat_price_cents=p.seat_price_cents,
            total_cents=p.active_user_count * p.seat_price_cents,
            over_soft_cap=p.over_soft_cap,
        )
        for p in periods
    ]


@router.get("/{org}/usage-events", response_model=UsageEventsOut)
async def usage_events(
    org: str,
    period_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    if period_id is None:
        period = await get_billing_summary(org)
        if not period:
            raise HTTPException(status_code=404, detail="No billing period found for this org")
        period_id = period.id
    else:
        period = await get_billing_period_by_id(period_id)
        if not period or period.org != org:
            raise HTTPException(status_code=404, detail="Billing period not found for this org")

    events = await get_usage_events_for_period(period_id, limit=limit, offset=offset)
    total = await count_usage_events_for_period(period_id)
    return UsageEventsOut(
        events=[
            UsageEventOut(
                id=e.id,
                repo_full_name=e.repo_full_name,
                pr_number=e.pr_number,
                pr_author=e.pr_author,
                event_type=e.event_type,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
