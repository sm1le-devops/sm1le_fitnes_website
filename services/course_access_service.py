from typing import Optional

from sqlalchemy.orm import Session

from models import GeneratedPlan, Purchase


def has_paid_purchase(db: Session, user_id: int, plan_id: str) -> bool:
    return (
        db.query(Purchase.id)
        .filter(
            Purchase.user_id == user_id,
            Purchase.plan_id == plan_id,
            Purchase.status == "paid",
        )
        .first()
        is not None
    )


def get_paid_plan_ids(db: Session, user_id: int) -> set[str]:
    rows = (
        db.query(Purchase.plan_id)
        .filter(
            Purchase.user_id == user_id,
            Purchase.status == "paid",
        )
        .all()
    )

    return {row[0] for row in rows}


def get_generated_plan(
    db: Session,
    user_id: int,
    plan_id: str,
) -> Optional[GeneratedPlan]:
    return (
        db.query(GeneratedPlan)
        .filter(
            GeneratedPlan.user_id == user_id,
            GeneratedPlan.plan_id == plan_id,
        )
        .first()
    )


def save_generated_plan(
    db: Session,
    user_id: int,
    plan_id: str,
    content: str,
) -> GeneratedPlan:
    generated_plan = get_generated_plan(
        db=db,
        user_id=user_id,
        plan_id=plan_id,
    )

    if generated_plan:
        generated_plan.content = content
    else:
        generated_plan = GeneratedPlan(
            user_id=user_id,
            plan_id=plan_id,
            content=content,
        )
        db.add(generated_plan)

    return generated_plan
