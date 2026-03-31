from sqlalchemy import Column, Integer, String, DateTime, Float
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(20), unique=True, index=True, nullable=False)
    email = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    gender = Column(String(10), nullable=True)
    age = Column(Integer, nullable=True)
    weight = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    target = Column(String(50), nullable=True) # Цель: похудение/набор
    current_plan = Column(String(50), nullable=True) # ID купленного плана
