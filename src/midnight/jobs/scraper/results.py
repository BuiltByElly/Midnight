"""Rank scraped jobs against the user profile and return the best ones.

Pipeline: clean -> normalize to :class:`models.JobPost` -> drop urls
already in ``seen.json`` -> score against the profile -> keep the top
:data:`TOP_JOBS` -> record their urls as seen -> append a run entry to
the manifest log -> return the winners as plain dicts.

Nothing is written as JSON output anymore; the only file touched is
the append-only :data:`config.MANIFEST_LOG`.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from midnight.jobs.scraper import config
from midnight.jobs.scraper.classify import clean_job_data
from midnight.jobs.scraper.models import JobPost, normalize_jobs
from midnight.profile import Profile, load_profile
from midnight.utils.seen import load_seen, save_seen

# Opportunity key used for job urls in seen.json.
SEEN_KEY = "jobs"

# How many top-ranked jobs to return per run.
TOP_JOBS = 7

# skill_level bonus by years of experience band.
_LEVEL_BONUS = {
    "junior": {"intern": 4, "entry": 5, "mid": 1, "senior": -1},
    "mid": {"intern": 2, "entry": 3, "mid": 5, "senior": -1},
    "senior": {"intern": -3, "entry": -1, "mid": 1, "senior": 2},
}


def _experience_band(years: int) -> str:
    """Map years of experience to a scoring band.

    Args:
        years: Years of experience from the profile.

    Returns:
        ``"junior"`` (<=4), ``"mid"`` (5-9), or ``"senior"`` (>9).
    """
    if years <= 4:
        return "junior"
    if years <= 9:
        return "mid"
    return "senior"


def _score_job(job: JobPost, profile: Profile) -> float:
    """Score a job against the profile (higher is better).

    Title matches on the tech stack (+3 each) and interests (+2 each),
    remote fit (+2 when both sides want remote, +2 for a profile
    city/state/country mention), a skill-level bonus for the
    experience band, and -2 for recruiter postings.

    Args:
        job: Normalized posting to score.
        profile: Loaded user profile.

    Returns:
        The relevance score.
    """
    user = profile.user
    title = job.title.lower()
    location = job.location.lower()
    score = 0.0

    for term in user.tech_stack:
        if term.lower() in title:
            score += 3
    for interest in user.interests:
        if interest.lower() in title:
            score += 2

    if job.remote and user.location.remote:
        score += 2
    for place in (user.location.city, user.location.state, user.location.country):
        if place and place.lower() in location:
            score += 2
            break

    band = _experience_band(user.years_of_experience)
    score += _LEVEL_BONUS[band].get(job.skill_level, 0)

    if job.is_recruiter:
        score -= 2
    return score


def _rank_jobs_from_profile(all_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank jobs by profile fit, skipping already-seen urls.

    Loads the profile and the seen job urls, normalizes the raw dicts
    to :pydantic:`JobPost`, drops posts without a trackable url or whose
    url was already seen, scores the rest, and keeps the top
    :data:`TOP_JOBS` (ties broken by company then title for stable
    output). The winners' urls are appended to seen.json via the
    :mod:`midnight.utils.seen` helpers.

    Args:
        all_jobs: Raw normalized job dicts from all platforms.

    Returns:
        Up to ``TOP_JOBS`` winners as plain dicts in the same shape
        as the normalized input (``JobPost.model_dump()``).
    """
    profile = load_profile()
    seen = load_seen(SEEN_KEY)
    seen_urls = set(seen)

    fresh = [
        post
        for post in normalize_jobs(all_jobs)
        if post.canonical_url and post.canonical_url not in seen_urls
    ]

    ranked = sorted(
        fresh,
        key=lambda post: (
            -_score_job(post, profile),
            post.company.lower(),
            post.title.lower(),
        ),
    )
    top = ranked[:TOP_JOBS]

    new_urls = [
        post.canonical_url for post in top if post.canonical_url not in seen_urls
    ]
    if new_urls:
        save_seen(SEEN_KEY, [*seen, *new_urls])

    return [post.model_dump() for post in top]


def _append_manifest(total_jobs: int, selected: list[dict[str, Any]]) -> None:
    """Append one JSON line for this run to the manifest log.

    Args:
        total_jobs: Number of cleaned jobs ranked this run.
        selected: The ranked winners (urls are logged).
    """
    os.makedirs(os.path.dirname(config.MANIFEST_LOG), exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "total_jobs": total_jobs,
        "selected": len(selected),
        "urls": [job.get("url") for job in selected],
    }
    with open(config.MANIFEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Manifest: {config.MANIFEST_LOG}")


def save_results(all_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean, rank, and return the best jobs (no JSON output files).

    Args:
        all_jobs: Raw normalized jobs from all platforms.

    Returns:
        The top-ranked jobs as plain dicts (see
        :func:`_rank_jobs_from_profile`). The only side effects are
        the seen.json update and one appended manifest-log line.
    """
    print("=" * 80)
    print("RANKING RESULTS")
    print("=" * 80 + "\n")

    original_count = len(all_jobs)
    all_jobs = clean_job_data(all_jobs)
    cleaned_count = original_count - len(all_jobs)
    print(f"Removed {cleaned_count:,} invalid jobs (blank/not specified titles)")

    top = _rank_jobs_from_profile(all_jobs)

    for i, job in enumerate(top, 1):
        print(f"  [{i}/{len(top)}] {job.get('title')} @ {job.get('company')}")

    _append_manifest(len(all_jobs), top)

    print(f"\nSelected {len(top):,} jobs out of {len(all_jobs):,}")
    print()
    return top
