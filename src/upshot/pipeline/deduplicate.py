"""Pipeline stage: Semantic deduplication via embedding clustering."""

from __future__ import annotations

import logging

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from upshot.clients.embeddings import (
    embed_texts,
    load_recent_centroids,
    store_centroid,
    store_embedding,
)
from upshot.config import get_settings
from upshot.db import get_connection
from upshot.models import PipelineRunResult, PipelineStage

logger = logging.getLogger(__name__)


def _get_items_to_embed(conn, target_date: str) -> list[dict]:
    """Get content items that need embeddings (fetched, non-ad, without embeddings)."""
    rows = conn.execute(
        """SELECT ci.id, ci.title, ci.snippet, ci.full_text
           FROM content_items ci
           LEFT JOIN embeddings e ON e.content_item_id = ci.id
           WHERE ci.fetch_status IN ('fetched', 'paywall')
             AND ci.is_ad = 0
             AND e.content_item_id IS NULL
             AND date(ci.created_at, 'localtime') <= ?""",
        (target_date,),
    ).fetchall()

    return [dict(row) for row in rows]


def _prepare_text_for_embedding(item: dict) -> str:
    """Combine title + snippet/text for embedding."""
    parts = []
    if item.get("title"):
        parts.append(item["title"])
    if item.get("snippet"):
        parts.append(item["snippet"][:500])
    elif item.get("full_text"):
        parts.append(item["full_text"][:500])
    return " ".join(parts) or "untitled"


def _cluster_items(
    item_ids: list[int],
    embeddings: np.ndarray,
    distance_threshold: float,
) -> list[list[int]]:
    """Cluster items by cosine similarity using AgglomerativeClustering.

    Returns list of clusters, each a list of item IDs.
    """
    if len(item_ids) <= 1:
        return [[item_id] for item_id in item_ids]

    # AgglomerativeClustering with cosine distance
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    )

    labels = clustering.fit_predict(embeddings)

    # Group item IDs by cluster label
    clusters: dict[int, list[int]] = {}
    for item_id, label in zip(item_ids, labels):
        clusters.setdefault(label, []).append(item_id)

    return list(clusters.values())


def _select_primary_item(conn, item_ids: list[int]) -> int:
    """Select the primary (most representative) item in a cluster.

    Prefers items with full_text, then longest content.
    """
    if len(item_ids) == 1:
        return item_ids[0]

    placeholders = ",".join("?" for _ in item_ids)
    rows = conn.execute(
        f"""SELECT id, word_count, full_text IS NOT NULL as has_text
            FROM content_items WHERE id IN ({placeholders})
            ORDER BY has_text DESC, word_count DESC NULLS LAST""",
        item_ids,
    ).fetchall()

    return rows[0]["id"] if rows else item_ids[0]


def _merge_with_recent_clusters(
    conn,
    new_clusters: list[list[int]],
    new_embeddings: dict[int, np.ndarray],
    settings,
) -> list[list[int]]:
    """Merge new clusters with recent cluster centroids for cross-day dedup."""
    recent = load_recent_centroids(days=settings.dedup.lookback_days)
    if not recent:
        return new_clusters

    final_clusters = []

    for cluster_items in new_clusters:
        # Compute centroid for new cluster
        vecs = [new_embeddings[iid] for iid in cluster_items if iid in new_embeddings]
        if not vecs:
            final_clusters.append(cluster_items)
            continue

        centroid = np.mean(vecs, axis=0)

        # Check similarity to recent centroids
        merged = False
        for existing_cluster_id, existing_centroid in recent:
            sim = cosine_similarity(
                centroid.reshape(1, -1), existing_centroid.reshape(1, -1)
            )[0, 0]

            if sim >= (1 - settings.dedup.distance_threshold):
                # Merge into existing cluster
                for item_id in cluster_items:
                    conn.execute(
                        "INSERT OR IGNORE INTO cluster_items (cluster_id, content_item_id) VALUES (?, ?)",
                        (existing_cluster_id, item_id),
                    )
                # Update coverage breadth
                conn.execute(
                    "UPDATE clusters SET coverage_breadth = coverage_breadth + ? WHERE id = ?",
                    (len(cluster_items), existing_cluster_id),
                )
                merged = True
                break

        if not merged:
            final_clusters.append(cluster_items)

    conn.commit()
    return final_clusters


def run_deduplicate(target_date: str) -> PipelineRunResult:
    """Generate embeddings and cluster content items for deduplication."""
    conn = get_connection()
    settings = get_settings()

    # Get items needing embeddings
    items = _get_items_to_embed(conn, target_date)
    if not items:
        logger.info("No items to embed/cluster")
        return PipelineRunResult(stage=PipelineStage.DEDUPLICATE, items_processed=0)

    # Generate embeddings
    texts = [_prepare_text_for_embedding(item) for item in items]
    item_ids = [item["id"] for item in items]

    logger.info("Embedding %d items...", len(texts))
    embeddings = embed_texts(texts)

    # Store embeddings
    id_to_embedding: dict[int, np.ndarray] = {}
    for item_id, emb in zip(item_ids, embeddings):
        store_embedding(item_id, emb)
        id_to_embedding[item_id] = emb

    # Cluster
    logger.info("Clustering %d items (threshold=%.2f)...", len(item_ids), settings.dedup.distance_threshold)
    clusters = _cluster_items(item_ids, embeddings, settings.dedup.distance_threshold)

    # Merge with recent clusters for cross-day dedup
    clusters = _merge_with_recent_clusters(conn, clusters, id_to_embedding, settings)

    # Store new clusters
    clusters_created = 0
    for cluster_items in clusters:
        primary_id = _select_primary_item(conn, cluster_items)

        # Get title from primary item
        row = conn.execute(
            "SELECT title FROM content_items WHERE id = ?", (primary_id,)
        ).fetchone()
        title = row["title"] if row else None

        cursor = conn.execute(
            "INSERT INTO clusters (date, title, coverage_breadth) VALUES (?, ?, ?)",
            (target_date, title, len(cluster_items)),
        )
        cluster_id = cursor.lastrowid

        # Store cluster membership
        for item_id in cluster_items:
            is_primary = 1 if item_id == primary_id else 0
            conn.execute(
                "INSERT INTO cluster_items (cluster_id, content_item_id, is_primary) VALUES (?, ?, ?)",
                (cluster_id, item_id, is_primary),
            )

        # Compute and store centroid
        vecs = [id_to_embedding[iid] for iid in cluster_items if iid in id_to_embedding]
        if vecs:
            centroid = np.mean(vecs, axis=0).astype(np.float32)
            store_centroid(cluster_id, centroid)

        clusters_created += 1

    conn.commit()
    logger.info("Created %d clusters from %d items", clusters_created, len(item_ids))

    return PipelineRunResult(
        stage=PipelineStage.DEDUPLICATE,
        items_processed=clusters_created,
    )
