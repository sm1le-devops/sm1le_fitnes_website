import json
import os
import logging

async def generate_training_plan(user_data: dict, plan_title: str):
    """
    Конструктор плана: собирает Markdown из JSON шаблонов.
    """
    try:
        # 1. Загружаем JSON
        # Убедись, что файл лежит в корне проекта
        with open("muscle_gain_data.json", "r", encoding="utf-8") as f:
            db = json.load(f)

        height = int(user_data.get("height", 170))
        # Очистка текста травм для надежного поиска
        injuries = str(user_data.get("injuries", "")).lower().strip()
        
        output = []
        
        # Шапка плана
        output.append(f"# {db['program_meta']['name']}")
        output.append(f"**Продолжительность:** {db['program_meta']['duration']}")
        output.append(f"**Основной фокус:** {db['program_meta']['focus']}\n")
        
        # Блок питания (оформляем как важную заметку)
        output.append("## 🍏 Базовые рекомендации по питанию")
        output.append(f"> {db['modules']['nutrition_base']}\n")

        # Адаптация под РОСТ
        if height >= 185:
            output.append("## 📏 Рекомендации по биомеханике (высокий рост)")
            output.append(f"> {db['modules']['tall_person_advice']}\n")

        # Адаптация под ТРАВМЫ
        has_shoulder_injury = any(x in injuries for x in ["плечо", "плече", "shoulder", "сустав"])
        if has_shoulder_injury:
            output.append("## ⚠️ Особые указания по безопасности")
            output.append(f"> {db['modules']['shoulder_injury_mod']}\n")

        # Сборка тренировочного процесса
        output.append("# 🏋️ Программа тренировок")
        
        for week in db['weeks']:
            output.append(f"## 📅 Неделя {week['week']}: {week['title']}")
            
            # Если это упрощенная неделя (просто текст)
            if isinstance(week['workouts'], str):
                output.append(week['workouts'])
                continue

            # Если детально расписанные тренировки
            for workout in week['workouts']:
                output.append(f"### ⚡ {workout['day']}")
                
                for ex in workout['exercises']:
                    name = ex['name']
                    # Логика замены упражнения при травме
                    if has_shoulder_injury and "жим штанги" in name.lower():
                        name = "Жим гантелей (нейтральный хват)"
                    
                    output.append(f"* **{name}** — `{ex['sets']}`")
                
                # Добавляем лайфхаки (те самые 3 совета)
                if "tips" in workout:
                    output.append("\n**💡 Лайфхаки и советы дня:**")
                    for tip in workout['tips']:
                        output.append(f"- {tip}")
                
                output.append("\n---") # Разделитель между днями

        # Собираем всё в одну строку
        final_text = "\n\n".join(output)
        
        logging.info("✅ План успешно собран конструктором")
        return final_text

    except Exception as e:
        logging.error(f"❌ Ошибка конструктора: {e}")
        return "Извините, возникла техническая ошибка при сборке плана. Мы уже работаем над этим!"