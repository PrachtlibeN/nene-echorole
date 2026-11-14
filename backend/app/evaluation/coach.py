from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.core.config import LLMProfile
from app.evaluation.interfaces import CoachContext, CoachOutput
from app.evaluation.prompts import build_coach_system_prompt, build_coach_user_prompt
from app.evaluation.rubric import CRITERIA
from app.llm.interfaces import LLMClient, LLMMessage
from app.schemas.contracts import CoachResult

LOGGER = logging.getLogger(__name__)
_TOP_LEVEL_FIELDS = {
    "summary",
    "task_outcome",
    "criteria",
    "strengths",
    "improvements",
    "next_task",
}
_NESTED_FIELDS: dict[str, set[str]] = {
    "task_outcome": {"achieved", "explanation"},
    "criteria": {"criterion", "score", "rationale", "evidence_turn_ids"},
    "strengths": {"text", "evidence_turn_ids"},
    "improvements": {"text", "evidence_turn_ids", "example_rewrite"},
    "next_task": {"title", "instructions"},
}


class EvaluationParseError(ValueError):
    def __init__(self, messages: list[LLMMessage]) -> None:
        super().__init__("The coach returned invalid output after one retry.")
        self.messages = messages


class EvaluationCoach:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def evaluate(self, ctx: CoachContext) -> CoachOutput:
        user_message = LLMMessage(
            role="user",
            content=build_coach_user_prompt(ctx.scenario, ctx.transcript),
        )
        llm_messages = [
            LLMMessage(role="system", content=build_coach_system_prompt()),
            user_message,
        ]
        history = [user_message]
        candidate_ids = {
            turn.id for turn in ctx.transcript if turn.speaker == "candidate"
        }
        total_latency_ms = 0
        model = self.llm.model_for(LLMProfile.EVALUATION)

        for attempt in range(2):
            response = self.llm.chat(
                LLMProfile.EVALUATION,
                llm_messages,
                json_mode=True,
                json_schema=self._schema_for_candidate_ids(candidate_ids),
            )
            total_latency_ms += response.latency_ms
            model = response.model
            assistant_message = LLMMessage(
                role="assistant",
                content=response.content,
            )
            llm_messages.append(assistant_message)
            history.append(assistant_message)
            raw: Any = None
            try:
                raw = json.loads(response.content)
                normalized = self._discard_extra_fields(raw)
                result = CoachResult.model_validate(normalized)
                self._validate_integer_scores(raw)
                self._validate_evidence(result, candidate_ids)
            except (TypeError, ValueError):
                if attempt == 1:
                    raise EvaluationParseError(history) from None
                correction = LLMMessage(
                    role="user",
                    content=(
                        f"Validation issue: {self._criterion_feedback(raw)} "
                        "Correct the schema errors in your previous answer. Return "
                        "only JSON with `task_outcome` as an object, `criteria` as "
                        "exactly these six objects, in order: "
                        f"{', '.join(criterion.value for criterion in CRITERIA)}. "
                        "Use each criterion exactly once. `strengths` and "
                        "`improvements` must be arrays of objects; `next_task` "
                        "must be an object. Each criterion needs an integer `score` "
                        "from 0 to 10, `rationale`, and `evidence_turn_ids`. Use only "
                        f"these candidate turn IDs: {', '.join(sorted(candidate_ids))}. "
                        "Do not cite interviewer turns or add fields."
                    ),
                )
                llm_messages.append(correction)
                history.append(correction)
                continue
            return CoachOutput(
                result=result,
                model=model,
                latency_ms=total_latency_ms,
                messages=history,
            )
        raise RuntimeError("Coach retry loop exited without a result")

    @staticmethod
    def _schema_for_candidate_ids(candidate_ids: set[str]) -> dict[str, Any]:
        schema = CoachResult.model_json_schema()
        definitions = schema.get("$defs")
        if isinstance(definitions, dict):
            for definition in definitions.values():
                if not isinstance(definition, dict):
                    continue
                properties = definition.get("properties")
                if not isinstance(properties, dict):
                    continue
                evidence = properties.get("evidence_turn_ids")
                if not isinstance(evidence, dict):
                    continue
                items = evidence.get("items")
                if isinstance(items, dict):
                    items["enum"] = sorted(candidate_ids)
        return schema

    @staticmethod
    def _criterion_feedback(raw: Any) -> str:
        if not isinstance(raw, Mapping):
            return "The previous answer was not a JSON object."
        criteria = raw.get("criteria")
        if not isinstance(criteria, list):
            return "The previous answer did not contain a criteria array."
        names = [
            item["criterion"]
            for item in criteria
            if isinstance(item, Mapping) and isinstance(item.get("criterion"), str)
        ]
        counts = Counter(names)
        missing = [
            criterion.value for criterion in CRITERIA if not counts[criterion.value]
        ]
        duplicated = [name for name, count in counts.items() if count > 1]
        if missing or duplicated:
            return (
                f"The criteria list duplicated {', '.join(duplicated) or 'none'} "
                f"and omitted {', '.join(missing) or 'none'}."
            )
        return "Use each required criterion exactly once."

    @classmethod
    def _discard_extra_fields(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        extra_fields = set(raw) - _TOP_LEVEL_FIELDS
        cls._log_discarded(extra_fields)
        normalized: dict[str, Any] = {}
        for key in _TOP_LEVEL_FIELDS & set(raw):
            value = raw[key]
            nested_fields = _NESTED_FIELDS.get(key)
            if nested_fields is None:
                normalized[key] = value
            elif key in {"criteria", "strengths", "improvements"} and isinstance(
                value, list
            ):
                normalized[key] = [
                    cls._clean_mapping(item, nested_fields) for item in value
                ]
            else:
                normalized[key] = cls._clean_mapping(value, nested_fields)
        return normalized

    @classmethod
    def _clean_mapping(cls, value: Any, allowed: set[str]) -> Any:
        if not isinstance(value, dict):
            return value
        cls._log_discarded(set(value) - allowed)
        return {key: item for key, item in value.items() if key in allowed}

    @staticmethod
    def _log_discarded(fields: set[str]) -> None:
        if fields:
            LOGGER.warning("Discarded unrecognized CoachResult fields: %s", sorted(fields))

    @staticmethod
    def _validate_integer_scores(raw: Any) -> None:
        if not isinstance(raw, Mapping):
            return
        criteria = raw.get("criteria")
        if not isinstance(criteria, list):
            return
        for item in criteria:
            if isinstance(item, Mapping) and "score" in item:
                score = item["score"]
                if type(score) is not int or not 0 <= score <= 10:
                    raise ValueError("Criterion scores must be integers from 0 to 10")

    @staticmethod
    def _validate_evidence(
        result: CoachResult,
        candidate_ids: set[str],
    ) -> None:
        evidence = [
            *(item.evidence_turn_ids for item in result.criteria),
            *(item.evidence_turn_ids for item in result.strengths),
            *(item.evidence_turn_ids for item in result.improvements),
        ]
        if any(
            turn_id not in candidate_ids
            for ids in evidence
            for turn_id in ids
        ):
            raise ValueError("Evidence IDs must refer to candidate turns in this transcript")
