"""Shared HTTP plumbing for the scrapers.

Holds the Paylocity thread-local session (one ``requests.Session`` per
worker thread with a capped pool), the User-Agent rotation used to
spread concurrent workers across fingerprints, and the shared
retry helpers (retryable statuses, exponential backoff, ``Retry-After``
support) used by every fetcher.
"""

import random
import threading
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests
from requests.adapters import HTTPAdapter

from midnight.jobs.scraper.config import USER_AGENTS

# Statuses worth retrying with backoff: rate limited (429) or
# transient upstream failures (502/503).
RETRYABLE_STATUSES = frozenset({429, 502, 503})

# Upper bound for any single retry sleep, including server hints.
MAX_RETRY_DELAY = 60.0

# One requests.Session per worker thread, with a capped connection pool.
_paylocity_local = threading.local()


def paylocity_session() -> requests.Session:
    """Return the calling thread's Paylocity session, creating it if needed.

    Returns:
        A ``requests.Session`` with a 4-connection pool mounted for HTTPS.
    """
    s = getattr(_paylocity_local, "session", None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4)
        s.mount("https://", adapter)
        _paylocity_local.session = s
    return s


def reset_paylocity_session() -> requests.Session:
    """Drop the calling thread's session and return a fresh one.

    Used when a connection is reset/aborted (Paylocity throttling) so the
    poisoned connection is not reused.

    Returns:
        A fresh thread-local ``requests.Session``.
    """
    _paylocity_local.session = None
    return paylocity_session()


def random_user_agent() -> str:
    """Pick a random browser User-Agent string.

    Returns:
        One entry of :data:`config.USER_AGENTS`.
    """
    return random.choice(USER_AGENTS)


def is_retryable_status(status_code: int | None) -> bool:
    """Check whether an HTTP status is worth retrying with backoff.

    Args:
        status_code: The response status, or None when no response
            was received.

    Returns:
        True for 429/502/503, False otherwise (including None).
    """
    return status_code in RETRYABLE_STATUSES


def compute_backoff(attempt: int, lo: float = 0.5, hi: float = 1.5) -> float:
    """Compute an exponential backoff delay with jitter.

    Args:
        attempt: Zero-based retry attempt (0 for the first retry).
        lo: Lower bound of the random jitter in seconds.
        hi: Upper bound of the random jitter in seconds.

    Returns:
        ``(2 ** attempt) + uniform(lo, hi)`` seconds.
    """
    return (2**attempt) + random.uniform(lo, hi)


def parse_retry_after(
    response: requests.Response,
    *,
    max_delay: float = MAX_RETRY_DELAY,
    now: datetime | None = None,
) -> float | None:
    """Parse a response's ``Retry-After`` header into seconds.

    Handles both forms from RFC 9110: delay-seconds (``"120"``) and an
    HTTP date. The result is clamped to ``[0, max_delay]`` so a hostile
    or stale hint can never stall a worker.

    Args:
        response: The HTTP response carrying the header.
        max_delay: Upper bound for the returned delay in seconds.
        now: Reference time for HTTP-date hints (defaults to UTC now).

    Returns:
        The suggested delay in seconds, or None when the header is
        missing, unparsable, or (for dates) already in the past.
    """
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    header = header.strip()
    if header.isdigit():
        return min(float(header), max_delay)
    try:
        retry_at = parsedate_to_datetime(header)
    except TypeError, ValueError:
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delay = (retry_at - (now or datetime.now(UTC))).total_seconds()
    if delay < 0:
        return None
    return min(delay, max_delay)


def retry_delay(
    response: requests.Response,
    attempt: int,
    lo: float = 0.5,
    hi: float = 1.5,
    max_delay: float = MAX_RETRY_DELAY,
) -> float:
    """Compute how long to wait before retrying a failed request.

    Prefers the server's ``Retry-After`` hint when present and falls
    back to exponential backoff otherwise.

    Args:
        response: The failed HTTP response.
        attempt: Zero-based retry attempt.
        lo: Backoff jitter lower bound in seconds.
        hi: Backoff jitter upper bound in seconds.
        max_delay: Upper bound for the returned delay in seconds.

    Returns:
        Seconds to sleep before the next attempt.
    """
    hint = parse_retry_after(response, max_delay=max_delay)
    if hint is not None:
        return hint
    return min(compute_backoff(attempt, lo, hi), max_delay)
