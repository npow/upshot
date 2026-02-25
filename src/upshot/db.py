"""SQLite database connection factory, WAL mode, and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from upshot.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

_connection: sqlite3.Connection | None = None


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get or create a SQLite connection with WAL mode enabled."""
    global _connection
    if _connection is not None:
        return _connection

    if db_path is None:
        db_path = get_settings().database.path

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    _connection = conn
    return conn


def close_connection() -> None:
    """Close the global connection if open."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def run_migrations(conn: sqlite3.Connection | None = None) -> list[str]:
    """Run all pending SQL migrations in order.

    Returns list of migration filenames that were applied.
    """
    if conn is None:
        conn = get_connection()

    # Create migrations tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)

    applied = {row["filename"] for row in conn.execute("SELECT filename FROM _migrations")}

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied = []

    for mig_path in migration_files:
        if mig_path.name in applied:
            continue
        sql = mig_path.read_text()
        conn.executescript(sql)
        conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (mig_path.name,))
        conn.commit()
        newly_applied.append(mig_path.name)

    return newly_applied


def reset_connection() -> None:
    """Reset the global connection (for testing)."""
    global _connection
    _connection = None
