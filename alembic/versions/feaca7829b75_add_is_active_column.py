"""add is_active column

Revision ID: feaca7829b75
Revises: 64989eae2466
Create Date: 2026-09-17 18:28:45.754815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feaca7829b75'
down_revision: Union[str, Sequence[str], None] = '64989eae2466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Сначала разрешаем NULL, чтобы колонку можно было добавить старым строкам
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=True)
    )

    # 2. Заполняем старых пользователей
    op.execute(
        sa.text(
            "UPDATE users "
            "SET is_active = TRUE "
            "WHERE is_active IS NULL"
        )
    )

    # 3. Теперь NULL больше не нужен
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
