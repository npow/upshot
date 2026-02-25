"""Configuration loading from config.yaml + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class GmailConfig(BaseModel):
    labels: list[str] = ["Newsletters"]
    max_results: int = 50
    initial_lookback_days: int = 7


class ExtractionConfig(BaseModel):
    requests_per_second: float = 2.0
    per_domain_requests_per_second: float = 1.0
    fetch_timeout: int = 30
    max_content_length: int = 50_000


class DedupConfig(BaseModel):
    distance_threshold: float = 0.35
    lookback_days: int = 7
    embedding_model: str = "all-MiniLM-L6-v2"


class ClaudeConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"
    base_url: str | None = None
    max_context_words_per_item: int = 2000
    max_tokens: int = 4096
    max_briefing_words: int = 80_000


class TranscriptionConfig(BaseModel):
    whisper_model: str = "large-v3"
    compute_type: str = "int8"
    device: str = "cpu"
    max_duration_minutes: int = 120
    partial_duration_minutes: int = 30


class RankingConfig(BaseModel):
    weight_coverage: float = 0.25
    weight_novelty: float = 0.25
    weight_interest: float = 0.25
    weight_contrarian: float = 0.10
    weight_recency: float = 0.15


class DigestConfig(BaseModel):
    top_stories_count: int = 5
    hidden_gems_count: int = 3
    trend_watch_count: int = 3
    output_dir: str = "digests"


class FeedsConfig(BaseModel):
    fetch_timeout: int = 30
    max_items_per_feed: int = 50


class DatabaseConfig(BaseModel):
    path: str = "upshot.db"


class Settings(BaseModel):
    gmail: GmailConfig = Field(default_factory=GmailConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    feeds: FeedsConfig = Field(default_factory=FeedsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # Environment-sourced secrets (not in config.yaml)
    anthropic_api_key: str = ""
    gmail_credentials_path: str = "credentials.json"


_settings: Settings | None = None


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from config.yaml, overlaid with environment variables."""
    global _settings

    if config_path is None:
        config_path = os.environ.get("UPSHOT_CONFIG", "config.yaml")

    config_path = Path(config_path)
    data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    settings = Settings(**data)

    # Overlay env vars for secrets
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        settings.anthropic_api_key = key
    if path := os.environ.get("GMAIL_CREDENTIALS_PATH"):
        settings.gmail_credentials_path = path

    _settings = settings
    return settings


def get_settings() -> Settings:
    """Get cached settings, loading if necessary."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
