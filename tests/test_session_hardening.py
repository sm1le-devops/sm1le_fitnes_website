import pytest

from services.session_service import (
    SESSION_ABSOLUTE_TTL_SECONDS,
    SESSION_IDLE_TTL_SECONDS,
    build_session_absolute_key,
    build_session_key,
    build_user_session_key,
    create_session,
    delete_session,
    delete_user_session,
    get_session_user_id,
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
async def test_create_session_has_idle_and_absolute_expiration():
    redis = FakeRedis()

    session_id = await create_session(
        redis,
        42,
    )

    session_key = build_session_key(
        session_id
    )
    absolute_key = (
        build_session_absolute_key(
            session_id
        )
    )
    user_key = build_user_session_key(
        42
    )

    assert redis.values[session_key] == "42"
    assert redis.values[absolute_key] == "42"
    assert redis.values[user_key] == session_id

    assert (
        redis.ttls[session_key]
        == SESSION_IDLE_TTL_SECONDS
    )
    assert (
        redis.ttls[absolute_key]
        == SESSION_ABSOLUTE_TTL_SECONDS
    )
    assert (
        redis.ttls[user_key]
        == SESSION_ABSOLUTE_TTL_SECONDS
    )


@pytest.mark.anyio
async def test_new_login_rotates_previous_session():
    redis = FakeRedis()

    first = await create_session(
        redis,
        42,
    )
    second = await create_session(
        redis,
        42,
    )

    assert first != second

    assert (
        await redis.get(
            build_session_key(first)
        )
        is None
    )
    assert (
        await redis.get(
            build_session_absolute_key(first)
        )
        is None
    )

    assert (
        await redis.get(
            build_user_session_key(42)
        )
        == second
    )


@pytest.mark.anyio
async def test_activity_refreshes_only_idle_timeout():
    redis = FakeRedis()

    session_id = await create_session(
        redis,
        42,
    )

    session_key = build_session_key(
        session_id
    )
    absolute_key = (
        build_session_absolute_key(
            session_id
        )
    )

    redis.ttls[session_key] = 10
    redis.ttls[absolute_key] = 123

    user_id = await get_session_user_id(
        redis,
        session_id,
    )

    assert user_id == 42

    assert (
        redis.ttls[session_key]
        == SESSION_IDLE_TTL_SECONDS
    )

    # Absolute lifetime must never slide.
    assert redis.ttls[absolute_key] == 123


@pytest.mark.anyio
async def test_rotated_stale_session_is_rejected():
    redis = FakeRedis()

    stale = await create_session(
        redis,
        42,
    )

    await redis.set(
        build_user_session_key(42),
        "different-session",
        ex=SESSION_ABSOLUTE_TTL_SECONDS,
    )

    user_id = await get_session_user_id(
        redis,
        stale,
    )

    assert user_id is None

    assert (
        await redis.get(
            build_session_key(stale)
        )
        is None
    )


@pytest.mark.anyio
async def test_delete_session_removes_all_session_keys():
    redis = FakeRedis()

    session_id = await create_session(
        redis,
        42,
    )

    await delete_session(
        redis,
        session_id,
    )

    assert (
        await redis.get(
            build_session_key(session_id)
        )
        is None
    )
    assert (
        await redis.get(
            build_session_absolute_key(
                session_id
            )
        )
        is None
    )
    assert (
        await redis.get(
            build_user_session_key(42)
        )
        is None
    )


@pytest.mark.anyio
async def test_delete_user_session_logs_user_out_everywhere():
    redis = FakeRedis()

    session_id = await create_session(
        redis,
        42,
    )

    await delete_user_session(
        redis,
        42,
    )

    assert (
        await redis.get(
            build_session_key(session_id)
        )
        is None
    )
    assert (
        await redis.get(
            build_session_absolute_key(
                session_id
            )
        )
        is None
    )
    assert (
        await redis.get(
            build_user_session_key(42)
        )
        is None
    )


@pytest.mark.anyio
async def test_legacy_session_is_upgraded_on_first_use():
    redis = FakeRedis()

    session_id = "legacy-session"

    await redis.set(
        build_session_key(
            session_id
        ),
        42,
        ex=123,
    )
    await redis.set(
        build_user_session_key(42),
        session_id,
        ex=123,
    )

    user_id = await get_session_user_id(
        redis,
        session_id,
    )

    assert user_id == 42

    assert (
        await redis.get(
            build_session_absolute_key(
                session_id
            )
        )
        == "42"
    )
