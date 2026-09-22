from services.payment_service import (
    get_purchase,
    get_purchase_by_stripe_session,
    save_paid_purchase,
)


def test_save_paid_purchase_creates_and_updates(
    db,
    make_user,
):
    user = make_user()

    first = save_paid_purchase(
        db=db,
        user_id=user.id,
        plan_id="plan-a",
        stripe_session_id="cs_1",
        amount_cents=1000,
        currency="RUB",
    )
    db.commit()

    second = save_paid_purchase(
        db=db,
        user_id=user.id,
        plan_id="plan-a",
        stripe_session_id="cs_2",
        amount_cents=1500,
        currency="rub",
    )
    db.commit()

    assert first.id == second.id

    stored = get_purchase(
        db,
        user.id,
        "plan-a",
    )

    assert stored.status == "paid"
    assert stored.stripe_session_id == "cs_2"
    assert stored.amount_cents == 1500
    assert stored.currency == "rub"

    assert (
        get_purchase_by_stripe_session(
            db,
            "cs_2",
        ).id
        == stored.id
    )
