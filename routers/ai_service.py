import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

async def generate_training_plan(user_data: dict, plan_title: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.error("КРИТИЧЕСКАЯ ОШИБКА: GEMINI_API_KEY не установлен!")
        return None

    # v1beta — лучший выбор для flash моделей сейчас
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = (
        f"Ты — профессиональный фитнес-тренер. Составь подробный план тренировок для курса '{plan_title}'.\n"
        f"Данные клиента: {user_data}.\n"
        f"Ответ должен быть на русском языке, использовать Markdown разметку."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logging.info("DEBUG: Отправка запроса в Gemini 1.5 Flash...")
            response = await client.post(url, json=payload)
            
            # Если 404, пробуем альтернативный эндпоинт без beta
            if response.status_code == 404:
                logging.warning("v1beta не ответил, пробую v1...")
                url_alt = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
                response = await client.post(url_alt, json=payload)

            if response.status_code != 200:
                logging.error(f"Ошибка API Google: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']

    except Exception as e:
        logging.error(f"Ошибка в ai_service: {e}")
        return None