from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
import os
from database import Base, engine
from routers import auth, auth_api, password_reset
from fastapi.templating import Jinja2Templates
import logging
from models import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Redis init ---
redis_client: Redis | None = None

@app.on_event("startup")
async def startup():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    app.state.redis = redis_client  # сохраняем в app.state
    await FastAPILimiter.init(redis_client)


@app.on_event("shutdown")
async def shutdown():
    redis: Redis = app.state.redis
    if redis:
        await redis.close()


# --- CORS ---
origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

# Добавляем Render URL в список ДО инициализации мидлвары
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
if RENDER_EXTERNAL_URL:
    origins.append(RENDER_EXTERNAL_URL)
    # Удаляем лишний слеш в конце, если он есть, т.к. CORS чувствителен к нему
    clean_url = RENDER_EXTERNAL_URL.rstrip('/')
    if clean_url not in origins:
        origins.append(clean_url)
    # На всякий случай вариант с http
    origins.append(clean_url.replace("https://", "http://"))

# Теперь добавляем мидлвару ОДИН РАЗ с полным списком
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- Static files ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Routers ---
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(auth_api.router)
app.include_router(password_reset.router, prefix="/auth", tags=["Password Reset"])

# --- Root page ---
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
