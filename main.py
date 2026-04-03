from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
import os
import json
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
def get_plans_data():
    """Функция для чтения JSON файла"""
    try:
        with open("plans.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("Файл plans.json не найден в корне проекта!")
        return {}
    
@app.get("/plans/{plan_id}")
async def get_plan_page(request: Request, plan_id: str):
    plans = get_plans_data()
    
    # Проверяем, есть ли такой план в JSON
    if plan_id not in plans:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Программа тренировок не найдена")
    
    plan_data = plans[plan_id]
    
    # Возвращаем новую страницу плана (создадим её на следующем шаге)
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, 
        "plan": plan_data,
        "plan_id": plan_id
    })

# --- Root page ---
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})