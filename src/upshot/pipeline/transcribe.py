"""Pipeline stage: Podcast transcription using faster-whisper."""

from __future__ import annotations

import logging
from pathlib import Path

from upshot.clients.whisper import transcribe_audio
from upshot.config import get_settings
from upshot.db import get_connection
from upshot.models import PipelineRunResult, PipelineStage
from upshot.parsers.podcast import download_audio

logger = logging.getLogger(__name__)


def _get_pending_podcasts(conn) -> list[dict]:
    """Get podcasts that need transcription."""
    rows = conn.execute(
        """SELECT p.id, p.content_item_id, p.audio_url, p.audio_path, p.duration_seconds
           FROM podcasts p
           WHERE p.transcription_status = 'pending'
             AND p.audio_url IS NOT NULL"""
    ).fetchall()
    return [dict(row) for row in rows]


def run_transcribe(target_date: str) -> PipelineRunResult:
    """Transcribe pending podcasts."""
    conn = get_connection()
    settings = get_settings()

    podcasts = _get_pending_podcasts(conn)
    if not podcasts:
        logger.info("No podcasts to transcribe")
        return PipelineRunResult(stage=PipelineStage.TRANSCRIBE, items_processed=0)

    max_duration = settings.transcription.max_duration_minutes * 60
    partial_duration = settings.transcription.partial_duration_minutes * 60
    transcribed = 0

    for podcast in podcasts:
        podcast_id = podcast["id"]
        audio_url = podcast["audio_url"]
        audio_path = podcast.get("audio_path")

        try:
            # Download audio if not already downloaded
            if not audio_path or not Path(audio_path).exists():
                logger.info("Downloading audio: %s", audio_url)
                result = download_audio(audio_url)
                audio_path = result["audio_path"]
                duration = result.get("duration_seconds")

                conn.execute(
                    "UPDATE podcasts SET audio_path = ?, duration_seconds = ? WHERE id = ?",
                    (audio_path, duration, podcast_id),
                )
                conn.commit()
            else:
                duration = podcast.get("duration_seconds")

            # Check duration limit
            if duration and duration > max_duration:
                logger.info(
                    "Podcast %d too long (%.0f min > %d min limit), transcribing first %d min",
                    podcast_id, duration / 60, max_duration / 60, partial_duration / 60,
                )
                max_seconds = partial_duration
            else:
                max_seconds = None

            # Transcribe
            logger.info("Transcribing podcast %d: %s", podcast_id, audio_path)
            result = transcribe_audio(audio_path, max_duration_seconds=max_seconds)

            conn.execute(
                """UPDATE podcasts SET
                     transcript = ?,
                     transcription_status = 'transcribed',
                     transcribed_at = datetime('now')
                   WHERE id = ?""",
                (result["text"], podcast_id),
            )

            # Also update the content item's full_text
            conn.execute(
                """UPDATE content_items SET
                     full_text = ?,
                     word_count = ?,
                     fetch_status = 'fetched'
                   WHERE id = ?""",
                (result["text"], len(result["text"].split()), podcast["content_item_id"]),
            )

            conn.commit()
            transcribed += 1

        except Exception as e:
            logger.error("Failed to transcribe podcast %d: %s", podcast_id, e)
            conn.execute(
                "UPDATE podcasts SET transcription_status = 'failed' WHERE id = ?",
                (podcast_id,),
            )
            conn.commit()

    logger.info("Transcribed %d/%d podcasts", transcribed, len(podcasts))

    return PipelineRunResult(
        stage=PipelineStage.TRANSCRIBE,
        items_processed=transcribed,
    )
