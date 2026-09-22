from models import GeneratedPlan, Purchase
from services.course_access_service import (
    get_generated_plan,
    get_paid_plan_ids,
    has_paid_purchase,
    save_generated_plan,
)


def test_paid_purchase_helpers(db, make_user):
    user = make_user()

    db.add(
        Purchase(
            user_id=user.id,
            plan_id="plan-a",
            status="paid",
        )
    )
    db.add(
        Purchase(
            user_id=user.id,
            plan_id="plan-b",
            status="refunded",
        )
    )
    db.commit()

    assert (
        has_paid_purchase(
            db,
            user.id,
            "plan-a",
        )
        is True
    )
    assert (
        has_paid_purchase(
            db,
            user.id,
            "plan-b",
        )
        is False
    )
    assert (
        get_paid_plan_ids(
            db,
            user.id,
        )
        == {"plan-a"}
    )


def test_save_generated_plan_is_upsert(
    db,
    make_user,
):
    user = make_user()

    first = save_generated_plan(
        db,
        user.id,
        "plan-a",
        "first",
    )
    db.commit()

    second = save_generated_plan(
        db,
        user.id,
        "plan-a",
        "second",
    )
    db.commit()

    assert first.id == second.id

    stored = get_generated_plan(
        db,
        user.id,
        "plan-a",
    )

    assert stored.content == "second"
    assert (
        db.query(GeneratedPlan)
        .filter(
            GeneratedPlan.user_id == user.id,
            GeneratedPlan.plan_id == "plan-a",
        )
        .count()
        == 1
    )
