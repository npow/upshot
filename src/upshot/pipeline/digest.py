"""Pipeline stage: Digest generation — render clusters into a markdown digest."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from upshot.config import get_settings
from upshot.db import get_connection
from upshot.models import DigestSection, PipelineRunResult, PipelineStage

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _get_section_clusters(conn, target_date: str, section: str) -> list[dict]:
    """Get clusters for a digest section, ordered by section_rank."""
    rows = conn.execute(
        """SELECT c.id, c.title, c.summary, c.key_insights, c.significance,
                  c.primary_source, c.topics, c.contrarian_views, c.category,
                  c.coverage_breadth, c.composite_score, c.section_rank
           FROM clusters c
           WHERE c.date = ? AND c.section = ?
           ORDER BY c.section_rank""",
        (target_date, section),
    ).fetchall()

    clusters = []
    for row in rows:
        cluster = dict(row)

        # Parse JSON fields
        for field in ["key_insights", "topics", "contrarian_views"]:
            try:
                cluster[field] = json.loads(cluster[field]) if cluster[field] else []
            except json.JSONDecodeError:
                cluster[field] = []

        # Get source items
        items = conn.execute(
            """SELECT ci.title, ci.url, s.name as source_name
               FROM cluster_items cit
               JOIN content_items ci ON ci.id = cit.content_item_id
               LEFT JOIN sources s ON s.id = ci.source_id
               WHERE cit.cluster_id = ?
               ORDER BY cit.is_primary DESC""",
            (cluster["id"],),
        ).fetchall()
        cluster["sources"] = [dict(item) for item in items]
        clusters.append(cluster)

    return clusters


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


def run_digest(target_date: str) -> PipelineRunResult:
    """Generate the daily digest markdown."""
    conn = get_connection()
    settings = get_settings()

    # Gather data for all sections
    top_stories = _get_section_clusters(conn, target_date, DigestSection.TOP_STORIES.value)
    hidden_gems = _get_section_clusters(conn, target_date, DigestSection.HIDDEN_GEMS.value)
    trend_watch = _get_section_clusters(conn, target_date, DigestSection.TREND_WATCH.value)
    paper_drops = _get_section_clusters(conn, target_date, DigestSection.PAPER_DROPS.value)

    total = len(top_stories) + len(hidden_gems) + len(trend_watch) + len(paper_drops)
    if total == 0:
        logger.info("No ranked clusters for digest")
        return PipelineRunResult(stage=PipelineStage.DIGEST, items_processed=0)

    stats = _compute_stats(conn, target_date)

    # Render template
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("digest.md.jinja2")

    markdown = template.render(
        date=target_date,
        top_stories=top_stories,
        hidden_gems=hidden_gems,
        trend_watch=trend_watch,
        paper_drops=paper_drops,
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

    logger.info("Generated digest: %s (%d stories)", output_path, total)

    return PipelineRunResult(stage=PipelineStage.DIGEST, items_processed=total)
