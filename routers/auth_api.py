import os
import google.generativeai as genai
import asyncio

# Настройка API ключа с явным указанием версии v1
# Это принудительно заставит библиотеку не использовать v1beta
os.environ["GOOGLE_API_VERSION"] = "v1" 

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def generate_training_plan(user_data: dict, plan_title: str):
    # Попробуем использовать модель без префикса models/, 
    # так как мы принудительно переключили версию API выше
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Ты — профессиональный фитнес-тренер. Составь план... (ваш текст)
    """

    try:
        # ЛОГ ДЛЯ ПРОВЕРКИ
        print(f"DEBUG: Попытка запроса к Gemini через API v1")
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        # Если снова 404, попробуйте заменить 'gemini-1.5-flash' на 'gemini-pro'
        return response.text

    except Exception as e:
        print(f"Критическая ошибка Gemini: {e}")
        # Если ошибка содержит 404, попробуем запасную модель
        if "404" in str(e):
             print("Пытаемся использовать запасную модель gemini-pro...")
             try:
                 fallback_model = genai.GenerativeModel('gemini-pro')
                 resp = await asyncio.to_thread(fallback_model.generate_content, prompt)
                 return resp.text
             except:
                 return None
        return None