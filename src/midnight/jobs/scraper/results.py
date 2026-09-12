"""Rank scraped jobs against the user profile and return the best ones.

Pipeline: clean -> normalize to :class:`models.JobPost` -> drop urls
already in ``seen.json`` -> title-rank -> enrich the top
:data:`details.MAX_FINALISTS` with descriptions -> re-rank with the
description signal -> keep the top :data:`TOP_JOBS` -> record their
urls as seen -> append a run entry to the manifest log -> return the
winners as plain dicts.

Nothing is written as JSON output anymore; the only file touched is
the append-only :data:`config.MANIFEST_LOG`.
"""

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from midnight.jobs.scraper import config
from midnight.jobs.scraper.classify import clean_job_data
from midnight.jobs.scraper.fetchers.details import MAX_FINALISTS, enrich_finalists
from midnight.jobs.scraper.models import JobPost, normalize_jobs
from midnight.profile import Profile, load_profile
from midnight.utils.seen import load_seen, save_seen

# Opportunity key used for job urls in seen.json.
SEEN_KEY = "jobs"

# How many top-ranked jobs to return per run.
TOP_JOBS = 7

# Cap on the total description contribution to a job's score, so long
# posts cannot dominate title/location/level signals.
MAX_DESCRIPTION_SCORE = 6

# Title variants for profile terms that rarely appear verbatim in job
# titles ("AI/ML" vs "Machine Learning Engineer", "Mobiles" vs
# "Mobile"). Keys and values are matched case-insensitively on word
# boundaries, so short aliases like "ai" never match inside "retail".
TERM_ALIASES = {
    "ai/ml": [
        "ai",
        "ml",
        "machine learning",
        "artificial intelligence",
        "data science",
        "deep learning",
        "llm",
        "nlp",
    ],
    "software development": [
        "software",
        "developer",
        "engineer",
        "engineering",
        "sde",
        "programmer",
    ],
    "mobiles": ["mobile", "android", "ios", "flutter", "react native"],
    "mobile": ["android", "ios"],
    "open source": ["open-source", "oss"],
    "web": [
        "frontend",
        "front-end",
        "backend",
        "back-end",
        "fullstack",
        "full-stack",
    ],
    "design": ["designer", "ux", "ui", "product design", "figma"],
    "javascript": ["js", "ecmascript"],
    "typescript": ["ts"],
    "react": ["reactjs", "react.js", "next.js", "nextjs"],
    "node.js": ["nodejs", "node"],
    "nodejs": ["node"],
    "next.js": ["nextjs"],
    "python": ["django", "flask", "fastapi"],
}


def _contains_word(text: str, term: str) -> bool:
    """Check for a whole-word (or phrase) match, case-insensitive.

    Args:
        text: Already-lowercased text to search.
        term: Term to find (matched literally, not as regex).

    Returns:
        True when ``term`` appears on word boundaries.
    """
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", text) is not None


def _split_exact_and_alias(text: str, terms: list[str]) -> tuple[set[str], set[str]]:
    """Partition profile terms into exact hits and alias hits.

    A term counts as exact when it appears verbatim; otherwise each of
    its :data:`TERM_ALIASES` present in the text counts as an alias hit.

    Args:
        text: Already-lowercased text to search.
        terms: Profile terms (tech stack or interests).

    Returns:
        ``(exact_terms, alias_terms)`` as lowercase sets.
    """
    exact, alias = set(), set()
    for term in terms:
        lowered = term.lower()
        if _contains_word(text, lowered):
            exact.add(lowered)
        else:
            for alt in TERM_ALIASES.get(lowered, []):
                if _contains_word(text, alt):
                    alias.add(alt)
    return exact, alias


# skill_level bonus by years of experience band. Kept small on purpose:
# skill relevance decides relevance, level only nudges. Shape mirrors
# the previous table (entry/intern favored for juniors, mid peak for
# mids, senior peak for seniors) at a scale that no longer swamps a
# +3 stack match.
_LEVEL_BONUS = {
    "junior": {"intern": 2, "entry": 2, "mid": 1, "senior": -1},
    "mid": {"intern": -2, "entry": 1, "mid": 2, "senior": 0},
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

    Whole-word title matches on the tech stack (+3 each) and interests
    (+2 each), plus :data:`TERM_ALIASES` hits (+1 each, only for terms
    without an exact match). Description matches score +1 each (capped
    at :data:`MAX_DESCRIPTION_SCORE`). Remote fit (+2 when both sides
    want remote, +2 for a profile city/state/country mention), a
    skill-level bonus for the experience band, and -2 for recruiter
    postings. Jobs without a description score exactly as before.

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

    stack_exact, stack_alias = _split_exact_and_alias(title, user.tech_stack)
    interest_exact, interest_alias = _split_exact_and_alias(title, user.interests)
    score += (
        3 * len(stack_exact)
        + 2 * len(interest_exact)
        + len(stack_alias | interest_alias)
    )

    if job.description:
        text = job.description.lower()
        desc_exact_stack, desc_alias_stack = _split_exact_and_alias(
            text, user.tech_stack
        )
        desc_exact_interest, desc_alias_interest = _split_exact_and_alias(
            text, user.interests
        )
        desc_score = (
            len(desc_exact_stack)
            + len(desc_exact_interest)
            + len(desc_alias_stack | desc_alias_interest)
        )
        score += min(desc_score, MAX_DESCRIPTION_SCORE)

    if job.remote and user.location.remote:
        score += 2
    for place in (user.location.city, user.location.state, user.location.country):
        if place and _contains_word(location, place):
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

    def _rank_key(post: JobPost) -> tuple[float, str, str]:
        return (
            -_score_job(post, profile),
            post.company.lower(),
            post.title.lower(),
        )

    # Title-rank first (descriptions already on board count too), then
    # fetch descriptions for the finalists and re-rank with the full
    # signal before cutting to TOP_JOBS.
    prelim = sorted(fresh, key=_rank_key)[:MAX_FINALISTS]
    enrich_finalists(prelim)
    ranked = sorted(fresh, key=_rank_key)
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
