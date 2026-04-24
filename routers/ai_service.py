import os
import httpx
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

async def generate_training_plan(user_data: dict, plan_title: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.error("КРИТИЧЕСКАЯ ОШИБКА: GEMINI_API_KEY не установлен!")
        return None

    model_name = "gemini-1.5-flash" 
    url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
    
    # Расширенный промпт для лучшего качества
    prompt = (
        f"Ты — профессиональный фитнес-тренер. Составь подробный план тренировок для курса '{plan_title}'.\n"
        f"Данные клиента: {user_data}.\n"
        f"Ответ должен быть на русском языке, использовать Markdown разметку, "
        f"включать упражнения, количество подходов и повторений."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logging.info(f"DEBUG: Попытка запроса к {model_name}...")
            response = await client.post(url, json=payload)
            
            # Если 404 (модель не найдена), пробуем старую добрую gemini-pro
            if response.status_code == 404:
                logging.warning(f"Модель {model_name} не найдена. Откат на gemini-pro...")
                url_old = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={api_key}"
                response = await client.post(url_old, json=payload)

            if response.status_code != 200:
                logging.error(f"Ошибка API Google (Status {response.status_code}): {response.text}")
                return None
                
            data = response.json()
            
            # Безопасное извлечение текста
            try:
                text = data['candidates'][0]['content']['parts'][0]['text']
                logging.info("✅ План успешно сгенерирован нейросетью.")
                return text
            except (KeyError, IndexError):
                logging.error(f"Ошибка парсинга ответа Google: {data}")
                return None

    except Exception as e:
        logging.error(f"Непредвиденная ошибка в ai_service: {e}")
        return None