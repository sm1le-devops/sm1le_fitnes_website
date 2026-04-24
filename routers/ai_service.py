import os
import google.generativeai as genai
from google.generativeai.types import RequestOptions
import asyncio
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

# Настройка
if api_key:
    genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Мы используем полный путь к модели. 
    # В некоторых версиях библиотеки это единственный способ пробиться через 404
    models_to_try = [
        "models/gemini-1.5-flash", 
        "models/gemini-1.5-pro",
        "models/gemini-pro"
    ]
    
    prompt = f"Ты фитнес-тренер. Составь план тренировок для курса {plan_title}. Данные: {user_data}. Ответ на русском в Markdown."

    # Создаем опции запроса вручную, чтобы принудительно выставить v1
    # Если api_version не поддерживается как аргумент, мы поймаем это в блоке try
    for m_name in models_to_try:
        try:
            print(f"DEBUG: Пробую принудительный вызов {m_name} через v1...")
            model = genai.GenerativeModel(model_name=m_name)
            
            # Прямая попытка генерации. 
            # Если RequestOptions вызовет ошибку, перейдем в except и попробуем без него
            try:
                response = await asyncio.to_thread(
                    model.generate_content, 
                    prompt,
                    request_options={"api_version": "v1"}
                )
            except:
                response = await asyncio.to_thread(model.generate_content, prompt)

            if response and response.text:
                return response.text
        except Exception as e:
            print(f"Ошибка с {m_name}: {e}")
            continue
            
    return None