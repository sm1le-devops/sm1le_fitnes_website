"""harden database models

Revision ID: 6e9d0fed6a9a
Revises: 2ae66534356b
Create Date: 2026-09-22 12:57:55.714234
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6e9d0fed6a9a"
down_revision: Union[str, Sequence[str], None] = "2ae66534356b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "email",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=254),
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.VARCHAR(length=200),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )

    op.alter_column(
        "user_profiles",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "user_profiles",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "purchases",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "purchases",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=sa.text("'paid'"),
    )

    op.alter_column(
        "generated_plans",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "generated_plans",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    op.create_check_constraint(
        "ck_purchase_status",
        "purchases",
        "status IN ('paid', 'refunded', 'canceled')",
    )

    op.create_check_constraint(
        "ck_purchase_amount_non_negative",
        "purchases",
        "amount_cents IS NULL OR amount_cents >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_purchase_amount_non_negative",
        "purchases",
        type_="check",
    )

    op.drop_constraint(
        "ck_purchase_status",
        "purchases",
        type_="check",
    )

    op.alter_column(
        "generated_plans",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "generated_plans",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "purchases",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "purchases",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "user_profiles",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "user_profiles",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        existing_nullable=False,
        server_default=None,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        type_=sa.VARCHAR(length=200),
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=254),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )