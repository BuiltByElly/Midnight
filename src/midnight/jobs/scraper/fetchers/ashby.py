"""Ashby fetcher (official posting API, GraphQL fallback).

Primary path is the public posting API::

    GET https://api.ashbyhq.com/posting-api/job-board/{slug}

which returns ``descriptionPlain`` plus ``isRemote``, ``workplaceType``,
``employmentType`` and ``publishedAt`` per posting at no extra cost.
Not every board is covered, so a 404 falls back to the undocumented
GraphQL board endpoint (title/location/id only, no descriptions).

Ashby throttles aggressively: requests are jittered, User-Agents rotated,
and 429/502/503 retried with exponential backoff.
"""

import random
import time

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.geo import enrich_location
from midnight.jobs.scraper.http import (
    is_retryable_status,
    random_user_agent,
    retry_delay,
)
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def _normalize_posting_api(slug: str, jobs: list) -> list:
    """Normalize official posting-API entries (with descriptions)."""
    normalized = []
    for job in jobs:
        location = (job.get("location") or "Not specified")[:50]
        remote = bool(job.get("isRemote"))
        coords = None
        if not remote:
            _, coords = enrich_location(location)
        normalized.append(
            {
                "company": slug,
                "company_slug": slug,
                "title": job.get("title", ""),
                "location": location,
                "remote": remote,
                "coords": coords,
                "url": job.get("jobUrl")
                or f"https://jobs.ashbyhq.com/{slug}/{job.get('id')}",
                "description": job.get("descriptionPlain"),
                "updated_at": job.get("publishedAt"),
                "is_recruiter": is_recruiter_company(slug),
                "ats": "Ashby",
                "skill_level": job_tier_classification(job.get("title", "")),
                **get_job_metadata(),
            }
        )
    return normalized


def _fetch_via_posting_api(slug: str) -> FetchResult | None:
    """Fetch via the official posting API.

    Args:
        slug: Ashby organization slug (e.g. ``"zip"``).

    Returns:
        ``(slug, jobs, status)``, or None when the board is not
        covered by this endpoint (404) and the caller should fall back
        to GraphQL.
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    headers = {
        "Accept": "application/json",
        "User-Agent": random_user_agent(),
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            return None  # board not covered -> GraphQL fallback
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as e:
                print(f"Error fetching Ashby for {slug}: {e}")
                return slug, [], None
            jobs = data.get("jobs", [])
            if jobs:
                return slug, _normalize_posting_api(slug, jobs), 200
            return slug, [], 404
        if is_retryable_status(response.status_code) and attempt < max_retries:
            delay = retry_delay(response, attempt)
            print(f"  Ashby {slug}: {response.status_code}, retrying in {delay:.1f}s")
            time.sleep(delay)
            headers["User-Agent"] = random_user_agent()
            continue
        return slug, [], response.status_code
    return slug, [], None


def _fetch_via_graphql(slug: str) -> FetchResult:
    """Fetch via the undocumented GraphQL board endpoint (no descriptions).

    Browser-console equivalent::

        fetch("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            operationName: "ApiJobBoardWithTeams",
            variables: {organizationHostedJobsPageName: "zip"},
            query: "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) "
                   + "{ jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: "
                   + "$organizationHostedJobsPageName) { jobPostings { id title locationName } } }",
          }),
        }).then(r => r.json()).then(console.log)

    Args:
        slug: Ashby organization slug.

    Returns:
        ``(slug, jobs, status)``. Records carry no descriptions or
        geocoordinates -- only ``title``, ``locationName`` and ``id``
        are available here.
    """
    try:
        url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id title locationName } } }",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": random_user_agent(),
        }

        max_retries = 2
        jobs = None
        for attempt in range(max_retries + 1):
            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                jobs = (data.get("data") or {}).get("jobBoard") or {}
                jobs = jobs.get("jobPostings") or []
            elif is_retryable_status(response.status_code) and attempt < max_retries:
                delay = retry_delay(response, attempt)
                print(
                    f"  Ashby {slug}: {response.status_code}, retrying in {delay:.1f}s"
                )
                time.sleep(delay)
                headers["User-Agent"] = random_user_agent()
                continue
            elif attempt > max_retries:
                print(f"  Ashby {slug}: {response.status_code}, max retries exhausted")
                return slug, [], response.status_code

        if jobs:
            normalized = []
            for job in jobs:
                normalized.append(
                    {
                        "company": slug,
                        "company_slug": slug,
                        "title": job.get("title", ""),
                        "location": job.get("locationName", "Not specified")[:50],
                        "url": f"https://jobs.ashbyhq.com/{slug}/{job.get('id')}",
                        "is_recruiter": is_recruiter_company(slug),
                        "ats": "Ashby",
                        "skill_level": job_tier_classification(job.get("title", "")),
                        **get_job_metadata(),
                    }
                )
            return slug, normalized, 200

        return slug, [], 404

    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching Ashby for {slug}: {e}")
    return slug, [], None


def fetch_company_jobs_ashby(slug: str) -> FetchResult:
    """Fetch all postings for an Ashby-hosted job board.

    Tries the official posting API first (includes descriptions),
    falling back to GraphQL for boards it does not cover.

    Args:
        slug: Ashby organization slug (e.g. ``"zip"``).

    Returns:
        ``(slug, jobs, status)`` with ``status`` None only when no
        HTTP response was received.
    """
    # Jitter before request to spread out concurrent workers
    time.sleep(random.uniform(0.5, 2.0))

    try:
        result = _fetch_via_posting_api(slug)
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching Ashby for {slug}: {e}")
        return slug, [], None
    if result is not None:
        return result
    print(f"  Ashby {slug}: posting API has no board, trying GraphQL")
    return _fetch_via_graphql(slug)
