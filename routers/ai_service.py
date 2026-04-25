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
        # ПРИНУДИТЕЛЬНО задаем v1, чтобы избежать 404 на v1beta
        genai.configure(api_key=api_key, transport='rest') 
        
        # Можно попробовать явно прописать версию, если SDK позволяет в твоей версии
        # Но самый надежный способ — проверить саму строку модели
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            f"Ты — профессиональный фитнес-тренер. Составь подробный план тренировок для курса '{plan_title}'.\n"
            f"Данные клиента: {user_data}.\n"
            f"Ответ должен быть на русском языке, использовать Markdown разметку."
        )

        logging.info("DEBUG: Запрос к Gemini через официальный SDK (v1)...")
        
        # Используем асинхронный вызов
        response = await model.generate_content_async(prompt)
        
        if response and response.text:
            logging.info("✅ План успешно сгенерирован!")
            return response.text
        else:
            logging.error("Получен пустой ответ от модели")
            return None

    except Exception as e:
        logging.error(f"Ошибка Google AI SDK: {e}")
        # Если 1.5-flash не найдена, пробуем 1.0-pro (gemini-pro иногда так называется в v1)
        try:
            logging.warning("Пробую gemini-1.0-pro...")
            model_alt = genai.GenerativeModel('gemini-1.0-pro')
            response = await model_alt.generate_content_async(prompt)
            return response.text
        except Exception as e2:
            logging.error(f"Полный отказ всех моделей: {e2}")
            return None