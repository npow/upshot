"""Pipeline stage: Content extraction — fetch full articles, papers, podcasts."""

from __future__ import annotations

import json
import logging

from upshot.db import get_connection
from upshot.models import ContentType, FetchStatus, PipelineRunResult, PipelineStage
from upshot.parsers.newsletter import parse_newsletter
from upshot.parsers.article import fetch_article, resolve_url
from upshot.parsers.pdf import fetch_paper
from upshot.parsers.podcast import is_podcast_url
from upshot.utils.hashing import sha256_hash
from upshot.utils.text import word_count

logger = logging.getLogger(__name__)


def _segment_emails(conn, target_date: str) -> int:
    """Parse unprocessed emails into content items."""
    rows = conn.execute(
        """SELECT e.id, e.raw_html, e.raw_text, e.sender_email,
                  s.id as source_id
           FROM emails e
           LEFT JOIN sources s ON s.sender_email = e.sender_email
           WHERE e.processed_at IS NOT NULL
             AND e.id NOT IN (SELECT DISTINCT email_id FROM content_items WHERE email_id IS NOT NULL)
             AND date(e.received_at) <= ?""",
        (target_date,),
    ).fetchall()

    total_items = 0
    for row in rows:
        html = row["raw_html"] or row["raw_text"] or ""
        if not html:
            continue

        items = parse_newsletter(html, email_id=row["id"], source_id=row["source_id"])
        for item in items:
            conn.execute(
                """INSERT INTO content_items
                   (email_id, source_id, title, url, content_type, snippet, is_ad, position_in_email, fetch_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.email_id,
                    item.source_id,
                    item.title,
                    item.url,
                    item.content_type.value,
                    item.snippet,
                    1 if item.is_ad else 0,
                    item.position_in_email,
                    "pending" if item.url and not item.is_ad else "skipped",
                ),
            )
            total_items += 1

    conn.commit()
    logger.info("Segmented %d emails into %d content items", len(rows), total_items)
    return total_items


def _fetch_content_item(conn, item_id: int, url: str, content_type: str) -> bool:
    """Fetch full content for a single content item. Returns True on success."""
    try:
        # Resolve URL (unwrap tracking redirects)
        resolved = resolve_url(url)

        # Re-classify based on resolved URL
        if "arxiv.org" in resolved:
            content_type = ContentType.PAPER.value
        elif is_podcast_url(resolved):
            content_type = ContentType.PODCAST.value

        if content_type == ContentType.PAPER.value:
            result = fetch_paper(resolved)
            text = result["text"]
            content_hash = sha256_hash(text) if text else None

            conn.execute(
                """UPDATE content_items
                   SET resolved_url = ?, full_text = ?, content_hash = ?,
                       word_count = ?, fetch_status = 'fetched', content_type = ?,
                       fetched_at = datetime('now')
                   WHERE id = ?""",
                (resolved, text, content_hash, word_count(text) if text else 0,
                 content_type, item_id),
            )

            # Store paper metadata
            conn.execute(
                """INSERT OR REPLACE INTO papers
                   (content_item_id, arxiv_id, pdf_url, authors, abstract, extracted_text)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    item_id,
                    result.get("arxiv_id"),
                    result.get("pdf_url"),
                    json.dumps(result.get("authors", [])),
                    result.get("abstract"),
                    text,
                ),
            )

        elif content_type == ContentType.PODCAST.value:
            # Just store the URL for now; transcription happens in a later stage
            conn.execute(
                """UPDATE content_items
                   SET resolved_url = ?, fetch_status = 'fetched', content_type = ?,
                       fetched_at = datetime('now')
                   WHERE id = ?""",
                (resolved, content_type, item_id),
            )
            conn.execute(
                """INSERT OR IGNORE INTO podcasts (content_item_id, audio_url)
                   VALUES (?, ?)""",
                (item_id, resolved),
            )

        else:
            # Standard article
            result = fetch_article(resolved)
            text = result["text"]
            content_hash = sha256_hash(text) if text else None
            status = "paywall" if result["is_paywall"] and not text else "fetched"

            title_update = result["title"] if result["title"] else None
            conn.execute(
                """UPDATE content_items
                   SET resolved_url = ?, full_text = ?, content_hash = ?,
                       word_count = ?, fetch_status = ?, content_type = ?,
                       title = COALESCE(?, title),
                       fetched_at = datetime('now')
                   WHERE id = ?""",
                (resolved, text, content_hash, word_count(text) if text else 0,
                 status, content_type, title_update, item_id),
            )

        conn.commit()
        return True

    except Exception as e:
        logger.warning("Failed to fetch item %d (%s): %s", item_id, url, e)
        conn.execute(
            "UPDATE content_items SET fetch_status = 'failed', fetch_error = ? WHERE id = ?",
            (str(e)[:500], item_id),
        )
        conn.commit()
        return False


def _segment_feed_items(conn, target_date: str) -> int:
    """Convert unprocessed feed_items into content_items."""
    rows = conn.execute(
        """SELECT fi.id, fi.feed_id, fi.url, fi.title, fi.summary, fi.published_at,
                  f.source_id
           FROM feed_items fi
           JOIN feeds f ON f.id = fi.feed_id
           WHERE fi.id NOT IN (
               SELECT feed_item_id FROM content_items WHERE feed_item_id IS NOT NULL
           )""",
        (),
    ).fetchall()

    total = 0
    for row in rows:
        conn.execute(
            """INSERT INTO content_items
               (feed_item_id, source_id, title, url, content_type, snippet, fetch_status)
               VALUES (?, ?, ?, ?, 'article', ?, 'pending')""",
            (
                row["id"],
                row["source_id"],
                row["title"],
                row["url"],
                (row["summary"] or "")[:1000],
            ),
        )
        total += 1

    conn.commit()
    logger.info("Segmented %d feed items into content items", total)
    return total


def run_extract(target_date: str) -> PipelineRunResult:
    """Extract content from all pending content items."""
    conn = get_connection()

    # First, segment any unprocessed emails and feed items
    _segment_emails(conn, target_date)
    _segment_feed_items(conn, target_date)

    # Fetch all pending items
    rows = conn.execute(
        """SELECT id, url, content_type FROM content_items
           WHERE fetch_status = 'pending' AND url IS NOT NULL
             AND date(created_at, 'localtime') <= ?""",
        (target_date,),
    ).fetchall()

    fetched = 0
    for row in rows:
        success = _fetch_content_item(conn, row["id"], row["url"], row["content_type"])
        if success:
            fetched += 1

    logger.info("Extracted content for %d/%d items", fetched, len(rows))

    return PipelineRunResult(
        stage=PipelineStage.EXTRACT,
        items_processed=fetched,
    )
