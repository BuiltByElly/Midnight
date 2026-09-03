
from bs4 import BeautifulSoup
from playwright.sync_api import Page

PAGE = 4
RESULT: list[dict[str, str]] = []


def scrape_devpost(page: Page):
    _ = page.goto(
        f"https://devpost.com/hackathons?challenge_type[]=online&length[]=weeks&length[]=months&open_to[]=public&order_by=recently-added&page=2&status[]=upcoming&status[]=open&themes[]=Beginner%20Friendly&themes[]=Machine%20Learning%2FAI&themes[]=Social%20Good&themes[]=Open%20Ended&themes[]=Web&themes[]=Design&themes[]=Mobile&page={PAGE}"
    )
    html = page.content()

    # Parsing
    soup = BeautifulSoup(html, "html.parser")
    hackathons = soup.select(".hackathon-tile")

    # Normalizing
    for hackathon in hackathons:
        title = hackathon.select_one("h3")
        url = hackathon.select_one(".tile-anchor")
        source = "Devpost"
        date = hackathon.select_one(".submission-period")

        RESULT.append(
            {
                "title": title.text if title else "Error getting title",
                "url": str(url.get("href")) if url else "Error getting url",
                "source": source,
                "date": date.text if date else "Error getting date",
            }
        )

    return RESULT
