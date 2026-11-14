from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.config import LLMProfile


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    profile: LLMProfile
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


@dataclass(frozen=True)
class LLMHealth:
    status: Literal["ok", "unavailable"]
    models: dict[str, str]
    detail: str | None = None


class LLMClient(Protocol):
    def model_for(self, profile: LLMProfile) -> str: ...

    def health(self) -> LLMHealth: ...

    def chat(
        self,
        profile: LLMProfile,
        messages: list[LLMMessage],
        *,
        json_mode: bool = False,
        json_schema: dict[str, object] | None = None,
    ) -> LLMResult: ...
