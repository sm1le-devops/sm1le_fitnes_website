from typing import Optional

from sqlalchemy.orm import Session

from models import Purchase


def get_purchase(
    db: Session,
    user_id: int,
    plan_id: str,
) -> Optional[Purchase]:
    return (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user_id,
            Purchase.plan_id == plan_id,
        )
        .first()
    )


def get_purchase_by_stripe_session(
    db: Session,
    stripe_session_id: str,
) -> Optional[Purchase]:
    return (
        db.query(Purchase)
        .filter(Purchase.stripe_session_id == stripe_session_id)
        .first()
    )


def save_paid_purchase(
    db: Session,
    user_id: int,
    plan_id: str,
    stripe_session_id: str,
    amount_cents: int | None,
    currency: str | None,
) -> Purchase:
    purchase = get_purchase(
        db=db,
        user_id=user_id,
        plan_id=plan_id,
    )

    if purchase is None:
        purchase = Purchase(
            user_id=user_id,
            plan_id=plan_id,
        )
        db.add(purchase)

    purchase.stripe_session_id = stripe_session_id
    purchase.status = "paid"
    purchase.amount_cents = amount_cents
    purchase.currency = currency.lower() if currency else None

    return purchase
