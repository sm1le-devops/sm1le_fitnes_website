import os
import google.generativeai as genai
from google.generativeai.types import RequestOptions
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Полностью очищаем переменные окружения, которые могут путать библиотеку
if "GOOGLE_API_VERSION" in os.environ:
    del os.environ["GOOGLE_API_VERSION"]

api_key = os.getenv("GEMINI_API_KEY")

# Настраиваем библиотеку
genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Используем имена БЕЗ префикса models/, так как новая версия библиотеки 
    # подставляет их сама, но добавим RequestOptions для фиксации версии API
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план тренировок.
    Курс: {plan_title}
    
    Данные клиента:
    - Пол: {user_data.get('gender')}, Вес: {user_data.get('weight')} кг, Рост: {user_data.get('height')} см
    - Возраст: {user_data.get('age')} лет, Опыт: {user_data.get('experience')}
    - Оборудование: {user_data.get('equipment')}, Травмы: {user_data.get('injuries')}

    Требования к ответу:
    1. Используй Markdown (заголовки ##, жирный текст).
    2. План на неделю + советы по питанию. Язык: Русский.
    """

    async def safe_generate(model_id):
        # RequestOptions(api_version='v1') — это КЛЮЧЕВОЙ момент, 
        # чтобы уйти от глючной v1beta, которая выдает 404
        model = genai.GenerativeModel(model_id)
        response = await asyncio.to_thread(
            model.generate_content, 
            prompt,
            request_options=RequestOptions(api_version='v1')
        )
        return response.text

    try:
        print(f"DEBUG: Попытка генерации через gemini-1.5-flash (v1)...")
        return await safe_generate('gemini-1.5-flash')
    except Exception as e:
        print(f"Ошибка Flash: {e}")
        try:
            print(f"DEBUG: Пробую gemini-1.5-pro (v1)...")
            return await safe_generate('gemini-1.5-pro')
        except Exception as e2:
            print(f"Критическая ошибка: {e2}")
            return None