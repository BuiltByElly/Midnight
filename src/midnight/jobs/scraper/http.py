"""Shared HTTP plumbing for the scrapers.

Holds the Paylocity thread-local session (one ``requests.Session`` per
worker thread with a capped pool) and the User-Agent rotation used to
spread concurrent workers across fingerprints.
"""

import random
import threading

import requests
from requests.adapters import HTTPAdapter

from midnight.jobs.scraper.config import USER_AGENTS

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
