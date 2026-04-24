import os
import google.generativeai as genai
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Убираем жесткую привязку к версии v1 в environ, 
# библиотека сама разберется, если мы дадим правильные имена моделей
if "GOOGLE_API_VERSION" in os.environ:
    del os.environ["GOOGLE_API_VERSION"]

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Используем ПОЛНЫЕ имена моделей с префиксом models/
    # Это самый надежный способ избежать 404
    primary_model_name = 'models/gemini-1.5-flash'
    fallback_model_name = 'models/gemini-pro'
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план тренировок.
    Курс: {plan_title}
    
    Данные клиента:
    - Пол: {user_data.get('gender')}
    - Вес: {user_data.get('weight')} кг
    - Рост: {user_data.get('height')} см
    - Возраст: {user_data.get('age')} лет
    - Опыт: {user_data.get('experience')}
    - Оборудование: {user_data.get('equipment')}
    - Травмы: {user_data.get('injuries')}

    Требования к ответу:
    1. Используй Markdown (заголовки ##, жирный текст).
    2. План на неделю + советы по питанию.
    3. Язык: Русский.
    """

    async def safe_generate(m_name):
        # Создаем модель с полным именем
        model = genai.GenerativeModel(model_name=m_name)
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        return response.text

    try:
        print(f"DEBUG: Попытка генерации через {primary_model_name}...")
        result = await safe_generate(primary_model_name)
        if result:
            return result
        raise Exception("Empty response")

    except Exception as e:
        print(f"Ошибка Gemini ({primary_model_name}): {e}")
        print(f"DEBUG: Пробую запасную модель {fallback_model_name}...")
        try:
            return await safe_generate(fallback_model_name)
        except Exception as e2:
            print(f"Критическая ошибка обеих моделей: {e2}")
            return None