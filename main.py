import os
import json
import io
import stripe
import logging
from typing import Optional
from routers.auth import generate_csrf_token,validate_csrf_token
from sqlalchemy.orm.attributes import flag_modified
from contextlib import asynccontextmanager
from routers.ai_service import generate_training_plan
from fastapi import Form
from fpdf import FPDF
from fastapi import FastAPI, Request, Depends, Cookie, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse, Response
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



# --- Вспомогательная логика ---
def load_plans():
    try:
        with open("plans.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Ошибка: файл plans.json не найден!")
        return {}

PLANS = load_plans()

def create_pdf_buffer(plan_text):
    # Используем fpdf2
    pdf = FPDF()
    pdf.add_page()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(base_dir, "static", "fonts", "DejaVuSans.ttf")
    
    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, unicode=True)
        pdf.set_font('DejaVu', '', 12)
    else:
        logging.error(f"Шрифт не найден: {font_path}")
        pdf.set_font("Arial", size=12)

    # Очистка текста от Markdown символов, чтобы PDF выглядел аккуратно
    clean_text = str(plan_text).replace("**", "").replace("__", "").replace("#", "")
    
    # Автоматический перенос строк (multi_cell)
    for line in clean_text.split('\n'):
        line = line.strip()
        if line:
            pdf.multi_cell(0, 10, txt=line)
        else:
            pdf.ln(5)
    
    try:
        # dest='S' принудительно возвращает документ как байтовую строку (String/Bytes)
        # Это самый надежный способ для FastAPI
        pdf_output = pdf.output(dest='S')
        
        # Если пришла строка (зависит от версии fpdf), кодируем в latin-1 или utf-8
        if isinstance(pdf_output, str):
            return pdf_output.encode('latin-1')
        return pdf_output
        
    except Exception as e:
        logging.error(f"Ошибка при сохранении PDF: {e}")
        # Возвращаем заглушку, чтобы сервер не упал
        return b"Error: Could not generate PDF"


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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_data,
        "plans": PLANS 
    })

@app.get("/auth/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, user_data=Depends(get_current_active_user)):
    return templates.TemplateResponse("welcome.html", {
        "request": request,
        "user": user_data,
        "plans": PLANS 
    })

@app.get("/questionnaire", response_class=HTMLResponse)
async def get_questionnaire(request: Request, plan_id: str, user_data=Depends(get_current_active_user)):
    if not user_data:
        return RedirectResponse(url="/auth/login")
    
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail="План не найден")
        
    # Генерируем токен и передаем его в шаблон
    token = generate_csrf_token()
    return templates.TemplateResponse("questionnaire.html", {
        "request": request, 
        "plan_id": plan_id,
        "csrf_token": token  # Передаем токен
    })
    
@app.get("/plans/{plan_id}", response_class=HTMLResponse)
async def get_plan_page(request: Request, plan_id: str, user_data=Depends(get_current_active_user)):
    # Проверяем наличие плана в глобальной переменной
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail="План не найден")
    
    is_purchased = False
    if user_data and plan_id in user_data["purchased_plans"]:
        is_purchased = True
    
    return templates.TemplateResponse("plan_detail.html", {
        "request": request, 
        "plan": PLANS[plan_id], 
        "plan_id": plan_id,
        "is_purchased": is_purchased,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY 
    })


@app.get("/course/{plan_id}/download")
async def download_pdf(
    plan_id: str, 
    user_data=Depends(get_current_active_user)
):
    if not user_data:
        raise HTTPException(status_code=401)

    user = user_data["obj"]
    plan_text = user.generated_plans.get(plan_id)

    if not plan_text:
        raise HTTPException(status_code=404, detail="Текст плана не найден")

    # Используем твою функцию-помощник (убедись, что шрифт по пути static/fonts/...)
    pdf_bytes = create_pdf_buffer(plan_text)
    
    return Response(
        content=pdf_bytes, 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"attachment; filename=plan_{plan_id}.pdf"}
    )

@app.get("/course/{plan_id}", response_class=HTMLResponse)
async def view_course(request: Request, plan_id: str, db: Session = Depends(get_db)):
    username = request.cookies.get("username")
    user = db.query(User).filter(User.username == username).first() if username else None
    
    # Пытаемся получить данные курса по его ID из нашего словаря (загруженного из файла)
    course_catalog_data = PLANS.get(plan_id)
    
    if not course_catalog_data:
        raise HTTPException(status_code=404, detail="Программа не найдена в каталоге")

    is_purchased = False
    generated_plan = None

    if user:
        # 1. Проверяем куплен ли курс (строка через запятую преобразуется в список)
        purchased_list = [p.strip() for p in (user.purchased_plans or "").split(",") if p.strip()]
        is_purchased = plan_id in purchased_list
        
        # 2. Если курс оплачен, проверяем наличие сгенерированного ИИ контента
        if is_purchased:
            # В модели User поле generated_plans — это JSON-столбец (словарь)
            generated_plan = (user.generated_plans or {}).get(plan_id)
            
            # 3. Если оплачено, но ИИ еще не составил план — отправляем на анкету
            if not generated_plan:
                return RedirectResponse(url=f"/questionnaire?plan_id={plan_id}")

    return templates.TemplateResponse("course_view.html", {
        "request": request,
        "plan": course_catalog_data,  
        "plan_id": plan_id,
        "is_purchased": is_purchased,
        "plan_json": generated_plan if generated_plan else None,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY
    })
    

@app.post("/generate-plan/{plan_id}")
async def process_questionnaire(
    request: Request,
    plan_id: str,
    gender: str = Form(...),
    weight: float = Form(...),
    height: float = Form(...),
    age: int = Form(...),
    experience: str = Form(...),
    equipment: str = Form(...),
    injuries: str = Form(...),
    db: Session = Depends(get_db),
    user_data=Depends(get_current_active_user) # Снова безопасность!
):
    
    form_data = await request.form()
    csrf_from_form = form_data.get("csrf_token")
    if not validate_csrf_token(csrf_from_form):
        raise HTTPException(status_code=403, detail="CSRF токен невалиден или просрочен")

    if not user_data:
        raise HTTPException(status_code=401)

    user = user_data["obj"]
    plan_info = PLANS.get(plan_id)
    
    if not plan_info:
        raise HTTPException(status_code=404, detail="План не найден")

    plan_title = plan_info.get("title", "Персональный план")
    
    ai_user_data = {
        "gender": gender, "weight": weight, "height": height,
        "age": age, "experience": experience,
        "equipment": equipment, "injuries": injuries
    }

    generated_text = await generate_training_plan(ai_user_data, plan_title)
    if generated_text is None:
        raise HTTPException(
            status_code=503, 
            detail="Нейросеть сейчас перегружена. Пожалуйста, подождите 30 секунд и нажмите кнопку снова."
        )

    current_plans = dict(user.generated_plans or {})
    current_plans[plan_id] = generated_text
    
    # ПРИНУДИТЕЛЬНО помечаем поле для SQLAlchemy
    user.generated_plans = current_plans
    flag_modified(user, "generated_plans") 
    
    db.add(user)
    db.commit()

    return HTMLResponse(content=f"""
        <html>
            <head><meta charset="utf-8"></head>
            <body>
                <script>
                    window.location.href = "/course/{plan_id}";
                </script>
            </body>
        </html>
    """)

@app.post("/create-checkout-session/{plan_id}")
async def create_checkout_session(plan_id: str, user_data=Depends(get_current_active_user)):
    if not user_data:
        raise HTTPException(status_code=401, detail="Войдите в аккаунт")
    
    plan = PLANS.get(plan_id)
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
                    
                    <button onclick="goToCourse()" style="display: inline-block; padding: 12px 24px; background: #F97316; color: white; border: none; font-size: 16px; cursor: pointer; border-radius: 8px; margin-top: 20px;">Перейти к курсу</button>
                    
                    <script>
                        function goToCourse() {{
                            // Трюк: подменяем страницу Stripe/Success в истории на список планов
                            window.history.replaceState(null, '', '/auth/welcome');
                            
                            // Теперь переходим на сам курс. Если нажать "Назад", браузер вернет на /auth/welcome
                            window.location.href = "/course/{plan_id}";
                        }}

                        // Запускаем автоматически через 4 секунды
                        setTimeout(goToCourse, 4000);
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