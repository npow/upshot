"""Podcast detection and audio download."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from upshot.utils.retry import retry

logger = logging.getLogger(__name__)

PODCAST_DOMAINS = [
    "podcasts.apple.com",
    "open.spotify.com",
    "overcast.fm",
    "pocketcasts.com",
    "castbox.fm",
    "anchor.fm",
    "buzzsprout.com",
    "podbean.com",
    "transistor.fm",
    "simplecast.com",
]

AUDIO_EXTENSIONS = [".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac"]


def is_podcast_url(url: str) -> bool:
    """Check if a URL is likely a podcast or audio content."""
    url_lower = url.lower()

    # Check domain
    for domain in PODCAST_DOMAINS:
        if domain in url_lower:
            return True

    # Check for YouTube (may contain podcast episodes)
    if re.search(r"(?:youtube\.com/watch|youtu\.be/)", url_lower):
        return True

    # Check file extension
    for ext in AUDIO_EXTENSIONS:
        if url_lower.endswith(ext):
            return True

    return False


@retry(max_attempts=2, base_delay=5.0, exceptions=(Exception,))
def download_audio(url: str, output_dir: Path | None = None) -> dict:
    """Download audio from a podcast/video URL using yt-dlp.

    Returns dict with: audio_path, duration_seconds, title
    """
    import yt_dlp

    if output_dir is None:
        output_dir = Path("downloads")
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        duration = info.get("duration")
        title = info.get("title", "")
        video_id = info.get("id", "unknown")

    audio_path = output_dir / f"{video_id}.mp3"

    return {
        "audio_path": str(audio_path),
        "duration_seconds": duration,
        "title": title,
    }
