import json

from services import ai_service


def test_generate_training_plan_from_json(
    tmp_path,
    monkeypatch,
):
    data = {
        "program_meta": {
            "name": "Test Program",
            "duration": "4 weeks",
            "focus": "strength",
        },
        "modules": {
            "nutrition_base": "Eat well",
            "tall_person_advice": "Control range",
            "shoulder_injury_mod": "Reduce load",
        },
        "weeks": [
            {
                "week": 1,
                "title": "Start",
                "workouts": [
                    {
                        "day": "Day 1",
                        "exercises": [
                            {
                                "name": "Жим штанги",
                                "sets": "3x8",
                            }
                        ],
                        "tips": [
                            "Sleep well"
                        ],
                    }
                ],
            }
        ],
    }

    path = tmp_path / "data.json"
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ai_service,
        "PROGRAM_DATA_PATH",
        path,
    )

    result = ai_service.generate_training_plan(
        {
            "height": 190,
            "injuries": "плечо",
        },
        "Custom title",
    )

    assert result is not None
    assert "# Custom title" in result
    assert "высокий рост" in result
    assert "Особые указания" in result
    assert "Жим гантелей" in result
    assert "Sleep well" in result


def test_generate_training_plan_returns_none_on_error(
    tmp_path,
    monkeypatch,
):
    missing = tmp_path / "missing.json"

    monkeypatch.setattr(
        ai_service,
        "PROGRAM_DATA_PATH",
        missing,
    )

    result = ai_service.generate_training_plan(
        {},
        "Title",
    )

    assert result is None
