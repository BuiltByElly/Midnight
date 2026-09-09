"""Persistence of scrape output.

:func:`save_results` cleans the collected jobs and writes
``all_companies.json``, ``active_companies.json``, ``all_jobs.json``
and ``metadata.json`` into :data:`config.OUTPUT_DIR`.

Deliberately out of scope (matching the pre-refactor behavior):

- Salary enrichment -- the lookup files don't exist in this repo, so
  the loader from the old scraper was dropped instead of ported.
- Frontend chunks/manifest -- owned by the merge workflow (see
  ``notes.txt``: ``scrape-jobs.yml`` runs ``merge_data.py``). This
  module still clears stale ``jobs_chunk_*.json.gz`` files so old
  chunks are never mistaken for fresh output.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from midnight.jobs.scraper import config
from midnight.jobs.scraper.classify import clean_job_data
from midnight.jobs.scraper.config import CHUNKS_DIR, OUTPUT_DIR, ensure_dirs


def _write_json(filepath: str, payload: Any) -> None:
    """Write ``payload`` as indented UTF-8 JSON.

    Args:
        filepath: Destination file path.
        payload: Any JSON-serializable object.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _clear_stale_chunks() -> None:
    """Create the chunks dir and delete leftover chunk archives.

    Args: none. Reads :data:`config.CHUNKS_DIR`.
    """
    os.makedirs(CHUNKS_DIR, exist_ok=True)

    # Remove old chunk files to prevent confusion and save space
    for old_chunk in os.listdir(CHUNKS_DIR):
        if old_chunk.startswith("jobs_chunk_") and old_chunk.endswith(".json.gz"):
            os.remove(os.path.join(CHUNKS_DIR, old_chunk))


def save_results(
    all_companies: set[str],
    active_companies: dict[str, int],
    all_jobs: list[dict[str, Any]],
) -> None:
    """Clean jobs and write every output file plus a run summary.

    Args:
        all_companies: Union of every platform's slugs (for totals).
        active_companies: Mapping of slug -> job count for boards
            that returned jobs.
        all_jobs: Raw normalized jobs from all platforms.
    """
    print("=" * 80)
    print("SAVING RESULTS")
    print("=" * 80 + "\n")

    ensure_dirs()

    original_count = len(all_jobs)
    all_jobs = clean_job_data(all_jobs)
    cleaned_count = original_count - len(all_jobs)
    print(f"Removed {cleaned_count:,} invalid jobs (blank/not specified titles)")

    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    # Save all companies list
    companies_file = os.path.join(OUTPUT_DIR, "all_companies.json")
    _write_json(companies_file, sorted(all_companies))
    print(f"All companies: {companies_file}")

    # Save active companies with job counts
    active_file = os.path.join(OUTPUT_DIR, "active_companies.json")
    with open(active_file, "w", encoding="utf-8") as f:
        json.dump(active_companies, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Active companies: {active_file}")

    # Save all jobs
    all_jobs_file = os.path.join(OUTPUT_DIR, "all_jobs.json")
    _write_json(all_jobs_file, all_jobs)
    print(f"All jobs: {all_jobs_file} ({len(all_jobs):,} jobs)")

    _clear_stale_chunks()

    recruiter_jobs = sum(1 for job in all_jobs if job.get("is_recruiter"))

    # Save metadata summary
    metadata = {
        "last_updated": timestamp,
        "total_companies": len(all_companies),
        "active_companies": len(active_companies),
        "total_jobs": len(all_jobs),
        "recruiter_jobs": recruiter_jobs,
        "source_type": config.SOURCE_TYPE,
        "platforms": "greenhouse_api, ashby_api, bamboohr_api, lever_api, workday_api, icims_sitemap, paylocity_scrape",
    }

    metadata_file = os.path.join(OUTPUT_DIR, "metadata.json")
    _write_json(metadata_file, metadata)
    print(f"Metadata: {metadata_file}")

    print()
