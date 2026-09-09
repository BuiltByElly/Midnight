import asyncio
from typing import Any

import httpx

DEVPOST_API_URL = "https://devpost.com/api/hackathons"

# Headers mimicking a standard browser AJAX request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# search filter mapping
QUERY_PARAMS: dict[str, Any] = {
    "challenge_type[]": "online",
    "length[]": ["weeks", "months"],
    "open_to[]": "public",
    "order_by": "recently-added",
    "status[]": ["upcoming", "open"],
    "themes[]": [
        "Beginner Friendly",
        "Machine Learning/AI",
        "Social Good",
        "Open Ended",
        "Web",
        "Design",
        "Mobile",
    ],
}


async def fetch_devpost_page(
    client: httpx.AsyncClient, page: int
) -> list[dict[str, Any]]:
    """Fetch a single page of hackathons from Devpost API."""
    params = {**QUERY_PARAMS, "page": page}
    try:
        response = await client.get(DEVPOST_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return []
        hackathons = data.get("hackathons", [])
        return hackathons if isinstance(hackathons, list) else []
    except httpx.HTTPStatusError as e:
        print(f"  Devpost page {page}: HTTP error {e.response.status_code}")
    except httpx.HTTPError as e:
        print(f"  Devpost page {page}: failed to fetch ({e})")
    return []


async def scrape_devpost(max_pages: int = 3) -> list[dict[str, Any]]:
    """Fetch pages concurrently using a shared async HTTP client."""
    if max_pages < 1:
        return []
    print("=" * 80)
    print(f"FETCHING HACKATHONS FROM {max_pages} PAGES ON DEVPOST")
    print("=" * 80 + "\n")

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        tasks = [fetch_devpost_page(client, page) for page in range(1, max_pages + 1)]
        pages = await asyncio.gather(*tasks)

    for i, items in enumerate(pages, 1):
        print(f"  [{i}/{len(pages)}] page {i}: {len(items):,} hackathons")

    total = sum(len(items) for items in pages)
    print("\nDETAILED STATS FOR DEVPOST:")
    print(f"  Pages checked: {len(pages)}")
    print(f"  Total hackathons: {total:,}")
    print()

    # Flatten page arrays into a single list
    return [item for page in pages for item in page]
