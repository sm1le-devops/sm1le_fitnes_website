import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PLANS_FILE = BASE_DIR / "plans.json"


def load_plans() -> dict:
    with PLANS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


PLANS = load_plans()