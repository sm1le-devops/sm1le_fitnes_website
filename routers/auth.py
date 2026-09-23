from secrets import compare_digest
from typing import Optional

from pydantic import BaseModel, EmailStr

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas

from core.config import settings
from core.security import (
    generate_csrf_token,
    get_password_hash,
    is_username_valid,
    validate_csrf_token,
    verify_password,
    verify_password_or_dummy,
)
from database import get_db
from dependencies import (
    get_current_user_optional,
    require_current_user,
)
from services.login_security_service import (
    LoginBlock,
    clear_login_user_failures,
    get_login_block,
    record_failed_login,
)
from services.email_verification_service import (
    send_verification_email,
)
from services.registration_security_service import (
    RateLimitBlock,
    consume_registration_attempt,
    consume_verification_resend_attempt,
    consume_verification_token,
    get_verification_user_id,
    issue_verification_token,
)
from services.session_service import (
    SESSION_COOKIE_MAX_AGE,
    create_session,
    delete_session,
    delete_user_session,
)

router = APIRouter()
templates = Jinja2Templates(
    directory="templates"
)


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    csrf_token: str


def raise_registration_blocked(
    block: RateLimitBlock,
) -> None:
    raise HTTPException(
        status_code=429,
        detail=(
            "Too many requests. "
            "Please try again later."
        ),
        headers={
            "Retry-After": str(
                max(block.retry_after, 1)
            )
        },
    )


def verification_link(
    token: str,
) -> str:
    current_domain = (
        settings.render_external_url
        or settings.your_domain
    ).rstrip("/")

    return (
        f"{current_domain}"
        f"/auth/verify-email?token={token}"
    )


def check_csrf(
    cookie_token: Optional[str],
    form_token: Optional[str],
) -> None:
    if (
        not cookie_token
        or not form_token
        or not compare_digest(
            cookie_token,
            form_token,
        )
        or not validate_csrf_token(
            form_token
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Security error (CSRF)",
        )


def get_client_ip(
    request: Request,
) -> str:
    if request.client is None:
        return "unknown"

    return request.client.host or "unknown"


def use_secure_cookie(
    request: Request,
) -> bool:
    if request.url.scheme == "https":
        return True

    return (
        settings.render_external_url
        .strip()
        .lower()
        .startswith("https://")
    )


def raise_login_blocked(
    block: LoginBlock,
) -> None:
    raise HTTPException(
        status_code=429,
        detail=(
            "Too many login attempts. "
            "Please try again later."
        ),
        headers={
            "Retry-After": str(
                max(block.retry_after, 1)
            )
        },
    )


@router.post("/register")
async def register(
    user: schemas.UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        user.csrf_token,
    )

    redis = request.app.state.redis
    client_ip = get_client_ip(
        request
    )

    registration_block = (
        await consume_registration_attempt(
            redis=redis,
            client_ip=client_ip,
        )
    )

    if registration_block is not None:
        raise_registration_blocked(
            registration_block
        )

    if not is_username_valid(
        user.username
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Username may contain only "
                "letters, numbers, and '_'"
            ),
        )

    normalized_email = str(
        user.email
    ).strip().lower()

    existing_user = (
        db.query(models.User)
        .filter(
            (
                models.User.username
                == user.username
            )
            | (
                func.lower(
                    models.User.email
                )
                == normalized_email
            )
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not register "
                "an account with these details"
            ),
        )

    new_user = models.User(
        username=user.username,
        email=normalized_email,
        hashed_password=get_password_hash(
            user.password
        ),
        email_verified=False,
    )

    new_user.profile = models.UserProfile()

    db.add(new_user)

    try:
        db.commit()
        db.refresh(
            new_user
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Could not register "
                "an account with these details"
            ),
        )

    token = await issue_verification_token(
        redis=redis,
        user_id=new_user.id,
        enforce_cooldown=False,
    )

    if token:
        background_tasks.add_task(
            send_verification_email,
            new_user.email,
            verification_link(token),
        )

    return {
        "message": "Success",
        "verification_required": True,
    }


@router.post("/resend-verification")
async def resend_verification(
    data: ResendVerificationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        data.csrf_token,
    )

    generic_response = {
        "message": (
            "If the account exists and the email is "
            "not yet verified, a verification email has been sent."
        )
    }

    redis = request.app.state.redis
    client_ip = get_client_ip(
        request
    )

    resend_block = (
        await consume_verification_resend_attempt(
            redis=redis,
            client_ip=client_ip,
        )
    )

    if resend_block is not None:
        raise_registration_blocked(
            resend_block
        )

    normalized_email = str(
        data.email
    ).strip().lower()

    user = (
        db.query(models.User)
        .filter(
            func.lower(
                models.User.email
            )
            == normalized_email
        )
        .first()
    )

    if (
        user is None
        or getattr(
            user,
            "email_verified",
            False,
        )
    ):
        return generic_response

    token = await issue_verification_token(
        redis=redis,
        user_id=user.id,
        enforce_cooldown=True,
    )

    if token:
        background_tasks.add_task(
            send_verification_email,
            user.email,
            verification_link(token),
        )

    return generic_response


@router.get(
    "/verify-email",
    response_class=HTMLResponse,
)
async def verify_email(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    redis = request.app.state.redis

    user_id = await get_verification_user_id(
        redis=redis,
        token=token,
    )

    if user_id is None:
        return HTMLResponse(
            content=(
                "<h2>The link is invalid or has expired.</h2>"
                '<p><a href="/auth/register">Back to registration</a></p>'
            ),
            status_code=400,
        )

    user = db.get(
        models.User,
        user_id,
    )

    if user is None:
        return HTMLResponse(
            content=(
                "<h2>Account not found.</h2>"
                '<p><a href="/auth/register">Back to registration</a></p>'
            ),
            status_code=404,
        )

    if not getattr(
        user,
        "email_verified",
        False,
    ):
        user.email_verified = True

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    await consume_verification_token(
        redis=redis,
        token=token,
        user_id=user.id,
    )

    return HTMLResponse(
        content=(
            "<h2>Email verified.</h2>"
            '<p><a href="/auth/login">Sign in to your account</a></p>'
        ),
        status_code=200,
    )


@router.post("/login")
async def login(
    data: schemas.UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        data.csrf_token,
    )

    redis = request.app.state.redis
    client_ip = get_client_ip(
        request
    )

    existing_block = await get_login_block(
        redis=redis,
        username=data.username,
        client_ip=client_ip,
    )

    if existing_block is not None:
        raise_login_blocked(
            existing_block
        )

    db_user = (
        db.query(models.User)
        .filter(
            models.User.username
            == data.username
        )
        .first()
    )

    password_is_valid = verify_password_or_dummy(
        data.password,
        (
            db_user.hashed_password
            if db_user is not None
            else None
        ),
    )

    if not password_is_valid:
        new_block = await record_failed_login(
            redis=redis,
            username=data.username,
            client_ip=client_ip,
        )

        if new_block is not None:
            raise_login_blocked(
                new_block
            )

        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid username or password"
            ),
        )

    if not getattr(
        db_user,
        "email_verified",
        True,
    ):
        raise HTTPException(
            status_code=403,
            detail="Verify your email before signing in",
        )

    if not db_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is disabled",
        )

    old_session_id = (
        request.cookies.get(
            "session_id"
        )
    )

    if old_session_id:
        await delete_session(
            redis,
            old_session_id,
        )

    session_id = await create_session(
        redis,
        db_user.id,
    )

    # Clear the account-specific counter only after
    # the session was successfully created.
    await clear_login_user_failures(
        redis=redis,
        username=data.username,
    )

    response = JSONResponse(
        {
            "redirect_url":
            "/auth/welcome"
        }
    )

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=use_secure_cookie(request),
        samesite="Lax",
        max_age=SESSION_COOKIE_MAX_AGE,
        path="/",
    )

    csrf_token = generate_csrf_token()

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=use_secure_cookie(request),
        samesite="Lax",
        path="/",
    )

    return response


@router.get(
    "/login",
    response_class=HTMLResponse,
)
async def get_login(
    request: Request,
):
    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
        },
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=use_secure_cookie(request),
        samesite="Lax",
        path="/",
    )

    return response


@router.get(
    "/register",
    response_class=HTMLResponse,
)
async def get_register(
    request: Request,
):
    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        request,
        "register.html",
        {
            "request": request,
            "csrf_token": csrf_token,
        },
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=use_secure_cookie(request),
        samesite="Lax",
        path="/",
    )

    return response


@router.get(
    "/profile",
    response_class=HTMLResponse,
)
async def get_profile_page(
    request: Request,
    current_user: Optional[
        models.User
    ] = Depends(
        get_current_user_optional
    ),
):
    if current_user is None:
        return RedirectResponse(
            url="/auth/login",
            status_code=303,
        )

    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "profile": (
                current_user.profile
            ),
            "csrf_token": csrf_token,
        },
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=use_secure_cookie(request),
        samesite="Lax",
        path="/",
    )

    return response


@router.post("/profile")
async def update_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    username: Optional[str] = Form(
        None
    ),
    email: Optional[str] = Form(
        None
    ),
    current_password: Optional[str] = Form(
        None
    ),
    password: Optional[str] = Form(
        None
    ),
    gender: Optional[str] = Form(
        None
    ),
    weight: Optional[float] = Form(
        None
    ),
    height: Optional[float] = Form(
        None
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_current_user
    ),
):
    form_data = await request.form()

    check_csrf(
        request.cookies.get(
            "csrf_token"
        ),
        form_data.get(
            "csrf_token"
        ),
    )

    normalized_email = None

    if email:
        normalized_email = (
            email.strip().lower()
        )

    email_changed = bool(
        normalized_email
        and normalized_email
        != current_user.email.lower()
    )

    password_changed = bool(
        password
    )

    sensitive_change = (
        email_changed
        or password_changed
    )

    if sensitive_change:
        if (
            not current_password
            or not verify_password(
                current_password,
                current_user.hashed_password,
            )
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "To change your email or password, "
                    "enter your current password"
                ),
            )

    if (
        username
        and username
        != current_user.username
    ):
        if not is_username_valid(
            username
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid "
                    "username"
                ),
            )

        username_exists = (
            db.query(models.User)
            .filter(
                models.User.username
                == username,
                models.User.id
                != current_user.id,
            )
            .first()
        )

        if username_exists:
            raise HTTPException(
                status_code=400,
                detail="Username is already taken",
            )

        current_user.username = username

    if email_changed:
        email_exists = (
            db.query(models.User)
            .filter(
                func.lower(
                    models.User.email
                )
                == normalized_email,
                models.User.id
                != current_user.id,
            )
            .first()
        )

        if email_exists:
            raise HTTPException(
                status_code=400,
                detail="Email is already taken",
            )

        current_user.email = (
            normalized_email
        )
        current_user.email_verified = False

    if password_changed:
        if len(password) < 12:
            raise HTTPException(
                status_code=400,
                detail=(
                    "New password must contain at least "
                    "12 characters"
                ),
            )

        if len(password) > 64:
            raise HTTPException(
                status_code=400,
                detail=(
                    "New password is too long"
                ),
            )

        current_user.hashed_password = (
            get_password_hash(
                password
            )
        )

    profile = current_user.profile

    if profile is None:
        profile = models.UserProfile(
            user_id=current_user.id
        )
        db.add(profile)

    profile.gender = gender or None
    profile.weight = weight
    profile.height = height

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Username or email is already taken"
            ),
        )

    verification_required = False

    if email_changed:
        token = await issue_verification_token(
            redis=request.app.state.redis,
            user_id=current_user.id,
            enforce_cooldown=False,
        )

        if token:
            background_tasks.add_task(
                send_verification_email,
                current_user.email,
                verification_link(token),
            )

        verification_required = True

    if sensitive_change:
        await delete_user_session(
            request.app.state.redis,
            current_user.id,
        )

        response = JSONResponse(
            {
                "message": (
                    "Changes saved. "
                    "Please sign in again."
                ),
                "session_invalidated": True,
                "verification_required": (
                    verification_required
                ),
            }
        )

        response.delete_cookie(
            "session_id",
            path="/",
        )
        response.delete_cookie(
            "csrf_token",
            path="/",
        )

        return response

    return {
        "message": "Changes saved",
        "session_invalidated": False,
    }


@router.post("/logout")
async def logout(
    request: Request,
    csrf_token: str = Form(...),
    session_id: Optional[str] = Cookie(
        None
    ),
):
    check_csrf(
        request.cookies.get(
            "csrf_token"
        ),
        csrf_token,
    )

    if session_id:
        await delete_session(
            request.app.state.redis,
            session_id,
        )

    response = RedirectResponse(
        url="/",
        status_code=303,
    )

    response.delete_cookie(
        "session_id",
        path="/",
    )

    response.delete_cookie(
        "csrf_token",
        path="/",
    )

    return response
