"""Geolocation wiring for the scraper.

The heavy locations lookup is built lazily and cached, so importing this
module never touches disk (the old scraper parsed locations.json at import
time). The table itself is shared read-only across scraper threads.
"""

from functools import lru_cache
from typing import Any

from midnight.jobs.geolocation import build_lookup, lookup_location
from midnight.jobs.scraper.config import LOCATIONS_FILE


@lru_cache(maxsize=1)
def get_location_maps() -> dict[str, dict[str, Any]]:
    """Build (once) and return the city/admin/country lookup tables.

    Returns:
        The maps produced by ``geolocation.build_lookup`` for
        ``LOCATIONS_FILE``.
    """
    print("Loading location lookup from locations.json...")
    maps = build_lookup(LOCATIONS_FILE)
    print(f"  {len(maps['city']):,} city-only entries loaded")
    return maps


def enrich_location(location_str: str | None) -> tuple[bool, list | None]:
    """Resolve a free-text location to a ``(remote, coords)`` pair.

    Args:
        location_str: Raw location text from a job posting
            (e.g. ``"San Francisco, CA"`` or ``"Remote - US"``).

    Returns:
        A ``(remote, coords)`` tuple where ``coords`` is ``[lat, lng]``
        or ``None`` when the location is unknown. Safe to call from
        worker threads; the lookup tables are read-only after load.
    """
    result = lookup_location(location_str, get_location_maps())
    return result["remote"], result["coords"]
