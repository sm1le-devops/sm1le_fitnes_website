import os
import logging
import asyncio
import hashlib
import json

from google import genai
from google.genai import types 
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
        
        # Используем API-ключ из твоего рабочего проекта Gsm1le (Free tier)
        _client = genai.Client(api_key=api_key)
        logging.info("✅ Gemini клиент инициализирован")
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

    # ИЗМЕНЕНИЕ 1: Используем 1.5 Flash. У неё ЕСТЬ лимиты на Free Tier, в отличие от 2.0.
    model_name = "gemini-1.5-flash" 

    for attempt in range(1, 4):
        try:
            logging.info(f"📡 Попытка {attempt}: запрос к {model_name}...")

            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                    # ИЗМЕНЕНИЕ 2: Снижаем пороги фильтрации, чтобы API не блокировал фитнес-советы
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    ]
                )
            )

            # Проверка, есть ли текст в ответе (защита от пустых ответов из-за фильтров)
            if response.candidates and response.candidates[0].content.parts:
                text = response.candidates[0].content.parts[0].text
            else:
                raise ValueError("Модель не смогла сгенерировать текст (возможно, сработал фильтр)")

            try:
                await redis_client.set(cache_key, text, ex=3600)
            except:
                pass

            logging.info("✅ План сгенерирован успешно!")
            return text

        except Exception as e:
            error_msg = str(e)
            # Если видим ошибку 429 (Too Many Requests), ждем дольше
            if "429" in error_msg:
                logging.warning(f"⏳ Превышен лимит (429). Ждем дольше...")
                await asyncio.sleep(20 * attempt)
            else:
                logging.warning(f"🔁 Ошибка API ({error_msg}). Повтор через {10 * attempt}с...")
                await asyncio.sleep(10 * attempt)

    logging.error("💥 Все попытки провалены")
    return "❌ Ошибка нейросети (лимиты или фильтры). Попробуйте позже."