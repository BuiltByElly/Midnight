"""Per-job description enrichment for ranking finalists.

Only posts still missing a description are fetched, and callers
(``results.py``) pass just the top title-ranked finalists, so detail
traffic stays in the dozens per run instead of thousands. Results are
cached by URL for the process lifetime. A failed fetch simply leaves
the description empty -- ranking falls back to title-only scoring.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from midnight.jobs.scraper.http import (
    compute_backoff,
    is_retryable_status,
    random_user_agent,
)
from midnight.jobs.scraper.models import JobPost, clean_description

# How many finalists may be enriched per run.
MAX_FINALISTS = 50

# Detail fetching is deliberately gentle.
DETAILS_WORKERS = 5

# url -> description (None marks a tried-but-absent page).
_detail_cache: dict[str, str | None] = {}


def _get(url: str, headers: dict | None = None) -> requests.Response | None:
    """GET with one backoff retry on throttling statuses.

    Args:
        url: Page or API url to fetch.
        headers: Optional headers (a rotated User-Agent is the default).

    Returns:
        The response on HTTP 200, else None.
    """
    headers = headers or {"User-Agent": random_user_agent()}
    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        return response
    if is_retryable_status(response.status_code):
        import time

        time.sleep(compute_backoff(0))
        try:
            response = requests.get(url, headers=headers, timeout=20)
        except requests.RequestException:
            return None
        if response.status_code == 200:
            return response
    return None


def _page_description(url: str, selectors: list[str]) -> str | None:
    """Extract a description from an HTML job page, best effort.

    Tries CSS selectors in order, then ``og:description``. Returns None
    when nothing plausible is found rather than boilerplate text.

    Args:
        url: Job detail page url.
        selectors: CSS selectors tried before the ``og:description`` fallback.

    Returns:
        Cleaned plaintext description, or None.
    """
    response = _get(url)
    if response is None:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    for selector in selectors:
        el = soup.select_one(selector)
        if el and len(el.get_text()) > 200:
            return clean_description(el.get_text(separator=" "))
    meta = soup.find("meta", property="og:description")
    if meta and meta.get("content"):
        return clean_description(meta["content"])
    return None


def _workday_description(post: JobPost) -> str | None:
    """Fetch a Workday posting's full description via the detail endpoint.

    Rebuilt as ``{base}/wday/cxs/{company}/{site}{externalPath}`` from
    the company triple and the ``/job/...`` suffix of the job url;
    the text lives at ``jobPostingInfo.jobDescription``.

    Args:
        post: Normalized Workday posting.

    Returns:
        Cleaned plaintext description, or None.
    """
    try:
        company, wd, site = post.company_slug.split("|")
    except ValueError:
        return None
    idx = post.canonical_url.find("/job/")
    if idx < 0:
        return None
    base = f"https://{company}.{wd}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{company}/{site}{post.canonical_url[idx:]}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": random_user_agent(),
        "Origin": base,
        "Referer": f"{base}/{site}",
    }
    response = _get(url, headers)
    if response is None:
        return None
    try:
        info = response.json().get("jobPostingInfo") or {}
    except ValueError:
        return None
    return clean_description(info.get("jobDescription"))


def _fetch_description(post: JobPost) -> str | None:
    """Dispatch to the per-ATS detail fetcher.

    Greenhouse, Lever and Ashby-posting-api records already carry
    descriptions, so only the ATS families without one are handled.

    Args:
        post: Normalized posting missing a description.

    Returns:
        Cleaned plaintext description, or None.
    """
    ats = (post.ats or "").lower()
    if ats == "workday":
        return _workday_description(post)
    if ats == "bamboohr":
        # Career pages are JS shells; og:description carries the text.
        return _page_description(post.canonical_url, [])
    if ats == "paylocity":
        return _page_description(post.canonical_url, ["div.job-preview-details"])
    if ats == "icims":
        return _page_description(
            post.canonical_url, ["div.iCIMS_JobContent", "div.iCIMS_JobContainer"]
        )
    return None


def enrich_finalists(posts: list[JobPost], limit: int = MAX_FINALISTS) -> list[JobPost]:
    """Fill missing descriptions for the leading posts, in place.

    Dedupes by url, skips cached urls, and fetches the rest over a
    small thread pool. Failures leave the description empty.

    Args:
        posts: Title-ranked finalists (mutated in place).
        limit: Max leading posts to consider.

    Returns:
        The same list, for chaining.
    """
    targets: dict[str, JobPost] = {}
    for post in posts[:limit]:
        url = post.canonical_url
        if post.description or not url or url in _detail_cache:
            continue
        targets.setdefault(url, post)

    if not targets:
        return posts

    with ThreadPoolExecutor(max_workers=DETAILS_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_description, post): url
            for url, post in targets.items()
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                _detail_cache[url] = future.result()
            except requests.RequestException, ValueError:
                # Enrichment must never fail a run; the post simply
                # keeps ranking on its title alone.
                _detail_cache[url] = None

    enriched = 0
    for url, post in targets.items():
        if _detail_cache[url]:
            post.description = _detail_cache[url]
            enriched += 1
    print(f"  Enriched {enriched}/{len(targets)} finalists with descriptions")
    return posts
