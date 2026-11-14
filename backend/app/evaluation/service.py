from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import LLMProfile, Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.evaluation.coach import EvaluationCoach, EvaluationParseError
from app.evaluation.interfaces import (
    Clock,
    CoachContext,
    SimulationService,
    format_timestamp,
    to_coach_scenario,
    utc_now,
)
from app.evaluation.metrics import compute_delivery_metrics
from app.evaluation.prompts import build_coach_system_prompt, build_coach_user_prompt
from app.evaluation.rubric import (
    CRITERIA,
    RUBRIC_VERSION,
    WEIGHTS,
    compute_overall_score,
    weighted_points,
)
from app.llm.interfaces import LLMClient, LLMMessage
from app.models.entities import (
    Conversation,
    Evaluation,
    EvaluationScore,
    Message,
)
from app.schemas.contracts import (
    CoachResult,
    CriterionScore,
    DeliveryMetrics,
    EvaluationError,
    EvaluationOut,
    EvaluationResult,
    EvaluationStatus,
    Improvement,
    NextTask,
    ScenarioCriterion,
    Strength,
    TaskOutcome,
)

LOGGER = logging.getLogger(__name__)
_EVALUATION_START_LOCK = threading.Lock()
_PARSE_FAILED_MESSAGE = "The coach returned an invalid evaluation. Please retry."


class EvaluationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        llm: LLMClient,
        simulation: SimulationService | None = None,
        clock: Clock | None = None,
        coach: EvaluationCoach | None = None,
    ) -> None:
        self.db = db
        self.session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        self.settings = settings
        self.llm = llm
        self.coach = coach or EvaluationCoach(llm)
        self.clock = clock or utc_now
        if simulation is None:
            from app.simulation.service import SimulationService as DefaultSimulationService

            simulation = cast(
                SimulationService,
                DefaultSimulationService(
                    session_factory=self.session_factory,
                    settings=settings,
                    clock=self.clock,
                ),
            )
        self.simulation = simulation

    def start_evaluation(self, session_id: str) -> EvaluationOut:
        with _EVALUATION_START_LOCK:
            self.simulation.assert_session_ended(session_id)
            transcript_data = self.simulation.get_transcript(session_id)
            candidate_turns = sum(
                1 for turn in transcript_data.turns if turn.speaker == "candidate"
            )
            if candidate_turns == 0:
                raise AppError(
                    ErrorCode.SESSION_TOO_SHORT,
                    "Session has no candidate turns and cannot be evaluated.",
                    409,
                    {"session_id": session_id},
                )

            running = self.db.scalar(
                select(Evaluation.id).where(
                    Evaluation.session_id == session_id,
                    Evaluation.status.in_(
                        [
                            EvaluationStatus.PENDING.value,
                            EvaluationStatus.RUNNING.value,
                        ]
                    ),
                )
            )
            if running is not None:
                raise AppError(
                    ErrorCode.EVALUATION_IN_PROGRESS,
                    "An evaluation is already in progress for this session.",
                    409,
                    {"session_id": session_id},
                )

            last_attempt = self.db.scalar(
                select(func.max(Evaluation.attempt)).where(
                    Evaluation.session_id == session_id
                )
            )
            now = format_timestamp(self.clock())
            evaluation = Evaluation(
                id=new_id("evl_"),
                session_id=session_id,
                conversation_id=None,
                attempt=(last_attempt or 0) + 1,
                status=EvaluationStatus.PENDING.value,
                rubric_version=RUBRIC_VERSION,
                overall_score=None,
                summary=None,
                result_json=None,
                metrics_json=None,
                error_code=None,
                error_message=None,
                model=None,
                created_at=now,
                completed_at=None,
            )
            self.db.add(evaluation)
            self.db.commit()
            return self._evaluation_out(self.db, evaluation)

    def get_evaluation(self, session_id: str, attempt: int | None) -> EvaluationOut:
        statement = select(Evaluation).where(Evaluation.session_id == session_id)
        if attempt is not None:
            statement = statement.where(Evaluation.attempt == attempt)
        else:
            statement = statement.order_by(Evaluation.attempt.desc())
        evaluation = self.db.scalars(statement.limit(1)).first()
        if evaluation is None:
            self.simulation.get_transcript(session_id)
            raise AppError(
                ErrorCode.EVALUATION_NOT_FOUND,
                f"No evaluation was found for session {session_id}.",
                404,
                {"session_id": session_id, "attempt": attempt},
            )
        return self._evaluation_out(self.db, evaluation)

    def run_evaluation(self, evaluation_id: str) -> None:
        try:
            self._run_evaluation(evaluation_id)
        except EvaluationParseError as exc:
            self.fail_evaluation(
                evaluation_id,
                ErrorCode.EVALUATION_PARSE_FAILED.value,
                _PARSE_FAILED_MESSAGE,
                exc.messages[1:],
            )
        except AppError as exc:
            self.fail_evaluation(
                evaluation_id,
                exc.code.value,
                exc.message,
            )
        except Exception:
            LOGGER.exception("Unexpected evaluation failure for %s", evaluation_id)
            self.fail_evaluation(
                evaluation_id,
                ErrorCode.INTERNAL_ERROR.value,
                "An unexpected error occurred while evaluating this session.",
            )

    def _run_evaluation(self, evaluation_id: str) -> None:
        session_id = self.pending_session_id(evaluation_id)
        if session_id is None:
            return
        transcript_data = self.simulation.get_transcript(session_id)
        scenario = to_coach_scenario(transcript_data.scenario)
        transcript = transcript_data.turns
        metrics = compute_delivery_metrics(transcript)
        system_prompt = build_coach_system_prompt()
        user_prompt = build_coach_user_prompt(scenario, transcript)
        conversation_id = new_id("cnv_ev_")
        model = self.llm.model_for(LLMProfile.EVALUATION)
        if not self.mark_running(
            evaluation_id,
            metrics,
            conversation_id,
            model,
            system_prompt,
            user_prompt,
        ):
            return

        context = CoachContext(
            evaluation_id=evaluation_id,
            conversation_id=conversation_id,
            scenario=scenario,
            transcript=transcript,
        )
        output = self.coach.evaluate(context)
        self.complete_evaluation(
            evaluation_id,
            output.result,
            output.messages[1:],
        )

    def pending_session_id(self, evaluation_id: str) -> str | None:
        with self.session_factory() as db:
            evaluation = db.get(Evaluation, evaluation_id)
            if evaluation is None or evaluation.status != EvaluationStatus.PENDING.value:
                return None
            return evaluation.session_id

    def mark_running(
        self,
        evaluation_id: str,
        metrics: DeliveryMetrics,
        conversation_id: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bool:
        now = format_timestamp(self.clock())
        with self.session_factory() as db, db.begin():
            evaluation = db.get(Evaluation, evaluation_id)
            if evaluation is None or evaluation.status != EvaluationStatus.PENDING.value:
                return False
            db.add(
                Conversation(
                    id=conversation_id,
                    session_id=evaluation.session_id,
                    agent_role="evaluation",
                    system_prompt=system_prompt,
                    model=model,
                    created_at=now,
                )
            )
            db.flush()
            evaluation.status = EvaluationStatus.RUNNING.value
            evaluation.metrics_json = metrics.model_dump_json()
            evaluation.conversation_id = conversation_id
            evaluation.model = model
            db.add(
                Message(
                    id=new_id("msg_"),
                    conversation_id=conversation_id,
                    seq=0,
                    role="user",
                    content=user_prompt,
                    turn_id=None,
                    created_at=now,
                )
            )
        return True

    def complete_evaluation(
        self,
        evaluation_id: str,
        result: CoachResult,
        messages: list[LLMMessage],
    ) -> None:
        with self.session_factory() as db, db.begin():
            evaluation = db.get(Evaluation, evaluation_id)
            if evaluation is None:
                raise RuntimeError(f"Evaluation {evaluation_id} disappeared")
            if evaluation.conversation_id is None:
                raise RuntimeError("Running evaluation has no Coach conversation")
            self._persist_messages(
                db,
                evaluation.conversation_id,
                messages,
                format_timestamp(self.clock()),
            )
            for item in result.criteria:
                db.add(
                    EvaluationScore(
                        id=new_id("esc_"),
                        evaluation_id=evaluation.id,
                        criterion=item.criterion.value,
                        score=item.score,
                        weight_percent=WEIGHTS[item.criterion],
                        rationale=item.rationale,
                        evidence_turn_ids_json=json.dumps(item.evidence_turn_ids),
                    )
                )
            evaluation.overall_score = compute_overall_score(result.criteria)
            evaluation.summary = result.summary
            evaluation.result_json = json.dumps(
                result.model_dump(mode="json", exclude={"summary", "criteria"}),
                separators=(",", ":"),
            )
            evaluation.status = EvaluationStatus.COMPLETED.value
            evaluation.error_code = None
            evaluation.error_message = None
            evaluation.completed_at = format_timestamp(self.clock())
            db.flush()

    def fail_evaluation(
        self,
        evaluation_id: str,
        error_code: str,
        error_message: str,
        messages: list[LLMMessage] | None = None,
    ) -> None:
        with self.session_factory() as db, db.begin():
            evaluation = db.get(Evaluation, evaluation_id)
            if evaluation is None or evaluation.status == EvaluationStatus.COMPLETED.value:
                return
            if messages and evaluation.conversation_id is not None:
                self._persist_messages(
                    db,
                    evaluation.conversation_id,
                    messages,
                    format_timestamp(self.clock()),
                )
            evaluation.status = EvaluationStatus.FAILED.value
            evaluation.error_code = error_code
            evaluation.error_message = error_message
            evaluation.completed_at = format_timestamp(self.clock())

    @classmethod
    def _evaluation_out(cls, db: Session, evaluation: Evaluation) -> EvaluationOut:
        metrics = (
            DeliveryMetrics.model_validate_json(evaluation.metrics_json)
            if evaluation.metrics_json is not None
            else None
        )
        result = (
            cls._evaluation_result(db, evaluation)
            if evaluation.status == EvaluationStatus.COMPLETED.value
            else None
        )
        if evaluation.status == EvaluationStatus.FAILED.value:
            if evaluation.error_code is None:
                raise RuntimeError("Failed evaluation has no error code")
            error = EvaluationError(
                code=evaluation.error_code,
                message=evaluation.error_message or "Evaluation failed.",
            )
        else:
            error = None
        return EvaluationOut(
            id=evaluation.id,
            session_id=evaluation.session_id,
            attempt=evaluation.attempt,
            status=EvaluationStatus(evaluation.status),
            rubric_version=evaluation.rubric_version,
            coach_conversation_id=evaluation.conversation_id,
            model=evaluation.model,
            metrics=metrics,
            result=result,
            error=error,
            created_at=datetime.fromisoformat(
                evaluation.created_at.replace("Z", "+00:00")
            ),
            completed_at=(
                datetime.fromisoformat(evaluation.completed_at.replace("Z", "+00:00"))
                if evaluation.completed_at is not None
                else None
            ),
        )

    @staticmethod
    def _evaluation_result(
        db: Session,
        evaluation: Evaluation,
    ) -> EvaluationResult:
        if evaluation.overall_score is None or evaluation.summary is None:
            raise RuntimeError("Completed evaluation is missing its computed result")
        qualitative = json.loads(evaluation.result_json or "{}")
        rows = db.scalars(
            select(EvaluationScore).where(
                EvaluationScore.evaluation_id == evaluation.id
            )
        ).all()
        scores = {ScenarioCriterion(row.criterion): row for row in rows}
        criteria = []
        for criterion in CRITERIA:
            score = scores.get(criterion)
            if score is None:
                raise RuntimeError(
                    f"Completed evaluation is missing score {criterion.value}"
                )
            criteria.append(
                CriterionScore(
                    criterion=criterion,
                    score=score.score,
                    weight_percent=score.weight_percent,
                    weighted_points=weighted_points(score.score, criterion),
                    rationale=score.rationale,
                    evidence_turn_ids=json.loads(score.evidence_turn_ids_json),
                )
            )
        return EvaluationResult(
            overall_score=evaluation.overall_score,
            summary=evaluation.summary,
            task_outcome=TaskOutcome.model_validate(qualitative["task_outcome"]),
            criteria=criteria,
            strengths=[
                Strength.model_validate(item) for item in qualitative["strengths"]
            ],
            improvements=[
                Improvement.model_validate(item)
                for item in qualitative["improvements"]
            ],
            next_task=NextTask.model_validate(qualitative["next_task"]),
        )

    @staticmethod
    def _persist_messages(
        db: Session,
        conversation_id: str,
        messages: list[LLMMessage],
        created_at: str,
    ) -> None:
        last_seq = db.scalar(
            select(func.max(Message.seq)).where(
                Message.conversation_id == conversation_id
            )
        )
        seq = 0 if last_seq is None else int(last_seq) + 1
        for message in messages:
            if message.role not in {"user", "assistant"}:
                raise RuntimeError(f"Invalid persisted coach role: {message.role}")
            db.add(
                Message(
                    id=new_id("msg_"),
                    conversation_id=conversation_id,
                    seq=seq,
                    role=message.role,
                    content=message.content,
                    turn_id=None,
                    created_at=created_at,
                )
            )
            seq += 1
        db.flush()
