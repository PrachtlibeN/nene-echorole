from collections import deque

from app.core.config import LLMProfile, Settings
from app.llm.interfaces import LLMHealth, LLMMessage, LLMResult


class FakeLLMClient:
    def __init__(
        self,
        settings: Settings,
        replies: list[str] | None = None,
    ) -> None:
        self.settings = settings
        self.replies = deque(replies or [])
        self.calls: list[tuple[LLMProfile, list[LLMMessage], bool]] = []
        self.json_schemas: list[dict[str, object] | None] = []

    def model_for(self, profile: LLMProfile) -> str:
        return self.settings.model_for(profile)

    def health(self) -> LLMHealth:
        return LLMHealth(
            status="ok",
            models={
                "roleplay": self.model_for(LLMProfile.ROLEPLAY),
                "evaluation": self.model_for(LLMProfile.EVALUATION),
            },
        )

    def chat(
        self,
        profile: LLMProfile,
        messages: list[LLMMessage],
        *,
        json_mode: bool = False,
        json_schema: dict[str, object] | None = None,
    ) -> LLMResult:
        self.calls.append((profile, list(messages), json_mode))
        self.json_schemas.append(json_schema)
        if not self.replies:
            raise RuntimeError("FakeLLMClient has no scripted reply for this call")
        content = self.replies.popleft()
        return LLMResult(
            content=content,
            model=self.model_for(profile),
            profile=profile,
            prompt_tokens=None,
            completion_tokens=None,
            latency_ms=0,
        )
