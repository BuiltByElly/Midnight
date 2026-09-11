"""Lever fetcher (public postings API, no auth).

Requests are jittered, carry a rotated browser User-Agent, and
429/502/503 responses (plus connection errors) are retried with
exponential backoff honoring ``Retry-After``.
"""

import random
import time

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.geo import enrich_location
from midnight.jobs.scraper.http import (
    compute_backoff,
    is_retryable_status,
    random_user_agent,
    retry_delay,
)
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_lever(slug: str) -> FetchResult:
    """Fetch all postings for a Lever company.

    Hits ``https://api.lever.co/v0/postings/{slug}``. The posting
    location comes from the ``categories.location`` field.

    Args:
        slug: Lever company slug.

    Returns:
        ``(slug, jobs, status)`` with ``status`` None on
        network/parse failure.
    """
    url = f"https://api.lever.co/v0/postings/{slug}"
    headers = {
        "Accept": "application/json",
        "User-Agent": random_user_agent(),
    }

    # Jitter before request to spread out concurrent workers
    time.sleep(random.uniform(0.5, 2.0))

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, timeout=30, headers=headers)
        except requests.RequestException as e:
            if attempt < max_retries:
                delay = compute_backoff(attempt)
                print(f"  Lever {slug}: connection error, retrying in {delay:.1f}s")
                time.sleep(delay)
                headers["User-Agent"] = random_user_agent()
                continue
            print(f"Error fetching Lever for {slug}: {e}")
            return slug, [], None

        if response.status_code == 200:
            try:
                jobs = response.json()
            except ValueError as e:
                print(f"Error fetching Lever for {slug}: {e}")
                return slug, [], None

            if jobs:
                normalized = []
                for job in jobs:
                    categories = job.get("categories", {})
                    location = categories.get("location", "Not specified")[:50]
                    remote, coords = enrich_location(location)
                    normalized.append(
                        {
                            "company": slug,
                            "company_slug": slug,
                            "title": job.get("text"),
                            "location": location,
                            "remote": remote,
                            "coords": coords,
                            "url": job.get("hostedUrl"),
                            "description": job.get("descriptionPlain")
                            or job.get("description"),
                            "is_recruiter": is_recruiter_company(slug),
                            "ats": "Lever",
                            "skill_level": job_tier_classification(job.get("text", "")),
                            **get_job_metadata(),
                        }
                    )
                return slug, normalized, response.status_code
            return slug, [], response.status_code

        if is_retryable_status(response.status_code) and attempt < max_retries:
            delay = retry_delay(response, attempt)
            print(f"  Lever {slug}: {response.status_code}, retrying in {delay:.1f}s")
            time.sleep(delay)
            headers["User-Agent"] = random_user_agent()
            continue

        return slug, [], response.status_code  # got a response, just not 200

    return slug, [], None
