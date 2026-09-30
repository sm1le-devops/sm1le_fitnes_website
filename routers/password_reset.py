from hashlib import sha256
from secrets import token_urlsafe
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
)

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from services.email_service import send_email
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas

from core.config import settings
from core.security import get_password_hash
from database import get_db
from services.session_service import delete_user_session


router = APIRouter()
templates = Jinja2Templates(directory="templates")

RESET_TOKEN_TTL = 60 * 60
RESET_COOLDOWN_TTL = 60 * 10

FORGOT_PASSWORD_LIMIT = 3
FORGOT_PASSWORD_WINDOW = 60 * 60


def token_hash(token: str) -> str:
    return sha256(
        token.encode("utf-8")
    ).hexdigest()


def forgot_password_limit_key(client_ip: str) -> str:
    normalized_ip = client_ip.strip() or "unknown"

    return (
        "password_reset:rate_limit:"
        f"{sha256(normalized_ip.encode('utf-8')).hexdigest()}"
    )


async def consume_forgot_password_attempt(
    redis,
    client_ip: str,
) -> tuple[bool, int]:
    key = forgot_password_limit_key(client_ip)

    created = await redis.set(
        key,
        "1",
        ex=FORGOT_PASSWORD_WINDOW,
        nx=True,
    )

    if created:
        return True, FORGOT_PASSWORD_WINDOW

    count = await redis.incr(key)

    ttl = await redis.ttl(key)

    if ttl is None or ttl < 0:
        await redis.expire(
            key,
            FORGOT_PASSWORD_WINDOW,
        )
        ttl = FORGOT_PASSWORD_WINDOW

    return (
        count <= FORGOT_PASSWORD_LIMIT,
        max(int(ttl), 1),
    )
def token_hash(token: str) -> str:
    return sha256(
        token.encode("utf-8")
    ).hexdigest()


def reset_token_key(token: str) -> str:
    return (
        "password_reset:token:"
        f"{token_hash(token)}"
    )


def user_reset_key(user_id: int) -> str:
    return f"password_reset:user:{user_id}"


def reset_cooldown_key(user_id: int) -> str:
    return f"password_reset:cooldown:{user_id}"


@router.get(
    "/forgot-password",
    response_class=HTMLResponse,
)
async def forgot_password_form(
    request: Request,
):
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"request": request},
    )


@router.get(
    "/reset-password",
    response_class=HTMLResponse,
)
async def reset_password_form(
    request: Request,
    token: Optional[str] = None,
):
    if not token:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "request": request,
                "error": "Token is missing",
            },
        )

    user_id = await request.app.state.redis.get(
        reset_token_key(token)
    )

    if user_id is None:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "request": request,
                "error": "Token is invalid or expired",
            },
        )

    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "request": request,
            "token": token,
        },
    )


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    request_data: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    redis = request.app.state.redis

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    allowed, retry_after = (
        await consume_forgot_password_attempt(
            redis,
            client_ip,
        )
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many password reset requests. Try again later.",
            headers={
                "Retry-After": str(retry_after)
            },
        )

    email = str(
        request_data.email
    ).strip().lower()

    user = (
        db.query(models.User)
        .filter(
            func.lower(models.User.email) == email
        )
        .first()
    )

    generic_response = {
        "message": (
            "If an account with this email exists, "
            "a recovery link has been sent to it"
        )
    }

    if not user:
        return generic_response

    cooldown_created = await redis.set(
        reset_cooldown_key(user.id),
        "1",
        ex=RESET_COOLDOWN_TTL,
        nx=True,
    )

    if not cooldown_created:
        return generic_response

    old_token_hash = await redis.get(
        user_reset_key(user.id)
    )

    if old_token_hash:
        await redis.delete(
            f"password_reset:token:{old_token_hash}"
        )

    token = token_urlsafe(32)
    hashed_token = token_hash(token)

    await redis.set(
        reset_token_key(token),
        user.id,
        ex=RESET_TOKEN_TTL,
    )

    await redis.set(
        user_reset_key(user.id),
        hashed_token,
        ex=RESET_TOKEN_TTL,
    )

    current_domain = (
        settings.render_external_url
        or settings.your_domain
    ).rstrip("/")

    reset_link = (
        f"{current_domain}"
        f"/auth/reset-password?token={token}"
    )

    background_tasks.add_task(
        send_email,
        user.email,
        "Password recovery",
        (
            "To reset your password, "
            "follow this link:\n"
            f"{reset_link}"
        ),
    )

    return generic_response


@router.post("/reset-password")
async def reset_password(
    request: Request,
    data: schemas.ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    redis = request.app.state.redis
    key = reset_token_key(data.token)

    user_id = await redis.getdel(key)

    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="Token is invalid or expired",
        )

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Token is invalid",
        )

    user = db.get(
        models.User,
        user_id,
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    user.hashed_password = get_password_hash(
        data.new_password
    )

    db.commit()

    await redis.delete(
        user_reset_key(user.id)
    )

    await delete_user_session(
        redis,
        user.id,
    )

    return {
        "message": "Password changed successfully"
    }
