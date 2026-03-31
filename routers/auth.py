import sys
import os, re, smtplib, stripe
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import (
    APIRouter, Depends, HTTPException, Request, Cookie, Form, File, UploadFile, Query
)
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import models, schemas
from database import get_db
import time
# --- Router init ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Load env ---
load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
YOUR_DOMAIN = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("YOUR_DOMAIN") or "http://localhost:8000"
UPLOAD_AVATAR_DIR = "/static/avatars"
MAX_AVATAR_SIZE = 10 * 1024 * 1024
os.makedirs(UPLOAD_AVATAR_DIR, exist_ok=True)


# --- CSRF ---
def get_csrf_serializer():
    secret = os.getenv("CSRF_SECRET", "dev-secret")
    return URLSafeTimedSerializer(secret)

def generate_csrf_token():
    return get_csrf_serializer().dumps("token")

def validate_csrf_token(token: str):
    try:
        get_csrf_serializer().loads(token, max_age=3600)
        return True
    except Exception:
        return False


# --- Models ---
class LoginRequest(BaseModel):
    username: str
    password: str
    csrf_token: str

class DonateRequest(BaseModel):
    amount: int
    csrf_token: str


# --- Utils ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def is_username_valid(username: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))


# --- Endpoints ---
@router.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if not is_username_valid(user.username):
        raise HTTPException(status_code=400, detail="The username must contain only English letters, numbers, and '_'")

    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="A user with this username or email already exists")

    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "You have successfully registered"}


@router.post("/login")
async def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    cookie_token = request.cookies.get("csrf_token")
    if not cookie_token or data.csrf_token != cookie_token or not validate_csrf_token(data.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")

    if not is_username_valid(data.username):
        raise HTTPException(status_code=400, detail="The username is invalid")

    db_user = db.query(models.User).filter(models.User.username == data.username).first()
    if not db_user or not verify_password(data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    response = JSONResponse(content={"redirect_url": "/auth/welcome"})
    response.set_cookie("username", db_user.username, httponly=True, samesite="none", secure=True)
    response.set_cookie("csrf_token", generate_csrf_token(), httponly=True, samesite="none", secure=True)
    return response


@router.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request, db: Session = Depends(get_db), username: str | None = Cookie(default=None), donation: str | None = Query(default=None)):
    if not username:
        return RedirectResponse(url="/", status_code=303)
    users = db.query(models.User).order_by(models.User.amount.desc()).limit(10).all()
    current_user = db.query(models.User).filter(models.User.username == username).first()
    if not current_user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("welcome.html", {"request": request, "top_users": users, "current_user": current_user, "donation": donation})


@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})
    response.set_cookie("csrf_token", csrf_token, httponly=True, secure=True, samesite="none")
    return response


@router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse("register.html", {"request": request, "csrf_token": csrf_token})
    response.set_cookie("csrf_token", csrf_token, httponly=True, secure=True, samesite="none")
    return response


@router.post("/donate")
async def donate(data: DonateRequest, request: Request, username: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    cookie_token = request.cookies.get("csrf_token")
    if not cookie_token or data.csrf_token != cookie_token or not validate_csrf_token(data.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")
    raise HTTPException(status_code=403, detail="Balance top-up is only available via Stripe")


@router.get("/profile", response_class=HTMLResponse)
async def get_profile_page(request: Request, db: Session = Depends(get_db)):
    # Извлекаем имя пользователя из куки
    username = request.cookies.get("username")
    
    # ЕСЛИ ПОЛЬЗОВАТЕЛЬ НЕ АВТОРИЗОВАН -> ПЕРЕНАПРАВЛЯЕМ НА РЕГИСТРАЦИЮ
    if not username:
        return RedirectResponse(url="/auth/register", status_code=303)

    # Ищем пользователя в базе данных
    user = db.query(models.User).filter(models.User.username == username).first()
    
    # Если кука есть, но пользователя нет в базе (ошибка данных)
    if not user:
        response = RedirectResponse(url="/auth/register", status_code=303)
        response.delete_cookie("username") # Сбрасываем некорректную куку
        return response

    # Если всё хорошо, отдаем страницу профиля с данными пользователя
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user
    })


@router.post("/profile")
async def update_profile(
    request: Request,
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_username: str = Cookie(..., alias="username")
):
    form = await request.form()
    csrf_token_form = form.get("csrf_token")
    csrf_token_cookie = request.cookies.get("csrf_token")

    # Проверка CSRF
    if not csrf_token_form or not csrf_token_cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if csrf_token_form != csrf_token_cookie:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    if not validate_csrf_token(csrf_token_form):
        raise HTTPException(status_code=403, detail="Expired or invalid CSRF token")

    if not current_username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.query(models.User).filter(models.User.username == current_username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # --- обновления ---
    if username and username != current_username:
        if db.query(models.User).filter(models.User.username == username).first():
            raise HTTPException(status_code=400, detail="Username is already taken")
        user.username = username

    if email and email != user.email:
        if db.query(models.User).filter(models.User.email == email).first():
            raise HTTPException(status_code=400, detail="Email is already in use")
        user.email = email

    if password:
        user.hashed_password = get_password_hash(password)

    # --- аватар ---
    if avatar and avatar.filename:
        contents = await avatar.read()
        if len(contents) > MAX_AVATAR_SIZE:
            raise HTTPException(status_code=413, detail="The file size is too large (maximum 10 MB)")

        from PIL import Image
        from io import BytesIO

        try:
            img = Image.open(BytesIO(contents))
            img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="The file is not an image")

        safe_filename = os.path.basename(avatar.filename)
        ext = os.path.splitext(safe_filename)[1].lower()
        ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file extension")

        avatar_filename = f"user_{user.id}_{int(time.time())}{ext}"
        avatar_path = os.path.join(UPLOAD_AVATAR_DIR, avatar_filename)

        if user.avatar:
            old_avatar_path = os.path.join(UPLOAD_AVATAR_DIR, user.avatar)
            if os.path.exists(old_avatar_path):
                try:
                    os.remove(old_avatar_path)
                except Exception as e:
                    print(f"Error deleting old avatar: {e}")

        with open(avatar_path, "wb") as buffer:
            buffer.write(contents)

        user.avatar = avatar_filename

    db.commit()

    response = JSONResponse(content={"message": "Profile updated successfully"})

    # если юзер сменил username → обновляем cookie
    if username and username != current_username:
        response.set_cookie(
            key="username",
            value=username,
            path="/",
            httponly=True,
            samesite="none",
            secure=True
        )

    return response




#end


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("username", path="/")
    response.delete_cookie("csrf_token", path="/")
    response.delete_cookie("__stripe_mid", path="/")
    response.delete_cookie("__stripe_sid", path="/")
    return response

@router.post("/payment")
async def process_payment(request: Request, amount: int = Form(...)):
    return RedirectResponse(url=f"/auth/payment?amount={amount}", status_code=303)

@router.get("/payment", response_class=HTMLResponse)
async def payment_page(request: Request, amount: int):
    return templates.TemplateResponse("payment.html", {"request": request, "amount": amount})



@router.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    username: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
):
    if not username:
        raise HTTPException(status_code=401, detail="Not authorized")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = await request.json()
    amount = data.get("amount", 0)
    if amount < 1:
        raise HTTPException(status_code=400, detail="Invalid amount")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": "Donate to the project"},
                    "unit_amount": int(amount * 100),  # Stripe требует целое число в центах
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{YOUR_DOMAIN}/auth/welcome?donation=success",
            cancel_url=f"{YOUR_DOMAIN}/cancel",
            customer_email=user.email,
            client_reference_id=user.id
        )


        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



def update_philanthrop_level(user):
    amount = user.amount

    # Пороговые суммы для одного цикла уровней
    thresholds = [50, 90, 150, 250, 350, 450, 550, 650, 750, 850]

    # Определяем, сколько полных циклов пользователь прошёл
    cycles = 0
    while amount >= thresholds[-1]:
        amount -= thresholds[-1]
        cycles += 1

    # Определяем уровень в текущем цикле
    level = 0
    for threshold in thresholds:
        if amount >= threshold:
            level += 1
        else:
            break

    # Название уровня
    if cycles == 0:
        user.philanthrop_level = f"F{level}"
    else:
        user.philanthrop_level = f"Elite-{level + (cycles - 1) * 10}"


WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email")
        amount_total = session.get("amount_total", 0) // 100

    

        if customer_email and amount_total > 0:
            user_id = session.get("client_reference_id")
            user = db.query(models.User).filter(models.User.id == user_id).first()

            
            if user:
                
                user.amount += amount_total
                user.last_donation_time = datetime.utcnow()
                update_philanthrop_level(user)  # <-- вызов функции обновления уровня
                db.commit()
                

    return {"status": "success"}






@router.get("/cancel", response_class=HTMLResponse)
async def cancel_page(request: Request):
    return HTMLResponse("<h1>Payment canceled ❌</h1><a href='/auth/welcome'>Back</a>")


