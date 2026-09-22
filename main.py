import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis

from core.config import settings
from routers import auth, courses, pages, password_reset, payments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    await redis_client.ping()

    app.state.redis = redis_client
    await FastAPILimiter.init(redis_client)

    logging.info("Redis connected")

    try:
        yield
    finally:
        await redis_client.aclose()
        logging.info("Redis disconnected")


app = FastAPI(
    title="sm1le.fitness API",
    lifespan=lifespan,
)

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if settings.render_external_url:
    origins.append(settings.render_external_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(password_reset.router, prefix="/auth", tags=["Password Reset"])
app.include_router(pages.router, tags=["Pages"])
app.include_router(courses.router, tags=["Courses"])
app.include_router(payments.router, tags=["Payments"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}