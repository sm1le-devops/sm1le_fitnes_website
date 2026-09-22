import secrets


# A session dies after 2 hours without activity.
SESSION_IDLE_TTL_SECONDS = 60 * 60 * 2

# Even an actively used session must be recreated after 7 days.
SESSION_ABSOLUTE_TTL_SECONDS = 60 * 60 * 24 * 7

# Browser cookie must never outlive the server-side absolute session.
SESSION_COOKIE_MAX_AGE = SESSION_ABSOLUTE_TTL_SECONDS

# Backward-compatible name used by older imports/tests.
SESSION_TTL_SECONDS = SESSION_COOKIE_MAX_AGE

SESSION_KEY_PREFIX = "session:"
SESSION_ABSOLUTE_KEY_PREFIX = "session_absolute:"
USER_SESSION_KEY_PREFIX = "user_session:"


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def build_session_key(
    session_id: str,
) -> str:
    return (
        f"{SESSION_KEY_PREFIX}"
        f"{session_id}"
    )


def build_session_absolute_key(
    session_id: str,
) -> str:
    return (
        f"{SESSION_ABSOLUTE_KEY_PREFIX}"
        f"{session_id}"
    )


def build_user_session_key(
    user_id: int,
) -> str:
    return (
        f"{USER_SESSION_KEY_PREFIX}"
        f"{user_id}"
    )


async def create_session(
    redis,
    user_id: int,
) -> str:
    """
    One active session per user.

    A new login always rotates the session id and invalidates the
    previously active session.
    """

    user_session_key = (
        build_user_session_key(
            user_id
        )
    )

    old_session_id = await redis.get(
        user_session_key
    )

    if old_session_id:
        await redis.delete(
            build_session_key(
                old_session_id
            ),
            build_session_absolute_key(
                old_session_id
            ),
        )

    session_id = generate_session_id()

    await redis.set(
        build_session_key(
            session_id
        ),
        user_id,
        ex=SESSION_IDLE_TTL_SECONDS,
    )

    await redis.set(
        build_session_absolute_key(
            session_id
        ),
        user_id,
        ex=SESSION_ABSOLUTE_TTL_SECONDS,
    )

    await redis.set(
        user_session_key,
        session_id,
        ex=SESSION_ABSOLUTE_TTL_SECONDS,
    )

    return session_id


async def get_session_user_id(
    redis,
    session_id: str,
) -> int | None:
    """
    Validate a session and refresh only its inactivity timeout.

    The absolute timeout is intentionally never refreshed.
    """

    session_key = build_session_key(
        session_id
    )
    absolute_key = (
        build_session_absolute_key(
            session_id
        )
    )

    user_id = await redis.get(
        session_key
    )

    if user_id is None:
        return None

    try:
        parsed_user_id = int(
            user_id
        )
    except (TypeError, ValueError):
        await redis.delete(
            session_key,
            absolute_key,
        )
        return None

    absolute_user_id = await redis.get(
        absolute_key
    )

    if absolute_user_id is None:
        # Transitional support for sessions created before the
        # absolute-expiration key existed. New sessions always
        # create this key at login.
        await redis.set(
            absolute_key,
            parsed_user_id,
            ex=(
                SESSION_ABSOLUTE_TTL_SECONDS
            ),
        )
    else:
        try:
            parsed_absolute_user_id = int(
                absolute_user_id
            )
        except (TypeError, ValueError):
            await delete_session(
                redis,
                session_id,
            )
            return None

        if (
            parsed_absolute_user_id
            != parsed_user_id
        ):
            await delete_session(
                redis,
                session_id,
            )
            return None

    user_session_key = (
        build_user_session_key(
            parsed_user_id
        )
    )

    active_session_id = await redis.get(
        user_session_key
    )

    if active_session_id is None:
        # Transitional support for legacy/test sessions.
        await redis.set(
            user_session_key,
            session_id,
            ex=(
                SESSION_ABSOLUTE_TTL_SECONDS
            ),
        )
    elif active_session_id != session_id:
        # Another login rotated this user's session.
        await redis.delete(
            session_key,
            absolute_key,
        )
        return None

    # Sliding inactivity timeout.
    await redis.set(
        session_key,
        parsed_user_id,
        ex=SESSION_IDLE_TTL_SECONDS,
    )

    return parsed_user_id


async def delete_session(
    redis,
    session_id: str,
) -> None:
    session_key = build_session_key(
        session_id
    )
    absolute_key = (
        build_session_absolute_key(
            session_id
        )
    )

    user_id = await redis.get(
        session_key
    )

    if user_id is None:
        user_id = await redis.get(
            absolute_key
        )

    await redis.delete(
        session_key,
        absolute_key,
    )

    if user_id is None:
        return

    try:
        parsed_user_id = int(
            user_id
        )
    except (TypeError, ValueError):
        return

    user_session_key = (
        build_user_session_key(
            parsed_user_id
        )
    )

    active_session_id = await redis.get(
        user_session_key
    )

    if active_session_id == session_id:
        await redis.delete(
            user_session_key
        )


async def delete_user_session(
    redis,
    user_id: int,
) -> None:
    """
    Invalidate the currently active session for this user.

    The project currently enforces one active session per user,
    so this is equivalent to "log out everywhere".
    """

    user_session_key = (
        build_user_session_key(
            user_id
        )
    )

    session_id = await redis.get(
        user_session_key
    )

    if session_id:
        await redis.delete(
            build_session_key(
                session_id
            ),
            build_session_absolute_key(
                session_id
            ),
        )

    await redis.delete(
        user_session_key
    )
