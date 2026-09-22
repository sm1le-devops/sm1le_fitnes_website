"""add email verification flag

Revision ID: c4f2a8b71d90
Revises: 7b0a4c2d1e6f
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f2a8b71d90"
down_revision: Union[str, Sequence[str], None] = "7b0a4c2d1e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing users are trusted as already verified.
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "users",
        "email_verified",
    )
