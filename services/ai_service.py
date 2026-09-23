import json
import logging
from pathlib import Path


PROGRAM_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "muscle_gain_data.json"
)


def generate_training_plan(
    user_data: dict,
    plan_title: str,
) -> str | None:
    try:
        with PROGRAM_DATA_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        height = int(user_data.get("height", 170))
        injuries = (
            str(user_data.get("injuries", ""))
            .lower()
            .strip()
        )

        output = []

        program_name = (
            plan_title
            or data["program_meta"]["name"]
        )

        output.append(f"# {program_name}")
        output.append(
            f"**Duration:** "
            f"{data['program_meta']['duration']}"
        )
        output.append(
            f"**Primary Focus:** "
            f"{data['program_meta']['focus']}\n"
        )

        output.append(
            "## 🍏 Basic Nutrition Guidelines"
        )
        output.append(
            f"> {data['modules']['nutrition_base']}\n"
        )

        if height >= 185:
            output.append(
                "## 📏 Biomechanics Recommendations "
                "(tall users)"
            )
            output.append(
                f"> {data['modules']['tall_person_advice']}\n"
            )

        has_shoulder_injury = any(
            word in injuries
            for word in (
                "плечо",
                "плече",
                "shoulder",
                "сустав",
            )
        )

        if has_shoulder_injury:
            output.append(
                "Special Safety Guidelines"
            )
            output.append(
                f"> {data['modules']['shoulder_injury_mod']}\n"
            )

        output.append("# 🏋️ Training Program")

        for week in data["weeks"]:
            output.append(
                f"## 📅 Week {week['week']}: "
                f"{week['title']}"
            )

            if isinstance(week["workouts"], str):
                output.append(week["workouts"])
                continue

            for workout in week["workouts"]:
                output.append(
                    f"### ⚡ {workout['day']}"
                )

                for exercise in workout["exercises"]:
                    name = exercise["name"]

                    if (
                        has_shoulder_injury
                        and any(
                            phrase in name.lower()
                            for phrase in (
                                "жим штанги",
                                "barbell press",
                                "barbell bench press",
                            )
                        )
                    ):
                        name = (
                            "Dumbbell Press "
                            "(neutral grip)"
                    )

                    output.append(
                        f"* **{name}** — "
                        f"`{exercise['sets']}`"
                    )

                if "tips" in workout:
                    output.append(
                        "\n**💡 Tips for the Day:**"
                    )

                    for tip in workout["tips"]:
                        output.append(f"- {tip}")

                output.append("\n---")

        final_text = "\n\n".join(output)

        logging.info(
            "Training plan generated successfully"
        )

        return final_text

    except Exception:
        logging.exception(
            "Failed to generate training plan"
        )
        return None
