"""RSS/Atom feed client — discovery, fetching, and parsing."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import feedparser
import httpx

from upshot.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_substack_url(url: str) -> str | None:
    """Normalize Substack URLs to canonical feed URL.

    Handles:
      - substack.com/@name → name.substack.com/feed
      - name.substack.com → name.substack.com/feed
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # substack.com/@name or www.substack.com/@name
    if host in ("substack.com", "www.substack.com"):
        match = re.match(r"/@([\w-]+)", parsed.path)
        if match:
            name = match.group(1)
            return f"https://{name}.substack.com/feed"
        return None

    # name.substack.com
    if host.endswith(".substack.com") and host.count(".") == 2:
        return f"https://{host}/feed"

    return None


def _find_feed_in_html(html: str, base_url: str) -> str | None:
    """Look for <link rel="alternate" type="application/rss+xml"> in HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("link", rel="alternate"):
        link_type = link.get("type", "")
        if "rss" in link_type or "atom" in link_type:
            href = link.get("href", "")
            if href:
                if href.startswith("/"):
                    parsed = urlparse(base_url)
                    return f"{parsed.scheme}://{parsed.netloc}{href}"
                if href.startswith("http"):
                    return href
    return None


def discover_feed_url(url: str) -> str:
    """Auto-detect the RSS/Atom feed URL from a website URL.

    Tries in order:
      1. Substack URL normalization
      2. Common feed paths (/feed, /rss, /atom.xml, /feed.xml, /rss.xml, /index.xml)
      3. HTML <link rel="alternate"> tag
    """
    settings = get_settings()
    timeout = settings.feeds.fetch_timeout

    url = url.rstrip("/")

    # 1. Substack shortcut
    substack_feed = _normalize_substack_url(url)
    if substack_feed:
        return substack_feed

    # 2. Try common feed paths
    common_paths = ["/feed", "/rss", "/atom.xml", "/feed.xml", "/rss.xml", "/index.xml"]
    for path in common_paths:
        candidate = f"{url}{path}"
        try:
            resp = httpx.get(candidate, timeout=timeout, follow_redirects=True)
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and (
                "xml" in content_type or "rss" in content_type or "atom" in content_type
                or resp.text.strip().startswith("<?xml")
                or "<rss" in resp.text[:500]
                or "<feed" in resp.text[:500]
            ):
                return candidate
        except httpx.HTTPError:
            continue

    # 3. Fetch the page and look for <link rel="alternate">
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            found = _find_feed_in_html(resp.text, url)
            if found:
                return found
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch %s for feed discovery: %s", url, e)

    raise ValueError(f"Could not discover RSS/Atom feed at {url}")


def _fetch_feed_content(feed_url: str) -> bytes:
    """Fetch raw feed content via httpx for reliable encoding handling."""
    settings = get_settings()
    resp = httpx.get(feed_url, timeout=settings.feeds.fetch_timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def fetch_feed(feed_url: str) -> list[dict]:
    """Parse an RSS/Atom feed and return a list of item dicts.

    Each dict has keys: guid, url, title, author, published_at, summary, content_html

    Accepts a URL (fetched via httpx) or raw XML content string.
    """
    settings = get_settings()
    max_items = settings.feeds.max_items_per_feed

    if feed_url.startswith(("http://", "https://")):
        content = _fetch_feed_content(feed_url)
    else:
        content = feed_url

    parsed = feedparser.parse(content)

    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Failed to parse feed: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries[:max_items]:
        # Extract content HTML (prefer content:encoded, fall back to summary)
        content_html = ""
        if hasattr(entry, "content") and entry.content:
            content_html = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content_html = entry.get("summary", "")

        # Extract published date
        published_at = None
        for date_field in ("published_parsed", "updated_parsed"):
            ts = getattr(entry, date_field, None)
            if ts:
                from datetime import datetime
                try:
                    published_at = datetime(*ts[:6]).isoformat()
                except (TypeError, ValueError):
                    pass
                break

        items.append({
            "guid": getattr(entry, "id", None) or entry.get("link", ""),
            "url": entry.get("link", ""),
            "title": entry.get("title", ""),
            "author": entry.get("author", ""),
            "published_at": published_at,
            "summary": entry.get("summary", "")[:2000],
            "content_html": content_html,
        })

    logger.info("Fetched %d items from feed: %s", len(items), feed_url)
    return items


def get_feed_title(feed_url: str) -> str:
    """Get the title of a feed."""
    try:
        if feed_url.startswith(("http://", "https://")):
            content = _fetch_feed_content(feed_url)
        else:
            content = feed_url
        parsed = feedparser.parse(content)
        title = parsed.feed.get("title", "")
        if title:
            return title
    except Exception:
        pass
    return urlparse(feed_url).hostname or feed_url
