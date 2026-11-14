from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.config import Settings, get_settings
from app.core.errors import API_ERROR_RESPONSES, AppError, ErrorCode
from app.schemas.contracts import (
    AudioLimits,
    SpeechStatusOut,
    STTStatus,
    TranscriptionOut,
    TTSStatus,
)
from app.schemas.contracts import (
    SpeechSegment as SpeechSegmentOut,
)
from app.speech.interfaces import SpeechEngine
from app.speech.stt import ACCEPTED_AUDIO_TYPES, get_speech_engine

router = APIRouter(
    prefix="/speech",
    tags=["speech"],
    responses=API_ERROR_RESPONSES,
)


@router.get("/status", response_model=SpeechStatusOut, operation_id="getSpeechStatus")
def get_speech_status(
    request: Request,
    engine: Annotated[SpeechEngine, Depends(get_speech_engine)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpeechStatusOut:
    app_settings = getattr(request.app.state, "settings", settings)
    status_info = engine.status()
    stt_status_val = str(status_info.get("status", "loading"))
    if stt_status_val not in ("ready", "loading", "unavailable"):
        stt_status_val = "loading"

    model_name = str(status_info.get("model") or app_settings.whisper_model)

    return SpeechStatusOut(
        stt=STTStatus(
            status=stt_status_val,
            engine=str(status_info.get("engine", "faster-whisper")),
            model=model_name,
            device=str(status_info.get("device", app_settings.whisper_device)),
            language="en",
        ),
        tts=TTSStatus(mode="browser", server_side=False),
        limits=AudioLimits(
            max_audio_seconds=app_settings.max_audio_seconds,
            max_audio_mb=app_settings.max_audio_mb,
            accepted_types=[
                "audio/webm",
                "audio/ogg",
                "audio/wav",
                "audio/mp4",
                "audio/mpeg",
            ],
        ),
    )


@router.post(
    "/transcribe",
    response_model=TranscriptionOut,
    operation_id="transcribeSpeech",
)
async def transcribe_speech(
    request: Request,
    audio: Annotated[UploadFile, File()],
    engine: Annotated[SpeechEngine, Depends(get_speech_engine)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TranscriptionOut:
    app_settings = getattr(request.app.state, "settings", settings)
    form = await request.form()
    form_keys = set(form.keys())
    if form_keys != {"audio"} or len(form.getlist("audio")) != 1:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Request must contain exactly one multipart part named 'audio'.",
            422,
            details={"received_parts": list(form_keys)},
        )

    status_info = engine.status()
    if status_info.get("status") == "unavailable":
        detail_msg = status_info.get("detail") or "faster-whisper is not installed"
        raise AppError(
            ErrorCode.STT_UNAVAILABLE,
            f"Speech recognition is unavailable: {detail_msg}",
            503,
            details=status_info,
        )
    if status_info.get("status") != "ready":
        raise AppError(
            ErrorCode.STT_NOT_READY,
            "Speech engine is still loading or not ready.",
            503,
            details=status_info,
        )

    raw_content_type = audio.content_type or ""
    content_type = raw_content_type.split(";")[0].strip().lower()
    if content_type not in ACCEPTED_AUDIO_TYPES:
        raise AppError(
            ErrorCode.AUDIO_UNSUPPORTED_FORMAT,
            f"Unsupported audio content type: {audio.content_type}",
            415,
        )

    audio_bytes = await audio.read()

    max_bytes = app_settings.max_audio_mb * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        msg = f"Audio file size exceeds limit of {app_settings.max_audio_mb} MB."
        raise AppError(
            ErrorCode.AUDIO_TOO_LARGE,
            msg,
            413,
        )

    if len(audio_bytes) == 0:
        raise AppError(
            ErrorCode.AUDIO_EMPTY_OR_SILENT,
            "Audio file is empty.",
            422,
        )

    transcription = engine.transcribe(audio_bytes, content_type)

    return TranscriptionOut(
        text=transcription.text,
        language="en",
        duration_ms=transcription.duration_ms,
        avg_confidence=transcription.avg_confidence,
        word_count=transcription.word_count,
        processing_ms=transcription.processing_ms,
        segments=[
            SpeechSegmentOut(
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=s.text,
                confidence=s.confidence,
            )
            for s in transcription.segments
        ],
    )
