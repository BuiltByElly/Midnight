from playwright.sync_api import sync_playwright

from midnight.hackathons.index import get_hackathon_data
from midnight.profile import load_profile


def main():
    profile = load_profile()
    print("Starting a chromium instance...")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        print("Getting tech opportunities...")
        hackathons = get_hackathon_data(browser)

    return hackathons


if __name__ == "__main__":
    _ = main()
