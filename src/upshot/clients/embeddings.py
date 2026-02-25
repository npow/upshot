"""Sentence-transformers wrapper for semantic embeddings."""

from __future__ import annotations

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from upshot.config import get_settings
from upshot.db import get_connection

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Get or load the sentence-transformers model."""
    global _model
    if _model is None:
        settings = get_settings()
        model_name = settings.dedup.embedding_model
        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of texts, returning an (N, D) float32 array."""
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return embeddings.astype(np.float32)


def embed_text(text: str) -> np.ndarray:
    """Embed a single text, returning a (D,) float32 array."""
    return embed_texts([text])[0]


def store_embedding(content_item_id: int, embedding: np.ndarray, model_name: str | None = None) -> None:
    """Store an embedding in the database."""
    conn = get_connection()
    if model_name is None:
        model_name = get_settings().dedup.embedding_model

    blob = embedding.tobytes()
    conn.execute(
        "INSERT OR REPLACE INTO embeddings (content_item_id, embedding, model) VALUES (?, ?, ?)",
        (content_item_id, blob, model_name),
    )
    conn.commit()


def load_embedding(content_item_id: int) -> np.ndarray | None:
    """Load an embedding from the database."""
    conn = get_connection()
    row = conn.execute(
        "SELECT embedding FROM embeddings WHERE content_item_id = ?",
        (content_item_id,),
    ).fetchone()

    if row is None:
        return None

    return np.frombuffer(row["embedding"], dtype=np.float32)


def load_embeddings(content_item_ids: list[int]) -> dict[int, np.ndarray]:
    """Load multiple embeddings from the database."""
    conn = get_connection()
    placeholders = ",".join("?" for _ in content_item_ids)
    rows = conn.execute(
        f"SELECT content_item_id, embedding FROM embeddings WHERE content_item_id IN ({placeholders})",
        content_item_ids,
    ).fetchall()

    return {
        row["content_item_id"]: np.frombuffer(row["embedding"], dtype=np.float32)
        for row in rows
    }


def store_centroid(cluster_id: int, centroid: np.ndarray, model_name: str | None = None) -> None:
    """Store a cluster centroid in the database."""
    conn = get_connection()
    if model_name is None:
        model_name = get_settings().dedup.embedding_model

    blob = centroid.tobytes()
    conn.execute(
        "INSERT OR REPLACE INTO cluster_centroids (cluster_id, centroid, model) VALUES (?, ?, ?)",
        (cluster_id, blob, model_name),
    )
    conn.commit()


def load_recent_centroids(days: int = 7) -> list[tuple[int, np.ndarray]]:
    """Load cluster centroids from the last N days."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT cc.cluster_id, cc.centroid
           FROM cluster_centroids cc
           JOIN clusters c ON c.id = cc.cluster_id
           WHERE c.created_at >= datetime('now', ? || ' days')""",
        (f"-{days}",),
    ).fetchall()

    return [
        (row["cluster_id"], np.frombuffer(row["centroid"], dtype=np.float32))
        for row in rows
    ]
