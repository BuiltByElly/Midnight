"""Greenhouse fetcher (public boards API, no auth).

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


def fetch_company_jobs_greenhouse(slug: str) -> FetchResult:
    """Fetch all jobs for a Greenhouse board.

    Hits ``https://boards-api.greenhouse.io/v1/boards/{slug}/jobs``
    and normalizes each posting (location geocoding, recruiter flag,
    seniority tier, scrape metadata).

    Args:
        slug: Greenhouse board slug (e.g. ``"stripe"``).

    Returns:
        ``(slug, jobs, status)`` where ``jobs`` is the normalized list
        and ``status`` is the HTTP status, or None on network/parse
        failure.
    """
    # content=true includes the full post description per job.
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
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
                print(
                    f"  Greenhouse {slug}: connection error, retrying in {delay:.1f}s"
                )
                time.sleep(delay)
                headers["User-Agent"] = random_user_agent()
                continue
            print(f"Error fetching Greenhouse for {slug}: {e}")
            return slug, [], None

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as e:
                print(f"Error fetching Greenhouse for {slug}: {e}")
                return slug, [], None
            jobs = data.get("jobs", [])

            if jobs:
                # Normalize job structure for frontend
                normalized = []
                for job in jobs:
                    location = job.get("location", {}).get("name", "Not specified")
                    remote, coords = enrich_location(location)
                    normalized.append(
                        {
                            "company": slug,
                            "company_slug": slug,
                            "title": job.get("title"),
                            "location": location,
                            "remote": remote,
                            "coords": coords,
                            "url": job.get("absolute_url"),
                            "absolute_url": job.get("absolute_url"),
                            "description": job.get("content"),
                            "departments": [
                                d.get("name") for d in job.get("departments", [])
                            ],
                            "id": job.get("id"),
                            "updated_at": job.get("updated_at"),
                            "is_recruiter": is_recruiter_company(slug),
                            "ats": "Greenhouse",
                            "skill_level": job_tier_classification(
                                job.get("title", "")
                            ),
                            **get_job_metadata(),
                        }
                    )

                return slug, normalized, response.status_code

            return slug, [], response.status_code

        if is_retryable_status(response.status_code) and attempt < max_retries:
            delay = retry_delay(response, attempt)
            print(
                f"  Greenhouse {slug}: {response.status_code}, retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            headers["User-Agent"] = random_user_agent()
            continue

        return slug, [], response.status_code  # got a response, just not 200

    return slug, [], None
