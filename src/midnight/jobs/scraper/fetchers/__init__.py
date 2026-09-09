"""Per-ATS job fetchers.

Each submodule exposes one ``fetch_company_jobs_*`` function with the
same contract (see :data:`models.FetchResult`):

    (slug, jobs, status) -- ``status`` is None without an HTTP response.

The :data:`FETCHERS` registry maps lowercase platform names to their
fetch function and is the single source of truth for :mod:`cli`.
"""

from midnight.jobs.scraper.fetchers.ashby import fetch_company_jobs_ashby
from midnight.jobs.scraper.fetchers.bamboohr import fetch_company_jobs_bamboohr
from midnight.jobs.scraper.fetchers.greenhouse import fetch_company_jobs_greenhouse
from midnight.jobs.scraper.fetchers.icims import fetch_company_jobs_icims
from midnight.jobs.scraper.fetchers.lever import fetch_company_jobs_lever
from midnight.jobs.scraper.fetchers.paylocity import fetch_company_jobs_paylocity
from midnight.jobs.scraper.fetchers.workday import fetch_company_jobs_workday
from midnight.jobs.scraper.models import Fetcher

FETCHERS: dict[str, Fetcher] = {
    "greenhouse": fetch_company_jobs_greenhouse,
    "ashby": fetch_company_jobs_ashby,
    "bamboohr": fetch_company_jobs_bamboohr,
    "lever": fetch_company_jobs_lever,
    "workday": fetch_company_jobs_workday,
    "icims": fetch_company_jobs_icims,
    "paylocity": fetch_company_jobs_paylocity,
}

__all__ = [
    "FETCHERS",
    "fetch_company_jobs_ashby",
    "fetch_company_jobs_bamboohr",
    "fetch_company_jobs_greenhouse",
    "fetch_company_jobs_icims",
    "fetch_company_jobs_lever",
    "fetch_company_jobs_paylocity",
    "fetch_company_jobs_workday",
]
