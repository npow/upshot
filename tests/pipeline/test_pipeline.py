"""Tests for pipeline orchestrator."""

from upshot.pipeline import ALL_STAGES, _get_completed_stages
from upshot.models import PipelineStage


def test_all_stages_defined():
    assert len(ALL_STAGES) == 5
    assert ALL_STAGES[0] == PipelineStage.INGEST
    assert ALL_STAGES[-1] == PipelineStage.SYNTHESIZE


def test_get_completed_stages(db):
    db.execute(
        "INSERT INTO pipeline_runs (date, stage, status) VALUES ('2024-01-01', 'ingest', 'completed')"
    )
    db.execute(
        "INSERT INTO pipeline_runs (date, stage, status) VALUES ('2024-01-01', 'extract', 'failed')"
    )
    db.commit()

    completed = _get_completed_stages(db, "2024-01-01")
    assert "ingest" in completed
    assert "extract" not in completed  # failed, not completed
