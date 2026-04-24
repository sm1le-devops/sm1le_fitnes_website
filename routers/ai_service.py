import os
import httpx
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

async def generate_training_plan(user_data: dict, plan_title: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.error("GEMINI_API_KEY не найден в переменных окружения")
        return None

    # Прямая ссылка на стабильную версию v1. 
    # Здесь 404 возникнуть не может, так как путь прописан вручную.
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь персональный план тренировок.
    Курс: {plan_title}
    Данные клиента:
    - Пол: {user_data.get('gender')}
    - Вес: {user_data.get('weight')} кг
    - Рост: {user_data.get('height')} см
    - Возраст: {user_data.get('age')} лет
    - Опыт: {user_data.get('experience', 'не указан')}
    - Оборудование: {user_data.get('equipment', 'не указано')}
    
    Требования к ответу:
    1. Используй Markdown (заголовки ##, жирный текст).
    2. План на неделю + советы по питанию.
    3. Язык: Русский.
    """

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        }
    }

    try:
        logging.info("DEBUG: Отправка прямого запроса к Gemini v1 через HTTP...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                logging.error(f"Ошибка API Google: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            
            # Проверка структуры ответа
            if 'candidates' in data and len(data['candidates']) > 0:
                return data['candidates'][0]['content']['parts'][0]['text']
            else:
                logging.error(f"Неожиданный формат ответа: {data}")
                return None

    except Exception as e:
        logging.error(f"Критическая ошибка при генерации: {e}")
        return None