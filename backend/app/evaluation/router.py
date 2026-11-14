from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import LLMProfile, Settings
from app.core.db import get_db
from app.core.errors import API_ERROR_RESPONSES, AppError, ErrorCode
from app.evaluation.coach import EvaluationCoach
from app.evaluation.interfaces import Clock, SimulationService, utc_now
from app.evaluation.service import EvaluationService
from app.llm.interfaces import LLMClient, LLMHealth, LLMMessage, LLMResult
from app.schemas.contracts import EmptyRequest, EvaluationOut


class _UnconfiguredLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def model_for(self, profile: LLMProfile) -> str:
        return self.settings.model_for(profile)

    def health(self) -> LLMHealth:
        return LLMHealth(
            status="unavailable",
            models={
                "roleplay": self.model_for(LLMProfile.ROLEPLAY),
                "evaluation": self.model_for(LLMProfile.EVALUATION),
            },
            detail="No LLM client is configured for this application.",
        )

    def chat(
        self,
        profile: LLMProfile,
        messages: list[LLMMessage],
        *,
        json_mode: bool = False,
        json_schema: dict[str, object] | None = None,
    ) -> LLMResult:
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "No LLM client is configured for this application.",
            503,
        )


def get_llm_client(request: Request) -> LLMClient:
    client = getattr(request.app.state, "llm_client", None)
    if client is not None:
        return cast(LLMClient, client)
    return _UnconfiguredLLMClient(request.app.state.settings)


def get_evaluation_clock(request: Request) -> Clock:
    return getattr(request.app.state, "evaluation_clock", utc_now)


def get_simulation_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SimulationService:
    service = getattr(request.app.state, "simulation_service", None)
    if service is not None:
        return cast(SimulationService, service)
    clock = getattr(request.app.state, "evaluation_clock", utc_now)
    from app.simulation.service import SimulationService as DefaultSimulationService

    session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return cast(
        SimulationService,
        DefaultSimulationService(
            session_factory=session_factory,
            settings=request.app.state.settings,
            clock=clock,
        ),
    )


def get_evaluation_coach(
    request: Request,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> EvaluationCoach:
    coach = getattr(request.app.state, "evaluation_coach", None)
    if coach is not None and getattr(coach, "llm", None) is llm:
        return cast(EvaluationCoach, coach)
    return EvaluationCoach(llm)


def get_evaluation_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    clock: Annotated[Clock, Depends(get_evaluation_clock)],
    simulation: Annotated[SimulationService, Depends(get_simulation_service)],
    coach: Annotated[EvaluationCoach, Depends(get_evaluation_coach)],
) -> EvaluationService:
    return EvaluationService(
        db=db,
        settings=request.app.state.settings,
        llm=llm,
        simulation=simulation,
        clock=clock,
        coach=coach,
    )


router = APIRouter(tags=["evaluation"], responses=API_ERROR_RESPONSES)


@router.post(
    "/sessions/{session_id}/evaluation",
    response_model=EvaluationOut,
    status_code=202,
    operation_id="startEvaluation",
)
def start_evaluation(
    session_id: str,
    payload: EmptyRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationOut:
    result = service.start_evaluation(session_id)
    background_tasks.add_task(service.run_evaluation, result.id)
    return result


@router.get(
    "/sessions/{session_id}/evaluation",
    response_model=EvaluationOut,
    operation_id="getEvaluation",
)
def get_evaluation(
    session_id: str,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    attempt: Annotated[int | None, Query(ge=1)] = None,
) -> EvaluationOut:
    return service.get_evaluation(session_id, attempt)
