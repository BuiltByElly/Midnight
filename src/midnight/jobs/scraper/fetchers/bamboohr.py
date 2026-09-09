"""BambooHR fetcher (``https://{slug}.bamboohr.com/careers/list``).

Browser-console equivalent::

    fetch("https://{slug}.bamboohr.com/careers/list", {
        method: "GET",
        headers: {"Content-Type": "application/json"},
    }).then(r => r.json()).then(console.log)
"""

import random
import time

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.geo import enrich_location
from midnight.jobs.scraper.http import random_user_agent
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_bamboohr(slug: str) -> FetchResult:
    """Fetch all openings for a BambooHR career site.

    A 200 without a JSON content-type means the slug has no BambooHR
    site and is reported as 404 (dead-slug candidate). 429/502/503 and
    TLS errors are retried with backoff.

    Args:
        slug: BambooHR subdomain slug.

    Returns:
        ``(slug, jobs, status)`` with ``status`` None only when no HTTP
        response was ever received.
    """
    url = f"https://{slug}.bamboohr.com/careers/list"

    time.sleep(random.uniform(0.5, 2.0))

    max_retries = 2
    for attempt in range(max_retries + 1):
        headers = {
            "Accept": "application/json",
            "User-Agent": random_user_agent(),
        }

        try:
            response = requests.get(url, timeout=30, headers=headers)

            if response.status_code == 200:
                if "application/json" not in response.headers.get("Content-Type", ""):
                    return slug, [], 404

                data = response.json()
                jobs = data.get("result", [])

                if jobs:
                    normalized = []
                    for job in jobs:
                        loc = job.get("location") or {}
                        if isinstance(loc, dict):
                            city = loc.get("city", "")
                            state = loc.get("state", "")
                            location = (
                                ", ".join(filter(None, [city, state]))
                                or "Not specified"
                            )
                        else:
                            location = str(loc) if loc else "Not specified"

                        remote, coords = enrich_location(location)
                        normalized.append(
                            {
                                "company": slug,
                                "company_slug": slug,
                                "title": job.get("jobOpeningName"),
                                "location": location[:50],
                                "remote": remote,
                                "coords": coords,
                                "url": f"https://{slug}.bamboohr.com/careers/{job.get('id')}",
                                "is_recruiter": is_recruiter_company(slug),
                                "ats": "BambooHR",
                                "skill_level": job_tier_classification(
                                    job.get("jobOpeningName", "")
                                ),
                                **get_job_metadata(),
                            }
                        )
                    return slug, normalized, response.status_code

                return slug, [], response.status_code

            if response.status_code in (429, 503, 502) and attempt < max_retries:
                backoff = (2**attempt) + random.uniform(0.5, 1.5)
                time.sleep(backoff)
                continue

            return slug, [], response.status_code

        except requests.exceptions.SSLError:
            if attempt < max_retries:
                time.sleep((2**attempt) + random.uniform(0.5, 1.5))
                continue
            return slug, [], None
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching BambooHR for {slug}: {e}")
            return slug, [], None

    return slug, [], None
