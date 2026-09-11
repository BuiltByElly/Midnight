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
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = os.path.join(ROOT_DIR, "data")

# Company lists (flat JSON slug lists), except Paylocity (see companies.py).
GREENHOUSE_FILE = os.path.join(DATA_DIR, "greenhouse_companies.json")
ASHBY_FILE = os.path.join(DATA_DIR, "ashby_companies.json")
BAMBOOHR_FILE = os.path.join(DATA_DIR, "bamboohr_companies.json")
WORKDAY_FILE = os.path.join(DATA_DIR, "workday_companies.json")
LEVER_FILE = os.path.join(DATA_DIR, "lever_companies.json")
ICIMS_FILE = os.path.join(DATA_DIR, "icims_companies.json")
PAYLOCITY_FILE = os.path.join(DATA_DIR, "paylocity_companies_clean.json")

LOCATIONS_FILE = os.path.join(DATA_DIR, "locations.json")

OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
DEAD_SLUG_DIR = os.path.join(DATA_DIR, "dead_slugs")

# Append-only run log: one JSON line per save_results() call
# (timestamp, totals, selected urls). Never rewritten, only appended.
MANIFEST_LOG = os.path.join(OUTPUT_DIR, "manifest.log")


# Matches ``window.pageData = {...};`` in Paylocity career pages.
PAGEDATA_RE = re.compile(r"window\.pageData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)

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


def ensure_dirs() -> None:
    """Create the output and dead-slug directories if missing.

    Safe to call repeatedly and from any thread before scraping.
    """
    os.makedirs(DEAD_SLUG_DIR, exist_ok=True)
