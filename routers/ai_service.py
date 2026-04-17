import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Инициализируем клиент. Ключ должен лежать в .env как OPENAI_API_KEY
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_training_plan(user_data: dict, plan_title: str):
    """
    Формирует запрос к ИИ на основе данных пользователя и возвращает текст плана.
    """
    prompt = f"""
    Ты — элитный фитнес-тренер. Составь персональный план тренировок.
    Курс: {plan_title}
    
    Данные клиента:
    - Пол: {user_data.get('gender')}
    - Вес: {user_data.get('weight')} кг
    - Рост: {user_data.get('height')} см
    - Возраст: {user_data.get('age')} лет
    - Опыт: {user_data.get('experience')}
    - Оборудование: {user_data.get('equipment')}
    - Ограничения/Травмы: {user_data.get('injuries')}

    Требования к ответу:
    1. Формат Markdown (используй заголовки ##, списки и жирный текст).
    2. План на 4 недели.
    3. Советы по питанию под эти параметры.
    4. Мотивирующее вступление.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # Или gpt-3.5-turbo для экономии
            messages=[
                {"role": "system", "content": "Ты эксперт по фитнесу и биомеханике. Отвечай на русском языке."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7 # Немного креативности, но без фанатизма
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка AI: {e}")
        return "Извини, произошла ошибка при генерации плана. Попробуй позже."