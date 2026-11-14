from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.health import router as health_router
from app.core.config import LLMProvider, Settings
from app.core.db import build_engine
from app.core.errors import register_exception_handlers
from app.core.ids import new_request_id
from app.core.logging import configure_logging
from app.evaluation.coach import EvaluationCoach
from app.evaluation.router import router as evaluation_router
from app.llm.client import OllamaClient, OpenAICompatibleClient
from app.llm.interfaces import LLMClient
from app.roleplay.agent import RoleplayAgent
from app.simulation.router import router as simulation_router
from app.speech.router import router as speech_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        engine = cast(Engine | None, getattr(application.state, "db_engine", None))
        owns_engine = engine is None
        if engine is None:
            engine = build_engine(app_settings.echorole_db_url)
            application.state.db_engine = engine

        owns_session_factory = not hasattr(application.state, "db_session_factory")
        if owns_session_factory:
            application.state.db_session_factory = sessionmaker(
                bind=engine,
                expire_on_commit=False,
            )

        llm_client = getattr(application.state, "llm_client", None)
        owns_llm_client = llm_client is None
        if llm_client is None:
            if app_settings.llm_provider is LLMProvider.OPENAI_COMPATIBLE:
                llm_client = OpenAICompatibleClient(app_settings)
            else:
                llm_client = OllamaClient(app_settings)
            application.state.llm_client = llm_client

        owns_roleplay_agent = getattr(application.state, "roleplay_agent", None) is None
        if owns_roleplay_agent:
            application.state.roleplay_agent = RoleplayAgent(
                cast(LLMClient, llm_client),
                app_settings,
            )
        owns_evaluation_coach = (
            getattr(application.state, "evaluation_coach", None) is None
        )
        if owns_evaluation_coach:
            application.state.evaluation_coach = EvaluationCoach(
                cast(LLMClient, llm_client)
            )

        try:
            yield
        finally:
            if owns_engine:
                engine.dispose()
            if owns_llm_client:
                cast(OllamaClient | OpenAICompatibleClient, llm_client).close()
            for name, owned in (
                ("db_engine", owns_engine),
                ("db_session_factory", owns_session_factory),
                ("llm_client", owns_llm_client),
                ("roleplay_agent", owns_roleplay_agent),
                ("evaluation_coach", owns_evaluation_coach),
            ):
                if owned and hasattr(application.state, name):
                    delattr(application.state, name)

    application = FastAPI(
        title="Nene API",
        version="0.1.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(application)

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        supplied_id = request.headers.get("X-Request-ID", "").strip()
        request_id = supplied_id if supplied_id and len(supplied_id) <= 128 else new_request_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    application.include_router(health_router, prefix="/api/v1")
    application.include_router(simulation_router, prefix="/api/v1")
    application.include_router(speech_router, prefix="/api/v1")
    application.include_router(evaluation_router, prefix="/api/v1")
    return application


app = create_app()
