from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint("language = 'en'", name="ck_scenarios_language"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="ck_scenarios_difficulty"),
        CheckConstraint("max_turns BETWEEN 1 AND 30", name="ck_scenarios_max_turns"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','active','ended','abandoned')",
            name="ck_sessions_status",
        ),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN "
            "('user_ended','max_turns','agent_concluded','timeout')",
            name="ck_sessions_end_reason",
        ),
        CheckConstraint("in_flight IN (0,1)", name="ck_sessions_in_flight"),
        Index("idx_sessions_status_created", "status", text("created_at DESC")),
        Index("idx_sessions_scenario", "scenario_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    end_reason: Mapped[str | None] = mapped_column(String)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_flight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String)
    ended_at: Mapped[str | None] = mapped_column(String)
    last_activity_at: Mapped[str] = mapped_column(String, nullable=False)

    turns: Mapped[list[Turn]] = relationship(back_populates="session", cascade="all, delete-orphan")
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (
        CheckConstraint(
            "speaker IN ('interviewer','candidate')",
            name="ck_turns_speaker",
        ),
        CheckConstraint(
            "source IN ('typed','speech','generated')",
            name="ck_turns_source",
        ),
        UniqueConstraint("session_id", "idx", name="uq_turns_session_idx"),
        Index("idx_turns_session_idx", "session_id", "idx"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String, nullable=False)
    speaker_id: Mapped[str | None] = mapped_column(String)
    speaker_name: Mapped[str | None] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    speech_meta_json: Mapped[str | None] = mapped_column(Text)
    llm_meta_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    session: Mapped[Session] = relationship(back_populates="turns")
    messages: Mapped[list[Message]] = relationship(back_populates="turn")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "agent_role IN ('roleplay','evaluation')",
            name="ck_conversations_agent_role",
        ),
        Index(
            "uq_conv_roleplay_per_session",
            "session_id",
            unique=True,
            sqlite_where=text("agent_role='roleplay'"),
        ),
        Index("idx_conv_session_role", "session_id", "agent_role"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_role: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    session: Mapped[Session] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_messages_role"),
        UniqueConstraint("conversation_id", "seq", name="uq_messages_conversation_seq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_id: Mapped[str | None] = mapped_column(ForeignKey("turns.id", ondelete="SET NULL"))
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    turn: Mapped[Turn | None] = relationship(back_populates="messages")


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="ck_evaluations_status",
        ),
        CheckConstraint(
            "overall_score IS NULL OR overall_score BETWEEN 0 AND 100",
            name="ck_evaluations_overall_score",
        ),
        UniqueConstraint("session_id", "attempt", name="uq_evaluations_session_attempt"),
        Index("idx_eval_session", "session_id", text("attempt DESC")),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), unique=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False)
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    overall_score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String)

    session: Mapped[Session] = relationship(back_populates="evaluations")
    scores: Mapped[list[EvaluationScore]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationScore(Base):
    __tablename__ = "evaluation_scores"
    __table_args__ = (
        CheckConstraint(
            "criterion IN ('clarity','structure','relevance','conciseness',"
            "'composure','language_accuracy')",
            name="ck_evaluation_scores_criterion",
        ),
        CheckConstraint("score BETWEEN 0 AND 10", name="ck_evaluation_scores_score"),
        CheckConstraint(
            "weight_percent BETWEEN 0 AND 100",
            name="ck_evaluation_scores_weight_percent",
        ),
        UniqueConstraint("evaluation_id", "criterion", name="uq_evaluation_scores_criterion"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    criterion: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_turn_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    evaluation: Mapped[Evaluation] = relationship(back_populates="scores")
