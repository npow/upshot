"""Pydantic data models for pipeline interchange."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import numpy as np
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    ARTICLE = "article"
    PAPER = "paper"
    PODCAST = "podcast"
    VIDEO = "video"
    THREAD = "thread"


class FetchStatus(str, Enum):
    PENDING = "pending"
    FETCHED = "fetched"
    FAILED = "failed"
    PAYWALL = "paywall"
    SKIPPED = "skipped"


class PipelineStage(str, Enum):
    INGEST = "ingest"
    EXTRACT = "extract"
    TRANSCRIBE = "transcribe"
    DEDUPLICATE = "deduplicate"
    ENRICH = "enrich"
    RANK = "rank"
    DIGEST = "digest"
    SYNTHESIZE = "synthesize"


class DigestSection(str, Enum):
    TOP_STORIES = "top_stories"
    HIDDEN_GEMS = "hidden_gems"
    TREND_WATCH = "trend_watch"
    PAPER_DROPS = "paper_drops"


# --- Pipeline data models ---


class EmailData(BaseModel):
    gmail_id: str
    thread_id: str | None = None
    subject: str | None = None
    sender: str | None = None
    sender_email: str | None = None
    received_at: datetime
    content_hash: str
    raw_html: str | None = None
    raw_text: str | None = None
    label: str | None = None


class ContentItem(BaseModel):
    id: int | None = None
    email_id: int | None = None
    source_id: int | None = None
    title: str | None = None
    url: str | None = None
    resolved_url: str | None = None
    content_type: ContentType = ContentType.ARTICLE
    snippet: str | None = None
    full_text: str | None = None
    content_hash: str | None = None
    word_count: int | None = None
    fetch_status: FetchStatus = FetchStatus.PENDING
    is_ad: bool = False
    position_in_email: int | None = None


class PodcastData(BaseModel):
    content_item_id: int
    audio_url: str | None = None
    audio_path: str | None = None
    duration_seconds: float | None = None
    transcript: str | None = None


class PaperData(BaseModel):
    content_item_id: int
    arxiv_id: str | None = None
    pdf_url: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    extracted_text: str | None = None


class ClusterEnrichment(BaseModel):
    """Structured output from Claude enrichment."""

    summary: str
    key_insights: list[str] = Field(default_factory=list)
    significance: str = ""
    primary_source: str = ""
    topics: list[str] = Field(default_factory=list)
    contrarian_views: list[str] = Field(default_factory=list)
    category: str = ""


class ClusterData(BaseModel):
    id: int | None = None
    date: str
    item_ids: list[int] = Field(default_factory=list)
    primary_item_id: int | None = None
    title: str | None = None
    enrichment: ClusterEnrichment | None = None
    coverage_breadth: int = 1
    composite_score: float = 0.0
    novelty_score: float = 0.0
    interest_score: float = 0.0
    contrarian_score: float = 0.0
    recency_score: float = 0.0
    section: DigestSection | None = None
    section_rank: int | None = None

    model_config = {"arbitrary_types_allowed": True}


class FeedData(BaseModel):
    id: int | None = None
    url: str
    name: str
    source_id: int | None = None
    feed_type: str = "rss"
    enabled: bool = True
    last_fetched_at: datetime | None = None


class FeedItemData(BaseModel):
    id: int | None = None
    feed_id: int
    guid: str
    url: str | None = None
    title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    content_html: str | None = None
    content_hash: str | None = None


class EmbeddingResult(BaseModel):
    """Wrapper around an embedding vector."""

    content_item_id: int
    vector: list[float]
    model: str

    def to_numpy(self) -> np.ndarray:
        return np.array(self.vector, dtype=np.float32)


class PipelineRunResult(BaseModel):
    stage: PipelineStage
    status: str = "completed"
    items_processed: int = 0
    error: str | None = None


class DigestData(BaseModel):
    date: str
    top_stories: list[ClusterData] = Field(default_factory=list)
    hidden_gems: list[ClusterData] = Field(default_factory=list)
    trend_watch: list[ClusterData] = Field(default_factory=list)
    paper_drops: list[ClusterData] = Field(default_factory=list)
    markdown: str = ""
    stats: dict = Field(default_factory=dict)
