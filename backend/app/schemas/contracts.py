from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]
EvidenceIds = Annotated[list[str], Field(min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyRequest(ContractModel):
    pass


class ScenarioCriterion(StrEnum):
    RELEVANCE = "relevance"
    STRUCTURE = "structure"
    CLARITY = "clarity"
    COMPOSURE = "composure"
    CONCISENESS = "conciseness"
    LANGUAGE_ACCURACY = "language_accuracy"


class ScenarioPersona(ContractModel):
    name: NonEmptyText
    role: NonEmptyText
    style: NonEmptyText
    pressure_level: int = Field(ge=1, le=3)


class ScenarioTask(ContractModel):
    goal: NonEmptyText
    success_criteria: Annotated[list[NonEmptyText], Field(min_length=1, max_length=10)]


class ScenarioPanelPersona(ContractModel):
    id: NonEmptyText
    name: NonEmptyText
    role_title: NonEmptyText
    focus_area: NonEmptyText
    voice_gender: Literal["male", "female"]
    persona_prompt: NonEmptyText


class ScenarioDefinition(ContractModel):
    persona: ScenarioPersona
    task: ScenarioTask
    evaluation_focus: Annotated[list[ScenarioCriterion], Field(min_length=1, max_length=6)]
    personas: list[ScenarioPanelPersona] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_panel_personas(self) -> ScenarioDefinition:
        if self.personas and len(self.personas) != 2:
            raise ValueError("personas must contain exactly two panel agents")
        return self


class ScenarioSummary(ContractModel):
    id: str
    slug: str
    title: str
    description: str
    language: Literal["en"]
    difficulty: int = Field(ge=1, le=3)
    max_turns: int = Field(ge=1, le=30)
    estimated_minutes: int = Field(ge=1)
    personas: list[ScenarioPanelPersona] = Field(default_factory=list, max_length=2)


class ScenarioOut(ScenarioSummary):
    definition: ScenarioDefinition


class SessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    ENDED = "ended"
    ABANDONED = "abandoned"


class EndReason(StrEnum):
    USER_ENDED = "user_ended"
    MAX_TURNS = "max_turns"
    AGENT_CONCLUDED = "agent_concluded"
    TIMEOUT = "timeout"


class SessionOut(ContractModel):
    id: str
    scenario_id: str
    status: SessionStatus
    end_reason: EndReason | None
    turn_count: int = Field(ge=0)
    max_turns: int = Field(ge=1, le=30)
    roleplay_conversation_id: str
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class SessionCreateIn(ContractModel):
    scenario_id: NonEmptyText


class SessionListOut(ContractModel):
    items: list[SessionOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class SpeechMeta(ContractModel):
    duration_ms: int = Field(ge=0)
    avg_confidence: float | None = Field(default=None, ge=0, le=1)
    word_count: int = Field(ge=0)
    language: Literal["en"]


class TurnSource(StrEnum):
    TYPED = "typed"
    SPEECH = "speech"
    GENERATED = "generated"


class TurnOut(ContractModel):
    id: str
    session_id: str
    idx: int = Field(ge=0)
    speaker: Literal["interviewer", "candidate"]
    text: str
    source: TurnSource
    speech_meta: SpeechMeta | None
    speaker_id: str | None = None
    speaker_name: str | None = None
    created_at: datetime


class TurnCreateIn(ContractModel):
    text: str = Field(min_length=1, max_length=2000)
    source: Literal["typed", "speech"]
    speech_meta: SpeechMeta | None

    @model_validator(mode="after")
    def validate_source_metadata(self) -> TurnCreateIn:
        if (self.source == "speech") != (self.speech_meta is not None):
            raise ValueError("speech_meta is required only when source is 'speech'")
        if self.text != self.text.strip():
            raise ValueError("text must be trimmed")
        return self


class ScenarioListOut(ContractModel):
    items: list[ScenarioSummary]
    total: int = Field(ge=0)


class StartSessionOut(ContractModel):
    session: SessionOut
    interviewer_turn: TurnOut
    interviewer_turns: list[TurnOut] = Field(default_factory=list)


class TurnSubmitOut(ContractModel):
    candidate_turn: TurnOut
    interviewer_turn: TurnOut
    session: SessionOut
    interviewer_turns: list[TurnOut] = Field(default_factory=list)


class TurnListOut(ContractModel):
    session_id: str
    items: list[TurnOut]


class HealthComponent(ContractModel):
    status: Literal["ok", "loading", "unavailable"]
    detail: str | None = None


class LLMHealthComponent(HealthComponent):
    models: dict[str, str]


class STTHealthComponent(ContractModel):
    status: Literal["ready", "loading", "unavailable"]
    model: str
    detail: str | None = None


class HealthComponents(ContractModel):
    database: HealthComponent
    llm: LLMHealthComponent
    stt: STTHealthComponent


class HealthOut(ContractModel):
    status: Literal["ok", "degraded"]
    version: str
    contract_version: str
    components: HealthComponents


class SpeechStatusOut(ContractModel):
    stt: STTStatus
    tts: TTSStatus
    limits: AudioLimits


class STTStatus(ContractModel):
    status: Literal["ready", "loading", "unavailable"]
    engine: str
    model: str
    device: str
    language: Literal["en"]


class TTSStatus(ContractModel):
    mode: Literal["browser"]
    server_side: Literal[False]


class AudioLimits(ContractModel):
    max_audio_seconds: int = Field(ge=1)
    max_audio_mb: int = Field(ge=1)
    accepted_types: list[str]


class SpeechSegment(ContractModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(ge=0, le=1)


class TranscriptionOut(ContractModel):
    text: str
    language: Literal["en"]
    duration_ms: int = Field(ge=0)
    avg_confidence: float | None = Field(ge=0, le=1)
    word_count: int = Field(ge=0)
    processing_ms: int = Field(ge=0)
    segments: list[SpeechSegment]


class TaskOutcome(ContractModel):
    achieved: Literal["yes", "partially", "no"]
    explanation: NonEmptyText


class CriterionScoreIn(ContractModel):
    criterion: ScenarioCriterion
    score: int = Field(ge=0, le=10)
    rationale: str = Field(max_length=300)
    evidence_turn_ids: EvidenceIds


class Strength(ContractModel):
    text: NonEmptyText
    evidence_turn_ids: EvidenceIds


class Improvement(ContractModel):
    text: NonEmptyText
    evidence_turn_ids: EvidenceIds
    example_rewrite: str | None = None


class NextTask(ContractModel):
    title: NonEmptyText
    instructions: NonEmptyText


class CoachResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(max_length=400)
    task_outcome: TaskOutcome
    criteria: Annotated[list[CriterionScoreIn], Field(min_length=6, max_length=6)]
    strengths: Annotated[list[Strength], Field(min_length=1, max_length=3)]
    improvements: Annotated[list[Improvement], Field(min_length=1, max_length=3)]
    next_task: NextTask

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> CoachResult:
        criterion_keys = [criterion.criterion for criterion in self.criteria]
        if len(set(criterion_keys)) != len(ScenarioCriterion):
            raise ValueError("criteria must contain each of the six criteria exactly once")
        return self


class CriterionScore(ContractModel):
    criterion: ScenarioCriterion
    score: int = Field(ge=0, le=10)
    weight_percent: int = Field(ge=0, le=100)
    weighted_points: float = Field(ge=0, le=100)
    rationale: str = Field(max_length=300)
    evidence_turn_ids: EvidenceIds


class DeliveryMetrics(ContractModel):
    candidate_turns: int = Field(ge=0)
    total_words: int = Field(ge=0)
    avg_words_per_turn: float = Field(ge=0)
    speaking_time_ms: int | None = Field(ge=0)
    words_per_minute: float | None = Field(ge=0)
    filler_words: FillerWords
    avg_stt_confidence: float | None = Field(ge=0, le=1)


class FillerWords(ContractModel):
    total: int = Field(ge=0)
    per_100_words: float = Field(ge=0)
    breakdown: dict[str, int]


class EvaluationResult(ContractModel):
    overall_score: int = Field(ge=0, le=100)
    summary: str = Field(max_length=400)
    task_outcome: TaskOutcome
    criteria: Annotated[list[CriterionScore], Field(min_length=6, max_length=6)]
    strengths: Annotated[list[Strength], Field(min_length=1, max_length=3)]
    improvements: Annotated[list[Improvement], Field(min_length=1, max_length=3)]
    next_task: NextTask


class EvaluationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationError(ContractModel):
    code: str
    message: str


class EvaluationOut(ContractModel):
    id: str
    session_id: str
    attempt: int = Field(ge=1)
    status: EvaluationStatus
    rubric_version: str
    coach_conversation_id: str | None
    model: str | None
    metrics: DeliveryMetrics | None
    result: EvaluationResult | None
    error: EvaluationError | None
    created_at: datetime
    completed_at: datetime | None
