from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.models import RepoStatus, Sentiment


class Base(DeclarativeBase):
    pass


class RepositoryRecord(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    installation_id: Mapped[int] = mapped_column(Integer)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    status: Mapped[str] = mapped_column(String(20), default=RepoStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewRecord(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_reviews_repo_pr", "repo_full_name", "pr_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(
        String(255), ForeignKey("repositories.full_name", ondelete="CASCADE"), index=True
    )
    pr_number: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(
        String(255), ForeignKey("repositories.full_name", ondelete="CASCADE"), index=True
    )
    original_comment: Mapped[str] = mapped_column(Text)
    user_response: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str] = mapped_column(String(20), default=Sentiment.NEUTRAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrgSettingsRecord(Base):
    __tablename__ = "org_settings"

    org: Mapped[str] = mapped_column(String(255), primary_key=True)
    language: Mapped[str] = mapped_column(String(10), default="pt-BR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BillingPeriodRecord(Base):
    __tablename__ = "billing_periods"
    __table_args__ = (UniqueConstraint("org", "period_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org: Mapped[str] = mapped_column(String(255), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    active_user_count: Mapped[int] = mapped_column(Integer, default=0)
    seat_price_cents: Mapped[int] = mapped_column(Integer, default=3900)
    soft_cap_reviews_per_seat: Mapped[int] = mapped_column(Integer, default=60)
    over_soft_cap: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingActiveUserRecord(Base):
    __tablename__ = "billing_active_users"
    __table_args__ = (UniqueConstraint("billing_period_id", "github_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("billing_periods.id", ondelete="CASCADE"), index=True
    )
    org: Mapped[str] = mapped_column(String(255), index=True)
    github_username: Mapped[str] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingUsageEventRecord(Base):
    __tablename__ = "billing_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("billing_periods.id", ondelete="CASCADE"), index=True
    )
    org: Mapped[str] = mapped_column(String(255), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), index=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    pr_author: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(50), default="review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookDeliveryRecord(Base):
    __tablename__ = "webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
