"""Workday fetcher (paginated ``/wday/cxs/.../jobs`` JSON API).

Slugs have the form ``"company|wd#|site_id"`` (e.g.
``"kohls|wd1|kohlscareers"``), mapping to::

    https://{company}.wd{num}.myworkdayjobs.com/wday/cxs/{company}/{site_id}/jobs

Pages of 20 are walked with jitter between them. Workday sometimes
changes ``total`` mid-pagination when throttling -- that is treated as
a silent block and pagination stops.
"""

import random
import time

import requests

from midnight.jobs.scraper.classify import (
    is_recruiter_company,
    job_tier_classification,
    parse_workday_posted_on,
)
from midnight.jobs.scraper.geo import enrich_location
from midnight.jobs.scraper.http import parse_retry_after, random_user_agent
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_workday(slug: str) -> FetchResult:
    """Fetch all postings for a Workday tenant, walking every page.

    Args:
        slug: ``"company|wd#|site_id"`` triple identifying the tenant.

    Returns:
        ``(slug, jobs, status)``. Malformed slugs and transport
        failures yield ``(slug, [], None)``; a non-200 page after
        retries ends pagination and returns what was collected with
        the last page's status.
    """
    try:
        parts = slug.split("|")
        if len(parts) != 3:
            return slug, [], None

        company, wd, site_id = parts
        wd_num = wd.replace("wd", "")

        base_url = f"https://{company}.wd{wd_num}.myworkdayjobs.com"
        api_url = f"{base_url}/wday/cxs/{company}/{site_id}/jobs"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": random_user_agent(),
            "Origin": base_url,
            "Referer": f"{base_url}/{site_id}",
        }

        normalized = []
        offset = 0
        limit = 20
        retries = 0
        max_retries = 2
        observed_total = None

        while True:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }

            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                if retries < max_retries:
                    retries += 1
                    hint = parse_retry_after(response)
                    time.sleep(hint if hint is not None else random.uniform(2.0, 4.0))
                    continue
                break

            data = response.json()
            jobs = data.get("jobPostings", [])
            total = data.get("total", 0)

            # Detect silent blocking / truncation
            if observed_total is None:
                observed_total = total
            elif total != observed_total:
                # Workday sometimes lies mid-pagination when blocking
                break

            if not jobs:
                break

            for job in jobs:
                job_path = job.get("externalPath", "")
                location = (job.get("locationsText") or "Not specified")[:50]
                remote, coords = enrich_location(location)
                normalized.append(
                    {
                        "company": company,
                        "company_slug": slug,
                        "title": job.get("title"),
                        "location": location,
                        "remote": remote,
                        "coords": coords,
                        "url": f"{base_url}/{site_id}{job_path}",
                        "updated_at": parse_workday_posted_on(job.get("postedOn")),
                        "is_recruiter": is_recruiter_company(company),
                        "ats": "Workday",
                        "skill_level": job_tier_classification(job.get("title", "")),
                        **get_job_metadata(),
                    }
                )

            offset += limit

            if offset >= total:
                break

            # Jitter between pages (critical)
            time.sleep(random.uniform(0.3, 1.0))

        return slug, normalized, response.status_code

    except requests.RequestException, ValueError:
        return slug, [], None
