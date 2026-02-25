#!/usr/bin/env python3
"""Read today's digest from the DB and write a Hugo blog post."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

from upshot.db import get_connection, run_migrations

BLOG_POSTS_DIR = Path(__file__).resolve().parent.parent / "blog" / "content" / "posts"


def publish(target_date: str) -> None:
    conn = get_connection()
    run_migrations(conn)

    row = conn.execute(
        "SELECT markdown FROM digests WHERE date = ?", (target_date,)
    ).fetchone()

    if row is None:
        # Fall back to digest file on disk
        digest_path = Path("digests") / f"{target_date}.md"
        if not digest_path.exists():
            print(f"No digest found for {target_date}", file=sys.stderr)
            sys.exit(1)
        markdown = digest_path.read_text()
    else:
        markdown = row["markdown"]

    # Strip the "# Daily Briefing — DATE" header line
    body = re.sub(r"^#\s+Daily Briefing\s*—\s*\S+\n*", "", markdown, count=1)

    # Strip leading horizontal rules
    body = re.sub(r"^---\n+", "", body)

    # Strip trailing stats table + footer (everything from "## Stats" onward)
    body = re.sub(r"\n## Stats\n.*", "", body, flags=re.DOTALL)

    body = body.strip()

    # Format date for display
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    title = f"AI Briefing — {dt.strftime('%B %d, %Y').replace(' 0', ' ')}"

    # Build frontmatter (no description — avoids duplicating the lead paragraph
    # on the post page; Hugo/PaperMod auto-generates list summaries from content)
    frontmatter = f"""---
title: "{title}"
date: {target_date}T08:00:00Z
draft: false
tags: ["daily-briefing", "ai-news"]
---"""

    BLOG_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BLOG_POSTS_DIR / f"{target_date}.md"
    out_path.write_text(f"{frontmatter}\n\n{body}\n")
    print(f"Published: {out_path}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    publish(target)
