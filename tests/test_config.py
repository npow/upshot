"""Tests for configuration loading."""

from upshot.config import Settings, load_settings


def test_default_settings():
    settings = Settings()
    assert settings.gmail.labels == ["Newsletters"]
    assert settings.dedup.distance_threshold == 0.35
    assert settings.ranking.weight_coverage == 0.25


def test_load_settings_from_yaml(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
gmail:
  labels: ["Test Label"]
  max_results: 10
dedup:
  distance_threshold: 0.4
""")
    settings = load_settings(config)
    assert settings.gmail.labels == ["Test Label"]
    assert settings.gmail.max_results == 10
    assert settings.dedup.distance_threshold == 0.4


def test_load_settings_missing_file():
    settings = load_settings("/nonexistent/config.yaml")
    assert settings.gmail.labels == ["Newsletters"]  # defaults
