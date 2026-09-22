from secrets import compare_digest
from typing import Optional

from fastapi import (
    APIRouter,
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
from sqlalchemy.orm import Session

import models
import schemas

from core.security import (
    generate_csrf_token,
    get_password_hash,
    is_username_valid,
    validate_csrf_token,
    verify_password,
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
from services.session_service import (
    SESSION_TTL_SECONDS,
    create_session,
    delete_session,
)

router = APIRouter()
templates = Jinja2Templates(
    directory="templates"
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
            detail="Ошибка безопасности (CSRF)",
        )


def get_client_ip(
    request: Request,
) -> str:
    if request.client is None:
        return "unknown"

    return request.client.host or "unknown"


def raise_login_blocked(
    block: LoginBlock,
) -> None:
    raise HTTPException(
        status_code=429,
        detail=(
            "Слишком много попыток входа. "
            "Попробуйте позже."
        ),
        headers={
            "Retry-After": str(
                max(block.retry_after, 1)
            )
        },
    )


@router.post("/register")
def register(
    user: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        user.csrf_token,
    )

    if not is_username_valid(
        user.username
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Имя может содержать только "
                "буквы, цифры и '_'"
            ),
        )

    existing_user = (
        db.query(models.User)
        .filter(
            (
                models.User.username
                == user.username
            )
            | (
                models.User.email
                == user.email
            )
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail=(
                "Логин или Email уже заняты"
            ),
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(
            user.password
        ),
    )

    new_user.profile = models.UserProfile()

    db.add(new_user)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Логин или Email уже заняты"
            ),
        )

    return {
        "message": "Success"
    }


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

    password_is_valid = bool(
        db_user
        and verify_password(
            data.password,
            db_user.hashed_password,
        )
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
                "Неверный логин или пароль"
            ),
        )

    if not db_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Аккаунт отключён",
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
        secure=True,
        samesite="Lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )

    csrf_token = generate_csrf_token()

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=True,
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
        secure=True,
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
        secure=True,
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
        secure=(
            request.url.scheme
            == "https"
        ),
        samesite="Lax",
        path="/",
    )

    return response


@router.post("/profile")
async def update_profile(
    request: Request,
    username: Optional[str] = Form(
        None
    ),
    email: Optional[str] = Form(
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
                    "Некорректное имя "
                    "пользователя"
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
                detail=(
                    "Логин уже занят"
                ),
            )

        current_user.username = username

    if (
        email
        and email
        != current_user.email
    ):
        email_exists = (
            db.query(models.User)
            .filter(
                models.User.email
                == email,
                models.User.id
                != current_user.id,
            )
            .first()
        )

        if email_exists:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Email уже занят"
                ),
            )

        current_user.email = email

    if password:
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
                "Логин или Email уже заняты"
            ),
        )

    return {
        "message": "Данные сохранены"
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
