import sys
import os, re
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Cookie, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

# Импорты твоих модулей
import models, schemas
from database import get_db

# --- Настройки ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
load_dotenv()

# --- CSRF Защита ---
def get_csrf_serializer():
    secret = os.getenv("CSRF_SECRET", "dev-secret")
    return URLSafeTimedSerializer(secret)

def generate_csrf_token():
    return get_csrf_serializer().dumps("token")

# --- Схемы данных ---
class LoginRequest(BaseModel):
    username: str
    password: str
    csrf_token: str

# --- Утилиты ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def is_username_valid(username: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_]+$', username))

# --- API Эндпоинты ---

@router.get("/api/check-auth")
async def check_auth(db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    if not username:
        return JSONResponse(status_code=401, content={"authenticated": False})
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return JSONResponse(status_code=401, content={"authenticated": False})
    
    return {
        "authenticated": True,
        "user": {
            "username": user.username,
            "purchased_plans": user.purchased_plans.split(",") if user.purchased_plans else []
        }
    }

@router.post("/register")
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if not is_username_valid(user.username):
        raise HTTPException(status_code=400, detail="Имя может содержать только буквы, цифры и '_'")

    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Логин или Email уже заняты")

    new_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        purchased_plans="" # Изначально планов нет
    )
    db.add(new_user)
    db.commit()
    return {"message": "Success"}

@router.post("/login")
async def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Проверка CSRF
    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or data.csrf_token != cookie_csrf:
         raise HTTPException(status_code=403, detail="Ошибка безопасности (CSRF)")

    db_user = db.query(models.User).filter(models.User.username == data.username).first()
    if not db_user or not verify_password(data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    response = JSONResponse(content={"redirect_url": "/auth/welcome"})
    # Ставим куки сессии
    response.set_cookie(key="username", value=db_user.username, httponly=False, secure=True, samesite="lax", path="/", max_age=86400)
    response.set_cookie(key="csrf_token", value=generate_csrf_token(), httponly=False, secure=True, samesite="lax", path="/")
    return response

# --- Страницы (HTML) ---

@router.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    csrf_token = generate_csrf_token()
    response = templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})
    response.set_cookie("csrf_token", csrf_token, httponly=False, secure=True, samesite="lax", path="/")
    return response

@router.get("/welcome", response_class=HTMLResponse)
def welcome(request: Request, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    if not username:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user: return RedirectResponse(url="/auth/register", status_code=303)
        
    return templates.TemplateResponse("welcome.html", {"request": request, "current_user": user})

@router.get("/profile", response_class=HTMLResponse)
async def get_profile_page(request: Request, db: Session = Depends(get_db), username: Optional[str] = Cookie(None)):
    if not username: return RedirectResponse(url="/auth/login", status_code=303)
    user = db.query(models.User).filter(models.User.username == username).first()
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@router.post("/profile")
async def update_profile(
    request: Request,
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    weight: Optional[float] = Form(None),
    height: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_username: str = Cookie(..., alias="username")
):
    # Валидация CSRF
    if (await request.form()).get("csrf_token") != request.cookies.get("csrf_token"):
        raise HTTPException(status_code=403, detail="CSRF invalid")

    user = db.query(models.User).filter(models.User.username == current_username).first()
    
    # Обновляем поля
    if username and username != current_username:
        if db.query(models.User).filter(models.User.username == username).first():
            raise HTTPException(status_code=400, detail="Логин занят")
        user.username = username
    
    if email: user.email = email
    if gender: user.gender = gender
    if weight: user.weight = weight
    if height: user.height = height

    db.commit()
    
    response = JSONResponse(content={"message": "Данные сохранены"})
    if username and username != current_username:
        response.set_cookie(key="username", value=username, path="/", httponly=False, secure=True)
    return response

@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("username", path="/")
    response.delete_cookie("csrf_token", path="/")
    return response