"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("installation_id", sa.Integer, nullable=False),
        sa.Column("default_branch", sa.String(100), server_default="main", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_full_name", sa.String(255), index=True, nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("comment_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reviews_repo_pr", "reviews", ["repo_full_name", "pr_number"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_full_name", sa.String(255), index=True, nullable=False),
        sa.Column("original_comment", sa.Text, nullable=False),
        sa.Column("user_response", sa.Text, nullable=False),
        sa.Column("sentiment", sa.String(20), server_default="neutral", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "org_settings",
        sa.Column("org", sa.String(255), primary_key=True),
        sa.Column("language", sa.String(10), server_default="pt-BR", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "billing_periods",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org", sa.String(255), index=True, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("active_user_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("seat_price_cents", sa.Integer, server_default="3900", nullable=False),
        sa.Column("soft_cap_reviews_per_seat", sa.Integer, server_default="60", nullable=False),
        sa.Column("over_soft_cap", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org", "period_start"),
    )

    op.create_table(
        "billing_active_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "billing_period_id",
            sa.Integer,
            sa.ForeignKey("billing_periods.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("org", sa.String(255), index=True, nullable=False),
        sa.Column("github_username", sa.String(255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("billing_period_id", "github_username"),
    )

    op.create_table(
        "billing_usage_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "billing_period_id",
            sa.Integer,
            sa.ForeignKey("billing_periods.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("org", sa.String(255), index=True, nullable=False),
        sa.Column("repo_full_name", sa.String(255), index=True, nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("pr_author", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(50), server_default="review", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("billing_usage_events")
    op.drop_table("billing_active_users")
    op.drop_table("billing_periods")
    op.drop_table("org_settings")
    op.drop_table("feedback")
    op.drop_index("ix_reviews_repo_pr", table_name="reviews")
    op.drop_table("reviews")
    op.drop_table("repositories")
