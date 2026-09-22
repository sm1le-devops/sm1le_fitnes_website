"""add stripe webhook event idempotency table

Revision ID: 7b0a4c2d1e6f
Revises: 6e9d0fed6a9a
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b0a4c2d1e6f"
down_revision: Union[str, Sequence[str], None] = "6e9d0fed6a9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stripe_webhook_events",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "stripe_session_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            name="uq_stripe_webhook_event_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
