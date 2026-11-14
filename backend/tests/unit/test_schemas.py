import pytest
from pydantic import ValidationError

from app.core.config import LLMProfile, Settings
from app.llm.fake import FakeLLMClient
from app.llm.interfaces import LLMMessage
from app.schemas.contracts import (
    CoachResult,
    ScenarioCriterion,
    SessionCreateIn,
    TurnCreateIn,
)


def test_request_schemas_reject_unknown_fields_and_invalid_metadata() -> None:
    with pytest.raises(ValidationError):
        SessionCreateIn(scenario_id="scn_test", unknown="not allowed")

    with pytest.raises(ValidationError, match="speech_meta is required"):
        TurnCreateIn(text="hello", source="speech", speech_meta=None)

    with pytest.raises(ValidationError, match="text must be trimmed"):
        TurnCreateIn(text=" hello ", source="typed", speech_meta=None)


def test_coach_result_drops_unknown_fields_and_requires_unique_criteria() -> None:
    output = {
        "summary": "A concise summary",
        "task_outcome": {"achieved": "yes", "explanation": "Task met"},
        "criteria": [
            {
                "criterion": item.value,
                "score": 7,
                "rationale": "Evidence supports this result",
                "evidence_turn_ids": ["trn_candidate"],
            }
            for item in ScenarioCriterion
        ],
        "strengths": [{"text": "Clear example", "evidence_turn_ids": ["trn_candidate"]}],
        "improvements": [{"text": "Add a result", "evidence_turn_ids": ["trn_candidate"]}],
        "next_task": {"title": "Try again", "instructions": "Add a measurable result"},
        "overall_score": 100,
        "weight_percent": 100,
    }

    result = CoachResult.model_validate(output)
    assert not hasattr(result, "overall_score")

    output["criteria"][0] = output["criteria"][1]
    with pytest.raises(ValidationError, match="each of the six criteria exactly once"):
        CoachResult.model_validate(output)


def test_fake_llm_records_calls_and_resolves_profile_models() -> None:
    client = FakeLLMClient(
        Settings(OLLAMA_MODEL="base", ollama_model_evaluation="evaluation"),
        replies=["scripted reply"],
    )
    result = client.chat(
        LLMProfile.EVALUATION,
        [LLMMessage(role="user", content="hello")],
        json_mode=True,
    )

    assert result.content == "scripted reply"
    assert result.model == "evaluation"
    assert client.calls[0][0] is LLMProfile.EVALUATION
    assert client.calls[0][2] is True
    with pytest.raises(RuntimeError, match="no scripted reply"):
        client.chat(LLMProfile.ROLEPLAY, [], json_mode=False)
