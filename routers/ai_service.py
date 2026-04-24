import os
import google.generativeai as genai
import asyncio # Добавляем для запуска в отдельном потоке
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ОШИБКА: Переменная GEMINI_API_KEY не найдена в .env")

genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
    
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
        # 1. Получаем ответ от модели
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        # 2. ПРОВЕРКА (Вставляем сюда)
        # Проверяем, есть ли в ответе "кандидаты" (сгенерированный контент)
        if not response.candidates or not response.candidates[0].content.parts:
            print("--- ERROR: Ответ заблокирован фильтрами безопасности или пуст ---")
            # Если нужно увидеть причину блокировки в логах Render:
            if response.prompt_feedback:
                print(f"Причина блокировки: {response.prompt_feedback}")
            return None
            
        # 3. Если проверка прошла, возвращаем текст
        return response.text

    except Exception as e:
        print(f"Критическая ошибка Gemini: {e}")
        return None