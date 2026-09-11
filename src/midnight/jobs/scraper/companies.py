"""Loading of company slugs for each ATS platform.

Most platforms use a flat JSON list of slugs, e.g. ``["stripe", "figma"]``.
Paylocity is the exception: its file holds ``[{guid, name, jobs}, ...]``,
so :func:`load_paylocity` returns the GUID set and records the
guid -> display-name mapping in :data:`PAYLOCITY_NAMES`.
"""

import html
import json

# guid -> company display name, filled by load_paylocity().
PAYLOCITY_NAMES: dict[str, str] = {}


def load_companies(filepath: str) -> set[str]:
    """Load a flat JSON slug list into a set.

    Args:
        filepath: Path to a JSON file containing a list of slugs.

    Returns:
        The slugs as a set. Empty when the file does not exist, so a
        missing platform list never aborts a whole scrape run.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            companies = set(json.load(f))
        print(f"Loaded {len(companies):,} companies from {filepath}")
        return companies
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return set()


def load_paylocity(filepath: str) -> set[str]:
    """Load Paylocity tenants from the enriched ``[{guid, name, ...}]`` file.

    Args:
        filepath: Path to the Paylocity clean JSON file.

    Returns:
        The tenant GUIDs. Also fills :data:`PAYLOCITY_NAMES` so the
        Paylocity fetcher can resolve a GUID back to a display name.
        Empty when the file does not exist.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            rows = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return set()
    guids = set()
    for r in rows:
        g = r.get("guid")
        if not g:
            continue
        guids.add(g)
        name = r.get("name") or g
        PAYLOCITY_NAMES[g] = html.unescape(name)
    print(f"Loaded {len(guids):,} Paylocity companies from {filepath}")
    return guids
