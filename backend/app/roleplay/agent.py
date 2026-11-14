from __future__ import annotations

import re

from app.core.config import LLMProfile, Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.llm.interfaces import LLMClient, LLMMessage
from app.roleplay.interfaces import LLMMeta, RoleplayContext, RoleplayReply
from app.roleplay.prompts import build_roleplay_prompt
from app.schemas.contracts import ScenarioPanelPersona

_END_MARKER = re.compile(r"\[END\]", re.IGNORECASE)


class RoleplayAgent:
    def __init__(self, llm: LLMClient, settings: Settings | None = None) -> None:
        self._llm = llm
        self._settings = settings or get_settings()

    def open_session(self, ctx: RoleplayContext) -> RoleplayReply | list[RoleplayReply]:
        personas = ctx.scenario.definition.personas
        if not personas:
            return self._generate(ctx, None, [], None, None)

        first = self._generate(
            ctx,
            personas[0],
            [],
            None,
            "Introduce the interview and briefly frame the situation. Do not ask the "
            "candidate a question; the other panel member will ask the first question.",
        )
        if first.should_end:
            return [first]
        history = [
            LLMMessage(
                role="assistant",
                content=self._labeled_text(first, personas[0].role_title),
            )
        ]
        second = self._generate(
            ctx,
            personas[1],
            history,
            None,
            "Briefly acknowledge the other panel member's opening, then ask the "
            "candidate one focused first question. Do not repeat the opening.",
        )
        return [first, second]

    def respond(
        self, ctx: RoleplayContext, candidate_text: str
    ) -> RoleplayReply | list[RoleplayReply]:
        personas = ctx.scenario.definition.personas
        if not personas:
            return self._generate(ctx, None, ctx.history, candidate_text, None)

        if ctx.turn_index % 2:
            first = self._generate(
                ctx,
                personas[0],
                ctx.history,
                candidate_text,
                "Briefly assess the candidate's answer from your focus area and add one "
                "specific observation or challenge. Do not ask a question; the other "
                "panel member will ask the follow-up.",
            )
            if first.should_end:
                return [first]
            history = [
                *ctx.history,
                LLMMessage(role="user", content=candidate_text),
                LLMMessage(
                    role="assistant",
                    content=self._labeled_text(first, personas[0].role_title),
                ),
            ]
            second = self._generate(
                ctx,
                personas[1],
                history,
                None,
                "Build on the previous panel member's observation without repeating "
                "it, then ask the candidate one probing follow-up question.",
            )
            return [first, second]

        persona_index = ((ctx.turn_index // 2) - 1) % 2
        return self._generate(
            ctx,
            personas[persona_index],
            ctx.history,
            candidate_text,
            "Continue the interview from your focus area. Ask at most one concise "
            "follow-up question and do not repeat earlier panel questions.",
        )

    def _generate(
        self,
        ctx: RoleplayContext,
        persona: ScenarioPanelPersona | None,
        history: list[LLMMessage],
        candidate_text: str | None,
        instruction: str | None,
    ) -> RoleplayReply:
        history_limit = self._settings.roleplay_history_turns * 2
        recent_history = history[-history_limit:]
        messages = [
            LLMMessage(
                role="system",
                content=build_roleplay_prompt(
                    ctx.scenario,
                    persona=persona,
                    instruction=instruction,
                ),
            ),
            *recent_history,
        ]
        if candidate_text is not None:
            messages.append(LLMMessage(role="user", content=candidate_text))
        result = self._llm.chat(LLMProfile.ROLEPLAY, messages)
        return self._reply(
            result.content,
            result.model,
            result.latency_ms,
            result.prompt_tokens,
            result.completion_tokens,
            persona,
        )

    @staticmethod
    def _labeled_text(reply: RoleplayReply, role_title: str) -> str:
        return f"[{reply.speaker_name} - {role_title}]: {reply.text}"

    @staticmethod
    def _reply(
        content: str,
        model: str,
        latency_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        persona: ScenarioPanelPersona | None = None,
    ) -> RoleplayReply:
        should_end = _END_MARKER.search(content) is not None
        text = " ".join(_END_MARKER.sub(" ", content).split())
        text = " ".join(text.split()[:60])
        if not text:
            raise AppError(
                ErrorCode.LLM_BAD_OUTPUT,
                "Roleplay model returned an empty reply.",
                502,
            )
        return RoleplayReply(
            text=text,
            should_end=should_end,
            llm=LLMMeta(
                model=model,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            speaker_id=persona.id if persona is not None else None,
            speaker_name=persona.name if persona is not None else None,
        )
