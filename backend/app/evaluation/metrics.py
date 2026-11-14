from __future__ import annotations

import re
from collections.abc import Sequence

from app.schemas.contracts import DeliveryMetrics, TurnOut

_WORD_PATTERN = re.compile(r"\b[\w]+(?:['’][\w]+)?\b", re.UNICODE)
_FILLER_KEYS = ("um", "uh", "like", "you know")


def _words(text: str) -> list[str]:
    return [match.group(0).casefold() for match in _WORD_PATTERN.finditer(text)]


def _count_fillers(words: list[str]) -> dict[str, int]:
    counts = dict.fromkeys(_FILLER_KEYS, 0)
    index = 0
    while index < len(words):
        if words[index : index + 2] == ["you", "know"]:
            counts["you know"] += 1
            index += 2
            continue
        if words[index] in {"um", "uh", "like"}:
            counts[words[index]] += 1
        index += 1
    return counts


def compute_delivery_metrics(transcript: Sequence[TurnOut]) -> DeliveryMetrics:
    candidates = [turn for turn in transcript if turn.speaker == "candidate"]
    tokenized = [_words(turn.text) for turn in candidates]
    total_words = sum(len(words) for words in tokenized)
    filler_breakdown = dict.fromkeys(_FILLER_KEYS, 0)
    for words in tokenized:
        for filler, count in _count_fillers(words).items():
            filler_breakdown[filler] += count
    filler_total = sum(filler_breakdown.values())

    speech_turns = [turn for turn in candidates if turn.source.value == "speech"]
    if speech_turns:
        speaking_time_ms = sum(
            turn.speech_meta.duration_ms
            for turn in speech_turns
            if turn.speech_meta is not None
        )
        speech_word_count = sum(len(_words(turn.text)) for turn in speech_turns)
        words_per_minute = (
            round(speech_word_count * 60_000 / speaking_time_ms, 1)
            if speaking_time_ms > 0
            else None
        )
        confidences = [
            turn.speech_meta.avg_confidence
            for turn in speech_turns
            if turn.speech_meta is not None
            and turn.speech_meta.avg_confidence is not None
        ]
        avg_stt_confidence = (
            round(sum(confidences) / len(confidences), 3) if confidences else None
        )
    else:
        speaking_time_ms = None
        words_per_minute = None
        avg_stt_confidence = None

    return DeliveryMetrics(
        candidate_turns=len(candidates),
        total_words=total_words,
        avg_words_per_turn=round(total_words / len(candidates), 1) if candidates else 0.0,
        speaking_time_ms=speaking_time_ms,
        words_per_minute=words_per_minute,
        filler_words={
            "total": filler_total,
            "per_100_words": round(filler_total * 100 / total_words, 1)
            if total_words
            else 0.0,
            "breakdown": filler_breakdown,
        },
        avg_stt_confidence=avg_stt_confidence,
    )
