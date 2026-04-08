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
origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
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
async def get_plan_page(request: Request, plan_id: str, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="План не найден")
    
    is_purchased = False
    if username:
        user = db.query(User).filter(User.username == username).first()
        if user and plan_id in (user.purchased_plans or "").split(","):
            is_purchased = True
    
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, 
        "plan": plans[plan_id], 
        "plan_id": plan_id,
        "is_purchased": is_purchased, # Передаем статус
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY 
    })

@app.get("/course/{plan_id}", response_class=HTMLResponse)
async def get_course_view(request: Request, plan_id: str, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="Курс не найден")
    
    # 1. Проверяем, авторизован ли пользователь
    if not username:
        return RedirectResponse(url="/auth/login")
    
    user = db.query(User).filter(User.username == username).first()
    
    # 2. Проверяем, куплен ли этот курс (безопасность)
    purchased_plans = (user.purchased_plans or "").split(",") if user else []
    if plan_id not in purchased_plans:
        # Если не куплено, отправляем обратно на страницу описания плана
        return RedirectResponse(url=f"/plans/{plan_id}")

    # 3. Если всё ок, показываем содержимое курса
    return templates.TemplateResponse("course_view.html", {
        "request": request,
        "plan": plans[plan_id],
        "plan_id": plan_id,
        "user": user
    })

@app.post("/create-checkout-session/{plan_id}")
async def create_checkout_session(plan_id: str, username: Optional[str] = Cookie(None)):
    # 1. Проверка авторизации
    print(f"DEBUG: Попытка оплаты. Юзер: {username}, План: {plan_id}")
    if not username:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    
    # 2. Получение данных плана
    plans = get_plans_data()
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")

    raw_domain = os.getenv('YOUR_DOMAIN') or os.getenv('RENDER_EXTERNAL_URL') or "http://localhost:8000"
    # Удаляем слэш в конце, чтобы ссылки типа domain/success не превратились в domain//success
    current_domain = raw_domain.rstrip('/')

    price_in_cents = int(float(plan["price"]) * 100)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            metadata={
                "username": username,
                "plan_id": plan_id
            },
            line_items=[{
                'price_data': {
                    'currency': 'rub',
                    'product_data': {'name': plan['title']},
                    'unit_amount': price_in_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{current_domain}/payment-success?plan_id={plan_id}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{current_domain}/plans/{plan_id}",
        )
        return {"id": checkout_session.id}
    except Exception as e:
        logging.error(f"Ошибка Stripe: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/payment-success")
async def payment_success(
    plan_id: str, 
    session_id: Optional[str] = None, # Делаем Optional, чтобы не было ошибки
    db: Session = Depends(get_db), 
    username: Optional[str] = Cookie(None)
):
    if not username: 
        return RedirectResponse("/")

    return RedirectResponse(url=f"/course/{plan_id}")


@app.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET") # Секрет из Stripe

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Невалидный payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Невалидная подпись
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Обрабатываем событие успешной оплаты
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Извлекаем данные, которые мы передали при создании сессии
        metadata = session.get('metadata', {})
        username = metadata.get('username')
        plan_id = metadata.get('plan_id')

        if username and plan_id:
            user = db.query(User).filter(User.username == username).first()
            if user:
                current_plans = (user.purchased_plans or "").split(",")
                if plan_id not in current_plans:
                    current_plans.append(plan_id)
                    user.purchased_plans = ",".join(filter(None, current_plans))
                    db.commit()
                    logging.info(f"КУРС АКТИВИРОВАН: Пользователь {username} купил {plan_id}")

    return {"status": "success"}