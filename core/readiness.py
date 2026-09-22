import asyncio
import logging
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine


CHECK_TIMEOUT_SECONDS = 2.0


class RedisPingClient(Protocol):
    async def ping(self) -> bool:
        ...


def _check_database_sync(
    engine: Engine,
) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return True

    except Exception:
        logging.exception(
            "Readiness database check failed"
        )
        return False


async def check_database(
    engine: Engine,
) -> bool:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _check_database_sync,
                engine,
            ),
            timeout=CHECK_TIMEOUT_SECONDS,
        )

    except TimeoutError:
        logging.error(
            "Readiness database check timed out"
        )
        return False


async def check_redis(
    redis_client: RedisPingClient | None,
) -> bool:
    if redis_client is None:
        return False

    try:
        result = await asyncio.wait_for(
            redis_client.ping(),
            timeout=CHECK_TIMEOUT_SECONDS,
        )

        return bool(result)

    except TimeoutError:
        logging.error(
            "Readiness Redis check timed out"
        )
        return False

    except Exception:
        logging.exception(
            "Readiness Redis check failed"
        )
        return False


async def get_readiness(
    engine: Engine,
    redis_client: RedisPingClient | None,
) -> dict[str, str]:
    database_ok, redis_ok = await asyncio.gather(
        check_database(engine),
        check_redis(redis_client),
    )

    return {
        "database": (
            "ok"
            if database_ok
            else "unavailable"
        ),
        "redis": (
            "ok"
            if redis_ok
            else "unavailable"
        ),
    }