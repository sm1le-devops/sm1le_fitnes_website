"""add normalized user profile purchases and generated plans

Revision ID: ce66bdc0e422
Revises: feaca7829b75
Create Date: 2026-09-22 12:13:50.712703
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "ce66bdc0e422"
down_revision: Union[str, Sequence[str], None] = "feaca7829b75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Новая таблица сгенерированных планов
    op.create_table(
        "generated_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "plan_id",
            name="uq_generated_plan_user_plan",
        ),
    )

    op.create_index(
        op.f("ix_generated_plans_plan_id"),
        "generated_plans",
        ["plan_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_generated_plans_user_id"),
        "generated_plans",
        ["user_id"],
        unique=False,
    )

    # 2. Таблица покупок
    op.create_table(
        "purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.String(length=100), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_session_id"),
        sa.UniqueConstraint(
            "user_id",
            "plan_id",
            name="uq_purchase_user_plan",
        ),
    )

    op.create_index(
        op.f("ix_purchases_plan_id"),
        "purchases",
        ["plan_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_purchases_user_id"),
        "purchases",
        ["user_id"],
        unique=False,
    )

    # 3. Таблица фитнес-профиля
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("target", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_user_profiles_user_id"),
        "user_profiles",
        ["user_id"],
        unique=True,
    )

    # --------------------------------------------------
    # DATA MIGRATION
    # --------------------------------------------------

    # 4. Перенос фитнес-профиля
    op.execute(
        """
        INSERT INTO user_profiles (
            user_id,
            gender,
            age,
            weight,
            height,
            target,
            created_at,
            updated_at
        )
        SELECT
            id,
            gender,
            age,
            weight,
            height,
            target,
            COALESCE(created_at, NOW()),
            NOW()
        FROM users;
        """
    )

    # 5. Перенос purchased_plans
    #
    # Было:
    # "muscle_gain,weight_loss"
    #
    # Станет:
    # purchases:
    # user_id | muscle_gain
    # user_id | weight_loss
    op.execute(
        """
        INSERT INTO purchases (
            user_id,
            plan_id,
            status,
            created_at
        )
        SELECT DISTINCT
            u.id,
            TRIM(plan.plan_id),
            'paid',
            COALESCE(u.created_at, NOW())
        FROM users u
        CROSS JOIN LATERAL
            unnest(
                string_to_array(
                    COALESCE(u.purchased_plans, ''),
                    ','
                )
            ) AS plan(plan_id)
        WHERE TRIM(plan.plan_id) <> '';
        """
    )

    # 6. Перенос JSON generated_plans
    #
    # Было:
    # {
    #   "muscle_gain": "текст...",
    #   "weight_loss": "текст..."
    # }
    #
    # Станет отдельными строками.
    op.execute(
        """
        INSERT INTO generated_plans (
            user_id,
            plan_id,
            content,
            created_at,
            updated_at
        )
        SELECT
            u.id,
            generated.key,
            generated.value,
            COALESCE(u.created_at, NOW()),
            NOW()
        FROM users u
        CROSS JOIN LATERAL
            json_each_text(
                COALESCE(
                    u.generated_plans,
                    '{}'::json
                )
            ) AS generated(key, value);
        """
    )

    # 7. Старые users.created_at могут содержать NULL.
    # Сначала исправляем данные.
    op.execute(
        """
        UPDATE users
        SET created_at = NOW()
        WHERE created_at IS NULL;
        """
    )

    # И только теперь ставим NOT NULL.
    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
    )

    op.drop_index(
        op.f("ix_user_profiles_user_id"),
        table_name="user_profiles",
    )
    op.drop_table("user_profiles")

    op.drop_index(
        op.f("ix_purchases_user_id"),
        table_name="purchases",
    )
    op.drop_index(
        op.f("ix_purchases_plan_id"),
        table_name="purchases",
    )
    op.drop_table("purchases")

    op.drop_index(
        op.f("ix_generated_plans_user_id"),
        table_name="generated_plans",
    )
    op.drop_index(
        op.f("ix_generated_plans_plan_id"),
        table_name="generated_plans",
    )
    op.drop_table("generated_plans")