"""Normalization helpers applied to every scraped job.

Covers recruiter detection, title-based seniority tiers, invalid-record
filtering, and the small per-ATS parsers (Workday dates, Paylocity
locations) that don't deserve their own module.
"""

import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from midnight.jobs.scraper.config import RECRUITER_TERMS

# Scored title patterns, compiled once. Positive weights push toward
# senior, negative toward entry; interns dominate via a large penalty.
_TIER_PATTERNS = [
    (re.compile(r"\b(?:chief|cto|ceo|cfo|vp|vice president|director)\b"), 50),
    (re.compile(r"\b(?:principal|distinguished|fellow)\b"), 40),
    (re.compile(r"\b(?:staff|lead|head of)\b"), 30),
    (re.compile(r"\b(?:senior|sr\.?)\b"), 20),
    (re.compile(r"\b(?:architect|manager)\b"), 15),
    (re.compile(r"\b(?:iii|iv|v|vi)\b"), 15),
    (re.compile(r"\blevel\s*[4-9]\b"), 15),
    (re.compile(r"\bengr?\s*[4-6]\b"), 15),
    (re.compile(r"\b(?:counsel|of\s*counsel)\b"), 20),
    (re.compile(r"\b(?:attending|charge)\b"), 20),
    (re.compile(r"\b(?:ii|2)\b"), 5),
    (re.compile(r"\blevel\s*3\b"), 5),
    (re.compile(r"\b(?:associate)\b"), -10),
    (re.compile(r"\b(?:junior|jr\.?)\b"), -20),
    (re.compile(r"\bentry[\s-]?level\b"), -25),
    (re.compile(r"\b(?:i|1)\b(?!\s*-|\d)"), -15),
    (re.compile(r"\b(?:trainee|graduate|new\s*grad)\b"), -25),
    (re.compile(r"\b(?:paralegal|clerk)\b"), -15),
    (re.compile(r"\b(?:resident|clinical\s*fellow)\b"), -15),
    (re.compile(r"\b(?:aide|assistant|tech)\b"), -10),
    (re.compile(r"\bintern(?:ship)?\b"), -100),
]


def is_recruiter_company(slug: str) -> bool:
    """Check whether a company slug looks like a recruiting agency.

    Args:
        slug: Company slug or display name.

    Returns:
        True when the lowercased slug contains any of
        :data:`config.RECRUITER_TERMS`. Keyword-based only, so staffing
        firms without those keywords are missed -- acceptable for a
        frontend filter flag.
    """
    slug = slug.lower()
    return any(term in slug for term in RECRUITER_TERMS)


def job_tier_classification(title: str) -> str:
    """Classify a job title into a seniority tier.

    Scores the title against :data:`_TIER_PATTERNS` and buckets it:

    - ``"intern"`` for scores <= -50 (intern penalty dominates),
    - ``"entry"`` for scores <= -5,
    - ``"senior"`` for scores >= 15,
    - ``"mid"`` otherwise.

    Args:
        title: Raw job title.

    Returns:
        One of ``"intern"``, ``"entry"``, ``"mid"``, ``"senior"``.
    """
    title_lower = title.lower()
    score = 0
    for pattern, weight in _TIER_PATTERNS:
        if pattern.search(title_lower):
            score += weight
    if score <= -50:
        return "intern"
    elif score <= -5:
        return "entry"
    elif score >= 15:
        return "senior"
    else:
        return "mid"


def clean_job_data(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop invalid job records (blank title, missing URL/company).

    Args:
        jobs: Raw normalized job dicts from the fetchers.

    Returns:
        The valid subset, preserving order. Prints a short
        skipped-by-reason summary when anything was dropped.
    """
    cleaned = []
    skipped_reasons = {"no_title": 0, "no_url": 0, "no_company": 0}

    for job in jobs:
        title = (job.get("title") or "").strip().lower()
        url = job.get("url") or job.get("absolute_url")
        company = job.get("company") or job.get("company_slug")

        # Skip jobs with invalid titles
        if not title or title in ["not specified", "n/a", "unknown", ""]:
            skipped_reasons["no_title"] += 1
            continue

        # Skip jobs without URLs
        if not url:
            skipped_reasons["no_url"] += 1
            continue

        # Skip jobs without company info
        if not company:
            skipped_reasons["no_company"] += 1
            continue

        cleaned.append(job)

    # Print summary
    total_skipped = sum(skipped_reasons.values())
    if total_skipped > 0:
        print(f"\n  Skipped {total_skipped:,} invalid jobs:")
        for reason, count in skipped_reasons.items():
            if count > 0:
                print(f"    - {reason.replace('_', ' ').title()}: {count:,}")

    return cleaned


def parse_workday_posted_on(text: str | None) -> str | None:
    """Convert a Workday relative date to an ISO date.

    Handles strings like ``"Posted 2 Days Ago"``, ``"Posted Today"``,
    ``"... 3 Weeks Ago"`` and ``"... 2 Months Ago"`` (30 days each).

    Args:
        text: Raw ``postedOn`` text from the Workday API.

    Returns:
        An ISO ``YYYY-MM-DD`` date, or None when the text is missing
        or unparsable.
    """
    if not text or not isinstance(text, str):
        return None
    t = text.strip().lower()
    today = datetime.now(UTC).date()
    if "today" in t:
        return today.isoformat()
    m = re.search(r"(\d+)\s+day", t)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s+week", t)
    if m:
        return (today - timedelta(weeks=int(m.group(1)))).isoformat()
    m = re.search(r"(\d+)\s+month", t)
    if m:
        return (today - timedelta(days=int(m.group(1)) * 30)).isoformat()
    return None


def paylocity_location(job: dict[str, Any]) -> str:
    """Pick the best location string from a Paylocity job blob.

    ``JobLocation`` carries the real city/state; ``LocationName`` is an
    internal label (``"Main"``, ``"AVI"``) and is only a last resort.

    Args:
        job: One entry of the page's ``window.pageData.Jobs`` array.

    Returns:
        A display location such as ``"Chicago, IL"``, or
        ``"Not specified"`` when nothing usable is present.
    """
    loc = job.get("JobLocation") or {}
    city, state = loc.get("City"), loc.get("State")
    if city and state:
        return html.unescape(f"{city}, {state}")
    if city:
        return html.unescape(city)
    return html.unescape(job.get("LocationName") or "Not specified")
