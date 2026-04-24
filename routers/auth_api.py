from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
# Добавьте сюда другие нужные импорты (модели, схемы и т.д.)

# ЭТО КРИТИЧЕСКИ ВАЖНО:
router = APIRouter()

@router.get("/api/status")
async def get_status():
    return {"status": "ok"}

