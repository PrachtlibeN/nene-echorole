from typing import Literal, cast

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import LLMProfile, Settings
from app.core.db import build_engine
from app.core.errors import API_ERROR_RESPONSES, AppError
from app.llm.interfaces import LLMClient
from app.schemas.contracts import (
    HealthComponent,
    HealthComponents,
    HealthOut,
    LLMHealthComponent,
    STTHealthComponent,
)
from app.speech.interfaces import SpeechEngine
from app.speech.stt import get_speech_engine

router = APIRouter(responses=API_ERROR_RESPONSES)


@router.get("/health", response_model=HealthOut, operation_id="getHealth")
def get_health(request: Request) -> HealthOut:
    settings: Settings = request.app.state.settings
    engine = getattr(request.app.state, "db_engine", None)
    owns_engine = engine is None
    if engine is None:
        engine = build_engine(settings.echorole_db_url)
    try:
        database = _database_health(engine)
    finally:
        if owns_engine:
            engine.dispose()

    llm_client = getattr(request.app.state, "llm_client", None)
    if llm_client is None:
        llm = LLMHealthComponent(
            status="loading",
            models={
                "roleplay": settings.model_for(LLMProfile.ROLEPLAY),
                "evaluation": settings.model_for(LLMProfile.EVALUATION),
            },
            detail="LLM client is not initialized.",
        )
    else:
        try:
            llm_status = cast(LLMClient, llm_client).health()
            llm = LLMHealthComponent(
                status=llm_status.status,
                models=llm_status.models,
                detail=llm_status.detail,
            )
        except AppError as exc:
            llm = LLMHealthComponent(
                status="unavailable",
                models={
                    "roleplay": settings.model_for(LLMProfile.ROLEPLAY),
                    "evaluation": settings.model_for(LLMProfile.EVALUATION),
                },
                detail=exc.message,
            )

    speech_engine = getattr(request.app.state, "speech_engine", None)
    if speech_engine is None:
        speech_engine = get_speech_engine()
    speech_status = cast(SpeechEngine, speech_engine).status()
    raw_stt_status = speech_status.get("status", "loading")
    if raw_stt_status not in ("ready", "loading", "unavailable"):
        stt_status: Literal["ready", "loading", "unavailable"] = "loading"
    else:
        stt_status = cast(
            Literal["ready", "loading", "unavailable"],
            raw_stt_status,
        )
    stt = STTHealthComponent(
        status=stt_status,
        model=str(speech_status.get("model") or settings.whisper_model),
        detail=(
            str(speech_status["detail"])
            if speech_status.get("detail") is not None
            else None
        ),
    )
    overall_status = (
        "ok"
        if database.status == "ok" and llm.status == "ok" and stt.status == "ready"
        else "degraded"
    )
    return HealthOut(
        status=overall_status,
        version="0.1.0",
        contract_version="0.4.0",
        components=HealthComponents(
            database=database,
            llm=llm,
            stt=stt,
        ),
    )


def _database_health(engine: Engine) -> HealthComponent:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM scenarios LIMIT 1"))
    except SQLAlchemyError:
        return HealthComponent(
            status="unavailable",
            detail="SQLite database or required schema is unavailable.",
        )
    return HealthComponent(status="ok")
