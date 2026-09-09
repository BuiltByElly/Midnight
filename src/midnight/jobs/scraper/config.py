"""Shared configuration for the jobs scraper.

This module is the single place for filesystem locations, HTTP constants,
and per-platform tuning. It performs no I/O on import -- directories are
created explicitly via :func:`ensure_dirs`.

Layout (all paths derive from this file's location):
    src/midnight/data/   company lists, locations, dead-slug cache
    src/midnight/jobs/output/  scraper output (all_jobs.json, metadata.json, ...)
"""

import os
import re

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.dirname(THIS_DIR)
MIDNIGHT_DIR = os.path.dirname(JOBS_DIR)
DATA_DIR = os.path.join(MIDNIGHT_DIR, "data")

# Company lists (flat JSON slug lists), except Paylocity (see companies.py).
GREENHOUSE_FILE = os.path.join(DATA_DIR, "greenhouse_companies.json")
ASHBY_FILE = os.path.join(DATA_DIR, "ashby_companies.json")
BAMBOOHR_FILE = os.path.join(DATA_DIR, "bamboohr_companies.json")
WORKDAY_FILE = os.path.join(DATA_DIR, "workday_companies.json")
LEVER_FILE = os.path.join(DATA_DIR, "lever_companies.json")
ICIMS_FILE = os.path.join(DATA_DIR, "icims_companies.json")
PAYLOCITY_FILE = os.path.join(DATA_DIR, "paylocity_companies_clean.json")

LOCATIONS_FILE = os.path.join(DATA_DIR, "locations.json")

OUTPUT_DIR = os.path.join(JOBS_DIR, "output")
CHUNKS_DIR = os.path.join(OUTPUT_DIR, "chunks")
DEAD_SLUG_DIR = os.path.join(DATA_DIR, "dead_slugs")

# Kept for backward compatibility: historical names for the dirs above.
SCRIPT_DIR = JOBS_DIR
ROOT_DIR = MIDNIGHT_DIR

# Matches ``window.pageData = {...};`` in Paylocity career pages.
PAGEDATA_RE = re.compile(r"window\.pageData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)

# ``"automated"`` (GitHub Actions) or ``"manual"`` (local run).
# Written into every job's metadata via models.get_job_metadata.
SOURCE_TYPE = "automated"


def set_source_type(source: str) -> None:
    """Set the source label stamped onto scraped jobs.

    Args:
        source: Either ``"automated"`` or ``"manual"``.

    Raises:
        ValueError: If ``source`` is not a known label.
    """
    if source not in ("automated", "manual"):
        msg = f"Unknown source type: {source!r}"
        raise ValueError(msg)
    global SOURCE_TYPE
    SOURCE_TYPE = source


# Substrings that mark a company slug as a recruiting/staffing agency.
RECRUITER_TERMS = [
    "recruit",
    "recruiting",
    "recruiter",
    "staffing",
    "staff",
    "talent",
    "talenthub",
    "talentgroup",
    "solutions",
    "consulting",
    "placement",
    "search",
    "resources",
    "agency",
]

# Rotated to spread concurrent workers across fingerprints.
USER_AGENTS = [
    # Chrome 144 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    # Chrome 144 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    # Chrome 144 - Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    # Firefox 147 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    # Firefox 147 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
    # Firefox 147 - Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",
    # Safari 26 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",
    # Edge 144 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
]

# Thread-pool sizes per platform. Low values (ashby/paylocity) are for
# endpoints that throttle aggressively; workday paginates so it wants more.
MAX_WORKERS = {
    "bamboohr": 10,
    "greenhouse": 30,
    "ashby": 5,
    "lever": 30,
    "workday": 50,
    "icims": 30,
    "paylocity": 5,
}

# Job keys kept in the slim frontend payload.
FRONTEND_FIELDS = frozenset(
    {
        "title",
        "company",
        "location",
        "url",
        "ats",
        "skill_level",
        "is_recruiter",
        "workplaceType",
        "scraped_at",
        "remote",
        "coords",
        "salary",
        "updated_at",
        "first_seen",
    }
)

# Frontend chunk size. Chunk/manifest writing is currently disabled
# (see results.save_results); the constant is kept for when it returns.
CHUNK_SIZE = 25_000


def ensure_dirs() -> None:
    """Create the output and dead-slug directories if missing.

    Safe to call repeatedly and from any thread before scraping.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DEAD_SLUG_DIR, exist_ok=True)
