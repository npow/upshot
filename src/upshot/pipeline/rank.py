"""Pipeline stage: Ranking — composite scoring and section assignment."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from upshot.clients.embeddings import load_recent_centroids
from upshot.config import get_settings
from upshot.db import get_connection
from upshot.models import DigestSection, PipelineRunResult, PipelineStage

logger = logging.getLogger(__name__)


def _compute_novelty(conn, cluster_id: int, target_date: str, lookback_days: int) -> float:
    """Compute novelty score based on how different this cluster is from recent ones.

    Higher score = more novel (less similar to recent clusters).
    """
    row = conn.execute(
        "SELECT centroid FROM cluster_centroids WHERE cluster_id = ?",
        (cluster_id,),
    ).fetchone()

    if not row:
        return 0.5  # default

    centroid = np.frombuffer(row["centroid"], dtype=np.float32)

    recent = load_recent_centroids(days=lookback_days)
    # Exclude self
    recent = [(cid, c) for cid, c in recent if cid != cluster_id]

    if not recent:
        return 1.0  # completely novel

    similarities = []
    for _, recent_centroid in recent:
        sim = cosine_similarity(
            centroid.reshape(1, -1), recent_centroid.reshape(1, -1)
        )[0, 0]
        similarities.append(sim)

    max_sim = max(similarities) if similarities else 0
    return 1.0 - max_sim  # novelty = 1 - max similarity


def _compute_interest_score(conn, cluster_id: int) -> float:
    """Compute interest score based on user interest profile."""
    # Get cluster topics
    row = conn.execute(
        "SELECT topics FROM clusters WHERE id = ?", (cluster_id,)
    ).fetchone()

    if not row or not row["topics"]:
        return 0.5

    try:
        topics = json.loads(row["topics"])
    except json.JSONDecodeError:
        return 0.5

    if not topics:
        return 0.5

    # Get user interests
    interests = conn.execute("SELECT topic, weight FROM user_interests").fetchall()
    if not interests:
        return 0.5  # no interests configured = neutral

    # Simple keyword matching (can be upgraded to embedding similarity)
    score = 0.0
    topic_text = " ".join(topics).lower()
    total_weight = 0.0

    for interest in interests:
        total_weight += interest["weight"]
        if interest["topic"].lower() in topic_text:
            score += interest["weight"]

    return min(score / max(total_weight, 1.0), 1.0)


def _compute_contrarian_score(conn, cluster_id: int) -> float:
    """Compute contrarian score based on whether the cluster has dissenting views."""
    row = conn.execute(
        "SELECT contrarian_views FROM clusters WHERE id = ?", (cluster_id,)
    ).fetchone()

    if not row or not row["contrarian_views"]:
        return 0.0

    try:
        views = json.loads(row["contrarian_views"])
    except json.JSONDecodeError:
        return 0.0

    # More contrarian views = higher score, capped at 1.0
    return min(len(views) / 3.0, 1.0)


def _compute_recency_score(conn, cluster_id: int) -> float:
    """Compute recency score — newer items score higher."""
    rows = conn.execute(
        """SELECT ci.created_at
           FROM cluster_items cit
           JOIN content_items ci ON ci.id = cit.content_item_id
           WHERE cit.cluster_id = ?
           ORDER BY ci.created_at DESC LIMIT 1""",
        (cluster_id,),
    ).fetchall()

    if not rows:
        return 0.5

    newest = datetime.fromisoformat(rows[0]["created_at"])
    age_hours = (datetime.now() - newest).total_seconds() / 3600

    # Exponential decay: half-life of 24 hours
    return math.exp(-0.693 * age_hours / 24)


def _detect_trends(conn, target_date: str) -> set[int]:
    """Detect clusters whose topics are trending (increasing frequency over 7 days)."""
    # Get topic frequencies over the last 7 days
    rows = conn.execute(
        """SELECT c.id, c.topics, c.date
           FROM clusters c
           WHERE c.date >= date(?, '-7 days') AND c.date <= ?
             AND c.topics IS NOT NULL""",
        (target_date, target_date),
    ).fetchall()

    if not rows:
        return set()

    # Count topic occurrences by date
    topic_by_date: dict[str, dict[str, int]] = {}
    cluster_topics: dict[int, list[str]] = {}

    for row in rows:
        try:
            topics = json.loads(row["topics"])
        except json.JSONDecodeError:
            continue
        cluster_topics[row["id"]] = topics
        for topic in topics:
            topic_lower = topic.lower()
            topic_by_date.setdefault(topic_lower, {})
            topic_by_date[topic_lower][row["date"]] = (
                topic_by_date[topic_lower].get(row["date"], 0) + 1
            )

    # Find trending topics (more mentions in recent days)
    trending_topics = set()
    for topic, dates in topic_by_date.items():
        if len(dates) < 2:
            continue
        sorted_dates = sorted(dates.keys())
        recent_count = sum(dates[d] for d in sorted_dates[-3:])
        older_count = sum(dates[d] for d in sorted_dates[:-3]) or 1
        if recent_count / older_count >= 1.5:
            trending_topics.add(topic)

    # Find today's clusters with trending topics
    trending_clusters = set()
    for row in rows:
        if row["date"] != target_date:
            continue
        topics = cluster_topics.get(row["id"], [])
        if any(t.lower() in trending_topics for t in topics):
            trending_clusters.add(row["id"])

    return trending_clusters


def run_rank(target_date: str) -> PipelineRunResult:
    """Rank clusters and assign them to digest sections."""
    conn = get_connection()
    settings = get_settings()

    # Get all enriched clusters for the date
    rows = conn.execute(
        "SELECT id, coverage_breadth, category FROM clusters WHERE date = ? AND enriched_at IS NOT NULL",
        (target_date,),
    ).fetchall()

    if not rows:
        logger.info("No enriched clusters to rank")
        return PipelineRunResult(stage=PipelineStage.RANK, items_processed=0)

    clusters = [dict(row) for row in rows]
    trending_ids = _detect_trends(conn, target_date)

    # Compute scores for each cluster
    for cluster in clusters:
        cid = cluster["id"]
        coverage = min(cluster["coverage_breadth"] / 5.0, 1.0)  # normalize to 0–1
        novelty = _compute_novelty(conn, cid, target_date, settings.dedup.lookback_days)
        interest = _compute_interest_score(conn, cid)
        contrarian = _compute_contrarian_score(conn, cid)
        recency = _compute_recency_score(conn, cid)

        composite = (
            settings.ranking.weight_coverage * coverage
            + settings.ranking.weight_novelty * novelty
            + settings.ranking.weight_interest * interest
            + settings.ranking.weight_contrarian * contrarian
            + settings.ranking.weight_recency * recency
        )

        cluster["novelty"] = novelty
        cluster["interest"] = interest
        cluster["contrarian"] = contrarian
        cluster["recency"] = recency
        cluster["coverage"] = coverage
        cluster["composite"] = composite
        cluster["is_trending"] = cid in trending_ids

        conn.execute(
            """UPDATE clusters SET
                 composite_score = ?, novelty_score = ?, interest_score = ?,
                 contrarian_score = ?, recency_score = ?
               WHERE id = ?""",
            (composite, novelty, interest, contrarian, recency, cid),
        )

    # Sort by composite score
    clusters.sort(key=lambda c: c["composite"], reverse=True)

    # Assign sections
    top_stories = []
    hidden_gems = []
    trend_watch = []
    paper_drops = []

    for cluster in clusters:
        cid = cluster["id"]

        # Paper drops
        if cluster["category"] == "research":
            paper_drops.append(cluster)
            continue

        # Top stories: high coverage
        if (
            cluster["coverage_breadth"] >= 2
            and len(top_stories) < settings.digest.top_stories_count
        ):
            top_stories.append(cluster)
            continue

        # Trend watch
        if cluster["is_trending"] and len(trend_watch) < settings.digest.trend_watch_count:
            trend_watch.append(cluster)
            continue

        # Hidden gems: high novelty, low coverage
        if (
            cluster["novelty"] >= 0.6
            and cluster["coverage_breadth"] <= 2
            and len(hidden_gems) < settings.digest.hidden_gems_count
        ):
            hidden_gems.append(cluster)
            continue

    # Write section assignments
    sections = [
        (top_stories, DigestSection.TOP_STORIES),
        (hidden_gems, DigestSection.HIDDEN_GEMS),
        (trend_watch, DigestSection.TREND_WATCH),
        (paper_drops, DigestSection.PAPER_DROPS),
    ]

    for section_clusters, section in sections:
        for rank, cluster in enumerate(section_clusters, 1):
            conn.execute(
                "UPDATE clusters SET section = ?, section_rank = ? WHERE id = ?",
                (section.value, rank, cluster["id"]),
            )

    conn.commit()
    total = sum(len(s) for s, _ in sections)
    logger.info(
        "Ranked %d clusters: %d top, %d gems, %d trends, %d papers",
        total,
        len(top_stories),
        len(hidden_gems),
        len(trend_watch),
        len(paper_drops),
    )

    return PipelineRunResult(stage=PipelineStage.RANK, items_processed=total)
