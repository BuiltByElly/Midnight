from time import perf_counter

from playwright.sync_api import sync_playwright

from midnight.hackathons.index import get_hackathon_data

# from midnight.profile import load_profile


def main():
    start = perf_counter()
    # profile = load_profile()
    print("Starting a chromium instance...")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        print("Getting tech opportunities...")
        hackathons = get_hackathon_data(browser)
    end = perf_counter()
    print(hackathons)
    print(f"finished in {round(end - start, 1)} seconds")


if __name__ == "__main__":
    _ = main()
