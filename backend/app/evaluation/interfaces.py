from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.llm.interfaces import LLMMessage
from app.schemas.contracts import (
    CoachResult,
    ScenarioCriterion,
    ScenarioOut,
    ScenarioPanelPersona,
    SessionOut,
    TurnOut,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Evaluation clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class CoachScenario:
    task_goal: str
    success_criteria: list[str]
    evaluation_focus: list[ScenarioCriterion]
    personas: list[ScenarioPanelPersona] = field(default_factory=list)


def to_coach_scenario(scenario: ScenarioOut | CoachScenario) -> CoachScenario:
    if isinstance(scenario, CoachScenario):
        return scenario
    return CoachScenario(
        task_goal=scenario.definition.task.goal,
        success_criteria=scenario.definition.task.success_criteria,
        evaluation_focus=scenario.definition.evaluation_focus,
        personas=scenario.definition.personas,
    )


@dataclass(frozen=True)
class Transcript:
    scenario: ScenarioOut | CoachScenario
    turns: list[TurnOut]
    session: SessionOut | None = None


class SimulationService(Protocol):
    def get_transcript(self, session_id: str) -> Transcript: ...
    def assert_session_ended(self, session_id: str) -> None: ...


@dataclass(frozen=True)
class CoachContext:
    evaluation_id: str
    conversation_id: str
    scenario: CoachScenario
    transcript: list[TurnOut]


@dataclass(frozen=True)
class CoachOutput:
    result: CoachResult
    model: str
    latency_ms: int
    messages: list[LLMMessage]


class EvaluationCoach(Protocol):
    def evaluate(self, ctx: CoachContext) -> CoachOutput: ...
