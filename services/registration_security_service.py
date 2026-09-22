from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe


REGISTER_IP_LIMIT = 5
REGISTER_IP_WINDOW_SECONDS = 30 * 60

VERIFY_RESEND_IP_LIMIT = 10
VERIFY_RESEND_IP_WINDOW_SECONDS = 60 * 60

VERIFY_TOKEN_TTL_SECONDS = 60 * 60
VERIFY_RESEND_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class RateLimitBlock:
    retry_after: int
    scope: str


def _hash_identifier(value: str) -> str:
    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def registration_ip_key(
    client_ip: str,
) -> str:
    normalized = client_ip.strip() or "unknown"

    return (
        "register:ip:"
        f"{_hash_identifier(normalized)}"
    )


def verification_resend_ip_key(
    client_ip: str,
) -> str:
    normalized = client_ip.strip() or "unknown"

    return (
        "verify_email:resend_ip:"
        f"{_hash_identifier(normalized)}"
    )


def verification_token_hash(
    token: str,
) -> str:
    return _hash_identifier(token)


def verification_token_key(
    token: str,
) -> str:
    return (
        "verify_email:token:"
        f"{verification_token_hash(token)}"
    )


def verification_token_key_from_hash(
    token_hash: str,
) -> str:
    return (
        "verify_email:token:"
        f"{token_hash}"
    )


def verification_user_key(
    user_id: int,
) -> str:
    return f"verify_email:user:{user_id}"


def verification_cooldown_key(
    user_id: int,
) -> str:
    return (
        f"verify_email:cooldown:{user_id}"
    )


async def _increment_fixed_window(
    redis,
    key: str,
    window_seconds: int,
) -> int:
    created = await redis.set(
        key,
        "1",
        ex=window_seconds,
        nx=True,
    )

    if created:
        return 1

    count = await redis.incr(key)

    ttl = await redis.ttl(key)

    if ttl is None or ttl < 0:
        await redis.expire(
            key,
            window_seconds,
        )

    return int(count)


async def _retry_after(
    redis,
    key: str,
    fallback: int,
) -> int:
    ttl = await redis.ttl(key)

    if ttl is None or ttl <= 0:
        return fallback

    return int(ttl)


async def consume_registration_attempt(
    redis,
    client_ip: str,
) -> RateLimitBlock | None:
    key = registration_ip_key(
        client_ip
    )

    count = await _increment_fixed_window(
        redis,
        key,
        REGISTER_IP_WINDOW_SECONDS,
    )

    if count <= REGISTER_IP_LIMIT:
        return None

    return RateLimitBlock(
        retry_after=await _retry_after(
            redis,
            key,
            REGISTER_IP_WINDOW_SECONDS,
        ),
        scope="register_ip",
    )


async def consume_verification_resend_attempt(
    redis,
    client_ip: str,
) -> RateLimitBlock | None:
    key = verification_resend_ip_key(
        client_ip
    )

    count = await _increment_fixed_window(
        redis,
        key,
        VERIFY_RESEND_IP_WINDOW_SECONDS,
    )

    if count <= VERIFY_RESEND_IP_LIMIT:
        return None

    return RateLimitBlock(
        retry_after=await _retry_after(
            redis,
            key,
            VERIFY_RESEND_IP_WINDOW_SECONDS,
        ),
        scope="verification_resend_ip",
    )


async def issue_verification_token(
    redis,
    user_id: int,
    *,
    enforce_cooldown: bool,
) -> str | None:
    if enforce_cooldown:
        cooldown_created = await redis.set(
            verification_cooldown_key(
                user_id
            ),
            "1",
            ex=VERIFY_RESEND_COOLDOWN_SECONDS,
            nx=True,
        )

        if not cooldown_created:
            return None
    else:
        await redis.set(
            verification_cooldown_key(
                user_id
            ),
            "1",
            ex=VERIFY_RESEND_COOLDOWN_SECONDS,
        )

    old_token_hash = await redis.get(
        verification_user_key(
            user_id
        )
    )

    if old_token_hash:
        await redis.delete(
            verification_token_key_from_hash(
                old_token_hash
            )
        )

    token = token_urlsafe(32)
    token_hash = verification_token_hash(
        token
    )

    await redis.set(
        verification_token_key(token),
        user_id,
        ex=VERIFY_TOKEN_TTL_SECONDS,
    )

    await redis.set(
        verification_user_key(
            user_id
        ),
        token_hash,
        ex=VERIFY_TOKEN_TTL_SECONDS,
    )

    return token


async def get_verification_user_id(
    redis,
    token: str,
) -> int | None:
    value = await redis.get(
        verification_token_key(
            token
        )
    )

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def consume_verification_token(
    redis,
    token: str,
    user_id: int,
) -> None:
    await redis.delete(
        verification_token_key(
            token
        ),
        verification_user_key(
            user_id
        ),
        verification_cooldown_key(
            user_id
        ),
    )
