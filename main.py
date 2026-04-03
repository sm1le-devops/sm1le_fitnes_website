import os
import json
import logging
from typing import Optional

from fastapi import FastAPI, Request, Depends, Cookie, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_limiter import FastAPILimiter

from redis.asyncio import Redis
from sqlalchemy.orm import Session

# Импорты ваших модулей
from database import Base, engine, get_db
from models import User
from routers import auth, auth_api, password_reset

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Создание таблиц
Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.filters["tojson"] = lambda data: json.dumps(data, ensure_ascii=False)

# --- Startup/Shutdown ---
@app.on_event("startup")
async def startup():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        app.state.redis = redis_client
        await FastAPILimiter.init(redis_client)
        logging.info("Redis подключен.")
    except Exception as e:
        logging.error(f"Redis не доступен: {e}")

@app.on_event("shutdown")
async def shutdown():
    if hasattr(app.state, "redis"):
        await app.state.redis.close()

# --- CORS ---
origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
if RENDER_URL:
    clean_url = RENDER_URL.rstrip('/')
    origins.extend([clean_url, clean_url.replace("https://", "http://")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Routers ---
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(auth_api.router)
app.include_router(password_reset.router, prefix="/auth", tags=["Password Reset"])

# --- Logic ---
def get_plans_data():
    try:
        with open("plans.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка JSON: {e}")
        return {}

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/plans/{plan_id}", response_class=HTMLResponse)
async def get_plan_page(request: Request, plan_id: str):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="План не найден")
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, "plan": plans[plan_id], "plan_id": plan_id
    })

@app.get("/course/{plan_id}", response_class=HTMLResponse)
async def get_course_view(
    request: Request, 
    plan_id: str, 
    db: Session = Depends(get_db), 
    username: Optional[str] = Cookie(None)
):
    if not username:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse(url="/auth/register", status_code=303)
    
    # Проверка купленных планов
    purchased = user.purchased_plans.split(",") if user.purchased_plans else []
    if plan_id not in purchased:
        return RedirectResponse(url=f"/plans/{plan_id}?error=not_paid", status_code=303)
    
    plans = get_plans_data()
    return templates.TemplateResponse("course_view.html", {
        "request": request, "plan": plans.get(plan_id), "plan_id": plan_id
    })