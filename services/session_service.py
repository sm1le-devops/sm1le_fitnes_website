import secrets


SESSION_TTL_SECONDS = 60 * 60 * 24
SESSION_KEY_PREFIX = "session:" 
USER_SESSION_KEY_PREFIX = "user_session:"



def generate_session_id() -> str:
    return secrets.token_urlsafe(32)

def build_session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def build_user_session_key(user_id: int) -> str:
    return f"{USER_SESSION_KEY_PREFIX}{user_id}"

async def create_session(redis, user_id: int) -> str:
    user_session_key = build_user_session_key(user_id)

    old_session_id = await redis.get(user_session_key)

    if old_session_id:
        old_session_key = build_session_key(old_session_id)
        await redis.delete(old_session_key)

    session_id = generate_session_id()
    session_key = build_session_key(session_id)

    await redis.set(
        session_key,
        user_id,
        ex=SESSION_TTL_SECONDS,
    )

    await redis.set(
        user_session_key,
        session_id,
        ex=SESSION_TTL_SECONDS,
    )

    return session_id

async def get_session_user_id(
    redis,
    session_id: str,
) -> int | None:
    key = build_session_key(session_id)

    user_id = await redis.get(key)

    if user_id is None:
        return None

    return int(user_id)

async def delete_session(redis, session_id: str) -> None:
    session_key = build_session_key(session_id)

    user_id = await redis.get(session_key)

    if user_id is None:
        return

    user_session_key = build_user_session_key(int(user_id))

    current_session_id = await redis.get(user_session_key)

    await redis.delete(session_key)

    if current_session_id == session_id:
        await redis.delete(user_session_key)
        
async def delete_user_session(
    redis,
    user_id: int,
) -> None:
    user_session_key = build_user_session_key(user_id)

    session_id = await redis.get(user_session_key)

    if session_id:
        session_key = build_session_key(session_id)
        await redis.delete(session_key)

    await redis.delete(user_session_key)