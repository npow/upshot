"""Text processing utilities."""

from __future__ import annotations

import re
import unicodedata


def truncate_words(text: str, max_words: int) -> str:
    """Truncate text to a maximum number of words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def clean_text(text: str) -> str:
    """Normalize whitespace and remove control characters."""
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Remove control chars except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    # Normalize whitespace (preserve paragraph breaks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc


def is_likely_tracking_url(url: str) -> bool:
    """Check if a URL looks like a tracking/redirect URL."""
    tracking_patterns = [
        r"click\.",
        r"track\.",
        r"redirect\.",
        r"link\.",
        r"/click\?",
        r"/track\?",
        r"utm_",
        r"mailchi\.mp",
        r"list-manage\.com",
        r"email\.mg\.",
        r"sendgrid\.net",
        r"substack\.com/redirect",
    ]
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in tracking_patterns)
