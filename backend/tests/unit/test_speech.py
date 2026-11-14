import io
import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.speech.interfaces import FakeSpeechEngine, SpeechSegment
from app.speech.stt import (
    ACCEPTED_AUDIO_TYPES,
    FasterWhisperEngine,
    reset_speech_engine,
    set_speech_engine,
)


def make_wav_bytes(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    amplitude: int = 0,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        num_samples = int(duration_s * sample_rate)
        if amplitude == 0:
            data = b"\x00" * (num_samples * 2)
        else:
            samples = [
                int(amplitude * math.sin(2 * math.pi * 440 * i / sample_rate))
                for i in range(num_samples)
            ]
            data = struct.pack(f"<{len(samples)}h", *samples)
        w.writeframes(data)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clean_speech_engine() -> None:
    reset_speech_engine()
    yield
    reset_speech_engine()


def test_speech_status_returns_contract_shape() -> None:
    fake = FakeSpeechEngine(ready=True, model="small", device="cpu")
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.get("/api/v1/speech/status")

    assert response.status_code == 200
    data = response.json()
    assert data["stt"]["status"] == "ready"
    assert data["stt"]["engine"] == "faster-whisper"
    assert data["stt"]["model"] == "small"
    assert data["stt"]["device"] == "cpu"
    assert data["stt"]["language"] == "en"
    assert data["tts"] == {"mode": "browser", "server_side": False}
    assert data["limits"]["max_audio_seconds"] == 120
    assert data["limits"]["max_audio_mb"] == 10
    assert set(data["limits"]["accepted_types"]) == {
        "audio/webm",
        "audio/ogg",
        "audio/wav",
        "audio/mp4",
        "audio/mpeg",
    }
    assert ACCEPTED_AUDIO_TYPES == frozenset(data["limits"]["accepted_types"])


def test_speech_status_reports_unavailable() -> None:
    fake = FakeSpeechEngine(unavailable=True, detail="faster-whisper is not installed")
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.get("/api/v1/speech/status")

    assert response.status_code == 200
    data = response.json()
    assert data["stt"]["status"] == "unavailable"


def test_speech_status_reports_loading_when_not_ready() -> None:
    fake = FakeSpeechEngine(ready=False, model="base.en")
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.get("/api/v1/speech/status")

    assert response.status_code == 200
    data = response.json()
    assert data["stt"]["status"] == "loading"
    assert data["stt"]["model"] == "base.en"


def test_speech_status_model_switch_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_MODEL", "base.en")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    engine = FasterWhisperEngine(warmup=False)
    set_speech_engine(engine)

    client = TestClient(create_app())
    response = client.get("/api/v1/speech/status")

    assert response.status_code == 200
    assert response.json()["stt"]["model"] == "base.en"
    assert response.json()["stt"]["device"] == "cpu"


def test_transcribe_success_returns_expected_contract_shape() -> None:
    fake = FakeSpeechEngine(
        ready=True,
        text="I led a project to migrate our backend.",
        duration_ms=4500,
        avg_confidence=0.94,
        segments=[
            SpeechSegment(
                start_ms=0,
                end_ms=4500,
                text="I led a project to migrate our backend.",
                confidence=0.94,
            )
        ],
    )
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=4.5)

    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("speech.wav", wav_data, "audio/wav")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "I led a project to migrate our backend."
    assert data["language"] == "en"
    assert data["duration_ms"] == 4500
    assert data["avg_confidence"] == 0.94
    assert data["word_count"] == 8
    assert data["processing_ms"] >= 0
    assert len(data["segments"]) == 1
    assert data["segments"][0]["text"] == "I led a project to migrate our backend."
    assert data["segments"][0]["confidence"] == 0.94


def test_transcribe_rejects_extra_multipart_field_with_422_validation_error() -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=1.0)

    # Sending extra multipart field 'language' must return 422 VALIDATION_ERROR
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("speech.wav", wav_data, "audio/wav")},
        data={"language": "en"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "audio" in body["error"]["message"] or "received_parts" in str(body["error"]["details"])


def test_transcribe_rejects_missing_audio_part_with_422_validation_error() -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"wrong_field": ("speech.wav", b"123", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_transcribe_returns_503_stt_not_ready_when_loading() -> None:
    fake = FakeSpeechEngine(ready=False)
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=1.0)

    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("speech.wav", wav_data, "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STT_NOT_READY"


def test_transcribe_returns_503_stt_unavailable() -> None:
    fake = FakeSpeechEngine(unavailable=True, detail="faster-whisper is not installed")
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=1.0)

    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("speech.wav", wav_data, "audio/wav")},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STT_UNAVAILABLE"


def test_transcribe_returns_415_on_unsupported_content_type() -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("doc.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "AUDIO_UNSUPPORTED_FORMAT"


def test_transcribe_returns_415_on_corrupt_audio_data() -> None:
    fake = FakeSpeechEngine(ready=True, should_fail_unsupported=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("corrupt.wav", b"not a real audio stream", "audio/wav")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "AUDIO_UNSUPPORTED_FORMAT"


def test_transcribe_returns_413_when_audio_exceeds_max_mb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    settings = Settings(max_audio_mb=1)
    app = create_app(settings)
    client = TestClient(app)

    # 1.5 MB payload
    large_audio = b"\x00" * int(1.5 * 1024 * 1024)
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("large.wav", large_audio, "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AUDIO_TOO_LARGE"


def test_transcribe_returns_422_when_audio_empty() -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_EMPTY_OR_SILENT"


def test_transcribe_returns_422_when_audio_silent() -> None:
    fake = FakeSpeechEngine(ready=True, should_fail_empty_or_silent=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=1.0)

    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("silent.wav", wav_data, "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_EMPTY_OR_SILENT"


def test_transcribe_returns_422_when_audio_too_long() -> None:
    fake = FakeSpeechEngine(ready=True, should_fail_too_long=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=125.0)

    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("long.wav", wav_data, "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_TOO_LONG"


def test_no_audio_files_persisted_to_disk(tmp_path: Path) -> None:
    fake = FakeSpeechEngine(ready=True)
    set_speech_engine(fake)

    client = TestClient(create_app())
    wav_data = make_wav_bytes(duration_s=2.0)

    files_before = set(Path(".").glob("**/*.wav"))
    response = client.post(
        "/api/v1/speech/transcribe",
        files={"audio": ("speech.wav", wav_data, "audio/wav")},
    )
    files_after = set(Path(".").glob("**/*.wav"))

    assert response.status_code == 200
    assert files_before == files_after


def test_faster_whisper_engine_handles_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FasterWhisperEngine, "_is_whisper_available", staticmethod(lambda: False))
    engine = FasterWhisperEngine()
    status = engine.status()
    assert status["status"] == "unavailable"
    assert "faster-whisper is not installed" in str(status["detail"])

    with pytest.raises(Exception) as exc_info:
        engine.transcribe(b"fake", "audio/wav")
    assert getattr(exc_info.value, "code", None) == "STT_UNAVAILABLE"


@pytest.mark.stt
def test_faster_whisper_engine_opt_in() -> None:
    engine = FasterWhisperEngine(model_name="tiny.en", warmup=True)
    # Wait briefly for warm-up thread to finish
    if engine._warmup_thread:
        engine._warmup_thread.join(timeout=30.0)

    status = engine.status()
    assert status["engine"] == "faster-whisper"
    assert status["model"] == "tiny.en"
    assert status["status"] == "ready"

    # Silent audio with VAD filter must raise AUDIO_EMPTY_OR_SILENT
    silent_wav = make_wav_bytes(duration_s=2.0, amplitude=0)
    with pytest.raises(Exception) as exc_info:
        engine.transcribe(silent_wav, "audio/wav")

    assert getattr(exc_info.value, "code", None) == "AUDIO_EMPTY_OR_SILENT"
