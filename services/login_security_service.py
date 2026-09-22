from dataclasses import dataclass
from hashlib import sha256


LOGIN_USER_FAIL_LIMIT = 10
LOGIN_USER_FAIL_WINDOW_SECONDS = 15 * 60

LOGIN_IP_FAIL_LIMIT = 20
LOGIN_IP_FAIL_WINDOW_SECONDS = 5 * 60


@dataclass(frozen=True)
class LoginBlock:
    retry_after: int
    scope: str


def normalize_username(username: str) -> str:
    return username.strip().casefold()


def _hash_identifier(value: str) -> str:
    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def build_login_user_fail_key(
    username: str,
) -> str:
    normalized = normalize_username(username)

    return (
        "login_fail:user:"
        f"{_hash_identifier(normalized)}"
    )


def build_login_ip_fail_key(
    client_ip: str,
) -> str:
    normalized = client_ip.strip() or "unknown"

    return (
        "login_fail:ip:"
        f"{_hash_identifier(normalized)}"
    )


async def _get_count(
    redis,
    key: str,
) -> int:
    value = await redis.get(key)

    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def _get_retry_after(
    redis,
    key: str,
    fallback: int,
) -> int:
    ttl = await redis.ttl(key)

    if ttl is None or ttl <= 0:
        return fallback

    return int(ttl)


async def _increment_with_fixed_window(
    redis,
    key: str,
    window_seconds: int,
) -> int:
    """
    Atomic-enough fixed-window counter without a permanent-key race:

    1. Try SET key=1 EX ttl NX.
    2. If another request already created it, INCR the existing key.

    The first write always has TTL attached.
    """

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

    # Defensive repair for a malformed old key that somehow lost TTL.
    if ttl is None or ttl < 0:
        await redis.expire(
            key,
            window_seconds,
        )

    return int(count)


async def get_login_block(
    redis,
    username: str,
    client_ip: str,
) -> LoginBlock | None:
    user_key = build_login_user_fail_key(
        username
    )
    ip_key = build_login_ip_fail_key(
        client_ip
    )

    user_count = await _get_count(
        redis,
        user_key,
    )
    ip_count = await _get_count(
        redis,
        ip_key,
    )

    blocks: list[LoginBlock] = []

    if user_count >= LOGIN_USER_FAIL_LIMIT:
        blocks.append(
            LoginBlock(
                retry_after=await _get_retry_after(
                    redis,
                    user_key,
                    LOGIN_USER_FAIL_WINDOW_SECONDS,
                ),
                scope="user",
            )
        )

    if ip_count >= LOGIN_IP_FAIL_LIMIT:
        blocks.append(
            LoginBlock(
                retry_after=await _get_retry_after(
                    redis,
                    ip_key,
                    LOGIN_IP_FAIL_WINDOW_SECONDS,
                ),
                scope="ip",
            )
        )

    if not blocks:
        return None

    # If both limits are active, the request is only useful again
    # after the longer remaining block has expired.
    return max(
        blocks,
        key=lambda item: item.retry_after,
    )


async def record_failed_login(
    redis,
    username: str,
    client_ip: str,
) -> LoginBlock | None:
    user_key = build_login_user_fail_key(
        username
    )
    ip_key = build_login_ip_fail_key(
        client_ip
    )

    user_count = await _increment_with_fixed_window(
        redis,
        user_key,
        LOGIN_USER_FAIL_WINDOW_SECONDS,
    )
    ip_count = await _increment_with_fixed_window(
        redis,
        ip_key,
        LOGIN_IP_FAIL_WINDOW_SECONDS,
    )

    blocks: list[LoginBlock] = []

    if user_count >= LOGIN_USER_FAIL_LIMIT:
        blocks.append(
            LoginBlock(
                retry_after=await _get_retry_after(
                    redis,
                    user_key,
                    LOGIN_USER_FAIL_WINDOW_SECONDS,
                ),
                scope="user",
            )
        )

    if ip_count >= LOGIN_IP_FAIL_LIMIT:
        blocks.append(
            LoginBlock(
                retry_after=await _get_retry_after(
                    redis,
                    ip_key,
                    LOGIN_IP_FAIL_WINDOW_SECONDS,
                ),
                scope="ip",
            )
        )

    if not blocks:
        return None

    return max(
        blocks,
        key=lambda item: item.retry_after,
    )


async def clear_login_user_failures(
    redis,
    username: str,
) -> None:
    """
    Clear only the account-specific failed-login counter after
    a successful login.

    We intentionally keep the IP counter. Otherwise an attacker
    could reset an IP-wide brute-force counter by successfully
    logging into any account they control.
    """

    await redis.delete(
        build_login_user_fail_key(
            username
        )
    )
