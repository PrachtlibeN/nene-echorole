from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import sessionmaker

from app.core.config import LLMProfile, Settings
from app.core.db import build_engine, get_db
from app.core.ids import new_id
from app.evaluation.coach import EvaluationCoach, EvaluationParseError
from app.evaluation.interfaces import CoachContext, CoachScenario
from app.evaluation.metrics import compute_delivery_metrics
from app.evaluation.prompts import build_coach_user_prompt
from app.evaluation.router import get_llm_client
from app.evaluation.rubric import CRITERIA, RUBRIC_DESCRIPTIONS
from app.evaluation.service import EvaluationService
from app.llm.fake import FakeLLMClient
from app.main import create_app
from app.models import Base
from app.models.entities import (
    Conversation,
    Evaluation,
    EvaluationScore,
    Message,
    Scenario,
    Turn,
)
from app.models.entities import (
    Session as InterviewSession,
)
from app.roleplay.interfaces import StubRoleplayAgent
from app.schemas.contracts import (
    ScenarioCriterion,
    ScenarioDefinition,
    ScenarioPanelPersona,
    ScenarioPersona,
    ScenarioTask,
    SpeechMeta,
    TurnOut,
    TurnSource,
)


class FrozenClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


@pytest.fixture
def evaluation_env(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[DBSession], FrozenClock, Any, Settings]]:
    settings = Settings(
        ollama_model="base-model",
        ollama_model_evaluation="evaluation-model",
        echorole_db_url=f"sqlite:///{(tmp_path / 'evaluation.db').as_posix()}",
        session_idle_timeout_minutes=60,
    )
    engine = build_engine(settings.echorole_db_url)
    Base.metadata.create_all(engine)
    factory: sessionmaker[DBSession] = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db, db.begin():
        db.add(
            Scenario(
                id="scn_test",
                slug="test-scenario",
                title="Test scenario",
                description="Evaluation fixture",
                language="en",
                difficulty=1,
                max_turns=8,
                definition_json=_scenario_definition().model_dump_json(),
                created_at="2026-01-01T00:00:00.000000Z",
                updated_at="2026-01-01T00:00:00.000000Z",
            )
        )

    app = create_app(settings)
    clock = FrozenClock()
    app.state.evaluation_clock = clock
    app.state.simulation_clock = clock
    app.state.roleplay_agent = StubRoleplayAgent()

    def override_db() -> Iterator[DBSession]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, factory, clock, app, settings
    engine.dispose()


def _scenario_definition() -> ScenarioDefinition:
    return ScenarioDefinition(
        persona=ScenarioPersona(
            name="Interviewer",
            role="Manager",
            style="Direct",
            pressure_level=1,
        ),
        task=ScenarioTask(
            goal="Describe a difficult project.",
            success_criteria=["Explain the outcome"],
        ),
        evaluation_focus=[ScenarioCriterion.STRUCTURE],
    )


def _coach_scenario() -> CoachScenario:
    return CoachScenario(
        task_goal="Describe a difficult project.",
        success_criteria=["Explain the outcome"],
        evaluation_focus=[ScenarioCriterion.STRUCTURE],
    )


def _turn(
    turn_id: str,
    speaker: str,
    text: str,
    source: TurnSource = TurnSource.TYPED,
    speech_meta: SpeechMeta | None = None,
) -> TurnOut:
    return TurnOut(
        id=turn_id,
        session_id="ses_test",
        idx=0,
        speaker=speaker,
        text=text,
        source=source,
        speech_meta=speech_meta,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _coach_result(
    evidence_id: str,
    *,
    include_backend_fields: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "summary": "Clear example, with room for a stronger outcome.",
        "task_outcome": {
            "achieved": "partially",
            "explanation": "The result was stated.",
        },
        "criteria": [
            {
                "criterion": criterion.value,
                "score": 7,
                "rationale": "The candidate gave a relevant example.",
                "evidence_turn_ids": [evidence_id],
                "weight_percent": 100,
                "weighted_points": 100,
            }
            for criterion in CRITERIA
        ],
        "strengths": [{"text": "Clear example.", "evidence_turn_ids": [evidence_id]}],
        "improvements": [
            {
                "text": "Quantify the outcome.",
                "evidence_turn_ids": [evidence_id],
                "example_rewrite": "We reduced processing time by 20%.",
            }
        ],
        "next_task": {
            "title": "Add a measurable result",
            "instructions": "Re-answer with one measurable outcome.",
        },
    }
    if include_backend_fields:
        result["overall_score"] = 1
        result["weights"] = {"relevance": 1}
        result["metrics"] = {"speaking_time_ms": 1}
    return result


def _create_session(
    factory: sessionmaker[DBSession],
    *,
    status: str = "ended",
    candidate_turn: bool = True,
    last_activity_at: str = "2026-01-01T00:00:00.000000Z",
) -> tuple[str, str | None]:
    session_id = new_id("ses_")
    candidate_id: str | None = new_id("trn_") if candidate_turn else None
    with factory() as db, db.begin():
        db.add(
            InterviewSession(
                id=session_id,
                scenario_id="scn_test",
                status=status,
                end_reason="user_ended" if status == "ended" else None,
                turn_count=1 if candidate_turn else 0,
                in_flight=0,
                created_at=last_activity_at,
                started_at=last_activity_at if status != "created" else None,
                ended_at=last_activity_at if status == "ended" else None,
                last_activity_at=last_activity_at,
            )
        )
        db.flush()
        db.add(
            Conversation(
                id=new_id("cnv_rp_"),
                session_id=session_id,
                agent_role="roleplay",
                system_prompt="private roleplay system prompt",
                model="roleplay-model",
                created_at=last_activity_at,
            )
        )
        if candidate_turn:
            db.add_all(
                [
                    Turn(
                        id=new_id("trn_"),
                        session_id=session_id,
                        idx=0,
                        speaker="interviewer",
                        text="Tell me about a difficult project.",
                        source="generated",
                        speech_meta_json=None,
                        llm_meta_json=None,
                        created_at=last_activity_at,
                    ),
                    Turn(
                        id=candidate_id,
                        session_id=session_id,
                        idx=1,
                        speaker="candidate",
                        text="Um, like, I led the response and improved uptime by 20%, you know.",
                        source="typed",
                        speech_meta_json=None,
                        llm_meta_json=None,
                        created_at=last_activity_at,
                    ),
                ]
            )
    return session_id, candidate_id


def test_delivery_metrics_count_candidate_speech_and_fillers() -> None:
    transcript = [
        _turn(
            "trn_speech",
            "candidate",
            "Um, like, I led the response, you know.",
            TurnSource.SPEECH,
            SpeechMeta(
                duration_ms=60_000,
                avg_confidence=0.8,
                word_count=8,
                language="en",
            ),
        ),
        _turn("trn_typed", "candidate", "Uh, we improved uptime."),
        _turn("trn_interviewer", "interviewer", "Like, what changed?"),
    ]

    metrics = compute_delivery_metrics(transcript)

    assert metrics.candidate_turns == 2
    assert metrics.total_words == 12
    assert metrics.avg_words_per_turn == 6.0
    assert metrics.speaking_time_ms == 60_000
    assert metrics.words_per_minute == 8.0
    assert metrics.filler_words.total == 4
    assert metrics.filler_words.breakdown == {
        "um": 1,
        "uh": 1,
        "like": 1,
        "you know": 1,
    }
    assert metrics.avg_stt_confidence == 0.8


def test_speech_metrics_are_null_without_speech_turns() -> None:
    metrics = compute_delivery_metrics(
        [_turn("trn_typed", "candidate", "A short answer.")]
    )

    assert metrics.speaking_time_ms is None
    assert metrics.words_per_minute is None
    assert metrics.avg_stt_confidence is None


def test_coach_transcript_labels_both_panel_agents_without_delivery_metrics() -> None:
    scenario = CoachScenario(
        task_goal="Describe the project.",
        success_criteria=["Explain the result."],
        evaluation_focus=[ScenarioCriterion.STRUCTURE],
        personas=[
            ScenarioPanelPersona(
                id="alex",
                name="Alex",
                role_title="Engineering Manager",
                focus_area="Execution",
                voice_gender="male",
                persona_prompt="Probe execution.",
            ),
            ScenarioPanelPersona(
                id="sarah",
                name="Sarah",
                role_title="People Partner",
                focus_area="Leadership",
                voice_gender="female",
                persona_prompt="Probe leadership.",
            ),
        ],
    )
    turns = [
        _turn("trn_candidate", "candidate", "I led the migration."),
        _turn("trn_alex", "interviewer", "What did you own?").model_copy(
            update={"speaker_id": "alex", "speaker_name": "Alex"}
        ),
        _turn("trn_sarah", "interviewer", "How did you handle conflict?").model_copy(
            update={"speaker_id": "sarah", "speaker_name": "Sarah"}
        ),
    ]

    prompt = build_coach_user_prompt(scenario, turns)

    assert "[Candidate]: I led the migration." in prompt
    assert "[Alex - Engineering Manager]: What did you own?" in prompt
    assert "[Sarah - People Partner]: How did you handle conflict?" in prompt
    assert "DeliveryMetrics" not in prompt
    assert "words_per_minute" not in prompt


def test_coach_uses_rubric_json_mode_and_discards_backend_fields() -> None:
    transcript = [
        _turn("trn_interviewer", "interviewer", "What did you improve?"),
        _turn("trn_candidate", "candidate", "I improved uptime."),
    ]
    llm = FakeLLMClient(
        Settings(OLLAMA_MODEL="base", ollama_model_evaluation="evaluation"),
        replies=[
            json.dumps(
                _coach_result("trn_candidate", include_backend_fields=True)
            )
        ],
    )
    output = EvaluationCoach(llm).evaluate(
        CoachContext(
            evaluation_id="evl_test",
            conversation_id="cnv_ev_test",
            scenario=_coach_scenario(),
            transcript=transcript,
        )
    )

    assert len(llm.calls) == 1
    assert llm.calls[0][0] is LLMProfile.EVALUATION
    assert llm.calls[0][2] is True
    schema = llm.json_schemas[0]
    assert schema is not None
    schema_properties = schema["properties"]
    assert isinstance(schema_properties, dict)
    criteria_schema = schema_properties["criteria"]
    assert isinstance(criteria_schema, dict)
    assert criteria_schema["minItems"] == len(CRITERIA)
    assert criteria_schema["maxItems"] == len(CRITERIA)
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    criterion = definitions["CriterionScoreIn"]
    assert isinstance(criterion, dict)
    properties = criterion["properties"]
    assert isinstance(properties, dict)
    evidence = properties["evidence_turn_ids"]
    assert isinstance(evidence, dict)
    items = evidence["items"]
    assert isinstance(items, dict)
    assert items["enum"] == ["trn_candidate"]
    assert not hasattr(output.result, "overall_score")
    assert output.result.criteria[0].score == 7
    assert all(
        description in llm.calls[0][1][0].content
        for descriptions in RUBRIC_DESCRIPTIONS.values()
        for description in descriptions
    )
    assert "speaking_time_ms" not in "\n".join(
        message.content for message in llm.calls[0][1]
    )


def test_coach_retries_invalid_evidence_once_and_then_fails() -> None:
    context = CoachContext(
        evaluation_id="evl_retry",
        conversation_id="cnv_ev_retry",
        scenario=_coach_scenario(),
        transcript=[_turn("trn_candidate", "candidate", "I led the project.")],
    )
    llm = FakeLLMClient(
        Settings(OLLAMA_MODEL="test-model"),
        replies=[
            json.dumps(_coach_result("trn_unknown")),
            json.dumps(_coach_result("trn_candidate")),
        ],
    )
    output = EvaluationCoach(llm).evaluate(context)
    assert len(llm.calls) == 2
    assert output.result.criteria[0].evidence_turn_ids == ["trn_candidate"]
    assert output.messages[2].role == "user"

    invalid_llm = FakeLLMClient(
        Settings(OLLAMA_MODEL="test-model"),
        replies=[
            json.dumps(_coach_result("trn_unknown")),
            json.dumps(_coach_result("trn_unknown")),
        ],
    )
    with pytest.raises(EvaluationParseError) as error:
        EvaluationCoach(invalid_llm).evaluate(context)
    assert len(invalid_llm.calls) == 2
    assert len(error.value.messages) == 4


def test_coach_retry_identifies_duplicate_and_missing_criteria() -> None:
    invalid = _coach_result("trn_candidate")
    criteria = invalid["criteria"]
    assert isinstance(criteria, list)
    criteria[-1] = dict(criteria[0])
    llm = FakeLLMClient(
        Settings(OLLAMA_MODEL="test-model"),
        replies=[
            json.dumps(invalid),
            json.dumps(_coach_result("trn_candidate")),
        ],
    )
    context = CoachContext(
        evaluation_id="evl_duplicate",
        conversation_id="cnv_ev_duplicate",
        scenario=_coach_scenario(),
        transcript=[_turn("trn_candidate", "candidate", "I led the project.")],
    )

    output = EvaluationCoach(llm).evaluate(context)

    assert output.result.criteria
    correction = output.messages[2].content
    assert "duplicated relevance" in correction
    assert "omitted language_accuracy" in correction


def test_evaluation_endpoints_persist_separate_coach_result_and_metrics(
    evaluation_env,
) -> None:
    client, factory, _, app, settings = evaluation_env
    session_id, candidate_id = _create_session(factory)
    assert candidate_id is not None
    llm = FakeLLMClient(
        settings,
        replies=[
            json.dumps(_coach_result(candidate_id, include_backend_fields=True))
        ],
    )
    app.dependency_overrides[get_llm_client] = lambda: llm

    started = client.post(
        f"/api/v1/sessions/{session_id}/evaluation",
        json={},
    )
    assert started.status_code == 202
    assert started.json()["status"] == "pending"
    assert started.json()["metrics"] is None
    assert started.json()["model"] is None
    assert len(llm.calls) == 1

    completed = client.get(f"/api/v1/sessions/{session_id}/evaluation")
    assert completed.status_code == 200
    payload = completed.json()
    assert payload["status"] == "completed"
    assert payload["attempt"] == 1
    assert payload["result"]["overall_score"] == 70
    assert payload["result"]["criteria"][0]["weight_percent"] == 25
    assert payload["result"]["criteria"][0]["weighted_points"] == 17.5
    assert payload["metrics"]["speaking_time_ms"] is None
    assert payload["metrics"]["avg_stt_confidence"] is None

    with factory() as db:
        evaluation = db.get(Evaluation, payload["id"])
        assert evaluation is not None
        assert evaluation.overall_score == 70
        assert evaluation.model == settings.model_for(LLMProfile.EVALUATION)
        assert evaluation.conversation_id is not None
        conversation = db.get(Conversation, evaluation.conversation_id)
        assert conversation is not None
        assert conversation.id.startswith("cnv_ev_")
        roleplay = db.scalar(
            select(Conversation).where(
                Conversation.session_id == session_id,
                Conversation.agent_role == "roleplay",
            )
        )
        assert roleplay is not None
        assert conversation.id != roleplay.id
        assert conversation.system_prompt != roleplay.system_prompt
        messages = db.scalars(
            select(Message).where(Message.conversation_id == conversation.id)
        ).all()
        assert all(roleplay.system_prompt not in message.content for message in messages)
        scores = db.scalars(
            select(EvaluationScore).where(
                EvaluationScore.evaluation_id == evaluation.id
            )
        ).all()
        assert len(scores) == 6
        assert sum(score.weight_percent for score in scores) == 100
        result_json = json.loads(evaluation.result_json or "{}")
        assert set(result_json) == {
            "task_outcome",
            "strengths",
            "improvements",
            "next_task",
        }
        assert "overall_score" not in result_json
        assert "weight_percent" not in result_json
        metrics_json = json.loads(evaluation.metrics_json or "{}")
        assert "rationale" not in metrics_json

    assert llm.calls[0][2] is True
    assert llm.calls[0][0] is LLMProfile.EVALUATION
    assert "speaking_time_ms" not in "\n".join(
        message.content for message in llm.calls[0][1]
    )


def test_invalid_coach_output_fails_with_metrics_and_retry_attempt(
    evaluation_env,
) -> None:
    client, factory, _, app, settings = evaluation_env
    session_id, candidate_id = _create_session(factory)
    assert candidate_id is not None
    invalid = json.dumps(_coach_result("trn_not_in_transcript"))
    first_llm = FakeLLMClient(settings, replies=[invalid, invalid])
    app.dependency_overrides[get_llm_client] = lambda: first_llm

    first = client.post(f"/api/v1/sessions/{session_id}/evaluation", json={})
    assert first.status_code == 202
    failed = client.get(f"/api/v1/sessions/{session_id}/evaluation")
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"]["code"] == "EVALUATION_PARSE_FAILED"
    assert failed.json()["metrics"] is not None
    assert failed.json()["result"] is None
    assert len(first_llm.calls) == 2

    second_llm = FakeLLMClient(
        settings,
        replies=[json.dumps(_coach_result(candidate_id))],
    )
    app.dependency_overrides[get_llm_client] = lambda: second_llm
    second = client.post(f"/api/v1/sessions/{session_id}/evaluation", json={})
    assert second.status_code == 202
    assert second.json()["attempt"] == 2
    completed = client.get(
        f"/api/v1/sessions/{session_id}/evaluation?attempt=2"
    )
    assert completed.json()["status"] == "completed"
    assert (
        completed.json()["coach_conversation_id"]
        != failed.json()["coach_conversation_id"]
    )


def test_evaluation_state_errors_and_missing_poll(evaluation_env) -> None:
    client, factory, _, app, settings = evaluation_env
    active_id, _ = _create_session(factory, status="active")
    not_ended = client.post(f"/api/v1/sessions/{active_id}/evaluation", json={})
    assert not_ended.status_code == 409
    assert not_ended.json()["error"]["code"] == "SESSION_NOT_ENDED"

    short_id, _ = _create_session(factory, candidate_turn=False)
    short = client.post(f"/api/v1/sessions/{short_id}/evaluation", json={})
    assert short.status_code == 409
    assert short.json()["error"]["code"] == "SESSION_TOO_SHORT"
    missing = client.get(f"/api/v1/sessions/{short_id}/evaluation")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVALUATION_NOT_FOUND"

    pending_id, candidate_id = _create_session(factory)
    assert candidate_id is not None
    llm = FakeLLMClient(
        settings,
        replies=[json.dumps(_coach_result(candidate_id))],
    )
    with factory() as db:
        service = EvaluationService(
            db=db,
            settings=settings,
            llm=llm,
            clock=app.state.evaluation_clock,
        )
        service.start_evaluation(pending_id)
    in_progress = client.post(
        f"/api/v1/sessions/{pending_id}/evaluation",
        json={},
    )
    assert in_progress.status_code == 409
    assert in_progress.json()["error"]["code"] == "EVALUATION_IN_PROGRESS"

def test_evaluation_start_lazily_abandons_idle_session(evaluation_env) -> None:
    client, factory, clock, _, _ = evaluation_env
    old_activity = (clock.current - timedelta(hours=2)).isoformat().replace(
        "+00:00", "Z"
    )
    session_id, _ = _create_session(
        factory,
        status="active",
        last_activity_at=old_activity,
    )

    response = client.post(f"/api/v1/sessions/{session_id}/evaluation", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_NOT_ENDED"
    assert response.json()["error"]["details"]["status"] == "abandoned"
    with factory() as db:
        session = db.get(InterviewSession, session_id)
        assert session is not None
        assert session.end_reason == "timeout"
        assert session.ended_at == old_activity


def test_evaluation_poll_lazily_abandons_without_refreshing_activity(
    evaluation_env,
) -> None:
    client, factory, clock, _, _ = evaluation_env
    old_activity = (clock.current - timedelta(hours=2)).isoformat().replace(
        "+00:00", "Z"
    )
    session_id, _ = _create_session(
        factory,
        status="active",
        last_activity_at=old_activity,
    )

    response = client.get(f"/api/v1/sessions/{session_id}/evaluation")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVALUATION_NOT_FOUND"
    with factory() as db:
        session = db.get(InterviewSession, session_id)
        assert session is not None
        assert session.status == "abandoned"
        assert session.last_activity_at == old_activity
