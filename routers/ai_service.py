import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

async def generate_training_plan(user_data: dict, plan_title: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.error("КРИТИЧЕСКАЯ ОШИБКА: GEMINI_API_KEY не установлен!")
        return None

    try:
        # Инициализация SDK
        genai.configure(api_key=api_key)
        
        # Выбираем модель. 1.5-flash сейчас самая стабильная для этого региона
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Ты — профессиональный фитнес-тренер. Составь подробный план тренировок для курса '{plan_title}'.\n"
            f"Данные клиента: {user_data}.\n"
            f"Ответ должен быть на русском языке, использовать Markdown разметку."
        )

        logging.info("DEBUG: Запрос к Gemini через официальный SDK...")
        
        # Генерация контента (в SDK это синхронный вызов, 
        # для асинхронности в высоконагруженных системах используют другие методы, 
        # но для твоего проекта этого достаточно)
        response = await model.generate_content_async(prompt)
        
        if response and response.text:
            logging.info("✅ План успешно сгенерирован!")
            return response.text
        else:
            logging.error("Получен пустой ответ от модели")
            return None

    except Exception as e:
        logging.error(f"Ошибка Google AI SDK: {e}")
        # Запасной вариант, если flash недоступна
        try:
            logging.warning("Пробую gemini-pro...")
            model_alt = genai.GenerativeModel('gemini-pro')
            # Также делаем асинхронно
            response = await model_alt.generate_content_async(prompt) 
            return response.text
        except Exception as e2:
            logging.error(f"Полный отказ всех моделей: {e2}")
            return None