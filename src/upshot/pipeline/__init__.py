"""Pipeline orchestrator with checkpointing and resume."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console

from upshot.db import get_connection
from upshot.models import PipelineStage

console = Console()

ALL_STAGES = [
    PipelineStage.INGEST,
    PipelineStage.EXTRACT,
    PipelineStage.TRANSCRIBE,
    PipelineStage.DEDUPLICATE,
    PipelineStage.SYNTHESIZE,
]

STAGE_RUNNERS = {
    PipelineStage.INGEST: "upshot.pipeline.ingest:run_ingest",
    PipelineStage.EXTRACT: "upshot.pipeline.extract:run_extract",
    PipelineStage.TRANSCRIBE: "upshot.pipeline.transcribe:run_transcribe",
    PipelineStage.DEDUPLICATE: "upshot.pipeline.deduplicate:run_deduplicate",
    PipelineStage.SYNTHESIZE: "upshot.pipeline.synthesize:run_synthesize",
    # Legacy stages — usable via --stages enrich,rank,digest
    PipelineStage.ENRICH: "upshot.pipeline.enrich:run_enrich",
    PipelineStage.RANK: "upshot.pipeline.rank:run_rank",
    PipelineStage.DIGEST: "upshot.pipeline.digest:run_digest",
}


def _import_runner(dotted_path: str):
    """Import a runner function from a dotted path like 'module:func'."""
    module_path, func_name = dotted_path.rsplit(":", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _get_completed_stages(conn, target_date: str) -> set[str]:
    """Get stages that completed successfully for a given date."""
    rows = conn.execute(
        "SELECT stage FROM pipeline_runs WHERE date = ? AND status = 'completed'",
        (target_date,),
    ).fetchall()
    return {row["stage"] for row in rows}


def _record_stage_start(conn, target_date: str, stage: str) -> int:
    """Record that a pipeline stage has started. Returns the run ID."""
    cursor = conn.execute(
        "INSERT INTO pipeline_runs (date, stage, status) VALUES (?, ?, 'running')",
        (target_date, stage),
    )
    conn.commit()
    return cursor.lastrowid


def _record_stage_end(conn, run_id: int, status: str, items: int, error: str | None = None):
    """Record that a pipeline stage has completed."""
    conn.execute(
        "UPDATE pipeline_runs SET status = ?, items_processed = ?, completed_at = datetime('now'), error = ? WHERE id = ?",
        (status, items, error, run_id),
    )
    conn.commit()


def run_pipeline(
    target_date: str,
    dry_run: bool = False,
    stages: list[str] | None = None,
    resume: bool = True,
) -> None:
    """Run the full pipeline or specific stages."""
    conn = get_connection()

    # Determine which stages to run
    if stages:
        stage_list = [PipelineStage(s) for s in stages]
    else:
        stage_list = ALL_STAGES

    # Filter out already-completed stages if resuming
    if resume:
        completed = _get_completed_stages(conn, target_date)
        stage_list = [s for s in stage_list if s.value not in completed]
        if not stage_list:
            console.print("[green]All stages already completed for this date.[/green]")
            return

    if dry_run:
        console.print(f"[bold]Dry run for {target_date}[/bold]")
        console.print(f"Stages to run: {', '.join(s.value for s in stage_list)}")
        for stage in stage_list:
            runner = _import_runner(STAGE_RUNNERS[stage])
            if hasattr(runner, "dry_run"):
                runner.dry_run(target_date)
            else:
                console.print(f"  [dim]{stage.value}: would process pending items[/dim]")
        return

    console.print(f"[bold]Running pipeline for {target_date}[/bold]")

    for stage in stage_list:
        console.print(f"\n[bold cyan]▶ {stage.value}[/bold cyan]")
        run_id = _record_stage_start(conn, target_date, stage.value)

        try:
            runner = _import_runner(STAGE_RUNNERS[stage])
            result = runner(target_date)
            items = result.items_processed if result else 0
            _record_stage_end(conn, run_id, "completed", items)
            console.print(f"  [green]✓ {stage.value} complete ({items} items)[/green]")
        except Exception as e:
            _record_stage_end(conn, run_id, "failed", 0, str(e))
            console.print(f"  [red]✗ {stage.value} failed: {e}[/red]")
            raise
