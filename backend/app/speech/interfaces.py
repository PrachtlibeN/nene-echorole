from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class SpeechSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None


@dataclass(frozen=True)
class Transcription:
    text: str
    language: str
    duration_ms: int
    avg_confidence: float | None
    word_count: int
    processing_ms: int
    segments: list[SpeechSegment]


class SpeechEngine(Protocol):
    def transcribe(self, audio: bytes, content_type: str) -> Transcription: ...

    def status(self) -> dict[str, object]: ...


class FakeSpeechEngine:
    def __init__(
        self,
        ready: bool = True,
        text: str = "A candidate response.",
        duration_ms: int = 1000,
        avg_confidence: float | None = 0.91,
        segments: list[SpeechSegment] | None = None,
        model: str = "configured",
        device: str = "cpu",
        engine: str = "faster-whisper",
        should_fail_not_ready: bool = False,
        should_fail_empty_or_silent: bool = False,
        should_fail_too_long: bool = False,
        should_fail_unsupported: bool = False,
        unavailable: bool = False,
        detail: str | None = None,
    ) -> None:
        self.ready = ready
        self.unavailable = unavailable
        self.detail = detail
        self.text = text
        self.duration_ms = duration_ms
        self.avg_confidence = avg_confidence
        self.segments = segments or [
            SpeechSegment(0, duration_ms, text, avg_confidence)
        ]
        self.model = model
        self.device = device
        self.engine = engine
        self.should_fail_not_ready = should_fail_not_ready
        self.should_fail_empty_or_silent = should_fail_empty_or_silent
        self.should_fail_too_long = should_fail_too_long
        self.should_fail_unsupported = should_fail_unsupported

    def transcribe(self, audio: bytes, content_type: str) -> Transcription:
        if self.unavailable:
            raise AppError(
                ErrorCode.STT_UNAVAILABLE,
                "Speech engine is unavailable.",
                503,
                details={"status": "unavailable", "detail": self.detail},
            )
        if not self.ready or self.should_fail_not_ready:
            raise AppError(
                ErrorCode.STT_NOT_READY,
                "Speech engine is still loading.",
                503,
            )
        if self.should_fail_unsupported:
            raise AppError(
                ErrorCode.AUDIO_UNSUPPORTED_FORMAT,
                "Audio format is unsupported or corrupt.",
                415,
            )
        if self.should_fail_too_long:
            raise AppError(
                ErrorCode.AUDIO_TOO_LONG,
                "Audio duration exceeds limit.",
                422,
            )
        if self.should_fail_empty_or_silent or not self.text.strip():
            raise AppError(
                ErrorCode.AUDIO_EMPTY_OR_SILENT,
                "No speech detected in audio.",
                422,
            )
        words = self.text.split()
        return Transcription(
            text=self.text,
            language="en",
            duration_ms=self.duration_ms,
            avg_confidence=self.avg_confidence,
            word_count=len(words),
            processing_ms=10,
            segments=self.segments,
        )

    def status(self) -> dict[str, object]:
        return {
            "status": "unavailable" if self.unavailable else ("ready" if self.ready else "loading"),
            "engine": self.engine,
            "model": self.model,
            "device": self.device,
            "language": "en",
            "detail": self.detail,
        }
