import os
import logging
import asyncio
import hashlib
import json

from google import genai
from google.genai import types # Импортируем типы для конфига
from dotenv import load_dotenv

import redis.asyncio as redis

load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- Redis ---
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# --- Gemini client ---
_client: genai.Client | None = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY не установлен")
        
        # Убираем жесткое указание версии здесь, доверяем SDK
        _client = genai.Client(api_key=api_key)
        logging.info("✅ Асинхронный Gemini клиент инициализирован")
    return _client

# --- Ключ кеша ---
def make_cache_key(user_data: dict, plan_title: str) -> str:
    raw = json.dumps({"u": user_data, "t": plan_title}, sort_keys=True, ensure_ascii=False)
    return "plan:" + hashlib.sha256(raw.encode()).hexdigest()

# --- Основная функция ---
async def generate_training_plan(user_data: dict, plan_title: str):
    client = get_client()

    user_data_str = json.dumps(user_data, ensure_ascii=False)[:1000]
    cache_key = make_cache_key(user_data, plan_title)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logging.info("⚡ План взят из кеша")
            return cached
    except Exception as e:
        logging.warning(f"⚠️ Redis недоступен: {e}")

    prompt = (
        f"Ты — профессиональный фитнес-тренер. "
        f"Составь подробный план тренировок для курса '{plan_title}'.\n"
        f"Данные клиента: {user_data_str}.\n"
        f"Ответ должен быть на русском языке и использовать Markdown."
    )

    # Используем 2.0 Flash, так как она видна в твоей AI Studio
    model_name = "gemini-2.0-flash" 

    for attempt in range(1, 4):
        try:
            logging.info(f"📡 Попытка {attempt}: запрос к {model_name}...")

            # Прямой асинхронный вызов через client.aio
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048
                )
            )

            text = response.text
            if not text:
                raise ValueError("Пустой ответ от модели")

            try:
                await redis_client.set(cache_key, text, ex=3600)
            except:
                pass

            logging.info("✅ План сгенерирован успешно!")
            return text

        except Exception as e:
            error_msg = str(e)
            logging.warning(f"🔁 Ошибка API ({error_msg}). Повтор...")
            if attempt < 3:
                await asyncio.sleep(10 * attempt) # Ждем 10с, потом 20с

    logging.error("💥 Все попытки провалены")
    return "❌ Ошибка нейросети. Попробуйте позже."