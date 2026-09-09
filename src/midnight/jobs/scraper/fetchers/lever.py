"""Lever fetcher (public postings API, no auth)."""

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.geo import enrich_location
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
    try:
        url = f"https://api.lever.co/v0/postings/{slug}"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            jobs = response.json()

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
                            "is_recruiter": is_recruiter_company(slug),
                            "ats": "Lever",
                            "skill_level": job_tier_classification(job.get("text", "")),
                            **get_job_metadata(),
                        }
                    )
                return slug, normalized, response.status_code
        return slug, [], response.status_code  # got a response, just not 200
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching Lever for {slug}: {e}")
    return slug, [], None
