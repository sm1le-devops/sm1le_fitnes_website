import os
import google.generativeai as genai
import asyncio
from dotenv import load_dotenv

load_dotenv()

# КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: принудительно используем стабильную версию API v1
os.environ["GOOGLE_API_VERSION"] = "v1"

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ОШИБКА: Переменная GEMINI_API_KEY не найдена в .env")

genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Пытаемся использовать 1.5-flash (быстрая)
    model_name = 'gemini-1.5-flash'
    
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

    async def safe_generate(current_model_name):
        model = genai.GenerativeModel(model_name=current_model_name)
        # Запускаем блокирующий сетевой запрос в отдельном потоке
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        return response.text

    try:
        print(f"DEBUG: Попытка генерации через {model_name}...")
        result = await safe_generate(model_name)
        if result:
            return result
        else:
            raise Exception("Пустой ответ от модели")

    except Exception as e:
        print(f"Ошибка Gemini ({model_name}): {e}")
        
        # Если 404 или любая другая ошибка — пробуем запасной вариант
        if "404" in str(e) or "500" in str(e) or "None" in str(e):
            print("DEBUG: Ошибка 1.5-flash. Пробую запасную модель gemini-pro...")
            try:
                return await safe_generate('gemini-pro')
            except Exception as e2:
                print(f"Ошибка запасной модели gemini-pro: {e2}")
                return None
        return None