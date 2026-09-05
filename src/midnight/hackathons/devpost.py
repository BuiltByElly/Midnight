import asyncio
from typing import Any

import httpx

PAGE = 4
RESULT: list[dict[str, str]] = []

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


async def fetch_devpost_page(client: httpx.AsyncClient, page: int):
    """Fetch a single page of hackathons from Devpost API."""
    params = {**QUERY_PARAMS, "page": page}
    try:
        response = await client.get(DEVPOST_API_URL, params=params)
        _ = response.raise_for_status()
        data = response.json()
        return data.get("hackathons", [])
    except httpx.HTTPStatusError as e:
        print(f"HTTP error on page {page}: {e.response.status_code}")
    except httpx.HTTPError as e:
        print(f"Failed to fetch Devpost page {page}: {e}")
    return []


async def scrape_devpost(max_pages: int = 3):
    """Fetch pages concurrently using a shared async HTTP client."""
    async with httpx.AsyncClient(
        headers=HEADERS, timeout=10.0, follow_redirects=True
    ) as client:
        tasks = [fetch_devpost_page(client, page) for page in range(1, max_pages + 1)]
        pages = await asyncio.gather(*tasks)
        # Flatten page arrays into a single list
        return [item for page in pages for item in page]
