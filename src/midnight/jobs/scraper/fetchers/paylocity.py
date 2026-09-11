"""Paylocity fetcher (HTML scrape, no JSON API).

Jobs come from the ``window.pageData`` blob in the page HTML at::

    https://recruiting.paylocity.com/recruiting/jobs/All/{guid}/

``slug`` here is the tenant GUID; the display name resolves via
:data:`companies.PAYLOCITY_NAMES`. A page that loads without the blob
is treated as a soft block (returned with status 200 so the slug
retries next run instead of being cached as dead). Reset/aborted
connections mean throttling: the thread's session is dropped and the
request retried with backoff.
"""

import contextlib
import html
import json
import random
import time

import requests

from midnight.jobs.scraper.classify import (
    is_recruiter_company,
    job_tier_classification,
    paylocity_location,
)
from midnight.jobs.scraper.companies import PAYLOCITY_NAMES
from midnight.jobs.scraper.config import PAGEDATA_RE
from midnight.jobs.scraper.geo import enrich_location
from midnight.jobs.scraper.http import (
    compute_backoff,
    is_retryable_status,
    paylocity_session,
    random_user_agent,
    reset_paylocity_session,
    retry_delay,
)
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_paylocity(slug: str) -> FetchResult:
    """Fetch all jobs for a Paylocity tenant GUID.

    Args:
        slug: Paylocity tenant GUID.

    Returns:
        ``(slug, jobs, status)``. Detail URLs point at
        ``.../Jobs/Details/{job_id}``. ``status`` is None only when no
        HTTP response was received after all retries.
    """
    url = f"https://recruiting.paylocity.com/recruiting/jobs/All/{slug}/"
    session = paylocity_session()
    # jitter so concurrent workers don't fire in lockstep
    time.sleep(random.uniform(0.5, 2.0))
    max_retries = 3
    for attempt in range(max_retries + 1):
        headers = {"User-Agent": random_user_agent()}
        try:
            response = session.get(url, timeout=30, headers=headers)
        except requests.RequestException as e:
            # reset/abort = throttling. drop the poisoned connection, back off, retry.
            with contextlib.suppress(OSError):
                session.close()
            session = reset_paylocity_session()
            if attempt < max_retries:
                time.sleep(compute_backoff(attempt, 1.0, 2.0))
                continue
            print(f"Error fetching Paylocity for {slug}: {e}")
            return slug, [], None
        if is_retryable_status(response.status_code):
            if attempt < max_retries:
                time.sleep(retry_delay(response, attempt, 1.0, 2.0))
                continue
            return slug, [], response.status_code
        if response.status_code != 200:
            return slug, [], response.status_code
        m = PAGEDATA_RE.search(response.text)
        if not m:
            # page loaded but blob missing = soft block or layout drift.
            # return 200 so it retries next run, NOT cached as dead.
            return slug, [], 200
        try:
            data = json.loads(m.group(1))
        except ValueError:
            return slug, [], 200
        company = PAYLOCITY_NAMES.get(slug, slug)
        normalized = []
        for job in data.get("Jobs") or []:
            job_id = job.get("JobId")
            title = html.unescape(job.get("JobTitle") or "")
            location = paylocity_location(job)
            inferred_remote, coords = enrich_location(location)
            remote = bool(job.get("IsRemote")) or inferred_remote
            dept = job.get("HiringDepartment")  # almost always null on Paylocity
            if dept:
                dept = html.unescape(dept)
            detail = (
                f"https://recruiting.paylocity.com/recruiting/Jobs/Details/{job_id}"
                if job_id
                else url
            )
            normalized.append(
                {
                    "company": company,
                    "company_slug": slug,  # the GUID
                    "title": title,
                    "location": location,
                    "remote": remote,
                    "coords": coords,
                    "url": detail,
                    "absolute_url": detail,
                    "description": job.get("Description"),
                    "departments": [dept] if dept else [],
                    "id": job_id,
                    "updated_at": job.get("PublishedDate"),
                    "is_recruiter": is_recruiter_company(company),
                    "ats": "Paylocity",
                    "skill_level": job_tier_classification(title or ""),
                    **get_job_metadata(),
                }
            )
        return slug, normalized, response.status_code
    return slug, [], None
