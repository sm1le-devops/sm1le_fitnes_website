import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
from core.request_logging import (
    RequestLoggingMiddleware,
)
from core.config import settings
from core.security_headers import (
    SecurityHeadersMiddleware,
    build_allowed_hosts,
)
from routers import (
    auth,
    courses,
    pages,
    password_reset,
    payments,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s [%(levelname)s] "
        "%(message)s"
    ),
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    await redis_client.ping()

    app.state.redis = redis_client

    await FastAPILimiter.init(
        redis_client
    )

    logging.info(
        "Redis connected"
    )

    try:
        yield

    finally:
        await redis_client.aclose()

        logging.info(
            "Redis disconnected"
        )


app = FastAPI(
    title="sm1le.fitness API",
    lifespan=lifespan,
)


allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if settings.render_external_url:
    allowed_origins.append(
        settings.render_external_url.rstrip(
            "/"
        )
    )

if (
    settings.your_domain
    and settings.your_domain.rstrip("/")
    not in allowed_origins
):
    allowed_origins.append(
        settings.your_domain.rstrip("/")
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
        "X-CSRF-Token",
    ],
    max_age=600,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=build_allowed_hosts(),
)

app.add_middleware(
    SecurityHeadersMiddleware,
)

app.add_middleware(
    RequestLoggingMiddleware,
)

app.mount(
    "/static",
    StaticFiles(
        directory="static"
    ),
    name="static",
)


app.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"],
)

app.include_router(
    password_reset.router,
    prefix="/auth",
    tags=["Password Reset"],
)

app.include_router(
    pages.router,
    tags=["Pages"],
)

app.include_router(
    courses.router,
    tags=["Courses"],
)

app.include_router(
    payments.router,
    tags=["Payments"],
)


@app.get(
    "/health",
    tags=["Health"],
)
async def health_check():
    return {
        "status": "ok"
    }
