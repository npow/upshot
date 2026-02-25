"""Shared test fixtures."""

import sqlite3
import pytest

from upshot.config import Settings, GmailConfig, ExtractionConfig, DedupConfig, ClaudeConfig, FeedsConfig
from upshot.db import run_migrations, reset_connection


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        gmail=GmailConfig(labels=["Test"]),
        extraction=ExtractionConfig(),
        dedup=DedupConfig(embedding_model="all-MiniLM-L6-v2"),
        claude=ClaudeConfig(model="claude-sonnet-4-20250514"),
        feeds=FeedsConfig(),
    )


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLite database with migrations applied."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    run_migrations(conn)
    yield conn
    conn.close()
    reset_connection()


@pytest.fixture
def sample_newsletter_html():
    """Sample newsletter HTML for testing."""
    return """
    <html><body>
    <h1>AI Weekly Newsletter</h1>
    <h2>OpenAI Releases GPT-5</h2>
    <p>OpenAI has announced GPT-5, their latest language model with significant improvements.</p>
    <a href="https://example.com/gpt5-article">Read more</a>

    <h2>Google DeepMind Publishes New Research</h2>
    <p>A new paper from DeepMind explores novel approaches to reasoning.</p>
    <a href="https://arxiv.org/abs/2401.12345">Paper link</a>

    <h2>Sponsored: Try Our AI Tool</h2>
    <p>Use our amazing AI tool for free! Limited time offer.</p>
    <a href="https://sponsor.example.com/deal">Get started</a>

    <h2>Podcast: The AI Future</h2>
    <p>Listen to our latest podcast episode about the future of AI.</p>
    <a href="https://open.spotify.com/episode/123">Listen now</a>
    </body></html>
    """
