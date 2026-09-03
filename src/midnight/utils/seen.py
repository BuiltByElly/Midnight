import json
from pathlib import Path

SEEN_PATH = Path(__file__).parent.parent / "data/seen.json"


def load_seen(opportunity_type: str) -> set[str]:
    with open(SEEN_PATH, "r") as file:
        data = json.load(file)

    return set(data["seen"].get(opportunity_type, []))


def save_seen(opportunity_type: str, seen: set[str]):
    with open(SEEN_PATH, "r") as file:
        data = json.load(file)

    data["seen"][opportunity_type] = list(seen)

    with open(SEEN_PATH, "w") as file:
        json.dump(data, file, indent=2)
