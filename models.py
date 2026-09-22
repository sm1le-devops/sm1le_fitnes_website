from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )
    email = Column(
        String(254),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password = Column(
        String(255),
        nullable=False,
    )
    is_active = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    purchases = relationship(
        "Purchase",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    generated_plans = relationship(
        "GeneratedPlan",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    gender = Column(String(10), nullable=True)
    age = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    target = Column(String(50), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship(
        "User",
        back_populates="profile",
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    plan_id = Column(
        String(100),
        nullable=False,
        index=True,
    )

    stripe_session_id = Column(
        String(255),
        nullable=True,
        unique=True,
    )

    status = Column(
        String(20),
        nullable=False,
        server_default="paid",
    )

    amount_cents = Column(
        Integer,
        nullable=True,
    )

    currency = Column(
        String(3),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user = relationship(
        "User",
        back_populates="purchases",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "plan_id",
            name="uq_purchase_user_plan",
        ),
        CheckConstraint(
            "status IN ('paid', 'refunded', 'canceled')",
            name="ck_purchase_status",
        ),
        CheckConstraint(
            "amount_cents IS NULL OR amount_cents >= 0",
            name="ck_purchase_amount_non_negative",
        ),
    )


class GeneratedPlan(Base):
    __tablename__ = "generated_plans"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    plan_id = Column(
        String(100),
        nullable=False,
        index=True,
    )

    content = Column(
        Text,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user = relationship(
        "User",
        back_populates="generated_plans",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "plan_id",
            name="uq_generated_plan_user_plan",
        ),
    )