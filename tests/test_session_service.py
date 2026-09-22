import asyncio

from services.session_service import (
    build_session_key,
    build_user_session_key,
    create_session,
    delete_session,
    delete_user_session,
    get_session_user_id,
)


def run(coro):
    return asyncio.run(coro)


def test_create_and_read_session(fake_redis):
    session_id = run(
        create_session(fake_redis, 123)
    )

    assert (
        run(
            get_session_user_id(
                fake_redis,
                session_id,
            )
        )
        == 123
    )


def test_new_session_invalidates_old_session(fake_redis):
    first = run(
        create_session(fake_redis, 123)
    )
    second = run(
        create_session(fake_redis, 123)
    )

    assert first != second

    assert (
        run(
            get_session_user_id(
                fake_redis,
                first,
            )
        )
        is None
    )
    assert (
        run(
            get_session_user_id(
                fake_redis,
                second,
            )
        )
        == 123
    )


def test_delete_session_removes_reverse_mapping(fake_redis):
    session_id = run(
        create_session(fake_redis, 7)
    )

    run(
        delete_session(
            fake_redis,
            session_id,
        )
    )

    assert (
        run(
            fake_redis.get(
                build_session_key(session_id)
            )
        )
        is None
    )
    assert (
        run(
            fake_redis.get(
                build_user_session_key(7)
            )
        )
        is None
    )


def test_delete_user_session(fake_redis):
    session_id = run(
        create_session(fake_redis, 9)
    )

    run(
        delete_user_session(
            fake_redis,
            9,
        )
    )

    assert (
        run(
            fake_redis.get(
                build_session_key(session_id)
            )
        )
        is None
    )
    assert (
        run(
            fake_redis.get(
                build_user_session_key(9)
            )
        )
        is None
    )
