"""Ashby fetcher (undocumented GraphQL board endpoint).

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

Ashby throttles aggressively: requests are jittered, User-Agents rotated,
and 429/502/503 retried with exponential backoff.
"""

import random
import time

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.http import (
    is_retryable_status,
    random_user_agent,
    retry_delay,
)
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_ashby(slug: str) -> FetchResult:
    """Fetch all postings for an Ashby-hosted job board.

    Args:
        slug: Ashby organization slug (e.g. ``"zip"``).

    Returns:
        ``(slug, jobs, status)``. ``status`` is 200 with jobs, 404 when
        the board has no postings, the last HTTP status when retries are
        exhausted, or None on network/parse failure. Only ``title``,
        ``locationName`` and ``id`` are available from this endpoint, so
        records carry no geocoordinates.
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

        # Jitter before request to spread out concurrent workers
        time.sleep(random.uniform(0.5, 2.0))

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
