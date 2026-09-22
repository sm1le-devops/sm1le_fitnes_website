import json
import logging
from secrets import compare_digest

import stripe
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import settings
from core.security import validate_csrf_token
from database import get_db
from dependencies import require_current_user
from models import User
from services.payment_service import (
    get_purchase,
    get_purchase_by_stripe_session,
    save_paid_purchase,
)
from services.plan_service import PLANS


router = APIRouter()
stripe.api_key = settings.stripe_secret_key


def check_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(
        "csrf_token"
    )
    header_token = request.headers.get(
        "X-CSRF-Token"
    )

    if (
        not cookie_token
        or not header_token
        or not compare_digest(
            cookie_token,
            header_token,
        )
        or not validate_csrf_token(header_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Ошибка безопасности (CSRF)",
        )


@router.post(
    "/create-checkout-session/{plan_id}"
)
def create_checkout_session(
    plan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_current_user
    ),
):
    check_csrf(request)

    plan = PLANS.get(plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="План не найден",
        )

    existing_purchase = get_purchase(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    if (
        existing_purchase
        and existing_purchase.status == "paid"
    ):
        raise HTTPException(
            status_code=409,
            detail="План уже куплен",
        )

    current_domain = (
        settings.render_external_url
        or settings.your_domain
    ).rstrip("/")

    price_in_cents = int(
        float(plan["price"]) * 100
    )

    try:
        checkout_session = (
            stripe.checkout.Session.create(
                payment_method_types=["card"],
                client_reference_id=str(
                    current_user.id
                ),
                metadata={
                    "user_id": str(
                        current_user.id
                    ),
                    "plan_id": plan_id,
                },
                line_items=[
                    {
                        "price_data": {
                            "currency": "rub",
                            "product_data": {
                                "name": plan["title"],
                            },
                            "unit_amount": (
                                price_in_cents
                            ),
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=(
                    f"{current_domain}"
                    "/payment-success"
                    "?session_id="
                    "{CHECKOUT_SESSION_ID}"
                ),
                cancel_url=(
                    f"{current_domain}"
                    f"/plans/{plan_id}"
                ),
            )
        )

        return {
            "id": checkout_session.id
        }

    except Exception:
        logging.exception(
            "Stripe checkout error"
        )
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать оплату",
        )


@router.get(
    "/payment-success",
    response_class=HTMLResponse,
)
def payment_success(
    session_id: str,
    current_user: User = Depends(
        require_current_user
    ),
):
    try:
        checkout_session = (
            stripe.checkout.Session.retrieve(
                session_id
            )
        )
    except Exception:
        logging.exception(
            "Stripe session retrieve failed"
        )
        raise HTTPException(
            status_code=400,
            detail="Некорректная Stripe session",
        )

    metadata = checkout_session.get(
        "metadata",
        {},
    )

    if (
        metadata.get("user_id")
        != str(current_user.id)
    ):
        raise HTTPException(
            status_code=403,
            detail="Эта оплата принадлежит другому пользователю",
        )

    plan_id = metadata.get("plan_id")

    if not plan_id or plan_id not in PLANS:
        raise HTTPException(
            status_code=400,
            detail="Некорректный план",
        )

    if (
        checkout_session.get(
            "payment_status"
        )
        != "paid"
    ):
        raise HTTPException(
            status_code=400,
            detail="Оплата ещё не подтверждена",
        )

    plan_id_js = json.dumps(plan_id)

    return HTMLResponse(
        content=f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >
    <title>Оплата подтверждена</title>
</head>
<body style="
    margin:0;
    background:#0F172A;
    color:white;
    display:flex;
    align-items:center;
    justify-content:center;
    min-height:100vh;
    font-family:sans-serif;
    text-align:center;
">
    <div style="padding:24px;">
        <h1 style="color:#22C55E;">
            Оплата прошла успешно
        </h1>

        <p id="status">
            Активируем доступ к программе...
        </p>

        <button
            id="open-course"
            disabled
            style="
                padding:12px 24px;
                background:#F97316;
                color:white;
                border:none;
                border-radius:8px;
                cursor:pointer;
                opacity:.6;
            "
        >
            Подождите...
        </button>
    </div>

    <script>
        const planId = {plan_id_js};
        const statusText =
            document.getElementById('status');
        const button =
            document.getElementById('open-course');

        async function checkPayment() {{
            try {{
                const response = await fetch(
                    '/payment-status?plan_id='
                    + encodeURIComponent(planId)
                );

                if (response.status === 401) {{
                    window.location.href =
                        '/auth/login';
                    return;
                }}

                const data =
                    await response.json();

                if (data.status === 'paid') {{
                    statusText.textContent =
                        'Доступ активирован.';

                    button.disabled = false;
                    button.style.opacity = '1';
                    button.textContent =
                        'Перейти к программе';

                    button.onclick = () => {{
                        window.location.href =
                            data.course_url;
                    }};

                    return;
                }}
            }} catch (error) {{
                console.error(error);
            }}

            setTimeout(checkPayment, 1000);
        }}

        checkPayment();
    </script>
</body>
</html>
"""
    )


@router.get("/payment-status")
def payment_status(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_current_user
    ),
):
    if plan_id not in PLANS:
        raise HTTPException(
            status_code=404,
            detail="План не найден",
        )

    purchase = get_purchase(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    if (
        purchase
        and purchase.status == "paid"
    ):
        return {
            "status": "paid",
            "course_url": (
                f"/course/{plan_id}"
            ),
        }

    return {
        "status": "processing"
    }


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    payload = await request.body()
    signature = request.headers.get(
        "stripe-signature"
    )

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Missing Stripe signature",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret,
        )
    except Exception:
        logging.exception(
            "Stripe webhook verification failed"
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook",
        )

    if (
        event["type"]
        != "checkout.session.completed"
    ):
        return {
            "status": "ignored"
        }

    session = event["data"]["object"]

    if session.get("payment_status") != "paid":
        return {
            "status": "ignored"
        }

    stripe_session_id = session.get("id")

    if not stripe_session_id:
        raise HTTPException(
            status_code=400,
            detail="Missing Stripe session id",
        )

    existing_session = (
        get_purchase_by_stripe_session(
            db=db,
            stripe_session_id=(
                stripe_session_id
            ),
        )
    )

    if existing_session:
        return {
            "status": "success"
        }

    metadata = session.get(
        "metadata",
        {},
    )

    user_id = metadata.get("user_id")
    plan_id = metadata.get("plan_id")

    if not user_id or not plan_id:
        return {
            "status": "ignored"
        }

    if plan_id not in PLANS:
        return {
            "status": "ignored"
        }

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Invalid user id",
        )

    user = db.get(
        User,
        user_id,
    )

    if not user:
        return {
            "status": "ignored"
        }

    save_paid_purchase(
        db=db,
        user_id=user.id,
        plan_id=plan_id,
        stripe_session_id=stripe_session_id,
        amount_cents=session.get(
            "amount_total"
        ),
        currency=session.get("currency"),
    )

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        existing_purchase = (
            get_purchase_by_stripe_session(
                db=db,
                stripe_session_id=(
                    stripe_session_id
                ),
            )
            or get_purchase(
                db=db,
                user_id=user.id,
                plan_id=plan_id,
            )
        )

        if (
            existing_purchase
            and existing_purchase.status == "paid"
        ):
            return {
                "status": "success"
            }

        logging.exception(
            "Stripe purchase conflict"
        )
        raise HTTPException(
            status_code=500,
            detail="Could not save purchase",
        )

    logging.info(
        "Stripe access granted: user=%s plan=%s",
        user.id,
        plan_id,
    )

    return {
        "status": "success"
    }
