import json
import logging
from secrets import compare_digest

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.security import validate_csrf_token
from database import get_db
from dependencies import require_current_user
from models import Purchase, User
from services.payment_service import (
    StripePaymentConflictError,
    get_paid_purchase,
    reserve_webhook_event,
    save_paid_purchase,
)
from services.plan_service import PLANS

router = APIRouter()

stripe.api_key = settings.stripe_secret_key

SUPPORTED_PAYMENT_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
}


def check_csrf(
    cookie_token: str | None,
    header_token: str | None,
) -> None:
    if (
        not cookie_token
        or not header_token
        or not compare_digest(cookie_token, header_token)
        or not validate_csrf_token(header_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Ошибка безопасности (CSRF)",
        )


def stripe_value(obj, key: str, default=None):
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_session_identity(session) -> tuple[int, str]:
    metadata = stripe_value(session, "metadata", {}) or {}

    user_id_raw = metadata.get("user_id")
    plan_id = metadata.get("plan_id")

    if not user_id_raw or not plan_id:
        raise HTTPException(
            status_code=400,
            detail="Stripe session metadata is incomplete",
        )

    if plan_id not in PLANS:
        raise HTTPException(
            status_code=400,
            detail="Unknown plan in Stripe session",
        )

    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Invalid user id in Stripe session",
        )

    return user_id, plan_id


def build_payment_success_html(session_id: str) -> str:
    safe_session_id_json = json.dumps(session_id)

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta
            name="viewport"
            content="width=device-width, initial-scale=1"
        >
        <title>Оплата успешна</title>
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
        <div>
            <h1 style="color:#22C55E;">
                Оплата прошла успешно
            </h1>

            <p id="status-text">
                Активируем доступ к программе...
            </p>

            <button
                id="course-button"
                disabled
                style="
                    padding:12px 24px;
                    background:#F97316;
                    color:white;
                    border:none;
                    border-radius:8px;
                    cursor:pointer;
                    opacity:.65;
                "
            >
                Подождите...
            </button>
        </div>

        <script>
            const sessionId = {safe_session_id_json};
            const button = document.getElementById("course-button");
            const statusText = document.getElementById("status-text");

            let attempts = 0;
            const maxAttempts = 30;

            async function checkPayment() {{
                attempts += 1;

                try {{
                    const response = await fetch(
                        `/payment-status?session_id=${{encodeURIComponent(sessionId)}}`,
                        {{
                            credentials: "same-origin"
                        }}
                    );

                    if (!response.ok) {{
                        throw new Error(
                            `payment-status failed: ${{response.status}}`
                        );
                    }}

                    const data = await response.json();

                    if (data.status === "paid") {{
                        button.disabled = false;
                        button.style.opacity = "1";
                        button.textContent = "Перейти к программе";
                        statusText.textContent = "Доступ активирован.";

                        button.onclick = () => {{
                            window.history.replaceState(
                                null,
                                "",
                                "/auth/welcome"
                            );
                            window.location.href = data.course_url;
                        }};

                        setTimeout(() => {{
                            button.click();
                        }}, 800);

                        return;
                    }}

                    if (attempts >= maxAttempts) {{
                        statusText.textContent =
                            "Активация занимает больше времени. Обновите страницу через несколько секунд.";
                        button.textContent = "Обновить";
                        button.disabled = false;
                        button.style.opacity = "1";
                        button.onclick = () => window.location.reload();
                        return;
                    }}

                    setTimeout(checkPayment, 1000);
                }} catch (error) {{
                    console.error(error);

                    if (attempts >= maxAttempts) {{
                        statusText.textContent =
                            "Не удалось проверить статус. Обновите страницу.";
                        button.textContent = "Обновить";
                        button.disabled = false;
                        button.style.opacity = "1";
                        button.onclick = () => window.location.reload();
                        return;
                    }}

                    setTimeout(checkPayment, 1500);
                }}
            }}

            checkPayment();
        </script>
    </body>
    </html>
    """


@router.post("/create-checkout-session/{plan_id}")
async def create_checkout_session(
    plan_id: str,
    request: Request,
    x_csrf_token: str | None = Header(
        None,
        alias="X-CSRF-Token",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        x_csrf_token,
    )

    plan = PLANS.get(plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="План не найден",
        )

    if get_paid_purchase(
        db,
        current_user.id,
        plan_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="Этот курс уже куплен",
        )

    current_domain = (
        settings.render_external_url
        or settings.your_domain
    ).rstrip("/")

    price_in_cents = int(
        float(plan["price"]) * 100
    )

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "plan_id": plan_id,
            },
            line_items=[
                {
                    "price_data": {
                        "currency": "rub",
                        "product_data": {
                            "name": plan["title"],
                        },
                        "unit_amount": price_in_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=(
                f"{current_domain}/payment-success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=(
                f"{current_domain}/plans/{plan_id}"
            ),
        )

        return {
            "id": checkout_session.id,
        }

    except Exception:
        logging.exception(
            "Stripe checkout creation failed"
        )
        raise HTTPException(
            status_code=502,
            detail="Не удалось создать оплату",
        )


@router.get(
    "/payment-success",
    response_class=HTMLResponse,
)
async def payment_success(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    try:
        session = stripe.checkout.Session.retrieve(
            session_id
        )
    except Exception:
        logging.exception(
            "Stripe session reconciliation failed"
        )
        raise HTTPException(
            status_code=502,
            detail="Не удалось проверить оплату",
        )

    session_user_id, plan_id = get_session_identity(
        session
    )

    if session_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="This Stripe session belongs to another user",
        )

    if stripe_value(
        session,
        "payment_status",
    ) == "paid":
        try:
            save_paid_purchase(
                db=db,
                user_id=current_user.id,
                plan_id=plan_id,
                stripe_session_id=session_id,
                amount_cents=stripe_value(
                    session,
                    "amount_total",
                ),
                currency=stripe_value(
                    session,
                    "currency",
                ),
            )
            db.commit()

        except StripePaymentConflictError:
            db.rollback()
            logging.exception(
                "Stripe reconciliation conflict"
            )
            raise HTTPException(
                status_code=409,
                detail="Payment reconciliation conflict",
            )

        except Exception:
            db.rollback()
            logging.exception(
                "Payment reconciliation DB failure"
            )
            raise HTTPException(
                status_code=500,
                detail="Не удалось активировать покупку",
            )

    return HTMLResponse(
        content=build_payment_success_html(
            session_id
        )
    )


@router.get("/payment-status")
async def payment_status(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user),
):
    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.user_id == current_user.id,
            Purchase.stripe_session_id == session_id,
            Purchase.status == "paid",
        )
        .first()
    )

    if purchase is None:
        return {
            "status": "processing",
        }

    return {
        "status": "paid",
        "course_url": f"/course/{purchase.plan_id}",
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

    event_id = stripe_value(
        event,
        "id",
    )
    event_type = stripe_value(
        event,
        "type",
    )

    if not event_id or not event_type:
        raise HTTPException(
            status_code=400,
            detail="Invalid Stripe event",
        )

    if event_type not in SUPPORTED_PAYMENT_EVENTS:
        return {
            "status": "ignored",
        }

    event_data = stripe_value(
        event,
        "data",
        {},
    ) or {}
    session = stripe_value(
        event_data,
        "object",
        {},
    ) or {}

    session_id = stripe_value(
        session,
        "id",
    )

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Stripe session id is missing",
        )

    if stripe_value(
        session,
        "payment_status",
    ) != "paid":
        return {
            "status": "ignored",
            "reason": "payment_not_paid",
        }

    try:
        user_id, plan_id = get_session_identity(
            session
        )
    except HTTPException:
        logging.warning(
            "Stripe event ignored due to invalid metadata: event=%s",
            event_id,
        )
        return {
            "status": "ignored",
            "reason": "invalid_metadata",
        }

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
        )
        .first()
    )

    if user is None:
        logging.warning(
            "Stripe event references missing user: event=%s user=%s",
            event_id,
            user_id,
        )
        return {
            "status": "ignored",
            "reason": "user_not_found",
        }

    reserved_event = reserve_webhook_event(
        db=db,
        event_id=event_id,
        event_type=event_type,
        stripe_session_id=session_id,
    )

    if reserved_event is None:
        return {
            "status": "already_processed",
        }

    try:
        save_paid_purchase(
            db=db,
            user_id=user.id,
            plan_id=plan_id,
            stripe_session_id=session_id,
            amount_cents=stripe_value(
                session,
                "amount_total",
            ),
            currency=stripe_value(
                session,
                "currency",
            ),
        )

        db.commit()

    except StripePaymentConflictError:
        db.rollback()
        logging.exception(
            "Stripe payment conflict: event=%s session=%s",
            event_id,
            session_id,
        )
        raise HTTPException(
            status_code=409,
            detail="Stripe payment conflict",
        )

    except Exception:
        db.rollback()
        logging.exception(
            "Stripe webhook DB processing failed: event=%s",
            event_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        )

    logging.info(
        "Stripe payment processed: event=%s session=%s user=%s plan=%s",
        event_id,
        session_id,
        user.id,
        plan_id,
    )

    return {
        "status": "success",
    }
