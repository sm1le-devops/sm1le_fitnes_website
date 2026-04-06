import os
import json
import stripe
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
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
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
async def root(request: Request, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    user_data = None
    if username:
        user = db.query(User).filter(User.username == username).first()
        if user:
            user_data = {
                "username": user.username,
                "purchased_plans": user.purchased_plans.split(",") if user.purchased_plans else []
            }
    
    # Получаем данные планов для отображения на главной
    plans = get_plans_data()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_data,
        "plans": plans  # Теперь в index.html заработает цикл {% for plan_id, plan in plans.items() %}
    })
    
@app.get("/auth/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    user_data = None
    if username:
        user = db.query(User).filter(User.username == username).first()
        if user:
            user_data = {
                "username": user.username,
                "purchased_plans": user.purchased_plans.split(",") if user.purchased_plans else []
            }
    
    # Загружаем планы, чтобы они отобразились в списке на странице welcome
    plans = get_plans_data()
    
    return templates.TemplateResponse("welcome.html", {
        "request": request,
        "user": user_data,
        "plans": plans
    })
    
@app.get("/plans/{plan_id}", response_class=HTMLResponse)
async def get_plan_page(request: Request, plan_id: str):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="План не найден")
    
    # Добавляем STRIPE_PUBLISHABLE_KEY в контекст шаблона
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, 
        "plan": plans[plan_id], 
        "plan_id": plan_id,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY 
    })




@app.post("/create-checkout-session/{plan_id}")
async def create_checkout_session(plan_id: str, username: Optional[str] = Cookie(None)):
    if not username:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    
    plans = get_plans_data()
    plan = plans.get(plan_id)
    
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")

    # Превращаем цену "2600" в число 260000 (для Stripe)
    price_in_cents = int(float(plan["price"]) * 100)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'rub', # Или 'usd'
                    'product_data': {'name': plan['title']},
                    'unit_amount': price_in_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{os.getenv('YOUR_DOMAIN')}/payment-success?plan_id={plan_id}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('YOUR_DOMAIN')}/plans/{plan_id}",
        )
        return {"id": checkout_session.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/payment-success")
async def payment_success(plan_id: str, session_id: str, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    if not username: 
        return RedirectResponse("/")
    
    try:
        # 1. Проверяем сессию в Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            raise HTTPException(status_code=400, detail="Оплата не подтверждена")
            
        # 2. Только если оплачено, добавляем курс
        user = db.query(User).filter(User.username == username).first()
        if user:
            current_plans = (user.purchased_plans or "").split(",")
            if plan_id not in current_plans:
                current_plans.append(plan_id)
                user.purchased_plans = ",".join(filter(None, current_plans))
                db.commit()
    except Exception as e:
        logging.error(f"Ошибка проверки платежа: {e}")
        return RedirectResponse(url=f"/course/{plan_id}?error=payment_failed")
    
    return RedirectResponse(url=f"/course/{plan_id}")