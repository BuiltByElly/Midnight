import asyncio
from time import perf_counter

from midnight.hackathons.index import get_hackathon_data

# from playwright.sync_api import sync_playwright

# from midnight.hackathons.index import get_hackathon_data

# from midnight.profile import load_profile


def main():
    start = perf_counter()
    # profile = load_profile()
    hackathon_data = asyncio.run(get_hackathon_data())
    end = perf_counter()
    print(hackathon_data)
    print(f"finished in {round(end - start, 1)} seconds")


if __name__ == "__main__":
    _ = main()
