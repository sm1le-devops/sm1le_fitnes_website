import os
import json
import stripe
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Cookie, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi_limiter import FastAPILimiter
from dotenv import load_dotenv
from redis.asyncio import Redis
from sqlalchemy.orm import Session

# Импорты ваших модулей
from database import Base, engine, get_db
from models import User
from routers import auth, auth_api, password_reset

# Загрузка переменных
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Проверка критических переменных
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = STRIPE_SECRET_KEY

if not STRIPE_PUBLISHABLE_KEY or not STRIPE_SECRET_KEY:
    logging.error("КРИТИЧЕСКАЯ ОШИБКА: Ключи Stripe не найдены в .env!")

# Глобальный кэш для планов
_PLANS_CACHE = None

# --- Вспомогательная логика ---

def get_plans_data():
    """Загружает планы из JSON с использованием кэша."""
    global _PLANS_CACHE
    if _PLANS_CACHE is not None:
        return _PLANS_CACHE
    try:
        with open("plans.json", "r", encoding="utf-8") as f:
            _PLANS_CACHE = json.load(f)
            return _PLANS_CACHE
    except Exception as e:
        logging.error(f"Ошибка чтения plans.json: {e}")
        return {}

async def get_current_active_user(
    db: Session = Depends(get_db), 
    username: Optional[str] = Cookie(None)
) -> Optional[dict]:
    """Зависимость для получения данных текущего пользователя."""
    if not username:
        return None
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    
    # Парсим купленные планы сразу здесь
    purchased_plans = [p.strip() for p in (user.purchased_plans or "").split(",") if p.strip()]
    
    return {
        "obj": user, # SQLAlchemy объект для обновлений
        "username": user.username,
        "purchased_plans": purchased_plans
    }

# --- Lifecycle ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создание таблиц при запуске
    Base.metadata.create_all(bind=engine)
    
    # Подключение Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        app.state.redis = redis_client
        await FastAPILimiter.init(redis_client)
        logging.info("✅ Redis подключен.")
    except Exception as e:
        logging.error(f"❌ Redis не доступен: {e}")
    
    yield
    
    # Отключение Redis
    if hasattr(app.state, "redis"):
        await app.state.redis.close()

# --- Приложение ---

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
templates.env.filters["tojson"] = lambda data: json.dumps(data, ensure_ascii=False)

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

app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключение роутеров
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(auth_api.router)
app.include_router(password_reset.router, prefix="/auth", tags=["Password Reset"])

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user_data=Depends(get_current_active_user)):
    plans = get_plans_data()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_data,
        "plans": plans
    })

@app.get("/auth/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, user_data=Depends(get_current_active_user)):
    plans = get_plans_data()
    return templates.TemplateResponse("welcome.html", {
        "request": request,
        "user": user_data,
        "plans": plans
    })

@app.get("/plans/{plan_id}", response_class=HTMLResponse)
async def get_plan_page(request: Request, plan_id: str, user_data=Depends(get_current_active_user)):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="План не найден")
    
    is_purchased = False
    if user_data and plan_id in user_data["purchased_plans"]:
        is_purchased = True
    
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, 
        "plan": plans[plan_id], 
        "plan_id": plan_id,
        "is_purchased": is_purchased,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY 
    })

@app.get("/course/{plan_id}", response_class=HTMLResponse)
async def get_course_view(request: Request, plan_id: str, user_data=Depends(get_current_active_user)):
    plans = get_plans_data()
    if plan_id not in plans:
        raise HTTPException(status_code=404, detail="Курс не найден")
    
    if not user_data:
        return RedirectResponse(url="/auth/login")
    
    # Если пользователь не покупал этот план, отправляем на страницу описания
    if plan_id not in user_data["purchased_plans"]:
        return RedirectResponse(url=f"/plans/{plan_id}")

    # Подготавливаем данные для JS (список упражнений)
    plan_info = plans[plan_id]
    plan_json_safe = json.dumps(plan_info, ensure_ascii=False)

    return templates.TemplateResponse("course_view.html", {
        "request": request,
        "plan": plan_info,
        "plan_id": plan_id,
        "user": user_data["obj"],
        "is_purchased": True,  # Обязательно передаем True, раз мы прошли проверку выше
        "stripe_pub_key": STRIPE_PUBLISHABLE_KEY, # Чтобы Stripe не ругался на пустой ключ
        "plan_json_safe": plan_json_safe # Чтобы JS видел упражнения
    })

@app.post("/create-checkout-session/{plan_id}")
async def create_checkout_session(plan_id: str, user_data=Depends(get_current_active_user)):
    if not user_data:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    
    plans = get_plans_data()
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")

    raw_domain = os.getenv('YOUR_DOMAIN') or os.getenv('RENDER_EXTERNAL_URL') or "http://localhost:8000"
    current_domain = raw_domain.rstrip('/')
    price_in_cents = int(float(plan["price"]) * 100)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            metadata={
                "username": user_data["username"],
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
async def payment_success(request: Request, plan_id: str):
    return HTMLResponse(content=f"""
        <html>
            <body style="background: #0F172A; color: white; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; text-align: center;">
                <div>
                    <h1 style="color: #22C55E;">Оплата прошла успешно!</h1>
                    <p>Активируем ваш доступ к курсу...</p>
                    
                    <button onclick="window.location.replace('/course/{plan_id}')" style="display: inline-block; padding: 12px 24px; background: #F97316; color: white; border: none; font-size: 16px; cursor: pointer; border-radius: 8px; margin-top: 20px;">Перейти к курсу</button>
                    
                    <script>
                        // Используем replace вместо href
                        setTimeout(() => {{ window.location.replace("/course/{plan_id}"); }}, 4000);
                        
                        // Дополнительная защита: если пользователь все же попал сюда по кнопке "назад", сразу кидаем на главную
                        window.onpageshow = function(event) {{
                            if (event.persisted) {{
                                window.location.replace("/");
                            }}
                        }};
                    </script>
                </div>
            </body>
        </html>
    """)

@app.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        username = metadata.get('username')
        plan_id = metadata.get('plan_id')

        if username and plan_id:
            user = db.query(User).filter(User.username == username).first()
            if user:
                current_plans = [p.strip() for p in (user.purchased_plans or "").split(",") if p.strip()]
                if plan_id not in current_plans:
                    current_plans.append(plan_id)
                    user.purchased_plans = ",".join(current_plans)
                    db.commit()
                    logging.info(f"✅ ДОСТУП ПРЕДОСТАВЛЕН: {username} -> {plan_id}")

    return {"status": "success"}