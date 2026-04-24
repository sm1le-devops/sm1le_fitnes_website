import os
import google.generativeai as genai
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Принудительно v1 для стабильности на Render
os.environ["GOOGLE_API_VERSION"] = "v1"

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    print("ОШИБКА: GEMINI_API_KEY не найден")

async def generate_training_plan(user_data: dict, plan_title: str):
    # Промпт оставляем ваш
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план.
    Курс: {plan_title}
    Данные клиента:
    - Пол: {user_data.get('gender')}, Вес: {user_data.get('weight')}, Рост: {user_data.get('height')}
    - Возраст: {user_data.get('age')}, Опыт: {user_data.get('experience')}
    - Оборудование: {user_data.get('equipment')}, Травмы: {user_data.get('injuries')}

    Требования: Markdown, тренировки на неделю, советы по питанию. Русский язык.
    """

    async def safe_generate(model_name):
        model = genai.GenerativeModel(model_name=model_name)
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        # Проверка на пустой ответ (Safety Filters)
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        return response.text

    try:
        # 1. Пробуем быструю модель
        result = await safe_generate('gemini-1.5-flash')
        if result: return result
        raise Exception("Flash returned empty")
    except Exception as e:
        print(f"Ошибка Flash: {e}. Пробуем Pro...")
        try:
            # 2. Запасной вариант
            return await safe_generate('gemini-pro')
        except Exception as e2:
            print(f"Критическая ошибка ИИ: {e2}")
            return None