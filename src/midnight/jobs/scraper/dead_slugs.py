"""Cache of permanently-dead company slugs per platform.

Slugs that return 404/410 are skipped on later runs via JSON files in
:data:`config.DEAD_SLUG_DIR` (``{platform}.json``). Only permanent
failures are cached -- rate limits and empty-but-live boards retry
every run.
"""

import json
import os

from midnight.jobs.scraper.config import DEAD_SLUG_DIR, ensure_dirs


def load_dead_slugs(platform: str) -> set[str]:
    """Load cached dead slugs for a platform.

    Args:
        platform: Lowercase platform name (e.g. ``"greenhouse"``).

    Returns:
        The cached dead slugs, or an empty set when no cache exists
        or it is unreadable.
    """
    filepath = os.path.join(DEAD_SLUG_DIR, f"{platform}.json")
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, encoding="utf-8") as f:
            return set(json.load(f))
    except OSError, json.JSONDecodeError:
        return set()


def save_dead_slugs(platform: str, slugs: set[str]) -> None:
    """Persist dead slugs for a platform.

    Args:
        platform: Lowercase platform name.
        slugs: Full dead-slug set to store (callers merge with cache).
    """
    ensure_dirs()
    filepath = os.path.join(DEAD_SLUG_DIR, f"{platform}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(sorted(slugs), f, ensure_ascii=False, indent=2)
    print(f"  Cached {len(slugs):,} dead slugs for {platform}")
