"""Pipeline stage: Synthesize — produce a single cohesive briefing from all clusters."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from upshot.clients.claude import synthesize_briefing
from upshot.config import get_settings
from upshot.db import get_connection
from upshot.models import PipelineRunResult, PipelineStage

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _gather_cluster_content(conn, target_date: str) -> list[dict]:
    """Collect all clusters and their content items for the date.

    Returns a flat list of dicts with keys: title, text, source, url
    (one per content item, ordered by cluster then by item quality).
    """
    clusters = conn.execute(
        "SELECT id, title FROM clusters WHERE date = ? ORDER BY coverage_breadth DESC, id",
        (target_date,),
    ).fetchall()

    items = []
    seen_urls = set()
    for cluster in clusters:
        rows = conn.execute(
            """SELECT ci.title, ci.snippet, ci.full_text, ci.url,
                      s.name as source_name
               FROM cluster_items cit
               JOIN content_items ci ON ci.id = cit.content_item_id
               LEFT JOIN sources s ON s.id = ci.source_id
               WHERE cit.cluster_id = ?
               ORDER BY cit.is_primary DESC, ci.word_count DESC NULLS LAST""",
            (cluster["id"],),
        ).fetchall()

        for row in rows:
            url = row["url"] or ""
            if url in seen_urls:
                continue
            seen_urls.add(url)

            text = row["full_text"] or row["snippet"] or ""
            items.append({
                "title": row["title"] or cluster["title"] or "Untitled",
                "text": text,
                "source": row["source_name"] or "Unknown",
                "url": url,
            })

    return items


def _compute_stats(conn, target_date: str) -> dict:
    """Compute digest statistics."""
    emails = conn.execute(
        "SELECT COUNT(*) as c FROM emails WHERE date(received_at) = ?",
        (target_date,),
    ).fetchone()["c"]

    items = conn.execute(
        "SELECT COUNT(*) as c FROM content_items WHERE date(created_at) = ?",
        (target_date,),
    ).fetchone()["c"]

    clusters = conn.execute(
        "SELECT COUNT(*) as c FROM clusters WHERE date = ?",
        (target_date,),
    ).fetchone()["c"]

    api_usage = conn.execute(
        """SELECT COALESCE(SUM(tokens_in), 0) as ti, COALESCE(SUM(tokens_out), 0) as to_
           FROM api_cache WHERE date(created_at) = ?""",
        (target_date,),
    ).fetchone()

    return {
        "emails_processed": emails,
        "content_items": items,
        "clusters_created": clusters,
        "api_tokens_in": api_usage["ti"],
        "api_tokens_out": api_usage["to_"],
    }


def run_synthesize(target_date: str) -> PipelineRunResult:
    """Generate a synthesized daily briefing from all clusters."""
    conn = get_connection()
    settings = get_settings()

    # Gather all deduplicated content
    items = _gather_cluster_content(conn, target_date)
    if not items:
        logger.info("No cluster content to synthesize")
        return PipelineRunResult(stage=PipelineStage.SYNTHESIZE, items_processed=0)

    logger.info("Synthesizing briefing from %d items", len(items))

    # Single Claude call to produce the briefing
    briefing_body = synthesize_briefing(items)

    stats = _compute_stats(conn, target_date)

    # Render final markdown via template (adds date header + stats)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("digest.md.jinja2")
    markdown = template.render(
        date=target_date,
        briefing=briefing_body,
        stats=stats,
    )

    # Store digest
    conn.execute(
        """INSERT OR REPLACE INTO digests (date, markdown, stats)
           VALUES (?, ?, ?)""",
        (target_date, markdown, json.dumps(stats)),
    )
    conn.commit()

    # Write to file
    output_dir = Path(settings.digest.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{target_date}.md"
    output_path.write_text(markdown)

    logger.info("Generated briefing: %s (%d items synthesized)", output_path, len(items))

    return PipelineRunResult(stage=PipelineStage.SYNTHESIZE, items_processed=len(items))
