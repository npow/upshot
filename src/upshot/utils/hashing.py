"""Hashing utilities for content deduplication."""

from __future__ import annotations

import hashlib


def sha256_hash(content: str | bytes) -> str:
    """Compute SHA-256 hex digest of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def content_hash(subject: str, body: str) -> str:
    """Hash email content for dedup (subject + body)."""
    combined = f"{subject or ''}\n{body or ''}"
    return sha256_hash(combined)


def cache_key(model: str, prompt_version: str, input_text: str) -> str:
    """Generate a cache key for API responses."""
    combined = f"{model}:{prompt_version}:{input_text}"
    return sha256_hash(combined)
