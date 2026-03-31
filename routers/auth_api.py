from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from routers.auth import validate_csrf_token

router = APIRouter()

@router.get("/api/check-auth")
def check_auth(request: Request, db: Session = Depends(get_db)):
    cookie_username = request.cookies.get("username")
    cookie_token = request.cookies.get("csrf_token")

    if not cookie_username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db_user = db.query(models.User).filter(models.User.username == cookie_username).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Возвращаем имя и аватарку, чтобы главная могла их отобразить
    return JSONResponse(content={
        "status": "ok", 
        "user": {
            "username": db_user.username,
            "avatar": db_user.avatar  # Добавили это поле
        }
    })