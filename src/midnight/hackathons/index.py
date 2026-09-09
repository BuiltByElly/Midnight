import asyncio
from random import choice
from typing import Any

from midnight.hackathons.devpost import scrape_devpost
from midnight.utils.seen import load_seen, save_seen

NUM_HACKATHONS = 5


async def get_hackathon_data() -> list[dict[str, Any]]:
    """Fetch hackathon data from the web."""
    print("\n" + "=" * 80)
    print("HACKATHON AGGREGATOR")
    print("Scraping hackathons worth your time")
    print("=" * 80)

    devpost_data = await scrape_devpost()
    print(f"\n  >>> DEVPOST COMPLETE: {len(devpost_data):,} hackathons <<<\n")

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
    print(f"  Skipping {len(devpost_data) - len(available):,} already seen hackathons")
    print(f"  Checking {len(available):,} new hackathons\n")

    selected: list[dict[str, Any]] = []
    while available and len(selected) < NUM_HACKATHONS:
        # Ranking
        hackathon = choice(available)

        selected.append(hackathon)
        url = hackathon.get("url")
        if isinstance(url, str):
            selected_urls.append(url)

        available.remove(hackathon)
        print(
            f"  [{len(selected)}/{NUM_HACKATHONS}] {hackathon.get('title', 'Untitled')}"
        )

    print("\nDETAILED STATS FOR HACKATHONS:")
    print(f"  Fetched: {len(devpost_data):,}")
    print(f"  Already seen: {len(devpost_data) - len(available) - len(selected):,}")
    print(f"  Selected: {len(selected):,}")
    print()

    seen_devpost.extend(selected_urls)
    save_seen("hackathons", seen_devpost)

    return selected


if __name__ == "__main__":
    hackathon_data = asyncio.run(get_hackathon_data())
    if hackathon_data:
        print("=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        for i, hackathon in enumerate(hackathon_data, 1):
            print(f"  [{i}/{len(hackathon_data)}] {hackathon.get('title', 'Untitled')}")
            print(f"    {hackathon.get('url', 'No URL')}")
        print(f"\nTotal hackathons:  {len(hackathon_data):,}")
        print("=" * 80 + "\n")
    else:
        print("No hackathons found.")
