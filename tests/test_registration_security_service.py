import pytest

from services.registration_security_service import (
    REGISTER_IP_LIMIT,
    REGISTER_IP_WINDOW_SECONDS,
    VERIFY_RESEND_COOLDOWN_SECONDS,
    VERIFY_RESEND_IP_LIMIT,
    consume_registration_attempt,
    consume_verification_resend_attempt,
    consume_verification_token,
    get_verification_user_id,
    issue_verification_token,
    registration_ip_key,
    verification_cooldown_key,
    verification_token_key,
    verification_user_key,
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

    async def ttl(self, key):
        if key not in self.values:
            return -2

        return self.ttls.get(
            key,
            -1,
        )

    async def expire(
        self,
        key,
        seconds,
    ):
        if key not in self.values:
            return False

        self.ttls[key] = int(seconds)
        return True

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
async def test_registration_ip_limit_blocks_on_threshold():
    redis = FakeRedis()
    block = None

    for _ in range(
        REGISTER_IP_LIMIT
    ):
        block = await consume_registration_attempt(
            redis=redis,
            client_ip="203.0.113.20",
        )

    assert block is None

    block = await consume_registration_attempt(
        redis=redis,
        client_ip="203.0.113.20",
    )

    assert block is not None
    assert block.scope == "register_ip"
    assert block.retry_after > 0

    key = registration_ip_key(
        "203.0.113.20"
    )

    assert (
        await redis.ttl(key)
        == REGISTER_IP_WINDOW_SECONDS
    )


@pytest.mark.anyio
async def test_registration_ip_key_is_hashed():
    key = registration_ip_key(
        "203.0.113.21"
    )

    assert "203.0.113.21" not in key


@pytest.mark.anyio
async def test_resend_ip_limit_blocks():
    redis = FakeRedis()
    block = None

    for _ in range(
        VERIFY_RESEND_IP_LIMIT
    ):
        block = (
            await consume_verification_resend_attempt(
                redis=redis,
                client_ip="203.0.113.22",
            )
        )

    assert block is None

    block = await consume_verification_resend_attempt(
        redis=redis,
        client_ip="203.0.113.22",
    )

    assert block is not None
    assert (
        block.scope
        == "verification_resend_ip"
    )


@pytest.mark.anyio
async def test_issue_verification_token_is_hashed_and_has_ttl():
    redis = FakeRedis()

    token = await issue_verification_token(
        redis=redis,
        user_id=42,
        enforce_cooldown=False,
    )

    assert token is not None

    token_key = verification_token_key(
        token
    )

    assert token not in token_key
    assert await redis.get(token_key) == "42"

    user_pointer = await redis.get(
        verification_user_key(42)
    )

    assert user_pointer is not None
    assert token not in user_pointer


@pytest.mark.anyio
async def test_resend_cooldown_prevents_immediate_second_token():
    redis = FakeRedis()

    first = await issue_verification_token(
        redis=redis,
        user_id=43,
        enforce_cooldown=False,
    )

    second = await issue_verification_token(
        redis=redis,
        user_id=43,
        enforce_cooldown=True,
    )

    assert first is not None
    assert second is None

    assert (
        await redis.ttl(
            verification_cooldown_key(43)
        )
        == VERIFY_RESEND_COOLDOWN_SECONDS
    )


@pytest.mark.anyio
async def test_new_verification_token_revokes_old_token():
    redis = FakeRedis()

    first = await issue_verification_token(
        redis=redis,
        user_id=44,
        enforce_cooldown=False,
    )

    await redis.delete(
        verification_cooldown_key(44)
    )

    second = await issue_verification_token(
        redis=redis,
        user_id=44,
        enforce_cooldown=True,
    )

    assert first is not None
    assert second is not None
    assert first != second

    assert (
        await get_verification_user_id(
            redis=redis,
            token=first,
        )
        is None
    )

    assert (
        await get_verification_user_id(
            redis=redis,
            token=second,
        )
        == 44
    )


@pytest.mark.anyio
async def test_consume_verification_token_removes_all_keys():
    redis = FakeRedis()

    token = await issue_verification_token(
        redis=redis,
        user_id=45,
        enforce_cooldown=False,
    )

    assert token is not None

    await consume_verification_token(
        redis=redis,
        token=token,
        user_id=45,
    )

    assert (
        await redis.get(
            verification_token_key(token)
        )
        is None
    )
    assert (
        await redis.get(
            verification_user_key(45)
        )
        is None
    )
    assert (
        await redis.get(
            verification_cooldown_key(45)
        )
        is None
    )
