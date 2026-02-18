"""Add FKs to reviews/feedback and updated_at to repositories.

Revision ID: 003
Revises: 002
Create Date: 2025-01-20 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clean orphaned rows before adding foreign keys
    op.execute("DELETE FROM reviews WHERE repo_full_name NOT IN (SELECT full_name FROM repositories)")
    op.execute("DELETE FROM feedback WHERE repo_full_name NOT IN (SELECT full_name FROM repositories)")

    # Add updated_at column to repositories
    op.add_column(
        "repositories",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add FK on reviews.repo_full_name -> repositories.full_name
    op.create_foreign_key(
        "fk_reviews_repo_full_name",
        "reviews",
        "repositories",
        ["repo_full_name"],
        ["full_name"],
        ondelete="CASCADE",
    )

    # Add FK on feedback.repo_full_name -> repositories.full_name
    op.create_foreign_key(
        "fk_feedback_repo_full_name",
        "feedback",
        "repositories",
        ["repo_full_name"],
        ["full_name"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_feedback_repo_full_name", "feedback", type_="foreignkey")
    op.drop_constraint("fk_reviews_repo_full_name", "reviews", type_="foreignkey")
    op.drop_column("repositories", "updated_at")
