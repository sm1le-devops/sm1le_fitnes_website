import os
import google.generativeai as genai
import asyncio
from dotenv import load_dotenv

# 1. Сначала загружаем .env
load_dotenv()

# 2. Устанавливаем версию API через системную переменную. 
# Это заставит ЛЮБУЮ версию библиотеки использовать стабильную v1.
os.environ["GOOGLE_API_VERSION"] = "v1"

api_key = os.getenv("GEMINI_API_KEY")

# 3. Настраиваем библиотеку простейшим способом
if api_key:
    genai.configure(api_key=api_key)

async def generate_training_plan(user_data: dict, plan_title: str):
    # Используем стандартные названия моделей
    # Если на сервере старая библиотека, она может не знать 'gemini-1.5-flash',
    # поэтому в fallback добавим старую добрую 'gemini-pro'
    models_to_try = ['gemini-1.5-flash', 'gemini-pro']
    
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

    for model_name in models_to_try:
        try:
            print(f"DEBUG: Попытка генерации через {model_name}...")
            # Создаем модель без лишних аргументов
            model = genai.GenerativeModel(model_name)
            
            # Вызываем генерацию
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            if response and response.text:
                return response.text
                
        except Exception as e:
            print(f"Ошибка с моделью {model_name}: {e}")
            continue # Пробуем следующую модель из списка
            
    return None