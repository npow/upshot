"""Tests for database operations."""

import sqlite3

import pytest


def test_migrations_applied(db):
    """Test that migrations create all expected tables."""
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row["name"] for row in tables}

    expected = {
        "emails", "sources", "content_items", "podcasts", "papers",
        "clusters", "cluster_items", "digests", "user_interests",
        "api_cache", "pipeline_runs", "embeddings", "cluster_centroids",
        "interest_embeddings", "_migrations",
    }
    assert expected.issubset(table_names)


def test_wal_mode(db):
    result = db.execute("PRAGMA journal_mode").fetchone()
    assert result[0] == "wal"


def test_email_unique_constraint(db):
    """Test that duplicate gmail_id is rejected."""
    db.execute(
        """INSERT INTO emails (gmail_id, received_at, content_hash)
           VALUES ('abc123', '2024-01-01', 'hash1')"""
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO emails (gmail_id, received_at, content_hash)
               VALUES ('abc123', '2024-01-01', 'hash2')"""
        )


def test_pipeline_runs(db):
    db.execute(
        "INSERT INTO pipeline_runs (date, stage, status) VALUES ('2024-01-01', 'ingest', 'running')"
    )
    db.commit()
    row = db.execute("SELECT * FROM pipeline_runs WHERE date = '2024-01-01'").fetchone()
    assert row["stage"] == "ingest"
    assert row["status"] == "running"
