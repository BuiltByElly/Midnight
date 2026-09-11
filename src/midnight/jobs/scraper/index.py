"""Command-line entry point: scrape every platform and rank results.

Flow: load company lists -> fan out per platform via
:func:`runner.fetch_all_jobs` (platforms run concurrently) -> merge ->
:func:`results.save_results` (clean, rank by profile, return top jobs)
-> print the final summary.

Run directly::

    python -m midnight.jobs.scraper
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from midnight.jobs.scraper.companies import load_companies, load_paylocity
from midnight.jobs.scraper.config import (
    ASHBY_FILE,
    BAMBOOHR_FILE,
    GREENHOUSE_FILE,
    ICIMS_FILE,
    LEVER_FILE,
    PAYLOCITY_FILE,
    WORKDAY_FILE,
    ensure_dirs,
)
from midnight.jobs.scraper.fetchers import FETCHERS
from midnight.jobs.scraper.models import Job
from midnight.jobs.scraper.results import save_results
from midnight.jobs.scraper.runner import fetch_all_jobs

# Platforms in scrape order: (company-file loader, file, display name).
_PLATFORMS: list[tuple[str, str, str]] = [
    ("greenhouse", GREENHOUSE_FILE, "GREENHOUSE"),
    ("ashby", ASHBY_FILE, "ASHBY"),
    ("bamboohr", BAMBOOHR_FILE, "BAMBOOHR"),
    ("lever", LEVER_FILE, "LEVER"),
    ("workday", WORKDAY_FILE, "WORKDAY"),
    ("icims", ICIMS_FILE, "iCIMS"),
]


def load_all_companies() -> dict[str, set[str]]:
    """Load company slugs for every platform.

    Returns:
        Mapping of lowercase platform name -> slug set. Paylocity
        tenants come from :func:`companies.load_paylocity`; the rest
        from :func:`companies.load_companies`. Missing files yield
        empty sets (never an exception).
    """
    companies = {name: load_companies(path) for name, path, _ in _PLATFORMS}
    companies["paylocity"] = load_paylocity(PAYLOCITY_FILE)
    return companies


def scrape_all(companies: dict[str, set[str]]) -> tuple[dict[str, int], list[Job]]:
    """Scrape every platform concurrently.

    Args:
        companies: Mapping of lowercase platform name -> slug set, as
            returned by :func:`load_all_companies`.

    Returns:
        ``(all_active_companies, all_jobs)`` merged across platforms.
    """
    all_active_companies: dict[str, int] = {}
    all_jobs: list[Job] = []

    display = {name: label for name, _, label in _PLATFORMS}
    display["paylocity"] = "PAYLOCITY"

    with ThreadPoolExecutor(max_workers=len(companies)) as platform_executor:
        futures = {
            platform_executor.submit(
                fetch_all_jobs, slugs, FETCHERS[name], display[name]
            ): display[name]
            for name, slugs in companies.items()
        }

        for future in as_completed(futures):
            name = futures[future]
            active, jobs = future.result()
            all_active_companies.update(active)
            all_jobs.extend(jobs)
            print(
                f"\n  >>> {name} COMPLETE: {len(active):,} active, {len(jobs):,} jobs <<<\n"
            )

    return all_active_companies, all_jobs


def main() -> list[dict[str, Any]]:
    """Run the full scrape and rank results."""
    print("\n" + "=" * 80)
    print("JOB BOARD AGGREGATOR")
    print("Scraping all jobs from ATS companies")
    print("=" * 80 + "\n")

    ensure_dirs()

    companies = load_all_companies()

    if not any(companies.values()):
        print("Exiting - no companies loaded!")
        return

    _, all_jobs = scrape_all(companies)

    # Combine all company sets for total count
    # all_companies = set().union(*companies.values())

    top_jobs = save_results(all_jobs)

    return top_jobs


if __name__ == "__main__":
    main()
