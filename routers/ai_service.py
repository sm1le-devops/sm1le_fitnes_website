import os
import google.generativeai as genai
import asyncio
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Если на Render установлена переменная GOOGLE_API_VERSION = v1,
    # то эти имена сработают без ошибок 404
    models_to_try = ['gemini-1.5-flash', 'gemini-pro']
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план тренировок.
    Курс: {plan_title}. Данные: {user_data}.
    Ответь на русском языке, используя Markdown.
    """

    for model_name in models_to_try:
        try:
            print(f"DEBUG: Генерация через {model_name}...")
            model = genai.GenerativeModel(model_name)
            
            # Добавляем таймаут, чтобы запрос не висел вечно
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Ошибка {model_name}: {e}")
            continue
            
    return None