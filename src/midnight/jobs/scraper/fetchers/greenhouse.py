"""Greenhouse fetcher (public boards API, no auth)."""

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.geo import enrich_location
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
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            data = response.json()
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

        return slug, [], response.status_code  # got a response, just not 200

    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching Greenhouse for {slug}: {e}")
    return slug, [], None
