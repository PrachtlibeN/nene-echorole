from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import LLMProfile, Settings
from app.core.db import build_engine
from app.core.errors import AppError, ErrorCode
from app.main import create_app
from app.models import Base
from app.models.entities import Conversation, Message, Scenario, Session, Turn
from app.roleplay.interfaces import (
    LLMMeta,
    RoleplayContext,
    RoleplayReply,
    StubRoleplayAgent,
)
from app.roleplay.prompts import build_roleplay_prompt


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class FailingAgent(StubRoleplayAgent):
    def respond(self, ctx: RoleplayContext, candidate_text: str) -> RoleplayReply:
        raise AppError(ErrorCode.LLM_UNAVAILABLE, "Agent is unavailable.", 503)


class BlockingAgent(StubRoleplayAgent):
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def respond(self, ctx: RoleplayContext, candidate_text: str) -> RoleplayReply:
        self.started.set()
        assert self.release.wait(timeout=5)
        return super().respond(ctx, candidate_text)


class ConcludingAgent(StubRoleplayAgent):
    def respond(self, ctx: RoleplayContext, candidate_text: str) -> RoleplayReply:
        return RoleplayReply(
            text="Thank you. That concludes our discussion.",
            should_end=True,
            llm=LLMMeta(model="", latency_ms=0),
        )


class CapturingAgent(StubRoleplayAgent):
    def __init__(self) -> None:
        self.context: RoleplayContext | None = None
        self.candidate_text: str | None = None

    def respond(self, ctx: RoleplayContext, candidate_text: str) -> RoleplayReply:
        self.context = ctx
        self.candidate_text = candidate_text
        return super().respond(ctx, candidate_text)


class PanelAgent(StubRoleplayAgent):
    def open_session(self, ctx: RoleplayContext) -> list[RoleplayReply]:
        return [
            RoleplayReply(
                text="Welcome. We will discuss your project.",
                should_end=False,
                llm=LLMMeta(model="test-model", latency_ms=1),
                speaker_id="alex",
                speaker_name="Alex",
            ),
            RoleplayReply(
                text="What project did you lead under pressure?",
                should_end=False,
                llm=LLMMeta(model="test-model", latency_ms=1),
                speaker_id="sarah",
                speaker_name="Sarah",
            ),
        ]

    def respond(
        self, ctx: RoleplayContext, candidate_text: str
    ) -> list[RoleplayReply]:
        return [
            RoleplayReply(
                text="Explain your technical decision.",
                should_end=False,
                llm=LLMMeta(model="test-model", latency_ms=1),
                speaker_id="alex",
                speaker_name="Alex",
            ),
            RoleplayReply(
                text="How did you resolve the disagreement?",
                should_end=False,
                llm=LLMMeta(model="test-model", latency_ms=1),
                speaker_id="sarah",
                speaker_name="Sarah",
            ),
        ]


@pytest.fixture
def environment(tmp_path):
    clock = FixedClock()
    with _client_environment(tmp_path, clock) as result:
        yield result


@contextmanager
def _client_environment(tmp_path, clock, agent=None):
    database_path = tmp_path / "simulation.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    settings = Settings(
        ollama_model="configured-test-model",
        echorole_db_url=database_url,
        session_idle_timeout_minutes=60,
    )
    application = create_app(settings)
    application.state.simulation_clock = clock
    application.state.roleplay_agent = agent or StubRoleplayAgent()

    with TestClient(application) as client:
        yield client, clock


def _create_started(client: TestClient) -> tuple[str, str]:
    scenarios = client.get("/api/v1/scenarios")
    assert scenarios.status_code == 200
    scenario_id = scenarios.json()["items"][0]["id"]
    created = client.post("/api/v1/sessions", json={"scenario_id": scenario_id})
    assert created.status_code == 201
    session_id = created.json()["id"]
    started = client.post(f"/api/v1/sessions/{session_id}/start", json={})
    assert started.status_code == 200
    return session_id, scenario_id


def _submit(client: TestClient, session_id: str):
    return client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={
            "text": "I led a project and reduced delivery time by 20%.",
            "source": "typed",
            "speech_meta": None,
        },
    )


def test_scenarios_are_valid_seeded_and_upserted_by_slug(environment) -> None:
    client, _ = environment
    response = client.get("/api/v1/scenarios")
    assert response.status_code == 200
    assert response.json()["total"] == 3
    scenarios = response.json()["items"]

    for item in scenarios:
        detail = client.get(f"/api/v1/scenarios/{item['id']}")
        assert detail.status_code == 200
        assert detail.json()["definition"]["task"]["goal"]

    service = client.app.state.simulation_service
    with service.session_factory() as db:
        original = db.scalar(select(Scenario).where(Scenario.slug == scenarios[0]["slug"]))
        assert original is not None
        original_id = original.id
        original.title = "Temporary value"
        db.commit()

    service.seed_scenarios()
    with service.session_factory() as db:
        refreshed = db.scalar(select(Scenario).where(Scenario.slug == scenarios[0]["slug"]))
        assert refreshed is not None
        assert refreshed.id == original_id
        assert refreshed.title == scenarios[0]["title"]
        assert (
            db.scalar(select(Scenario.id).where(Scenario.slug == scenarios[0]["slug"]))
            == original_id
        )


def test_session_create_start_turn_history_end_and_m6_interface(environment) -> None:
    client, _ = environment
    session_id, scenario_id = _create_started(client)

    created = client.get(f"/api/v1/sessions/{session_id}")
    assert created.status_code == 200
    assert created.json()["status"] == "active"
    assert created.json()["scenario_id"] == scenario_id

    turn = _submit(client, session_id)
    assert turn.status_code == 200
    assert turn.json()["candidate_turn"]["idx"] == 1
    assert turn.json()["interviewer_turn"]["idx"] == 2
    assert turn.json()["session"]["turn_count"] == 1

    listed = client.get(f"/api/v1/sessions/{session_id}/turns")
    assert [item["idx"] for item in listed.json()["items"]] == [0, 1, 2]
    transcript = client.app.state.simulation_service.get_transcript(session_id)
    assert transcript.scenario.id == scenario_id
    assert [item.idx for item in transcript.turns] == [0, 1, 2]

    service = client.app.state.simulation_service
    with pytest.raises(AppError) as error:
        service.assert_session_ended(session_id)
    assert error.value.code is ErrorCode.SESSION_NOT_ENDED
    ended = client.post(f"/api/v1/sessions/{session_id}/end", json={})
    assert ended.status_code == 200
    assert ended.json()["end_reason"] == "user_ended"
    service.assert_session_ended(session_id)
    assert client.post(f"/api/v1/sessions/{session_id}/end", json={}).json() == ended.json()

    with service.session_factory() as db:
        conversation = db.scalar(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        assert conversation is not None
        assert conversation.model == service.settings.model_for(LLMProfile.ROLEPLAY)
        assert conversation.id == created.json()["roleplay_conversation_id"]
        scenario = service.get_transcript(session_id).scenario
        assert conversation.system_prompt == build_roleplay_prompt(scenario)


def test_panel_start_and_turn_responses_preserve_legacy_final_turn_and_speaker_ids(
    tmp_path,
) -> None:
    clock = FixedClock()
    with _client_environment(tmp_path, clock, PanelAgent()) as (client, _):
        scenarios = client.get("/api/v1/scenarios").json()
        scenario_summary = scenarios["items"][0]
        assert [persona["name"] for persona in scenario_summary["personas"]] == [
            "Alex",
            "Sarah",
        ]
        created = client.post(
            "/api/v1/sessions",
            json={"scenario_id": scenario_summary["id"]},
        )
        session_id = created.json()["id"]

        started = client.post(f"/api/v1/sessions/{session_id}/start", json={})

        assert started.status_code == 200
        start_data = started.json()
        assert [turn["speaker_id"] for turn in start_data["interviewer_turns"]] == [
            "alex",
            "sarah",
        ]
        assert start_data["interviewer_turn"]["id"] == start_data["interviewer_turns"][-1]["id"]
        assert [turn["idx"] for turn in start_data["interviewer_turns"]] == [0, 1]

        response = _submit(client, session_id)

        assert response.status_code == 200
        result = response.json()
        assert [turn["speaker_id"] for turn in result["interviewer_turns"]] == [
            "alex",
            "sarah",
        ]
        assert result["interviewer_turn"]["id"] == result["interviewer_turns"][-1]["id"]
        assert [turn["idx"] for turn in result["interviewer_turns"]] == [3, 4]
        assert result["candidate_turn"]["idx"] == 2
        assert result["session"]["turn_count"] == 1

        service = client.app.state.simulation_service
        with service.session_factory() as db:
            messages = db.scalars(
                select(Message)
                .where(
                    Message.conversation_id
                    == start_data["session"]["roleplay_conversation_id"]
                )
                .order_by(Message.seq)
            ).all()
        assistant_content = [message.content for message in messages if message.role == "assistant"]
        assert assistant_content[0].startswith("[Alex - Engineering Manager]:")
        assert assistant_content[1].startswith("[Sarah - People Partner]:")
        assert assistant_content[2].startswith("[Alex - Engineering Manager]:")
        assert assistant_content[3].startswith("[Sarah - People Partner]:")


def test_agent_conclusion_ends_automatically(tmp_path) -> None:
    clock = FixedClock()
    with _client_environment(tmp_path, clock, ConcludingAgent()) as (client, _):
        session_id, _ = _create_started(client)
        result = _submit(client, session_id)
        assert result.status_code == 200
        assert result.json()["session"]["status"] == "ended"
        assert result.json()["session"]["end_reason"] == "agent_concluded"


def test_roleplay_agent_receives_history_without_current_candidate(tmp_path) -> None:
    clock = FixedClock()
    agent = CapturingAgent()
    with _client_environment(tmp_path, clock, agent) as (client, _):
        session_id, _ = _create_started(client)
        candidate_text = "The candidate turn is supplied separately."
        response = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"text": candidate_text, "source": "typed", "speech_meta": None},
        )
        assert response.status_code == 200
        assert agent.context is not None
        assert [(message.role, message.content) for message in agent.context.history] == [
            ("assistant", "Tell me about a project you led under a tight deadline.")
        ]
        assert agent.candidate_text == candidate_text


def test_max_turn_limit_adds_closing_interviewer_turn(environment) -> None:
    client, _ = environment
    session_id, scenario_id = _create_started(client)
    service = client.app.state.simulation_service
    with service.session_factory() as db:
        db.execute(update(Scenario).where(Scenario.id == scenario_id).values(max_turns=1))
        db.commit()

    result = _submit(client, session_id)
    assert result.status_code == 200
    body = result.json()
    assert body["session"]["status"] == "ended"
    assert body["session"]["end_reason"] == "max_turns"
    assert body["interviewer_turn"]["speaker"] == "interviewer"


def test_agent_failure_rolls_back_turn_and_clears_guard(tmp_path) -> None:
    clock = FixedClock()
    with _client_environment(tmp_path, clock, FailingAgent()) as (client, _):
        session_id, _ = _create_started(client)
        response = _submit(client, session_id)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_UNAVAILABLE"

        service = client.app.state.simulation_service
        with service.session_factory() as db:
            session = db.get(Session, session_id)
            assert session is not None
            assert session.in_flight == 0
            assert session.turn_count == 0
            assert session.last_activity_at == "2026-11-13T09:00:00.000000Z"
            assert len(db.scalars(select(Turn).where(Turn.session_id == session_id)).all()) == 1
            assert len(
                db.scalars(
                    select(Message).where(
                        Message.conversation_id == (
                            select(Conversation.id).where(
                                Conversation.session_id == session_id
                            ).scalar_subquery()
                        )
                    )
                ).all()
            ) == 1


def test_concurrent_turn_is_rejected_while_first_is_in_flight(tmp_path) -> None:
    clock = FixedClock()
    agent = BlockingAgent()
    with _client_environment(tmp_path, clock, agent) as (client, _):
        session_id, _ = _create_started(client)
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(_submit, client, session_id)
            assert agent.started.wait(timeout=5)
            second = _submit(client, session_id)
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "TURN_IN_PROGRESS"
            agent.release.set()
            first_response = first.result(timeout=5)
        assert first_response.status_code == 200


def test_timeout_boundary_get_does_not_refresh_and_created_sessions_are_exempt(
    environment,
) -> None:
    client, clock = environment
    session_id, scenario_id = _create_started(client)
    created = client.post("/api/v1/sessions", json={"scenario_id": scenario_id})
    created_id = created.json()["id"]

    clock.advance(timedelta(minutes=60))
    boundary = client.get(f"/api/v1/sessions/{session_id}")
    assert boundary.json()["status"] == "active"
    clock.advance(timedelta(microseconds=1))
    expired = client.get(f"/api/v1/sessions/{session_id}")
    assert expired.json()["status"] == "abandoned"
    assert expired.json()["end_reason"] == "timeout"
    assert expired.json()["ended_at"] == "2026-11-13T09:00:00Z"
    abandoned_turn = _submit(client, session_id)
    assert abandoned_turn.status_code == 409
    assert abandoned_turn.json()["error"]["code"] == "SESSION_NOT_ACTIVE"
    assert abandoned_turn.json()["error"]["details"]["status"] == "abandoned"
    abandoned_end = client.post(f"/api/v1/sessions/{session_id}/end", json={})
    assert abandoned_end.status_code == 409
    assert abandoned_end.json()["error"]["code"] == "SESSION_INVALID_STATE"
    assert client.get(f"/api/v1/sessions/{created_id}").json()["status"] == "created"


def test_list_sweeps_idle_sessions_but_not_inflight_or_created(environment) -> None:
    client, clock = environment
    active_id, scenario_id = _create_started(client)
    in_flight_id = client.post("/api/v1/sessions", json={"scenario_id": scenario_id}).json()[
        "id"
    ]
    client.post(f"/api/v1/sessions/{in_flight_id}/start", json={})
    service = client.app.state.simulation_service
    with service.session_factory() as db:
        db.execute(
            update(Session).where(Session.id == in_flight_id).values(in_flight=1)
        )
        db.commit()
    created_id = client.post("/api/v1/sessions", json={"scenario_id": scenario_id}).json()["id"]

    clock.advance(timedelta(minutes=61))
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()["items"]}
    assert by_id[active_id]["status"] == "abandoned"
    assert by_id[in_flight_id]["status"] == "active"
    assert by_id[created_id]["status"] == "created"


def test_startup_performs_lazy_timeout_sweep(tmp_path) -> None:
    clock = FixedClock()
    with _client_environment(tmp_path, clock) as (client, _):
        session_id, _ = _create_started(client)
    clock.advance(timedelta(minutes=61))
    with _client_environment(tmp_path, clock) as (restarted_client, _):
        response = restarted_client.get(f"/api/v1/sessions/{session_id}")
        assert response.json()["status"] == "abandoned"


def test_contract_errors_and_session_pagination(environment) -> None:
    client, _ = environment
    missing_scenario = client.post("/api/v1/sessions", json={"scenario_id": "scn_missing"})
    assert missing_scenario.status_code == 404
    assert missing_scenario.json()["error"]["code"] == "SCENARIO_NOT_FOUND"
    assert missing_scenario.json()["error"]["request_id"]

    malformed = client.post(
        "/api/v1/sessions",
        json={"scenario_id": "scn_missing", "unexpected": True},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"

    missing_session = client.get("/api/v1/sessions/ses_missing")
    assert missing_session.status_code == 404
    assert missing_session.json()["error"]["code"] == "SESSION_NOT_FOUND"

    scenario_id = client.get("/api/v1/scenarios").json()["items"][0]["id"]
    created_session = client.post("/api/v1/sessions", json={"scenario_id": scenario_id})
    created_id = created_session.json()["id"]
    inactive_turn = _submit(client, created_id)
    assert inactive_turn.status_code == 409
    assert inactive_turn.json()["error"]["code"] == "SESSION_NOT_ACTIVE"
    invalid_end = client.post(f"/api/v1/sessions/{created_id}/end", json={})
    assert invalid_end.status_code == 409
    assert invalid_end.json()["error"]["code"] == "SESSION_INVALID_STATE"
    assert client.post(f"/api/v1/sessions/{created_id}/start", json={}).status_code == 200
    invalid_start = client.post(f"/api/v1/sessions/{created_id}/start", json={})
    assert invalid_start.status_code == 409
    assert invalid_start.json()["error"]["code"] == "SESSION_INVALID_STATE"

    _, scenario_id = _create_started(client)
    response = client.get("/api/v1/sessions?status=active&limit=1&offset=0")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["limit"] == 1
    assert response.json()["items"][0]["scenario_id"] == scenario_id
