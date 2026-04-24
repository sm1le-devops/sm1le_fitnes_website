import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Настройка API ключа
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def generate_training_plan(user_data: dict, plan_title: str):
    """
    Генерирует план через Google Gemini 1.5 Flash
    """
    # Инициализация модели
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план.
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
    2. План должен включать тренировки на неделю и краткие советы по питанию.
    3. Тон общения: мотивирующий, профессиональный.
    4. Язык: Русский.
    """

    try:
        # Генерация контента
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "Ошибка при генерации плана ИИ. Пожалуйста, попробуйте позже."