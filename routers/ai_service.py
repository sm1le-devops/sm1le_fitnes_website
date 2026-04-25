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
        # Настройка ключа
        genai.configure(api_key=api_key) 
        
        # 1. Используем flash-latest — это самый надежный путь в v1
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = (
            f"Ты — профессиональный фитнес-тренер. Составь подробный план тренировок для курса '{plan_title}'.\n"
            f"Данные клиента: {user_data}.\n"
            f"Ответ должен быть на русском языке, использовать Markdown разметку."
        )

        logging.info("DEBUG: Запрос к Gemini (модель: 1.5-flash-latest)...")
        
        response = await model.generate_content_async(prompt)
        
        if response and response.text:
            logging.info("✅ План успешно сгенерирован!")
            return response.text

    except Exception as e:
        logging.error(f"Ошибка Flash модели: {e}")
        # 2. Если Flash упала (например, 404), пробуем стабильный Pro
        try:
            logging.warning("Пробую gemini-pro (fallback)...")
            model_alt = genai.GenerativeModel('gemini-pro')
            response = await model_alt.generate_content_async(prompt)
            return response.text
        except Exception as e2:
            logging.error(f"Полный отказ всех моделей: {e2}")
            return None