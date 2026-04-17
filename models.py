from sqlalchemy import Column, Integer, String, Float, DateTime, JSON  # Добавили JSON
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(20), unique=True, index=True, nullable=False)
    email = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    
    # Личные данные для фитнеса
    gender = Column(String(10), nullable=True) # Мужской / Женский
    age = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    
    # Цели и доступ
    target = Column(String(50), nullable=True)
    purchased_plans = Column(String, default="") 
    
    # --- НОВОЕ ПОЛЕ ---
    # Здесь будут лежать планы в формате: {"plan_id": "Текст от нейросети"}
    generated_plans = Column(JSON, default={}) 
    
    created_at = Column(DateTime, default=datetime.utcnow)