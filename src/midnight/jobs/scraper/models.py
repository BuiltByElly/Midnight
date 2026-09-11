"""Core job-record types and per-job metadata.

Every fetcher returns plain-dict jobs with the same envelope:

    {
        "company": ..., "company_slug": ..., "title": ...,
        "location": ..., "remote": ..., "coords": ...,
        "url": ..., "ats": ..., "skill_level": ...,
        "is_recruiter": ..., "scraped_at": ...,
    }
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# A normalized job record.
Job = dict[str, Any]


class JobPost(BaseModel):
    """A validated, normalized job posting.

    Fetchers return plain dicts with slightly different envelopes per
    ATS; this model coerces them into one shape (sensible defaults,
    ``url``/``company`` fallbacks, constrained ``skill_level``).
    Unknown keys are kept via ``extra="allow"`` so no fetcher data
    is lost, and :meth:`model_dump` returns the same dict shape.
    """

    model_config = ConfigDict(extra="allow")

    company: str = ""
    company_slug: str = ""
    title: str = ""
    location: str = "Not specified"
    remote: bool = False
    coords: list[float] | None = None
    url: str = ""
    absolute_url: str | None = None
    departments: list[str] = []
    id: int | str | None = None
    updated_at: str | None = None
    is_recruiter: bool = False
    ats: str = "unknown"
    skill_level: str = "mid"
    scraped_at: str | None = None

    @field_validator("skill_level", mode="before")
    @classmethod
    def _constrain_skill_level(cls, value: Any) -> str:
        """Coerce unknown tiers to ``"entry"``."""
        level = str(value or "mid").lower()
        if level in {"intern", "entry", "mid", "senior"}:
            return level
        return "entry"

    @model_validator(mode="after")
    def _apply_fallbacks(self) -> JobPost:
        """Fill ``url``/``company`` from alternates and derive a missing
        ``is_recruiter`` flag from the company slug (explicit fetcher
        values always win)."""
        if not self.url and self.absolute_url:
            self.url = self.absolute_url
        if not self.company and self.company_slug:
            self.company = self.company_slug
        if "is_recruiter" not in self.model_fields_set:
            from midnight.jobs.scraper.classify import is_recruiter_company

            self.is_recruiter = is_recruiter_company(self.company or self.company_slug)
        return self

    @property
    def canonical_url(self) -> str:
        """The URL used for seen-tracking (``""`` when untrackable)."""
        return self.url or self.absolute_url or ""


def normalize_jobs(raw_jobs: list[Any]) -> list[JobPost]:
    """Validate raw fetcher dicts into :class:`JobPost` records.

    Args:
        raw_jobs: Plain-dict jobs from the fetchers (or any mapping).

    Returns:
        The valid posts in input order. Non-mapping items and records
        that fail validation are skipped.
    """
    posts = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        try:
            posts.append(JobPost(**raw))
        except ValueError:
            continue
    return posts


# What every per-company fetcher returns: (slug, jobs, HTTP status).
# ``status`` is None when no HTTP response was received (network error).
FetchResult = tuple[str, list[Job], int | None]

# A function fetching all jobs for one company slug.
Fetcher = Callable[[str], FetchResult]


def get_job_metadata() -> dict[str, str]:
    """Build the metadata stamped onto every scraped job.

    Returns:
        ``{"scraped_at": <UTC ISO-8601 "Z" timestamp>}`` captured at
        call time.
    """
    return {
        "scraped_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


__all__ = [
    "FetchResult",
    "Fetcher",
    "Job",
    "JobPost",
    "get_job_metadata",
    "normalize_jobs",
]
