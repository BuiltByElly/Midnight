import json
from pathlib import Path

SEEN_PATH = Path(__file__).parent.parent / "data/seen.json"


def load_seen(opportunity_type: str) -> list[str]:
    with open(SEEN_PATH, "r") as file:
        data = json.load(file)

    return data["seen"].get(opportunity_type, [])


def save_seen(opportunity_type: str, seen: list[str]):
    with open(SEEN_PATH, "r") as file:
        data = json.load(file)

    data["seen"][opportunity_type] = seen
    with open(SEEN_PATH, "w") as file:
        json.dump(data, file, indent=2)
