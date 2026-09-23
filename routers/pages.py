from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from dependencies import get_current_user_optional
from models import User
from services.course_access_service import (
    get_paid_plan_ids,
    has_paid_purchase,
)
from services.plan_service import PLANS


router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(
        get_current_user_optional
    ),
):
    purchased_plan_ids = (
        get_paid_plan_ids(db, user.id)
        if user
        else set()
    )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": user,
            "plans": PLANS,
            "purchased_plan_ids": purchased_plan_ids,
        },
    )


@router.get(
    "/auth/welcome",
    response_class=HTMLResponse,
)
async def welcome_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_current_user_optional
    ),
):
    if current_user is None:
        return RedirectResponse(
            url="/auth/login",
            status_code=303,
        )

    purchased_plan_ids = get_paid_plan_ids(
        db,
        current_user.id,
    )

    return templates.TemplateResponse(
        request,
        "welcome.html",
        {
            "request": request,
            "user": current_user,
            "plans": PLANS,
            "purchased_plan_ids": purchased_plan_ids,
        },
    )


@router.get(
    "/plans/{plan_id}",
    response_class=HTMLResponse,
)
async def get_plan_page(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_current_user_optional
    ),
):
    plan = PLANS.get(plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    is_purchased = False

    if current_user:
        is_purchased = has_paid_purchase(
            db=db,
            user_id=current_user.id,
            plan_id=plan_id,
        )

    return templates.TemplateResponse(
        request,
        "plan_detail.html",
        {
            "request": request,
            "plan": plan,
            "plan_id": plan_id,
            "is_purchased": is_purchased,
            "stripe_publishable_key": (
                settings.stripe_publishable_key
            ),
        },
    )
