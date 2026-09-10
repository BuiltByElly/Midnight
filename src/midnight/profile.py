from pathlib import Path

import yaml
from pydantic import BaseModel


class ProfileSchedule(BaseModel):
    send_time: str
    timezone: str


class ProfileLocation(BaseModel):
    city: str
    state: str
    country: str
    remote: bool


class ProfileUser(BaseModel):
    name: str
    email: str
    years_of_experience: int
    location: ProfileLocation
    tech_stack: list[str]
    interests: list[str]


class Profile(BaseModel):
    user: ProfileUser
    opportunities: list[str]
    schedule: ProfileSchedule


PROFILE_PATH = Path(__file__).parent.parent / "profile.yaml"


def load_profile() -> Profile:
    with open(PROFILE_PATH, "r") as f:
        return Profile(**yaml.safe_load(f))


if __name__ == "__main__":
    profile = load_profile()
    print(profile.model_dump_json())
