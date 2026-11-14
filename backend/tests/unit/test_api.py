import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import build_engine
from app.evaluation.coach import EvaluationCoach
from app.llm.client import OpenAICompatibleClient
from app.llm.fake import FakeLLMClient
from app.main import create_app
from app.models import Base
from app.roleplay.agent import RoleplayAgent
from app.speech.interfaces import FakeSpeechEngine


def test_app_lifespan_wires_real_llm_agents(tmp_path) -> None:
    settings = Settings(
        ollama_model="test-model",
        echorole_db_url=f"sqlite:///{(tmp_path / 'di.db').as_posix()}",
    )
    engine = build_engine(settings.echorole_db_url)
    Base.metadata.create_all(engine)
    application = create_app(settings)
    try:
        with TestClient(application):
            llm = application.state.llm_client
            assert isinstance(application.state.roleplay_agent, RoleplayAgent)
            assert isinstance(application.state.evaluation_coach, EvaluationCoach)
            assert application.state.roleplay_agent._llm is llm
            assert application.state.evaluation_coach.llm is llm
    finally:
        engine.dispose()


def test_app_selects_openai_compatible_provider_for_health(
    tmp_path, monkeypatch
) -> None:
    settings = Settings(
        _env_file=None,
        LLM_PROVIDER="openai_compatible",
        openai_model="cloud-test-model",
        openai_api_key="test-token",
        echorole_db_url=f"sqlite:///{(tmp_path / 'cloud-health.db').as_posix()}",
    )
    engine = build_engine(settings.echorole_db_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"data": [{"id": "cloud-test-model"}]},
        )
    )
    provider_client = httpx.Client(transport=transport)
    class MockedOpenAICompatibleClient(OpenAICompatibleClient):
        def __init__(self, active_settings: Settings) -> None:
            super().__init__(active_settings, provider_client)

    monkeypatch.setattr("app.main.OpenAICompatibleClient", MockedOpenAICompatibleClient)
    application = create_app(settings)

    try:
        with TestClient(application) as client:
            assert isinstance(application.state.llm_client, OpenAICompatibleClient)
            response = client.get("/api/v1/health")
    finally:
        provider_client.close()

    assert response.status_code == 200
    assert response.json()["components"]["llm"]["status"] == "ok"
    assert response.json()["components"]["llm"]["models"] == {
        "roleplay": "cloud-test-model",
        "evaluation": "cloud-test-model",
    }


def test_health_has_contract_shape_and_echoes_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"X-Request-ID": "req-test-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-1"
    assert response.json()["contract_version"] == "0.4.0"
    assert response.json()["components"]["llm"]["models"]["roleplay"]


def test_health_checks_sqlite_ollama_and_speech_states(tmp_path) -> None:
    settings = Settings(
        ollama_model="test-model",
        echorole_db_url=f"sqlite:///{(tmp_path / 'health.db').as_posix()}",
    )
    engine = build_engine(settings.echorole_db_url)
    Base.metadata.create_all(engine)
    application = create_app(settings)
    application.state.db_engine = engine
    application.state.llm_client = FakeLLMClient(settings)
    application.state.speech_engine = FakeSpeechEngine()

    response = TestClient(application).get("/api/v1/health")
    engine.dispose()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["components"]["database"]["status"] == "ok"
    assert payload["components"]["llm"]["status"] == "ok"
    assert payload["components"]["stt"]["status"] == "ready"


def test_openapi_declares_exactly_fourteen_contract_endpoints() -> None:
    client = TestClient(create_app())
    paths = client.get("/openapi.json").json()["paths"]

    assert len(paths) == 11
    assert sum(len(path_item) for path_item in paths.values()) == 14
