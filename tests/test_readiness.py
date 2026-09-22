import asyncio

from sqlalchemy import create_engine

from core import readiness


class HealthyRedis:
    async def ping(self) -> bool:
        return True


class BrokenRedis:
    async def ping(self) -> bool:
        raise ConnectionError(
            "Redis unavailable"
        )


def test_database_readiness_check():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    try:
        assert (
            readiness._check_database_sync(
                engine
            )
            is True
        )

    finally:
        engine.dispose()


def test_redis_readiness_check():
    result = asyncio.run(
        readiness.check_redis(
            HealthyRedis()
        )
    )

    assert result is True


def test_broken_redis_is_not_ready():
    result = asyncio.run(
        readiness.check_redis(
            BrokenRedis()
        )
    )

    assert result is False


def test_combined_readiness(
    monkeypatch,
):
    async def database_ok(
        _engine,
    ):
        return True

    monkeypatch.setattr(
        readiness,
        "check_database",
        database_ok,
    )

    result = asyncio.run(
        readiness.get_readiness(
            engine=object(),
            redis_client=HealthyRedis(),
        )
    )

    assert result == {
        "database": "ok",
        "redis": "ok",
    }