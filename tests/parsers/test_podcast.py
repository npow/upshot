"""Tests for podcast detection."""

from upshot.parsers.podcast import is_podcast_url


def test_spotify_detected():
    assert is_podcast_url("https://open.spotify.com/episode/abc123")


def test_apple_podcasts_detected():
    assert is_podcast_url("https://podcasts.apple.com/us/podcast/123")


def test_youtube_detected():
    assert is_podcast_url("https://youtube.com/watch?v=abc123")
    assert is_podcast_url("https://youtu.be/abc123")


def test_audio_file_detected():
    assert is_podcast_url("https://example.com/episode.mp3")
    assert is_podcast_url("https://example.com/audio.m4a")


def test_regular_url_not_podcast():
    assert not is_podcast_url("https://example.com/article")
    assert not is_podcast_url("https://arxiv.org/abs/2401.12345")
