"""Article content extraction — URL resolution, trafilatura, paywall detection."""

from __future__ import annotations

import logging
import re

import httpx
import trafilatura
from readability.readability import Document as ReadabilityDocument

from upshot.utils.rate_limiter import get_rate_limiter
from upshot.utils.retry import retry
from upshot.utils.text import clean_text, is_likely_tracking_url

logger = logging.getLogger(__name__)

# Paywall indicators
PAYWALL_PATTERNS = [
    r"subscribe to (?:read|continue|unlock)",
    r"this (?:content|article) is (?:for|available to) (?:paid )?(?:subscribers|members)",
    r"paywall",
    r"sign.?up to (?:read|continue)",
    r"premium (?:content|article)",
    r"you.ve reached your (?:free )?(?:article )?limit",
]
PAYWALL_REGEX = re.compile("|".join(PAYWALL_PATTERNS), re.IGNORECASE)


@retry(max_attempts=2, base_delay=2.0, exceptions=(httpx.HTTPError, httpx.TimeoutException))
def resolve_url(url: str, timeout: int = 15) -> str:
    """Follow redirects to get the final URL.

    Unwraps tracking redirects from newsletter services.
    """
    if not is_likely_tracking_url(url):
        return url

    rate_limiter = get_rate_limiter()
    rate_limiter.acquire(url)

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.head(url)
        return str(resp.url)


def detect_paywall(html: str) -> bool:
    """Check if an HTML page likely has a paywall."""
    return bool(PAYWALL_REGEX.search(html[:5000]))


@retry(max_attempts=2, base_delay=2.0, exceptions=(httpx.HTTPError, httpx.TimeoutException))
def fetch_article(url: str, timeout: int = 30) -> dict:
    """Fetch and extract article content from a URL.

    Returns dict with keys: title, text, resolved_url, is_paywall
    """
    from upshot.config import get_settings

    settings = get_settings()
    rate_limiter = get_rate_limiter()
    rate_limiter.acquire(url)

    with httpx.Client(
        follow_redirects=True,
        timeout=settings.extraction.fetch_timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text
        resolved_url = str(resp.url)

    # Check for paywall
    is_paywall = detect_paywall(html)

    # Try trafilatura first (better at main content extraction)
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )

    title = None

    # Fall back to readability-lxml if trafilatura fails
    if not text:
        doc = ReadabilityDocument(html)
        title = doc.short_title()
        summary_html = doc.summary()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(summary_html, "lxml")
        text = clean_text(soup.get_text())

    # Extract title from trafilatura metadata if not already set
    if not title:
        metadata = trafilatura.extract(html, output_format="json")
        if metadata:
            import json
            try:
                meta_dict = json.loads(metadata)
                title = meta_dict.get("title")
            except (json.JSONDecodeError, TypeError):
                pass

    text = clean_text(text) if text else ""

    # Truncate if needed
    max_len = settings.extraction.max_content_length
    if len(text) > max_len:
        text = text[:max_len] + "..."

    return {
        "title": title,
        "text": text,
        "resolved_url": resolved_url,
        "is_paywall": is_paywall,
    }
