"""Parallel orchestration for scraping one platform.

:func:`fetch_all_jobs` fans a platform's slugs out over a thread pool,
skips known-dead slugs, and records newly-dead (404/410) slugs back to
the cache. Platforms themselves run concurrently in :mod:`cli`.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from midnight.jobs.scraper.config import MAX_WORKERS
from midnight.jobs.scraper.dead_slugs import load_dead_slugs, save_dead_slugs
from midnight.jobs.scraper.models import Fetcher, Job


def fetch_all_jobs(
    companies: set[str], fetcher: Fetcher, platform: str = "ATS"
) -> tuple[dict[str, int], list[Job]]:
    """Fetch jobs for every live company slug on one platform.

    Args:
        companies: All known slugs for the platform.
        fetcher: Per-company fetch function (see :mod:`fetchers`).
        platform: Display/lowercase platform name (e.g. ``"GREENHOUSE"``).
            Lowercased for dead-slug cache keys and worker sizing.

    Returns:
        ``(active_companies, all_jobs)`` where ``active_companies`` maps
        slug -> job count for slugs that returned jobs.
    """
    print("=" * 80)
    print(f"FETCHING JOBS FROM {len(companies):,} COMPANIES FROM PLATFORM: {platform}")
    print("=" * 80 + "\n")

    platform_lower = platform.lower()

    # Skip known dead slugs
    dead_slugs = load_dead_slugs(platform_lower)
    live_companies = [s for s in companies if s not in dead_slugs]
    if dead_slugs:
        print(f"  Skipping {len(dead_slugs):,} known dead slugs")
        print(f"  Checking {len(live_companies):,} potentially active companies\n")

    all_jobs: list[Job] = []
    active_companies: dict[str, int] = {}
    failed = 0
    new_dead = set()

    max_workers = MAX_WORKERS.get(platform_lower, 30)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetcher, slug): slug for slug in live_companies}

        for i, future in enumerate(as_completed(futures), 1):
            # fetcher returns slug, jobs, status_code (if implemented)
            slug, jobs, status_code = future.result()

            if jobs:
                all_jobs.extend(jobs)
                active_companies[slug] = len(jobs)
                print(f"  [{i}/{len(live_companies)}] {slug}: {len(jobs)} jobs")
            else:
                failed += 1
                # Only cache permanent failures
                if status_code in (404, 410):
                    new_dead.add(slug)
                if i % 50 == 0:
                    print(
                        f"  [{i}/{len(live_companies)}] Checked... ({failed} inactive)"
                    )

    # Update dead slug cache
    if new_dead:
        all_dead = dead_slugs | new_dead
        save_dead_slugs(platform_lower, all_dead)

    print(f"\nDETAILED STATS FOR {platform}:")
    print(f"  Companies checked: {len(live_companies)}")
    print(f"  Companies with jobs: {len(active_companies)}")
    print(f"  Failed/empty: {failed}")
    print(f"  Newly dead: {len(new_dead)}")
    print(f"  Total jobs: {len(all_jobs)}")

    return active_companies, all_jobs
