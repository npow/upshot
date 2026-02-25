"""Pipeline stage: ingestion — fetch from Gmail and RSS feeds, dedup, store."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from upshot.db import get_connection
from upshot.models import EmailData, PipelineRunResult, PipelineStage
from upshot.utils.hashing import sha256_hash

logger = logging.getLogger(__name__)


def _store_email(conn, email: EmailData) -> int | None:
    """Store an email in the database. Returns row ID or None if duplicate."""
    try:
        cursor = conn.execute(
            """INSERT INTO emails (gmail_id, thread_id, subject, sender, sender_email,
                                   received_at, content_hash, raw_html, raw_text, label)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email.gmail_id,
                email.thread_id,
                email.subject,
                email.sender,
                email.sender_email,
                email.received_at.isoformat(),
                email.content_hash,
                email.raw_html,
                email.raw_text,
                email.label,
            ),
        )
        return cursor.lastrowid
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            logger.debug("Skipping duplicate email: %s", email.gmail_id)
            return None
        raise


def _ensure_source(conn, email: EmailData) -> int:
    """Get or create a source record for the email sender."""
    row = conn.execute(
        "SELECT id FROM sources WHERE sender_email = ?",
        (email.sender_email,),
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE sources SET last_seen_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )
        return row["id"]

    cursor = conn.execute(
        "INSERT INTO sources (name, sender_email, type) VALUES (?, ?, 'newsletter')",
        (email.sender or email.sender_email, email.sender_email),
    )
    return cursor.lastrowid


def _get_last_email_date(conn) -> datetime | None:
    """Get the most recent email date we've processed."""
    row = conn.execute("SELECT MAX(received_at) as latest FROM emails").fetchone()
    if row and row["latest"]:
        return datetime.fromisoformat(row["latest"])
    return None


def _ingest_gmail(conn) -> int:
    """Fetch new emails from Gmail. Returns count of newly stored emails."""
    token_path = Path("token.json")
    if not token_path.exists():
        logger.info("No token.json found — skipping Gmail ingestion")
        return 0

    from upshot.clients.gmail import fetch_emails

    since = _get_last_email_date(conn)
    emails = fetch_emails(since=since)

    stored = 0
    for email in emails:
        email_id = _store_email(conn, email)
        if email_id is not None:
            _ensure_source(conn, email)
            conn.execute(
                "UPDATE emails SET processed_at = datetime('now') WHERE id = ?",
                (email_id,),
            )
            stored += 1

    conn.commit()
    logger.info("Ingested %d new emails (of %d fetched)", stored, len(emails))
    return stored


def _store_feed_item(conn, feed_id: int, item: dict) -> int | None:
    """Store a feed item. Returns row ID or None if duplicate."""
    content_html = item.get("content_html", "")
    content_hash = sha256_hash(content_html) if content_html else None

    try:
        cursor = conn.execute(
            """INSERT INTO feed_items
               (feed_id, guid, url, title, author, published_at, summary, content_html, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                feed_id,
                item["guid"],
                item.get("url"),
                item.get("title"),
                item.get("author"),
                item.get("published_at"),
                item.get("summary"),
                content_html,
                content_hash,
            ),
        )
        return cursor.lastrowid
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            logger.debug("Skipping duplicate feed item: %s", item.get("guid"))
            return None
        raise


def _ingest_feeds(conn, target_date: str) -> int:
    """Fetch new items from all enabled feeds. Returns count of new items."""
    from upshot.clients.feed import fetch_feed

    feeds = conn.execute(
        "SELECT id, url, name FROM feeds WHERE enabled = 1"
    ).fetchall()

    if not feeds:
        logger.debug("No feeds configured")
        return 0

    total_stored = 0
    for feed in feeds:
        try:
            items = fetch_feed(feed["url"])
            stored = 0
            for item in items:
                item_id = _store_feed_item(conn, feed["id"], item)
                if item_id is not None:
                    stored += 1

            conn.execute(
                "UPDATE feeds SET last_fetched_at = datetime('now') WHERE id = ?",
                (feed["id"],),
            )
            conn.commit()
            total_stored += stored
            logger.info("Feed '%s': %d new items (of %d)", feed["name"], stored, len(items))
        except Exception as e:
            logger.warning("Failed to fetch feed '%s' (%s): %s", feed["name"], feed["url"], e)

    return total_stored


def run_ingest(target_date: str) -> PipelineRunResult:
    """Fetch new emails from Gmail and items from RSS feeds."""
    conn = get_connection()

    gmail_count = _ingest_gmail(conn)
    feed_count = _ingest_feeds(conn, target_date)

    total = gmail_count + feed_count
    logger.info("Ingestion complete: %d emails, %d feed items", gmail_count, feed_count)

    return PipelineRunResult(
        stage=PipelineStage.INGEST,
        items_processed=total,
    )
