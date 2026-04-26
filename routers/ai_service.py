import json
import os
import logging

async def generate_training_plan(user_data: dict, plan_title: str):
    try:
        with open("muscle_gain_data.json", "r", encoding="utf-8") as f:
            db = json.load(f)

        gender = str(user_data.get("gender", "Мужской")).lower()
        height = int(user_data.get("height", 170))
        
        output = []
        output.append(f"# {db['program_meta']['name']}")
        output.append(f"> {db['modules']['nutrition_base']}\n")

        # Адаптация под ПОЛ (Новое!)
        if "жен" in gender:
            output.append("## 🌸 Особенности женского рациона")
            output.append(db['modules']['gender_female_advice'])
        else:
            output.append("## 🛡️ Особенности мужского рациона")
            output.append(db['modules']['gender_male_advice'])

        if height >= 185:
            output.append(f"\n> **Совет для высоких:** {db['modules']['tall_person_advice']}")

        output.append("\n## 🍽️ Твое меню на день")
        for meal in db['meals']:
            output.append(f"### {meal['type']}")
            # Выбираем первый вариант или можно добавить рандом
            choice = meal['options'][0] 
            output.append(f"* **{choice['name']}**")
            output.append(f"  *📊 {choice['macros']}*")

        output.append("\n---\n**💡 Совет дня:** Пей не менее 35мл воды на 1кг веса для лучшего синтеза белка.")

        return "\n\n".join(output)
    except Exception as e:
        return f"Ошибка сборки рациона: {e}"