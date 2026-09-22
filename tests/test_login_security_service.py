import pytest

from services.login_security_service import (
    LOGIN_IP_FAIL_LIMIT,
    LOGIN_IP_FAIL_WINDOW_SECONDS,
    LOGIN_USER_FAIL_LIMIT,
    LOGIN_USER_FAIL_WINDOW_SECONDS,
    build_login_ip_fail_key,
    build_login_user_fail_key,
    clear_login_user_failures,
    get_login_block,
    record_failed_login,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(
        self,
        key,
        value,
        ex=None,
        nx=False,
    ):
        if nx and key in self.values:
            return False

        self.values[key] = str(value)

        if ex is not None:
            self.ttls[key] = int(ex)

        return True

    async def incr(self, key):
        value = int(
            self.values.get(key, "0")
        ) + 1

        self.values[key] = str(value)

        return value

    async def expire(
        self,
        key,
        seconds,
    ):
        if key not in self.values:
            return False

        self.ttls[key] = int(seconds)

        return True

    async def ttl(self, key):
        if key not in self.values:
            return -2

        return self.ttls.get(
            key,
            -1,
        )

    async def delete(self, *keys):
        deleted = 0

        for key in keys:
            if key in self.values:
                deleted += 1

            self.values.pop(
                key,
                None,
            )
            self.ttls.pop(
                key,
                None,
            )

        return deleted


@pytest.mark.anyio
async def test_first_failed_login_sets_user_and_ip_ttl():
    redis = FakeRedis()

    block = await record_failed_login(
        redis=redis,
        username="admin",
        client_ip="203.0.113.10",
    )

    assert block is None

    user_key = build_login_user_fail_key(
        "admin"
    )
    ip_key = build_login_ip_fail_key(
        "203.0.113.10"
    )

    assert await redis.get(user_key) == "1"
    assert await redis.get(ip_key) == "1"

    assert (
        await redis.ttl(user_key)
        == LOGIN_USER_FAIL_WINDOW_SECONDS
    )
    assert (
        await redis.ttl(ip_key)
        == LOGIN_IP_FAIL_WINDOW_SECONDS
    )


@pytest.mark.anyio
async def test_username_limit_blocks_after_threshold():
    redis = FakeRedis()

    block = None

    for _ in range(
        LOGIN_USER_FAIL_LIMIT
    ):
        block = await record_failed_login(
            redis=redis,
            username="admin",
            client_ip="203.0.113.11",
        )

    assert block is not None
    assert block.scope == "user"
    assert block.retry_after > 0

    existing = await get_login_block(
        redis=redis,
        username="admin",
        client_ip="203.0.113.11",
    )

    assert existing is not None
    assert existing.scope == "user"


@pytest.mark.anyio
async def test_ip_limit_blocks_username_spraying():
    redis = FakeRedis()

    block = None

    for index in range(
        LOGIN_IP_FAIL_LIMIT
    ):
        block = await record_failed_login(
            redis=redis,
            username=f"user-{index}",
            client_ip="203.0.113.12",
        )

    assert block is not None
    assert block.scope == "ip"
    assert block.retry_after > 0


@pytest.mark.anyio
async def test_success_clears_username_counter_only():
    redis = FakeRedis()

    username = "admin"
    client_ip = "203.0.113.13"

    await record_failed_login(
        redis=redis,
        username=username,
        client_ip=client_ip,
    )

    user_key = build_login_user_fail_key(
        username
    )
    ip_key = build_login_ip_fail_key(
        client_ip
    )

    await clear_login_user_failures(
        redis=redis,
        username=username,
    )

    assert await redis.get(user_key) is None

    # We intentionally preserve IP-wide abuse history.
    assert await redis.get(ip_key) == "1"


@pytest.mark.anyio
async def test_username_counter_is_case_insensitive():
    redis = FakeRedis()

    await record_failed_login(
        redis=redis,
        username="Admin",
        client_ip="203.0.113.14",
    )

    key_lower = build_login_user_fail_key(
        "admin"
    )
    key_mixed = build_login_user_fail_key(
        "  AdMiN  "
    )

    assert key_lower == key_mixed
    assert await redis.get(key_lower) == "1"


@pytest.mark.anyio
async def test_fixed_window_ttl_is_not_refreshed_on_each_failure():
    redis = FakeRedis()

    key = build_login_user_fail_key(
        "admin"
    )

    await record_failed_login(
        redis=redis,
        username="admin",
        client_ip="203.0.113.15",
    )

    redis.ttls[key] = 321

    await record_failed_login(
        redis=redis,
        username="admin",
        client_ip="203.0.113.15",
    )

    assert await redis.ttl(key) == 321
