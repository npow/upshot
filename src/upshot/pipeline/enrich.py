"""Pipeline stage: Claude enrichment — summarize and extract insights for each cluster."""

from __future__ import annotations

import json
import logging

from upshot.clients.claude import summarize_cluster
from upshot.db import get_connection
from upshot.models import PipelineRunResult, PipelineStage

logger = logging.getLogger(__name__)


def _get_unenriched_clusters(conn, target_date: str) -> list[dict]:
    """Get clusters that haven't been enriched yet."""
    rows = conn.execute(
        """SELECT id, title, coverage_breadth FROM clusters
           WHERE date = ? AND enriched_at IS NULL""",
        (target_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def _get_cluster_items(conn, cluster_id: int) -> list[dict]:
    """Get content items belonging to a cluster with their text."""
    rows = conn.execute(
        """SELECT ci.id, ci.title, ci.snippet, ci.full_text, ci.url, ci.content_type,
                  s.name as source_name
           FROM cluster_items cit
           JOIN content_items ci ON ci.id = cit.content_item_id
           LEFT JOIN sources s ON s.id = ci.source_id
           WHERE cit.cluster_id = ?
           ORDER BY cit.is_primary DESC, ci.word_count DESC NULLS LAST""",
        (cluster_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _determine_content_type(items: list[dict]) -> str:
    """Determine the dominant content type for a cluster."""
    type_counts: dict[str, int] = {}
    for item in items:
        ct = item.get("content_type", "article")
        type_counts[ct] = type_counts.get(ct, 0) + 1
    return max(type_counts, key=type_counts.get) if type_counts else "article"


def run_enrich(target_date: str) -> PipelineRunResult:
    """Enrich clusters with Claude-generated summaries and insights."""
    conn = get_connection()

    clusters = _get_unenriched_clusters(conn, target_date)
    if not clusters:
        logger.info("No clusters to enrich")
        return PipelineRunResult(stage=PipelineStage.ENRICH, items_processed=0)

    enriched = 0
    for cluster in clusters:
        cluster_id = cluster["id"]
        items = _get_cluster_items(conn, cluster_id)

        if not items:
            logger.warning("Cluster %d has no items, skipping", cluster_id)
            continue

        # Prepare items for Claude
        claude_items = []
        for item in items:
            text = item.get("full_text") or item.get("snippet") or ""
            claude_items.append({
                "title": item.get("title") or "Untitled",
                "text": text,
                "source": item.get("source_name") or "Unknown",
                "url": item.get("url") or "",
            })

        content_type = _determine_content_type(items)

        try:
            result = summarize_cluster(claude_items, content_type=content_type)

            # Update cluster with enrichment data
            conn.execute(
                """UPDATE clusters SET
                     title = COALESCE(?, title),
                     summary = ?,
                     key_insights = ?,
                     significance = ?,
                     primary_source = ?,
                     topics = ?,
                     contrarian_views = ?,
                     category = ?,
                     enriched_at = datetime('now')
                   WHERE id = ?""",
                (
                    result.get("summary", "")[:200] if not cluster["title"] else None,
                    result.get("summary"),
                    json.dumps(result.get("key_insights", [])),
                    result.get("significance"),
                    result.get("primary_source"),
                    json.dumps(result.get("topics", [])),
                    json.dumps(result.get("contrarian_views", [])),
                    result.get("category"),
                    cluster_id,
                ),
            )
            conn.commit()
            enriched += 1
            logger.info("Enriched cluster %d: %s", cluster_id, cluster.get("title", "Untitled"))

        except Exception as e:
            logger.error("Failed to enrich cluster %d: %s", cluster_id, e)
            continue

    logger.info("Enriched %d/%d clusters", enriched, len(clusters))

    return PipelineRunResult(
        stage=PipelineStage.ENRICH,
        items_processed=enriched,
    )
