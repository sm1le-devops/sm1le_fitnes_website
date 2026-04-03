import sys
import os, re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import (
    APIRouter, Depends, HTTPException, Request, Cookie, Form
)
# JSONResponse, HTMLResponse и RedirectResponse импортируем только отсюда
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext
from datetime import datetime
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
import models, schemas
from database import get_db

# --- Router init ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Load env ---
load_dotenv()
# На Render используем относительный путь для статики
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_AVATAR_DIR = os.path.join(os.path.dirname(BASE_DIR), "static", "avatars")
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

# --- Utils ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def is_username_valid(username: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))

# --- Endpoints ---
@router.get("/api/check-auth")
async def check_auth(db: Session = Depends(get_db), username: str | None = Cookie(default=None)):
    if not username:
        return JSONResponse(status_code=401, content={"authenticated": False})
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return JSONResponse(status_code=401, content={"authenticated": False})
    
    return JSONResponse(content={
        "authenticated": True,
        "user": {
            "username": user.username,
            "current_plan": getattr(user, 'current_plan', None)
        }
    })
@router.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if not is_username_valid(user.username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers and '_'")

    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username or Email already exists")

    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": "Success"}

@router.post("/login")
async def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Проверка CSRF
    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or data.csrf_token != cookie_csrf:
         raise HTTPException(status_code=403, detail="CSRF error")

    db_user = db.query(models.User).filter(models.User.username == data.username).first()
    if not db_user or not verify_password(data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    response = JSONResponse(content={"redirect_url": "/auth/welcome"})
    
    # Устанавливаем куки
    response.set_cookie(key="username", value=db_user.username, httponly=False, secure=True, samesite="lax", path="/", max_age=86400)
    response.set_cookie(key="csrf_token", value=generate_csrf_token(), httponly=False, secure=True, samesite="lax", path="/")
    return response
@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})
    # Обязательно ставим куку с токеном, чтобы форма логина могла его отправить
    response.set_cookie("csrf_token", csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return response

@router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse("register.html", {"request": request, "csrf_token": csrf_token})
    response.set_cookie("csrf_token", csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return response

@router.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request, db: Session = Depends(get_db), username: str | None = Cookie(default=None)):
    if not username:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    current_user = db.query(models.User).filter(models.User.username == username).first()
    if not current_user:
        return RedirectResponse(url="/auth/register", status_code=303)
        
    return templates.TemplateResponse("welcome.html", {
        "request": request, 
        "current_user": current_user
    })

@router.get("/profile", response_class=HTMLResponse)
async def get_profile_page(request: Request, db: Session = Depends(get_db), username: str | None = Cookie(default=None)):
    if not username:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return RedirectResponse(url="/auth/register", status_code=303)

    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@router.post("/profile")
async def update_profile(
    request: Request,
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    weight: Optional[float] = Form(None),
    height: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_username: str = Cookie(..., alias="username")
):
    # 1. Простая проверка CSRF
    form_data = await request.form()
    if form_data.get("csrf_token") != request.cookies.get("csrf_token"):
        raise HTTPException(status_code=403, detail="CSRF invalid")

    user = db.query(models.User).filter(models.User.username == current_username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Обновление данных (только тех, что есть в вашей модели)
    if username and username != current_username:
        if db.query(models.User).filter(models.User.username == username).first():
            raise HTTPException(status_code=400, detail="Username taken")
        user.username = username

    if email and email != user.email:
        user.email = email

    if password and password.strip():
        user.hashed_password = get_password_hash(password)

    user.weight = weight
    user.height = height

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="DB Error")

    response = JSONResponse(content={"message": "Updated"})
    if username and username != current_username:
        response.set_cookie(key="username", value=username, path="/", httponly=False, secure=True)
    
    return response

@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("username", path="/")
    response.delete_cookie("csrf_token", path="/")
    return response

