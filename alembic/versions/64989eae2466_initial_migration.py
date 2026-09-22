"""initial_migration

Revision ID: 64989eae2466
Revises:
Create Date: 2026-04-25 14:28:01.437862
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "64989eae2466"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=50), nullable=False),
        sa.Column("hashed_password", sa.String(length=200), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("target", sa.String(length=50), nullable=True),
        sa.Column("purchased_plans", sa.String(), nullable=True),
        sa.Column("generated_plans", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_users_id",
        "users",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )

    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")

    op.drop_table("users")