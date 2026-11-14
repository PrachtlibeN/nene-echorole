from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import statistics
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

os.environ.setdefault("HF_HUB_OFFLINE", "1")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# App imports follow the path bootstrap and offline-mode setup above.
from app.core.config import Settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.evaluation.coach import EvaluationCoach, EvaluationParseError  # noqa: E402
from app.evaluation.interfaces import CoachContext, to_coach_scenario  # noqa: E402
from app.evaluation.rubric import compute_overall_score  # noqa: E402
from app.llm.client import OllamaClient  # noqa: E402
from app.roleplay.agent import RoleplayAgent  # noqa: E402
from app.roleplay.interfaces import RoleplayContext  # noqa: E402
from app.schemas.contracts import (  # noqa: E402
    ScenarioDefinition,
    ScenarioOut,
    TurnOut,
    TurnSource,
)
from app.speech.stt import FasterWhisperEngine  # noqa: E402

_CANDIDATE_ANSWERS = {
    "strong": (
        "I led a six-person migration that was two weeks behind schedule. I split the "
        "work into daily milestones, resolved an API ownership conflict, and coordinated "
        "a staged rollout. We launched on time and reduced p95 latency by 32 percent."
    ),
    "average": (
        "I worked on a migration with my team. We had some challenges, communicated, "
        "and finished the work. It went well and people were happy with the result."
    ),
    "weak": (
        "I do not have a specific example. The team usually figures things out, and "
        "I just try to help. I cannot remember the result."
    ),
}
_MARKDOWN_RE = re.compile(r"(^|\n)\s*(?:#{1,6}\s|[-*+]\s)|```|(?:\*\*|__|`)")
_STAGE_DIRECTION_RE = re.compile(r"\[[^\]]+\]|\*[^*]+\*")


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _available_memory_mb() -> float | None:
    if os.name != "nt":
        return None
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullAvailPhys / (1024 * 1024)


class _MemoryMonitor:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.lowest_available_mb: float | None = None

    def __enter__(self) -> _MemoryMonitor:
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._sample()

    def _sample(self) -> None:
        available = _available_memory_mb()
        if available is not None and (
            self.lowest_available_mb is None or available < self.lowest_available_mb
        ):
            self.lowest_available_mb = available

    def _run(self) -> None:
        while not self._stop.wait(1):
            self._sample()


def _scenario_fixtures() -> list[ScenarioOut]:
    scenarios: list[ScenarioOut] = []
    scenario_dir = BACKEND_ROOT / "app" / "simulation" / "scenarios"
    for path in sorted(scenario_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append(
            ScenarioOut(
                id=f"scn_benchmark_{raw['slug']}",
                slug=raw["slug"],
                title=raw["title"],
                description=raw["description"],
                language=raw["language"],
                difficulty=raw["difficulty"],
                max_turns=raw["max_turns"],
                estimated_minutes=raw["estimated_minutes"],
                definition=ScenarioDefinition.model_validate(raw["definition"]),
            )
        )
    if len(scenarios) != 3:
        raise RuntimeError(f"Expected 3 scenario fixtures; found {len(scenarios)}.")
    return scenarios


def _transcript_fixtures() -> dict[str, list[TurnOut]]:
    dialogues = {
        "strong": [
            ("interviewer", "Tell me about a difficult project and your contribution."),
            (
                "candidate",
                "I led a six-person migration that was two weeks behind. I created "
                "daily milestones, resolved an ownership conflict, and coordinated a "
                "staged rollout. We launched on time and reduced p95 latency by 32 percent.",
            ),
            ("interviewer", "How did you know your approach worked?"),
            (
                "candidate",
                "I compared the six-week baseline with production metrics after rollout. "
                "Latency fell from 410 to 279 milliseconds, and error rates stayed flat.",
            ),
        ],
        "average": [
            ("interviewer", "Tell me about a difficult project and your contribution."),
            (
                "candidate",
                "I worked on a migration with my team. There were some problems, but we "
                "communicated and got it done. It went well and everyone was pleased.",
            ),
            ("interviewer", "What did you personally change?"),
            (
                "candidate",
                "I helped where I could and attended the meetings. I think the process "
                "was better by the end.",
            ),
        ],
        "weak": [
            ("interviewer", "Tell me about a difficult project and your contribution."),
            (
                "candidate",
                "I do not have a specific example. The team usually figures things out, "
                "and I just try to help. I cannot remember the result.",
            ),
            ("interviewer", "What was your individual role?"),
            (
                "candidate",
                "I am not sure. I mostly waited for tasks and do not know what changed.",
            ),
        ],
    }
    created_at = datetime.now(UTC)
    return {
        label: [
            TurnOut(
                id=f"trn_benchmark_{label}_{index}",
                session_id=f"ses_benchmark_{label}",
                idx=index,
                speaker=speaker,
                text=text,
                source=TurnSource.GENERATED
                if speaker == "interviewer"
                else TurnSource.TYPED,
                speech_meta=None,
                created_at=created_at,
            )
            for index, (speaker, text) in enumerate(turns)
        ]
        for label, turns in dialogues.items()
    }


def _p95(samples: list[int]) -> int | None:
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _ollama_loaded_models(base_url: str) -> list[dict[str, object]] | None:
    response = httpx.get(f"{base_url.rstrip('/')}/api/ps", timeout=5)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    return [
        {
            "name": item.get("name"),
            "size_bytes": item.get("size"),
            "size_vram_bytes": item.get("size_vram"),
            "processor": item.get("details", {}).get("format")
            if isinstance(item.get("details"), dict)
            else None,
        }
        for item in models
        if isinstance(item, dict)
    ]


def _benchmark_whisper(models: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model in models:
        started = time.perf_counter()
        engine = FasterWhisperEngine(
            model_name=model,
            device="cpu",
            compute_type="int8",
            warmup=True,
        )
        deadline = started + 300
        status = engine.status()
        while status["status"] == "loading" and time.perf_counter() < deadline:
            time.sleep(0.2)
            status = engine.status()
        results.append(
            {
                "model": model,
                "status": status["status"],
                "load_and_warmup_ms": round((time.perf_counter() - started) * 1000),
                "detail": status.get("detail"),
                "transcription_latency_ms": None,
                "wer_percent": None,
                "audio_fixture_note": "No labeled audio fixtures are present in the repository.",
            }
        )
    return results


def _benchmark_model(
    model: str,
    runs: int,
    whisper_models: list[str],
    behavior_review_passed: bool,
) -> dict[str, Any]:
    settings = Settings(
        ollama_model=model,
        ollama_model_roleplay=model,
        ollama_model_evaluation=model,
    )
    llm = OllamaClient(settings)
    with _MemoryMonitor() as memory:
        try:
            health = llm.health()
            if health.status != "ok":
                raise RuntimeError(health.detail or "Ollama model health check failed.")

            scenarios = _scenario_fixtures()
            transcripts = _transcript_fixtures()
            roleplay_samples: list[dict[str, Any]] = []
            coach_samples: list[dict[str, Any]] = []
            roleplay_latencies: list[int] = []
            evaluation_latencies: list[int] = []
            scores: dict[str, list[int]] = {label: [] for label in transcripts}

            for run in range(runs):
                for scenario in scenarios:
                    for answer_type, answer in _CANDIDATE_ANSWERS.items():
                        context = RoleplayContext(
                            session_id=f"ses_benchmark_{run}_{scenario.slug}_{answer_type}",
                            conversation_id=f"cnv_benchmark_{run}_{scenario.slug}",
                            scenario=scenario,
                            history=[],
                            turn_index=0,
                            max_turns=scenario.max_turns,
                        )
                        try:
                            reply = RoleplayAgent(llm, settings).respond(context, answer)
                        except AppError as exc:
                            roleplay_samples.append(
                                {
                                    "run": run + 1,
                                    "scenario": scenario.slug,
                                    "answer_type": answer_type,
                                    "error": exc.code.value,
                                }
                            )
                            continue

                        latency = reply.llm.latency_ms
                        roleplay_latencies.append(latency)
                        roleplay_samples.append(
                            {
                                "run": run + 1,
                                "scenario": scenario.slug,
                                "answer_type": answer_type,
                                "latency_ms": latency,
                                "word_count": len(reply.text.split()),
                                "markdown": bool(_MARKDOWN_RE.search(reply.text)),
                                "stage_directions": bool(
                                    _STAGE_DIRECTION_RE.search(reply.text)
                                ),
                                "question_marks": reply.text.count("?"),
                            }
                        )

                for label, transcript in transcripts.items():
                    context = CoachContext(
                        evaluation_id=f"evl_benchmark_{run}_{label}",
                        conversation_id=f"cnv_ev_benchmark_{run}_{label}",
                        scenario=to_coach_scenario(scenarios[0]),
                        transcript=transcript,
                    )
                    evaluation_started = time.perf_counter()
                    try:
                        output = EvaluationCoach(llm).evaluate(context)
                    except EvaluationParseError as exc:
                        latency_ms = round((time.perf_counter() - evaluation_started) * 1000)
                        evaluation_latencies.append(latency_ms)
                        assistant_outputs = [
                            message.content
                            for message in exc.messages
                            if message.role == "assistant"
                        ]
                        coach_samples.append(
                            {
                                "run": run + 1,
                                "fixture": label,
                                "valid": False,
                                "error": "EVALUATION_PARSE_FAILED",
                                "latency_ms": latency_ms,
                                "last_output": assistant_outputs[-1][:500]
                                if assistant_outputs
                                else None,
                            }
                        )
                        continue
                    except AppError as exc:
                        latency_ms = round((time.perf_counter() - evaluation_started) * 1000)
                        evaluation_latencies.append(latency_ms)
                        coach_samples.append(
                            {
                                "run": run + 1,
                                "fixture": label,
                                "valid": False,
                                "error": exc.code.value,
                                "latency_ms": latency_ms,
                            }
                        )
                        continue

                    score = compute_overall_score(output.result.criteria)
                    scores[label].append(score)
                    latency_ms = round((time.perf_counter() - evaluation_started) * 1000)
                    evaluation_latencies.append(latency_ms)
                    candidate_ids = {
                        turn.id for turn in transcript if turn.speaker == "candidate"
                    }
                    evidence_ids = {
                        evidence_id
                        for item in output.result.criteria
                        for evidence_id in item.evidence_turn_ids
                    }
                    coach_samples.append(
                        {
                            "run": run + 1,
                            "fixture": label,
                            "valid": True,
                            "valid_on_first_try": len(output.messages) == 2,
                            "evidence_ids_valid": evidence_ids.issubset(candidate_ids),
                            "overall_score": score,
                            "latency_ms": latency_ms,
                        }
                    )

            format_passes = [
                sample
                for sample in roleplay_samples
                if "error" not in sample
                and sample["word_count"] <= 60
                and not sample["markdown"]
                and not sample["stage_directions"]
            ]
            valid_coach = [sample for sample in coach_samples if sample.get("valid")]
            first_try = [
                sample for sample in valid_coach if sample["valid_on_first_try"]
            ]
            evidence_valid = [
                sample for sample in valid_coach if sample["evidence_ids_valid"]
            ]
            reply_p95 = _p95(roleplay_latencies[1:])
            format_pass_percent = (
                100 * len(format_passes) / len(roleplay_samples)
                if roleplay_samples
                else None
            )
            first_try_percent = (
                100 * len(first_try) / len(coach_samples) if coach_samples else None
            )
            retry_percent = (
                100 * len(valid_coach) / len(coach_samples) if coach_samples else None
            )
            evidence_valid_percent = (
                100 * len(evidence_valid) / len(valid_coach) if valid_coach else None
            )
            score_gap = (
                statistics.mean(scores["strong"]) - statistics.mean(scores["weak"])
                if scores["strong"] and scores["weak"]
                else None
            )
            strong_score_stddev = (
                statistics.pstdev(scores["strong"])
                if len(scores["strong"]) > 1
                else None
            )
            evaluation_p95 = _p95(evaluation_latencies)
            whisper_results = _benchmark_whisper(whisper_models)
            eligible_for_lock = (
                runs >= 20
                and reply_p95 is not None
                and reply_p95 <= 8000
                and format_pass_percent is not None
                and format_pass_percent >= 90
                and first_try_percent is not None
                and first_try_percent >= 90
                and retry_percent is not None
                and retry_percent >= 98
                and evidence_valid_percent is not None
                and evidence_valid_percent >= 95
                and score_gap is not None
                and score_gap >= 15
                and strong_score_stddev is not None
                and strong_score_stddev <= 8
                and evaluation_p95 is not None
                and evaluation_p95 <= 60_000
                and bool(whisper_results)
                and all(result["status"] == "ready" for result in whisper_results)
                and all(result["wer_percent"] is not None for result in whisper_results)
                and behavior_review_passed
            )
            return {
                "model": model,
                "runs": runs,
                "cold_start_reply_ms": roleplay_latencies[0]
                if roleplay_latencies
                else None,
                "roleplay": {
                    "samples": len(roleplay_samples),
                    "successful_samples": len(roleplay_latencies),
                    "reply_p95_ms_warm": reply_p95,
                    "format_pass_percent": round(format_pass_percent, 1)
                    if format_pass_percent is not None
                    else None,
                    "markdown_or_stage_directions": sum(
                        bool(sample.get("markdown") or sample.get("stage_directions"))
                        for sample in roleplay_samples
                    ),
                    "one_question_percent": round(
                        100
                        * sum(
                            sample.get("question_marks") == 1
                            for sample in roleplay_samples
                        )
                        / len(roleplay_samples),
                        1,
                    )
                    if roleplay_samples
                    else None,
                    "human_behavior_review": "not performed by this automated tool",
                    "samples_detail": roleplay_samples,
                },
                "coach": {
                    "samples": len(coach_samples),
                    "valid_first_try_percent": round(first_try_percent, 1)
                    if first_try_percent is not None
                    else None,
                    "valid_after_retry_percent": round(retry_percent, 1)
                    if retry_percent is not None
                    else None,
                    "evidence_valid_percent": round(evidence_valid_percent, 1)
                    if evidence_valid_percent is not None
                    else None,
                    "strong_weak_score_gap": score_gap,
                    "strong_score_stddev": round(strong_score_stddev, 2)
                    if strong_score_stddev is not None
                    else None,
                    "evaluation_p95_ms": evaluation_p95,
                    "samples_detail": coach_samples,
                },
                "whisper": whisper_results,
                "resources": {
                    "lowest_available_host_ram_mb": round(memory.lowest_available_mb)
                    if memory.lowest_available_mb is not None
                    else None,
                    "ollama_loaded_models": _ollama_loaded_models(
                        settings.ollama_base_url
                    ),
                    "gpu_vram_measurement": "not available from this CPU-only Ollama run",
                },
                "human_behavior_review_passed": behavior_review_passed,
                "eligible_for_lock": eligible_for_lock,
            }
        finally:
            llm.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local EchoRole models.")
    parser.add_argument("--models", required=True, help="Comma-separated Ollama model names.")
    parser.add_argument(
        "--whisper",
        default="",
        help="Optional comma-separated local faster-whisper model names.",
    )
    parser.add_argument("--runs", type=int, default=20, help="Repeated fixture runs.")
    parser.add_argument(
        "--behavior-review-passed",
        action="store_true",
        help="Set only after a reviewer passes at least 20 sampled roleplay turns.",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    models = [value.strip() for value in args.models.split(",") if value.strip()]
    whisper_models = [value.strip() for value in args.whisper.split(",") if value.strip()]
    if not models:
        parser.error("--models must include at least one model")
    if args.behavior_review_passed and args.runs * 9 < 20:
        parser.error("--behavior-review-passed requires at least 3 runs (27 turns).")

    results = [
        _benchmark_model(
            model,
            args.runs,
            whisper_models,
            args.behavior_review_passed,
        )
        for model in models
    ]
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
