from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Purchase, StripeWebhookEvent


class StripePaymentConflictError(Exception):
    pass


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


def get_paid_purchase(
    db: Session,
    user_id: int,
    plan_id: str,
) -> Optional[Purchase]:
    return (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user_id,
            Purchase.plan_id == plan_id,
            Purchase.status == "paid",
        )
        .first()
    )


def get_purchase_by_stripe_session(
    db: Session,
    stripe_session_id: str,
) -> Optional[Purchase]:
    return (
        db.query(Purchase)
        .filter(
            Purchase.stripe_session_id == stripe_session_id,
        )
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
    existing_session_purchase = get_purchase_by_stripe_session(
        db,
        stripe_session_id,
    )

    if existing_session_purchase is not None:
        if (
            existing_session_purchase.user_id != user_id
            or existing_session_purchase.plan_id != plan_id
        ):
            raise StripePaymentConflictError(
                "Stripe session is already linked to another purchase"
            )

        existing_session_purchase.status = "paid"
        existing_session_purchase.amount_cents = amount_cents
        existing_session_purchase.currency = (
            currency.lower() if currency else None
        )
        return existing_session_purchase

    purchase = get_purchase(
        db,
        user_id,
        plan_id,
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
    purchase.currency = (
        currency.lower() if currency else None
    )

    return purchase


def get_webhook_event(
    db: Session,
    event_id: str,
) -> Optional[StripeWebhookEvent]:
    return (
        db.query(StripeWebhookEvent)
        .filter(
            StripeWebhookEvent.event_id == event_id,
        )
        .first()
    )


def reserve_webhook_event(
    db: Session,
    event_id: str,
    event_type: str,
    stripe_session_id: str | None,
) -> StripeWebhookEvent | None:
    if get_webhook_event(db, event_id) is not None:
        return None

    event = StripeWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        stripe_session_id=stripe_session_id,
    )
    db.add(event)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None

    return event
