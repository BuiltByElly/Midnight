"""iCIMS fetcher (career-site sitemap, no per-job requests).

Reads ``https://careers-{slug}.icims.com/sitemap.xml``. Job URLs look like::

    https://careers-{slug}.icims.com/jobs/9620/financial-service-representative/job

The title is decoded from the URL path. Location is not in the sitemap,
so records carry ``"Not specified"`` and no coordinates -- fetching each
job page for locations was deliberately skipped as too many requests.
"""

import xml.etree.ElementTree as ET
from urllib.parse import unquote

import requests

from midnight.jobs.scraper.classify import is_recruiter_company, job_tier_classification
from midnight.jobs.scraper.http import random_user_agent
from midnight.jobs.scraper.models import FetchResult, get_job_metadata


def fetch_company_jobs_icims(slug: str) -> FetchResult:
    """Fetch the job index for an iCIMS career site via its sitemap.

    Args:
        slug: iCIMS career-site slug (``careers-{slug}.icims.com``).

    Returns:
        ``(slug, jobs, status)``. ``/jobs/intro`` sitemap entries and
        URLs without a decodable title segment are skipped. ``status``
        is None on network/parse failure.
    """
    sitemap_url = f"https://careers-{slug}.icims.com/sitemap.xml"
    headers = {
        "Accept": "application/xml",
        "User-Agent": random_user_agent(),
    }

    try:
        resp = requests.get(sitemap_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return slug, [], resp.status_code

        root = ET.fromstring(resp.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        normalized = []
        for url_el in root.findall(".//s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            if loc_el is None:
                continue
            job_url = loc_el.text.strip() if loc_el.text else ""
            if (
                not job_url
                or "/jobs/" not in job_url
                or job_url.endswith("/jobs/intro")
            ):
                continue

            path = job_url.split("/jobs/")[-1]
            parts = path.split("/")
            if len(parts) >= 2:
                title = unquote(parts[1]).replace("-", " ").strip().title()
            else:
                continue

            lastmod_el = url_el.find("s:lastmod", ns)
            updated_at = (
                lastmod_el.text.strip()
                if lastmod_el is not None and lastmod_el.text
                else None
            )

            remote, coords = False, None
            normalized.append(
                {
                    "company": slug,
                    "company_slug": slug,
                    "title": title,
                    "location": "Not specified",
                    "remote": remote,
                    "coords": coords,
                    "url": job_url,
                    "updated_at": updated_at,
                    "is_recruiter": is_recruiter_company(slug),
                    "ats": "iCIMS",
                    "skill_level": job_tier_classification(title),
                    **get_job_metadata(),
                }
            )

        return slug, normalized, resp.status_code

    except (requests.RequestException, ET.ParseError, ValueError) as e:
        print(f"Error fetching iCIMS for {slug}: {e}")
        return slug, [], None
