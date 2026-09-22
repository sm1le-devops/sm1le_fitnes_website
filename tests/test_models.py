import pytest
from sqlalchemy.exc import IntegrityError

from models import (
    GeneratedPlan,
    Purchase,
    User,
    UserProfile,
)


def create_user(db, username="user", email="user@example.com"):
    user = User(
        username=username,
        email=email,
        hashed_password="hash",
    )
    user.profile = UserProfile()

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def test_user_profile_is_one_to_one(db):
    user = create_user(db)

    assert user.profile is not None
    assert user.profile.user_id == user.id


def test_purchase_user_plan_is_unique(db):
    user = create_user(db)

    db.add_all(
        [
            Purchase(
                user_id=user.id,
                plan_id="plan-a",
                status="paid",
            ),
            Purchase(
                user_id=user.id,
                plan_id="plan-a",
                status="paid",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_generated_plan_user_plan_is_unique(db):
    user = create_user(db)

    db.add_all(
        [
            GeneratedPlan(
                user_id=user.id,
                plan_id="plan-a",
                content="one",
            ),
            GeneratedPlan(
                user_id=user.id,
                plan_id="plan-a",
                content="two",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


@pytest.mark.parametrize(
    "status",
    ["something", "pending", "broken"],
)
def test_purchase_rejects_unknown_status(db, status):
    user = create_user(db)

    db.add(
        Purchase(
            user_id=user.id,
            plan_id="plan-a",
            status=status,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_purchase_rejects_negative_amount(db):
    user = create_user(db)

    db.add(
        Purchase(
            user_id=user.id,
            plan_id="plan-a",
            status="paid",
            amount_cents=-1,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_user_delete_cascades_related_rows(db):
    user = create_user(db)

    db.add(
        Purchase(
            user_id=user.id,
            plan_id="plan-a",
            status="paid",
        )
    )
    db.add(
        GeneratedPlan(
            user_id=user.id,
            plan_id="plan-a",
            content="content",
        )
    )
    db.commit()

    user_id = user.id

    db.delete(user)
    db.commit()

    assert (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user_id)
        .count()
        == 0
    )
    assert (
        db.query(Purchase)
        .filter(Purchase.user_id == user_id)
        .count()
        == 0
    )
    assert (
        db.query(GeneratedPlan)
        .filter(GeneratedPlan.user_id == user_id)
        .count()
        == 0
    )
