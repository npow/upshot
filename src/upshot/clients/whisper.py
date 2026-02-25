"""Faster-whisper wrapper for podcast transcription."""

from __future__ import annotations

import logging
from pathlib import Path

from upshot.config import get_settings

logger = logging.getLogger(__name__)

_model = None


def get_model():
    """Get or load the faster-whisper model."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        settings = get_settings()
        logger.info(
            "Loading Whisper model: %s (compute=%s, device=%s)",
            settings.transcription.whisper_model,
            settings.transcription.compute_type,
            settings.transcription.device,
        )
        _model = WhisperModel(
            settings.transcription.whisper_model,
            device=settings.transcription.device,
            compute_type=settings.transcription.compute_type,
        )
    return _model


def transcribe_audio(audio_path: str | Path, max_duration_seconds: float | None = None) -> dict:
    """Transcribe an audio file using faster-whisper.

    Args:
        audio_path: Path to the audio file.
        max_duration_seconds: If set, only transcribe up to this many seconds.

    Returns:
        Dict with: text, language, duration_seconds, segments
    """
    model = get_model()
    audio_path = str(audio_path)

    segments_iter, info = model.transcribe(
        audio_path,
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=True,
    )

    text_parts = []
    segments = []
    total_duration = 0.0

    for segment in segments_iter:
        if max_duration_seconds and segment.start > max_duration_seconds:
            break

        text_parts.append(segment.text)
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        })
        total_duration = segment.end

    return {
        "text": " ".join(text_parts).strip(),
        "language": info.language,
        "duration_seconds": total_duration,
        "segments": segments,
    }
