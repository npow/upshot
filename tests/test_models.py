"""Tests for data models."""

from upshot.models import (
    ContentItem,
    ContentType,
    FetchStatus,
    ClusterEnrichment,
    DigestData,
    EmailData,
    PipelineStage,
)
from datetime import datetime


def test_content_item_defaults():
    item = ContentItem()
    assert item.content_type == ContentType.ARTICLE
    assert item.fetch_status == FetchStatus.PENDING
    assert item.is_ad is False


def test_email_data():
    email = EmailData(
        gmail_id="abc123",
        received_at=datetime(2024, 1, 1),
        content_hash="hash123",
    )
    assert email.gmail_id == "abc123"
    assert email.subject is None


def test_cluster_enrichment():
    enrichment = ClusterEnrichment(
        summary="Test summary",
        key_insights=["insight 1", "insight 2"],
        significance="Very important",
        topics=["AI", "ML"],
        category="research",
    )
    assert len(enrichment.key_insights) == 2
    assert enrichment.category == "research"


def test_digest_data():
    digest = DigestData(date="2024-01-01")
    assert digest.top_stories == []
    assert digest.stats == {}


def test_pipeline_stages():
    assert PipelineStage.INGEST.value == "ingest"
    assert PipelineStage.DIGEST.value == "digest"
    assert PipelineStage.SYNTHESIZE.value == "synthesize"
