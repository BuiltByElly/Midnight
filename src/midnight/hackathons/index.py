from random import choice

from playwright.sync_api import Browser

from midnight.hackathons.devpost import scrape_devpost
from midnight.utils.seen import load_seen, save_seen

NUM_HACKATHONS = 5
HACKATHON_DATA: list[dict[str, str]] = []


def get_hackathon_data(browser: Browser):
    context = browser.new_context()
    devpost_page = context.new_page()

    print("Scraping web for hackathons ...")
    devpost_data = scrape_devpost(devpost_page)

    seen = load_seen("hackathons")
    selected_urls: set[str] = set()

    available = [
        hackathon for hackathon in devpost_data if hackathon["url"] not in seen
    ]

    while available and len(HACKATHON_DATA) < NUM_HACKATHONS:
        hackathon = choice(available)

        HACKATHON_DATA.append(hackathon)
        selected_urls.add(hackathon["url"])

        available.remove(hackathon)

    print(f"Found {len(HACKATHON_DATA)} hackathons worth your time...")

    seen.update(selected_urls)
    save_seen("hackathons", seen)
    context.close()

    return HACKATHON_DATA
