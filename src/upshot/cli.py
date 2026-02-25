"""CLI interface using Typer + Rich."""

from __future__ import annotations

from datetime import date, datetime

import typer
from rich.console import Console
from rich.table import Table

from upshot.config import load_settings
from upshot.db import get_connection, run_migrations

app = typer.Typer(
    name="upshot",
    help="Blinkist for newsletters — synthesizes your feeds into a single daily intelligence briefing.",
    no_args_is_help=True,
)
console = Console()


def _ensure_db() -> None:
    """Load settings, connect to DB, and run migrations."""
    load_settings()
    conn = get_connection()
    applied = run_migrations(conn)
    if applied:
        console.print(f"[dim]Applied {len(applied)} migration(s): {', '.join(applied)}[/dim]")


@app.command()
def run(
    date_str: str = typer.Option(
        None, "--date", "-d", help="Date to process (YYYY-MM-DD). Defaults to today."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed."),
    stages: str = typer.Option(
        None,
        "--stages",
        "-s",
        help="Comma-separated stages to run (ingest,extract,transcribe,deduplicate,synthesize).",
    ),
    resume: bool = typer.Option(
        True, "--resume/--no-resume", help="Resume from last completed stage."
    ),
) -> None:
    """Run the full pipeline or specific stages."""
    _ensure_db()
    from upshot.pipeline import run_pipeline

    target_date = date_str or date.today().isoformat()
    stage_list = [s.strip() for s in stages.split(",")] if stages else None

    run_pipeline(
        target_date=target_date,
        dry_run=dry_run,
        stages=stage_list,
        resume=resume,
    )


@app.command()
def auth(
    setup: bool = typer.Option(False, "--setup", help="Run interactive OAuth setup."),
) -> None:
    """Manage Gmail authentication."""
    _ensure_db()
    from upshot.clients.gmail import authenticate

    if setup:
        console.print("[bold]Starting Gmail OAuth setup...[/bold]")
        authenticate(interactive=True)
        console.print("[green]Authentication successful![/green]")
    else:
        console.print("Use --setup to run interactive OAuth flow.")


@app.command()
def digest(
    date_str: str = typer.Option(
        None, "--date", "-d", help="Date of digest (YYYY-MM-DD). Defaults to today."
    ),
    open_file: bool = typer.Option(False, "--open", help="Open the digest file after generation."),
) -> None:
    """View or regenerate the daily digest."""
    _ensure_db()

    target_date = date_str or date.today().isoformat()
    conn = get_connection()
    row = conn.execute("SELECT markdown FROM digests WHERE date = ?", (target_date,)).fetchone()

    if row:
        console.print(row["markdown"])
        if open_file:
            import subprocess

            settings = load_settings()
            path = f"{settings.digest.output_dir}/{target_date}.md"
            subprocess.run(["open", path], check=False)
    else:
        console.print(f"[yellow]No digest found for {target_date}. Run the pipeline first.[/yellow]")


@app.command()
def sources() -> None:
    """List known newsletter sources."""
    _ensure_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, sender_email, type, trust_score, last_seen_at FROM sources ORDER BY last_seen_at DESC"
    ).fetchall()

    if not rows:
        console.print("[dim]No sources found yet. Run the pipeline to discover sources.[/dim]")
        return

    table = Table(title="Newsletter Sources")
    table.add_column("Name", style="bold")
    table.add_column("Email")
    table.add_column("Type")
    table.add_column("Trust", justify="right")
    table.add_column("Last Seen")

    for row in rows:
        table.add_row(
            row["name"],
            row["sender_email"] or "",
            row["type"],
            f"{row['trust_score']:.2f}",
            row["last_seen_at"] or "",
        )
    console.print(table)


@app.command()
def interests(
    add: str = typer.Option(None, "--add", "-a", help="Add a topic of interest."),
    remove: str = typer.Option(None, "--remove", "-r", help="Remove a topic of interest."),
    weight: float = typer.Option(1.0, "--weight", "-w", help="Weight for the topic (0.0–2.0)."),
) -> None:
    """Manage interest profile for personalized ranking."""
    _ensure_db()
    conn = get_connection()

    if add:
        conn.execute(
            "INSERT INTO user_interests (topic, weight) VALUES (?, ?)",
            (add, weight),
        )
        conn.commit()
        console.print(f"[green]Added interest: {add} (weight={weight})[/green]")
    elif remove:
        deleted = conn.execute(
            "DELETE FROM user_interests WHERE topic = ?", (remove,)
        ).rowcount
        conn.commit()
        if deleted:
            console.print(f"[yellow]Removed interest: {remove}[/yellow]")
        else:
            console.print(f"[red]Interest not found: {remove}[/red]")
    else:
        rows = conn.execute(
            "SELECT topic, weight, created_at FROM user_interests ORDER BY weight DESC"
        ).fetchall()
        if not rows:
            console.print("[dim]No interests configured. Use --add to add topics.[/dim]")
            return
        table = Table(title="Interest Profile")
        table.add_column("Topic", style="bold")
        table.add_column("Weight", justify="right")
        table.add_column("Added")
        for row in rows:
            table.add_row(row["topic"], f"{row['weight']:.1f}", row["created_at"])
        console.print(table)


@app.command()
def stats(
    date_str: str = typer.Option(
        None, "--date", "-d", help="Date to show stats for. Defaults to today."
    ),
) -> None:
    """Show pipeline statistics."""
    _ensure_db()
    conn = get_connection()
    target_date = date_str or date.today().isoformat()

    # Overall counts
    total_emails = conn.execute("SELECT COUNT(*) as c FROM emails").fetchone()["c"]
    total_items = conn.execute("SELECT COUNT(*) as c FROM content_items").fetchone()["c"]
    total_clusters = conn.execute("SELECT COUNT(*) as c FROM clusters").fetchone()["c"]

    # Today's counts
    day_emails = conn.execute(
        "SELECT COUNT(*) as c FROM emails WHERE date(received_at) = ?", (target_date,)
    ).fetchone()["c"]
    day_items = conn.execute(
        "SELECT COUNT(*) as c FROM content_items WHERE date(created_at) = ?", (target_date,)
    ).fetchone()["c"]
    day_clusters = conn.execute(
        "SELECT COUNT(*) as c FROM clusters WHERE date = ?", (target_date,)
    ).fetchone()["c"]

    # API cost estimate
    cache_row = conn.execute(
        "SELECT COALESCE(SUM(tokens_in), 0) as ti, COALESCE(SUM(tokens_out), 0) as to_ FROM api_cache"
    ).fetchone()

    table = Table(title=f"Pipeline Stats ({target_date})")
    table.add_column("Metric", style="bold")
    table.add_column("Today", justify="right")
    table.add_column("All Time", justify="right")

    table.add_row("Emails", str(day_emails), str(total_emails))
    table.add_row("Content Items", str(day_items), str(total_items))
    table.add_row("Clusters", str(day_clusters), str(total_clusters))
    table.add_row("API Tokens In", "", f"{cache_row['ti']:,}")
    table.add_row("API Tokens Out", "", f"{cache_row['to_']:,}")

    console.print(table)

    # Pipeline runs for the date
    runs = conn.execute(
        "SELECT stage, status, items_processed, started_at, completed_at FROM pipeline_runs WHERE date = ? ORDER BY started_at",
        (target_date,),
    ).fetchall()
    if runs:
        run_table = Table(title="Pipeline Runs")
        run_table.add_column("Stage")
        run_table.add_column("Status")
        run_table.add_column("Items", justify="right")
        run_table.add_column("Started")
        run_table.add_column("Completed")
        for r in runs:
            status_style = {"completed": "green", "failed": "red", "running": "yellow"}.get(
                r["status"], ""
            )
            run_table.add_row(
                r["stage"],
                f"[{status_style}]{r['status']}[/{status_style}]",
                str(r["items_processed"]),
                r["started_at"] or "",
                r["completed_at"] or "",
            )
        console.print(run_table)


@app.command()
def add(
    url: str = typer.Argument(help="URL of a blog or newsletter (e.g. Substack URL)."),
) -> None:
    """Add an RSS/URL feed by discovering its feed URL."""
    _ensure_db()
    from upshot.clients.feed import discover_feed_url, get_feed_title

    conn = get_connection()

    try:
        feed_url = discover_feed_url(url)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Check if already exists
    existing = conn.execute("SELECT id, name FROM feeds WHERE url = ?", (feed_url,)).fetchone()
    if existing:
        console.print(f"[yellow]Feed already exists: {existing['name']} ({feed_url})[/yellow]")
        return

    name = get_feed_title(feed_url)

    # Create a source entry for this feed
    source_row = conn.execute(
        "SELECT id FROM sources WHERE name = ?", (name,)
    ).fetchone()
    if source_row:
        source_id = source_row["id"]
        conn.execute(
            "UPDATE sources SET last_seen_at = datetime('now') WHERE id = ?",
            (source_id,),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO sources (name, type) VALUES (?, 'feed')",
            (name,),
        )
        source_id = cursor.lastrowid

    conn.execute(
        "INSERT INTO feeds (url, name, source_id) VALUES (?, ?, ?)",
        (feed_url, name, source_id),
    )
    conn.commit()

    console.print(f"[green]Added feed:[/green] {name}")
    console.print(f"  [dim]URL: {feed_url}[/dim]")


feeds_app = typer.Typer(name="feeds", help="Manage RSS/URL feeds.", no_args_is_help=False)
app.add_typer(feeds_app, name="feeds")


@feeds_app.callback(invoke_without_command=True)
def feeds_list(ctx: typer.Context) -> None:
    """List all RSS/URL feeds."""
    if ctx.invoked_subcommand is not None:
        return
    _ensure_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, url, enabled, last_fetched_at, created_at FROM feeds ORDER BY created_at DESC"
    ).fetchall()

    if not rows:
        console.print("[dim]No feeds configured. Use 'upshot add <url>' to add one.[/dim]")
        return

    table = Table(title="RSS/URL Feeds")
    table.add_column("Name", style="bold")
    table.add_column("URL")
    table.add_column("Enabled")
    table.add_column("Last Fetched")
    table.add_column("Added")

    for row in rows:
        table.add_row(
            row["name"],
            row["url"],
            "[green]yes[/green]" if row["enabled"] else "[red]no[/red]",
            row["last_fetched_at"] or "[dim]never[/dim]",
            row["created_at"] or "",
        )
    console.print(table)


@feeds_app.command("remove")
def feeds_remove(
    name_or_url: str = typer.Argument(help="Feed name or URL to remove."),
) -> None:
    """Remove an RSS/URL feed."""
    _ensure_db()
    conn = get_connection()

    row = conn.execute(
        "SELECT id, name, url FROM feeds WHERE name = ? OR url = ?",
        (name_or_url, name_or_url),
    ).fetchone()

    if not row:
        console.print(f"[red]Feed not found: {name_or_url}[/red]")
        raise typer.Exit(1)

    conn.execute("DELETE FROM feed_items WHERE feed_id = ?", (row["id"],))
    conn.execute("DELETE FROM feeds WHERE id = ?", (row["id"],))
    conn.commit()
    console.print(f"[yellow]Removed feed: {row['name']} ({row['url']})[/yellow]")


@app.command()
def config() -> None:
    """Show current configuration."""
    from upshot.config import get_settings

    settings = get_settings()
    console.print_json(settings.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
