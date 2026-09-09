"""Core job-record types and per-job metadata.

Every fetcher returns plain-dict jobs with the same envelope:

    {
        "company": ..., "company_slug": ..., "title": ...,
        "location": ..., "remote": ..., "coords": ...,
        "url": ..., "ats": ..., "skill_level": ...,
        "is_recruiter": ..., "scraped_at": ..., "source": ...,
    }
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

# A normalized job record.
Job = dict[str, Any]

# What every per-company fetcher returns: (slug, jobs, HTTP status).
# ``status`` is None when no HTTP response was received (network error).
FetchResult = tuple[str, list[Job], int | None]

# A function fetching all jobs for one company slug.
Fetcher = Callable[[str], FetchResult]


def get_job_metadata() -> dict[str, str]:
    """Build the metadata stamped onto every scraped job.

    Returns:
        ``{"scraped_at": <UTC ISO-8601 "Z" timestamp>, "source": ...}``
        where ``source`` is the active :data:`config.SOURCE_TYPE`
        (``"automated"`` or ``"manual"``). Read at call time so the CLI
        ``--source`` flag applies to jobs scraped after parsing args.
    """
    # Import here so tests can monkeypatch config.SOURCE_TYPE freely.
    from midnight.jobs.scraper import config

    return {
        "scraped_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": config.SOURCE_TYPE,
    }


__all__ = ["FetchResult", "Fetcher", "Job", "get_job_metadata"]
