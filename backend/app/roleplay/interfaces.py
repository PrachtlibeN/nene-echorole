from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.llm.interfaces import LLMMessage
from app.schemas.contracts import ScenarioOut


@dataclass(frozen=True)
class RoleplayContext:
    session_id: str
    conversation_id: str
    scenario: ScenarioOut
    history: list[LLMMessage]
    turn_index: int
    max_turns: int


@dataclass(frozen=True)
class LLMMeta:
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class RoleplayReply:
    text: str
    should_end: bool
    llm: LLMMeta
    speaker_id: str | None = None
    speaker_name: str | None = None


class RoleplayAgent(Protocol):
    def open_session(self, ctx: RoleplayContext) -> RoleplayReply | list[RoleplayReply]: ...

    def respond(
        self, ctx: RoleplayContext, candidate_text: str
    ) -> RoleplayReply | list[RoleplayReply]: ...


class StubRoleplayAgent:
    def open_session(self, ctx: RoleplayContext) -> RoleplayReply:
        return RoleplayReply(
            text="Tell me about a project you led under a tight deadline.",
            should_end=False,
            llm=LLMMeta(model="", latency_ms=0),
        )

    def respond(self, ctx: RoleplayContext, candidate_text: str) -> RoleplayReply:
        return RoleplayReply(
            text="What was the measurable outcome of that work?",
            should_end=ctx.turn_index >= ctx.max_turns,
            llm=LLMMeta(model="", latency_ms=0),
        )
