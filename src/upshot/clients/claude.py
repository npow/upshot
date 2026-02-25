"""Anthropic Claude API wrapper with structured output and response caching."""

from __future__ import annotations

import json
import logging
import os

import anthropic

from upshot.config import get_settings
from upshot.db import get_connection
from upshot.utils.hashing import cache_key

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

# Bump this when you change prompts to invalidate cache
PROMPT_VERSION = "v3"


def get_client() -> anthropic.Anthropic:
    """Get or create the Anthropic client."""
    global _client
    if _client is None:
        settings = get_settings()
        kwargs: dict = {}
        if settings.claude.base_url:
            kwargs["base_url"] = settings.claude.base_url
            kwargs["api_key"] = settings.anthropic_api_key or "unused"
        elif settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        _client = anthropic.Anthropic(timeout=900.0, **kwargs)
    return _client


def _check_cache(key: str) -> str | None:
    """Check if a cached response exists."""
    conn = get_connection()
    row = conn.execute(
        "SELECT response FROM api_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    return row["response"] if row else None


def _store_cache(
    key: str, model: str, input_hash: str, response: str,
    tokens_in: int, tokens_out: int,
) -> None:
    """Store a response in the cache."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO api_cache
           (cache_key, model, prompt_version, input_hash, response, tokens_in, tokens_out)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (key, model, PROMPT_VERSION, input_hash, response, tokens_in, tokens_out),
    )
    conn.commit()


def summarize_cluster(
    items: list[dict],
    content_type: str = "article",
) -> dict:
    """Summarize a cluster of content items using Claude.

    Args:
        items: List of dicts with keys: title, text, source, url
        content_type: article, paper, or podcast

    Returns:
        Dict with: summary, key_insights, significance, primary_source,
                   topics, contrarian_views, category
    """
    settings = get_settings()

    # Build context from items
    context_parts = []
    for i, item in enumerate(items, 1):
        text = item.get("text", "")
        # Truncate each item
        words = text.split()
        if len(words) > settings.claude.max_context_words_per_item:
            text = " ".join(words[:settings.claude.max_context_words_per_item]) + "..."

        context_parts.append(
            f"--- Source {i}: {item.get('title', 'Untitled')} ---\n"
            f"From: {item.get('source', 'Unknown')}\n"
            f"URL: {item.get('url', 'N/A')}\n\n"
            f"{text}"
        )

    context = "\n\n".join(context_parts)

    # Prompt varies by content type
    type_instruction = {
        "article": "Focus on the key claims, evidence, and implications.",
        "paper": "Focus on the research contribution, methodology, key findings, and limitations. Include the paper's significance to the field.",
        "podcast": "Focus on the main discussion points, notable quotes or insights, and any disagreements between speakers.",
    }.get(content_type, "Focus on the key claims, evidence, and implications.")

    prompt = f"""Analyze the following content from {len(items)} source(s) covering the same topic/story.
{type_instruction}

{context}

Respond with a JSON object containing these fields:
- "summary": A concise 2-3 sentence summary of the story/topic
- "key_insights": Array of 3-5 key insights or takeaways (strings)
- "significance": One sentence on why this matters
- "primary_source": The most authoritative source name
- "topics": Array of 2-4 topic tags (e.g., "LLMs", "robotics", "funding")
- "contrarian_views": Array of any contrarian or dissenting views mentioned (can be empty)
- "category": One of: "research", "product", "funding", "policy", "opinion", "tutorial", "industry"

Respond ONLY with valid JSON, no markdown formatting."""

    # Check cache
    input_hash = cache_key(settings.claude.model, PROMPT_VERSION, context)
    key = cache_key(settings.claude.model, PROMPT_VERSION, prompt + context)

    cached = _check_cache(key)
    if cached:
        logger.debug("Cache hit for cluster summarization")
        return json.loads(cached)

    # Call Claude
    client = get_client()
    response = client.messages.create(
        model=settings.claude.model,
        max_tokens=settings.claude.max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text

    # Parse JSON response
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        import re
        json_match = re.search(r"\{[\s\S]+\}", response_text)
        if json_match:
            result = json.loads(json_match.group())
        else:
            logger.error("Failed to parse Claude response as JSON: %s", response_text[:200])
            result = {
                "summary": response_text[:500],
                "key_insights": [],
                "significance": "",
                "primary_source": "",
                "topics": [],
                "contrarian_views": [],
                "category": "industry",
            }

    # Store in cache
    _store_cache(
        key=key,
        model=settings.claude.model,
        input_hash=input_hash,
        response=json.dumps(result),
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
    )

    return result


def synthesize_briefing(items: list[dict]) -> str:
    """Send all deduplicated content to Claude and return a markdown briefing.

    Args:
        items: List of dicts with keys: title, text, source, url

    Returns:
        Markdown string with the synthesized briefing.
    """
    settings = get_settings()

    # Build context from all items, respecting word budget
    context_parts = []
    total_words = 0
    max_words = settings.claude.max_briefing_words

    for i, item in enumerate(items, 1):
        text = item.get("text", "")
        words = text.split()
        if total_words + len(words) > max_words:
            remaining = max_words - total_words
            if remaining > 100:
                text = " ".join(words[:remaining]) + "..."
            else:
                break
            total_words = max_words
        else:
            total_words += len(words)

        context_parts.append(
            f"--- Item {i}: {item.get('title', 'Untitled')} ---\n"
            f"Source: {item.get('source', 'Unknown')}\n"
            f"URL: {item.get('url', 'N/A')}\n\n"
            f"{text}"
        )

    context = "\n\n".join(context_parts)

    prompt = f"""You are a senior tech editor writing a daily intelligence briefing from {len(items)} items. Maximize information density — every word must earn its place.

Format:
- 1-2 sentence lead: the single most important thing today + one secondary theme
- 3-6 theme sections, each: **Bold headline phrase** followed by 1-3 bullets
- Bullets: state the fact/claim directly. No setup, no "importantly," no "this means." Just the information.
- If a bullet has a non-obvious implication, append it after an em dash
- Every bullet MUST end with a source link so readers can drill in. Format: "claim or fact ([source label](URL))" — use the URLs provided with each item
- When a single bullet synthesizes multiple sources, append each link separated by commas: "claim ([label1](url1), [label2](url2))"
- Do NOT include a separate links/references section at the end — all links are inline in bullets
- No intro/outro fluff, no section transitions, no "let's dive in"
- Do NOT include a title/date header

Anti-patterns to avoid:
- Restating what something is before saying what happened ("X, the well-known Y, has Z" → "X did Z")
- Bullet points that just summarize an article without extracting the actual claim or number
- Using two sentences where one compound sentence works
- Adjectives that don't add information (significant, notable, important, interesting)

Here are today's items:

{context}

Write the briefing now."""

    # Check cache
    input_hash = cache_key(settings.claude.model, PROMPT_VERSION, context)
    key = cache_key(settings.claude.model, PROMPT_VERSION, prompt)

    cached = _check_cache(key)
    if cached:
        logger.debug("Cache hit for briefing synthesis")
        return cached

    # Call Claude
    client = get_client()
    response = client.messages.create(
        model=settings.claude.model,
        max_tokens=settings.claude.max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    briefing = response.content[0].text

    # Store in cache (raw markdown, not JSON)
    _store_cache(
        key=key,
        model=settings.claude.model,
        input_hash=input_hash,
        response=briefing,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
    )

    return briefing
