import asyncio
from random import choice

from midnight.hackathons.devpost import scrape_devpost
from midnight.utils.seen import load_seen, save_seen

NUM_HACKATHONS = 5
HACKATHON_DATA: list[dict[str, str]] = []


async def get_hackathon_data():

    print("Scraping web for hackathons ...")
    devpost_data = await scrape_devpost()
    # return devpost_data
    seen_devpost = load_seen("hackathons")
    selected_urls_devpost: dict[str, list[str]] = {"devpost": []}

    available = [
        hackathon for hackathon in devpost_data if hackathon["url"] not in seen_devpost
    ]

    while available and len(HACKATHON_DATA) < NUM_HACKATHONS:
        # Ranking
        hackathon = choice(available)

        HACKATHON_DATA.append(hackathon)
        selected_urls_devpost["devpost"].append(hackathon["url"])

        available.remove(hackathon)

    print(f"Found {len(HACKATHON_DATA)} hackathons worth your time...")

    seen_devpost.extend(selected_urls_devpost["devpost"])
    save_seen("hackathons", seen_devpost)

    return HACKATHON_DATA


if __name__ == "__main__":
    hackathon_data = asyncio.run(get_hackathon_data())
    # print(hackathon_data[0])
