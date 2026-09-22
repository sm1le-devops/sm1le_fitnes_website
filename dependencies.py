from typing import Optional

from fastapi import (
    Cookie,
    Depends,
    HTTPException,
    Request,
)
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.session_service import (
    get_session_user_id,
)


def get_redis(
    request: Request,
) -> Redis:
    redis = getattr(
        request.app.state,
        "redis",
        None,
    )

    if redis is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Authentication service "
                "unavailable"
            ),
        )

    return redis


async def get_current_user_optional(
    db: Session = Depends(
        get_db
    ),
    redis: Redis = Depends(
        get_redis
    ),
    session_id: Optional[str] = Cookie(
        None
    ),
) -> Optional[User]:
    if not session_id:
        return None

    user_id = await get_session_user_id(
        redis,
        session_id,
    )

    if user_id is None:
        return None

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:
        return None

    if not user.is_active:
        return None

    if not getattr(
        user,
        "email_verified",
        True,
    ):
        return None

    return user


async def require_current_user(
    user: Optional[User] = Depends(
        get_current_user_optional
    ),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    return user
