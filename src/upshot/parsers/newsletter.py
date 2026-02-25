"""Newsletter HTML parsing — story segmentation and ad detection."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from upshot.models import ContentItem, ContentType
from upshot.utils.text import clean_text

logger = logging.getLogger(__name__)

# Domains commonly used in newsletter ads
AD_DOMAINS = {
    "sponsor.", "ads.", "ad.", "partner.", "promo.",
    "click.convertkit", "trk.", "track.",
}

# Keywords that suggest ad/sponsored content
AD_KEYWORDS = [
    r"\bsponsored?\b", r"\bad\b", r"\bpartner\b", r"\bpromo(?:tion)?\b",
    r"\baffiliate\b", r"\bdeal\b", r"\bdiscount\b", r"\bcoupon\b",
    r"\bbrought to you by\b", r"\bpresented by\b", r"\bin partnership with\b",
]
AD_PATTERN = re.compile("|".join(AD_KEYWORDS), re.IGNORECASE)


@dataclass
class StorySegment:
    """A segmented story from a newsletter."""
    title: str = ""
    snippet: str = ""
    urls: list[str] = field(default_factory=list)
    is_ad: bool = False
    position: int = 0


def _extract_urls(element) -> list[str]:
    """Extract all href URLs from an element (including if element itself is an <a>)."""
    urls = []
    # Check if the element itself is an <a> tag
    if element.name == "a" and element.get("href", "").startswith(("http://", "https://")):
        urls.append(element["href"].strip())
    for a in element.find_all("a", href=True):
        href = a["href"].strip()
        if href and href.startswith(("http://", "https://")):
            urls.append(href)
    return urls


def _is_ad_section(title: str, text: str, urls: list[str]) -> bool:
    """Heuristic check if a section is an ad."""
    combined = f"{title} {text}"

    # Check ad keywords
    if AD_PATTERN.search(combined):
        return True

    # Check ad domains in URLs
    for url in urls:
        url_lower = url.lower()
        if any(d in url_lower for d in AD_DOMAINS):
            return True

    return False


def _segment_by_headings(soup: BeautifulSoup) -> list[StorySegment]:
    """Segment newsletter by heading tags."""
    segments: list[StorySegment] = []
    headings = soup.find_all(["h1", "h2", "h3", "h4"])

    for i, heading in enumerate(headings):
        title = clean_text(heading.get_text())
        if not title:
            continue

        # Collect content until next heading
        content_parts = []
        urls = _extract_urls(heading)

        for sibling in heading.find_next_siblings():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                break
            content_parts.append(clean_text(sibling.get_text()))
            urls.extend(_extract_urls(sibling))

        snippet = "\n".join(p for p in content_parts if p)
        is_ad = _is_ad_section(title, snippet, urls)

        segments.append(StorySegment(
            title=title,
            snippet=snippet[:1000],
            urls=list(dict.fromkeys(urls)),  # dedupe preserving order
            is_ad=is_ad,
            position=i,
        ))

    return segments


def _segment_by_separators(soup: BeautifulSoup) -> list[StorySegment]:
    """Segment newsletter by <hr> tags or visual separators."""
    segments: list[StorySegment] = []
    separators = soup.find_all(["hr"])

    # Also look for div/table separators with border styles
    for div in soup.find_all(["div", "td"]):
        style = div.get("style", "")
        if "border-bottom" in style or "border-top" in style:
            separators.append(div)

    if not separators:
        return segments

    # Sort separators by document order and segment between them
    all_elements = list(soup.descendants)
    sep_positions = []
    for sep in separators:
        try:
            pos = all_elements.index(sep)
            sep_positions.append(pos)
        except ValueError:
            pass

    if not sep_positions:
        return segments

    # Collect text blocks between separators
    current_text = []
    current_urls = []
    segment_idx = 0

    for element in soup.find_all(["p", "div", "li", "span", "a", "h1", "h2", "h3", "h4"]):
        if element in separators or element.find_parent(separators):
            if current_text:
                text = "\n".join(current_text)
                title_candidate = current_text[0] if current_text else ""
                is_ad = _is_ad_section(title_candidate, text, current_urls)
                segments.append(StorySegment(
                    title=title_candidate[:200],
                    snippet=text[:1000],
                    urls=list(dict.fromkeys(current_urls)),
                    is_ad=is_ad,
                    position=segment_idx,
                ))
                segment_idx += 1
                current_text = []
                current_urls = []
        else:
            t = clean_text(element.get_text())
            if t and element.name not in ["a"]:
                current_text.append(t)
            if element.name == "a" and element.get("href", "").startswith("http"):
                current_urls.append(element["href"])

    # Don't forget the last segment
    if current_text:
        text = "\n".join(current_text)
        title_candidate = current_text[0] if current_text else ""
        is_ad = _is_ad_section(title_candidate, text, current_urls)
        segments.append(StorySegment(
            title=title_candidate[:200],
            snippet=text[:1000],
            urls=list(dict.fromkeys(current_urls)),
            is_ad=is_ad,
            position=segment_idx,
        ))

    return segments


def parse_newsletter(html: str, email_id: int, source_id: int | None = None) -> list[ContentItem]:
    """Parse a newsletter email into individual content items.

    Uses heading-based segmentation first, falling back to separator-based.
    Detects and flags ad/sponsored sections.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try heading-based segmentation first
    segments = _segment_by_headings(soup)

    # Fall back to separator-based if no headings found
    if len(segments) < 2:
        sep_segments = _segment_by_separators(soup)
        if len(sep_segments) > len(segments):
            segments = sep_segments

    # If still no segments, treat the whole email as one item
    if not segments:
        text = clean_text(soup.get_text())
        urls = _extract_urls(soup)
        segments = [StorySegment(
            title="",
            snippet=text[:1000],
            urls=urls,
            is_ad=False,
            position=0,
        )]

    items: list[ContentItem] = []
    for seg in segments:
        # Use the first URL as the primary URL for this story
        primary_url = seg.urls[0] if seg.urls else None

        # Detect content type from URL
        content_type = ContentType.ARTICLE
        if primary_url:
            url_lower = primary_url.lower()
            if "arxiv.org" in url_lower:
                content_type = ContentType.PAPER
            elif any(d in url_lower for d in ["youtube.com", "youtu.be", "spotify.com", "apple.com/podcast"]):
                content_type = ContentType.PODCAST

        items.append(ContentItem(
            email_id=email_id,
            source_id=source_id,
            title=seg.title or None,
            url=primary_url,
            content_type=content_type,
            snippet=seg.snippet or None,
            is_ad=seg.is_ad,
            position_in_email=seg.position,
        ))

    logger.info(
        "Parsed newsletter (email_id=%d): %d items (%d ads)",
        email_id,
        len(items),
        sum(1 for i in items if i.is_ad),
    )
    return items
