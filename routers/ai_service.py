import os
import logging
import asyncio
import hashlib
import json

from google import genai
from dotenv import load_dotenv
from fastapi.concurrency import run_in_threadpool

import redis.asyncio as redis

load_dotenv()

# Настройка логирования (важно для Render)
logging.basicConfig(level=logging.INFO)

# --- Redis ---
redis_client = redis.from_url(
    os.getenv("REDIS_URL"),
    decode_responses=True
)

# --- Gemini client ---
_client: genai.Client | None = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY не установлен")
        
        # Используем стабильную версию API v1
        _client = genai.Client(
            api_key=api_key,
            http_options={'api_version': 'v1beta'} 
        )
    return _client

# --- Ключ кеша ---
def make_cache_key(user_data: dict, plan_title: str) -> str:
    raw = json.dumps(
        {"u": user_data, "t": plan_title},
        sort_keys=True,
        ensure_ascii=False
    )
    return "plan:" + hashlib.sha256(raw.encode()).hexdigest()

# --- Основная функция ---
async def generate_training_plan(user_data: dict, plan_title: str):
    client = get_client()

    user_data_str = json.dumps(user_data, ensure_ascii=False)[:1000]
    cache_key = make_cache_key(user_data, plan_title)

    # 1. Читаем кеш
    cached = None
    try:
        cached = await redis_client.get(cache_key)
    except Exception as e:
        logging.warning(f"⚠️ Redis недоступен: {e}")

    if cached:
        logging.info("⚡ План взят из кеша")
        return cached

    prompt = (
        f"Ты — профессиональный фитнес-тренер. "
        f"Составь подробный план тренировок для курса '{plan_title}'.\n"
        f"Данные клиента: {user_data_str}.\n"
        f"Ответ должен быть на русском языке и использовать Markdown."
    )

    max_retries = 3
    delay = 10  # Увеличили начальную паузу для Free Tier

    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"📡 Попытка {attempt}: запрос к Gemini (1.5-flash)...")

            # Используем 1.5-flash-8b и увеличили таймаут до 30с
            response = await asyncio.wait_for(
                run_in_threadpool(
                    client.models.generate_content,
                    model="gemini-1.5-flash", 
                    contents=prompt
                ),
                timeout=30
            )

            text = getattr(response, "text", None)

            if not text:
                raise ValueError("Пустой ответ от Gemini")

            # Сохраняем в кеш
            try:
                await redis_client.set(cache_key, text, ex=3600)
            except Exception as e:
                logging.warning(f"⚠️ Не удалось сохранить в Redis: {e}")

            logging.info("✅ План сгенерирован успешно")
            return text

        except asyncio.TimeoutError:
            logging.warning(f"⏱ Таймаут на попытке {attempt}")

        except Exception as e:
            error_text = str(e)
            if any(x in error_text for x in ["429", "500", "503", "404"]):
                logging.warning(f"🔁 Ошибка API ({error_text}). Повтор...")
            else:
                logging.error(f"❌ Критическая ошибка: {e}")
                return "❌ Ошибка при генерации плана."

        if attempt < max_retries:
            await asyncio.sleep(delay)
            delay *= 2 # Экспоненциальное ожидание (10с, 20с...)

    logging.error("💥 Все попытки генерации провалились")
    return "❌ Не удалось получить ответ от нейросети. Пожалуйста, попробуйте позже."