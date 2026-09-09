import asyncio
from random import choice
from typing import Any

from midnight.hackathons.devpost import scrape_devpost
from midnight.utils.seen import load_seen, save_seen

NUM_HACKATHONS = 5


async def get_hackathon_data() -> list[dict[str, Any]]:
    """Fetch hackathon data from the web."""
    print("Scraping web for hackathons ...")
    devpost_data = await scrape_devpost()
    seen_devpost = load_seen("hackathons")
    seen_urls = set(seen_devpost)
    selected_urls: list[str] = []

    available = [
        hackathon
        for hackathon in devpost_data
        if isinstance(hackathon, dict)
        and hackathon.get("url")
        and hackathon.get("url") not in seen_urls
    ]

    selected: list[dict[str, Any]] = []
    while available and len(selected) < NUM_HACKATHONS:
        # Ranking
        hackathon = choice(available)

        selected.append(hackathon)
        url = hackathon.get("url")
        if isinstance(url, str):
            selected_urls.append(url)

        available.remove(hackathon)

    print(f"Found {len(selected)} hackathons worth your time...")

    seen_devpost.extend(selected_urls)
    save_seen("hackathons", seen_devpost)

    return selected


if __name__ == "__main__":
    hackathon_data = asyncio.run(get_hackathon_data())
    if hackathon_data:
        print(hackathon_data[0])
    else:
        print("No hackathons found.")
