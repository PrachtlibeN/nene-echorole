from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import sessionmaker

from app.core.config import LLMProfile, Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.llm.interfaces import LLMMessage
from app.models.entities import Conversation, Message, Scenario, Session, Turn
from app.roleplay.interfaces import (
    RoleplayAgent,
    RoleplayContext,
    RoleplayReply,
    StubRoleplayAgent,
)
from app.roleplay.prompts import build_roleplay_prompt
from app.schemas.contracts import (
    EndReason,
    ScenarioDefinition,
    ScenarioListOut,
    ScenarioOut,
    ScenarioSummary,
    SessionListOut,
    SessionOut,
    SessionStatus,
    SpeechMeta,
    StartSessionOut,
    TurnCreateIn,
    TurnListOut,
    TurnOut,
    TurnSource,
    TurnSubmitOut,
)
from app.simulation.repository import SimulationRepository

logger = logging.getLogger(__name__)
ScenarioSessionFactory = sessionmaker[DBSession]
Clock = Callable[[], datetime]
T = TypeVar("T")


class ScenarioSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    language: Literal["en"]
    difficulty: int = Field(ge=1, le=3)
    max_turns: int = Field(ge=1, le=30)
    estimated_minutes: int = Field(ge=1)
    definition: ScenarioDefinition


class Transcript(BaseModel):
    session: SessionOut
    scenario: ScenarioOut
    turns: list[TurnOut]


class SimulationService:
    def __init__(
        self,
        session_factory: ScenarioSessionFactory,
        settings: Settings,
        agent: RoleplayAgent | None = None,
        clock: Clock | None = None,
        scenario_dir: Path | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.repository = SimulationRepository(session_factory)
        self.settings = settings
        self.agent = agent or StubRoleplayAgent()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.scenario_dir = scenario_dir or Path(__file__).with_name("scenarios")
        self._estimated_minutes: dict[str, int] = {}

    @contextmanager
    def _transaction(self) -> Iterator[DBSession]:
        with self.repository.transaction() as db:
            yield db

    def seed_scenarios(self) -> None:
        seeds = [
            ScenarioSeed.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.scenario_dir.glob("*.json"))
        ]
        if len(seeds) != 3:
            raise RuntimeError(f"Expected exactly three scenario JSON files, found {len(seeds)}.")

        now = _timestamp(self.clock())
        with self._transaction() as db:
            for seed in seeds:
                self._estimated_minutes[seed.slug] = seed.estimated_minutes
                scenario = self.repository.get_scenario_by_slug(db, seed.slug)
                if scenario is None:
                    scenario = Scenario(
                        id=new_id("scn_"),
                        slug=seed.slug,
                        title=seed.title,
                        description=seed.description,
                        language=seed.language,
                        difficulty=seed.difficulty,
                        max_turns=seed.max_turns,
                        definition_json=seed.definition.model_dump_json(),
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(scenario)
                else:
                    scenario.title = seed.title
                    scenario.description = seed.description
                    scenario.language = seed.language
                    scenario.difficulty = seed.difficulty
                    scenario.max_turns = seed.max_turns
                    scenario.definition_json = seed.definition.model_dump_json()
                    scenario.updated_at = now

    def sweep_idle_sessions(self) -> int:
        now = self.clock()
        cutoff = _timestamp(now - timedelta(minutes=self.settings.session_idle_timeout_minutes))
        with self._transaction() as db:
            result = cast(
                CursorResult[Any],
                db.execute(
                    update(Session)
                    .where(
                        Session.status == SessionStatus.ACTIVE.value,
                        Session.in_flight == 0,
                        Session.last_activity_at < cutoff,
                    )
                    .values(
                        status=SessionStatus.ABANDONED.value,
                        end_reason=EndReason.TIMEOUT.value,
                        ended_at=Session.last_activity_at,
                    )
                ),
            )
            return result.rowcount or 0

    def list_scenarios(self) -> ScenarioListOut:
        with self.session_factory() as db:
            scenarios = self.repository.list_scenarios(db)
            items = [self._scenario_summary(scenario) for scenario in scenarios]
        return ScenarioListOut(items=items, total=len(items))

    def get_scenario(self, scenario_id: str) -> ScenarioOut:
        with self.session_factory() as db:
            scenario = self.repository.get_scenario(db, scenario_id)
            if scenario is None:
                raise AppError(
                    ErrorCode.SCENARIO_NOT_FOUND,
                    f"Scenario {scenario_id} was not found.",
                    404,
                    {"scenario_id": scenario_id},
                )
            return self._scenario_out(scenario)

    def create_session(self, scenario_id: str) -> SessionOut:
        now = _timestamp(self.clock())
        with self._transaction() as db:
            scenario = self.repository.get_scenario(db, scenario_id)
            if scenario is None:
                raise AppError(
                    ErrorCode.SCENARIO_NOT_FOUND,
                    f"Scenario {scenario_id} was not found.",
                    404,
                    {"scenario_id": scenario_id},
                )
            session = Session(
                id=new_id("ses_"),
                scenario_id=scenario.id,
                status=SessionStatus.CREATED.value,
                end_reason=None,
                turn_count=0,
                in_flight=0,
                created_at=now,
                started_at=None,
                ended_at=None,
                last_activity_at=now,
            )
            db.add(session)
            conversation = Conversation(
                id=new_id("cnv_rp_"),
                session_id=session.id,
                agent_role="roleplay",
                system_prompt=build_roleplay_prompt(self._scenario_out(scenario)),
                model=self.settings.model_for(LLMProfile.ROLEPLAY),
                created_at=now,
            )
            db.add(conversation)
            db.flush()
            output = self._session_out(db, session)
        return output

    def list_sessions(
        self,
        status: SessionStatus | None,
        limit: int,
        offset: int,
    ) -> SessionListOut:
        self.sweep_idle_sessions()
        with self.session_factory() as db:
            sessions, total = self.repository.list_sessions(
                db,
                status.value if status is not None else None,
                limit,
                offset,
            )
            items = [self._session_out(db, session) for session in sessions]
        return SessionListOut(items=items, total=total, limit=limit, offset=offset)

    def get_session(self, session_id: str) -> SessionOut:
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            return self._session_out(db, session)

    def start_session(self, session_id: str) -> StartSessionOut:
        activity_at = _timestamp(self.clock())
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            if session.status != SessionStatus.CREATED.value:
                raise _invalid_state(session_id, session.status, ["created"])
            scenario = self.repository.get_scenario(db, session.scenario_id)
            conversation = self._roleplay_conversation(db, session_id)
            scenario_out = self._scenario_out(_required(scenario, "Scenario not found"))
            conversation_id = conversation.id
            session_snapshot_id = session.id

        replies = _replies(
            self.agent.open_session(
                RoleplayContext(
                    session_id=session_snapshot_id,
                    conversation_id=conversation_id,
                    scenario=scenario_out,
                    history=[],
                    turn_index=0,
                    max_turns=scenario_out.max_turns,
                )
            )
        )
        for reply in replies:
            _validate_reply(reply)
        now = _timestamp(self.clock())
        with self._transaction() as db:
            starting_session = self.repository.get_session(db, session_id)
            if starting_session is None:
                raise _session_not_found(session_id)
            if starting_session.status != SessionStatus.CREATED.value:
                raise _invalid_state(session_id, starting_session.status, ["created"])
            if starting_session.in_flight:
                raise _turn_in_progress(session_id)

            starting_session.status = SessionStatus.ACTIVE.value
            starting_session.started_at = activity_at
            starting_session.last_activity_at = activity_at
            turns = [
                Turn(
                    id=new_id("trn_"),
                    session_id=starting_session.id,
                    idx=index,
                    speaker="interviewer",
                    speaker_id=reply.speaker_id,
                    speaker_name=reply.speaker_name,
                    text=reply.text,
                    source=TurnSource.GENERATED.value,
                    speech_meta_json=None,
                    llm_meta_json=_reply_metadata(
                        reply, self.settings.model_for(LLMProfile.ROLEPLAY)
                    ),
                    created_at=now,
                )
                for index, reply in enumerate(replies)
            ]
            db.add_all(turns)
            db.add_all(
                [
                    Message(
                        id=new_id("msg_"),
                        conversation_id=conversation_id,
                        seq=index,
                        role="assistant",
                        content=_labeled_reply_content(reply, scenario_out),
                        turn_id=turn.id,
                        created_at=now,
                    )
                    for index, (reply, turn) in enumerate(zip(replies, turns, strict=True))
                ]
            )
            db.flush()
            turn_outputs = [_turn_out(turn) for turn in turns]
            output = StartSessionOut(
                session=self._session_out(db, starting_session),
                interviewer_turn=turn_outputs[-1],
                interviewer_turns=turn_outputs,
            )
        return output

    def submit_turn(self, session_id: str, payload: TurnCreateIn) -> TurnSubmitOut:
        accepted_at = _timestamp(self.clock())
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            if session.status != SessionStatus.ACTIVE.value:
                raise _not_active(session_id, session.status)
            if session.in_flight:
                raise _turn_in_progress(session_id)
            previous_activity_at = session.last_activity_at

            result = cast(
                CursorResult[Any],
                db.execute(
                    update(Session)
                    .where(
                        Session.id == session_id,
                        Session.status == SessionStatus.ACTIVE.value,
                        Session.in_flight == 0,
                    )
                    .values(in_flight=1, last_activity_at=accepted_at)
                ),
            )
            if result.rowcount != 1:
                current = self.repository.get_session(db, session_id)
                if current is None:
                    raise _session_not_found(session_id)
                if current.status != SessionStatus.ACTIVE.value:
                    raise _not_active(session_id, current.status)
                raise _turn_in_progress(session_id)

            session = _required(
                self.repository.get_session(db, session_id),
                "Session not found",
            )
            scenario = self._scenario_out(
                _required(
                    self.repository.get_scenario(db, session.scenario_id),
                    "Scenario not found",
                )
            )
            conversation = self._roleplay_conversation(db, session_id)
            messages = self.repository.list_messages(db, conversation.id)
            history = [
                _llm_message(message.role, message.content) for message in messages
            ]
            context = RoleplayContext(
                session_id=session.id,
                conversation_id=conversation.id,
                scenario=scenario,
                history=history,
                turn_index=session.turn_count + 1,
                max_turns=scenario.max_turns,
            )
            old_turn_count = session.turn_count
            conversation_id = conversation.id

        try:
            replies = _replies(self.agent.respond(context, payload.text))
            for reply in replies:
                _validate_reply(reply)
            persisted = self._persist_turn(
                session_id,
                conversation_id,
                payload,
                replies,
                scenario,
                old_turn_count,
                accepted_at,
            )
        except Exception:
            self._clear_in_flight(session_id, previous_activity_at)
            raise
        return persisted

    def list_turns(self, session_id: str) -> TurnListOut:
        with self._transaction() as db:
            self._load_single_session(db, session_id)
            turns = self.repository.list_turns(db, session_id)
            return TurnListOut(session_id=session_id, items=[_turn_out(turn) for turn in turns])

    def end_session(self, session_id: str) -> SessionOut:
        now = _timestamp(self.clock())
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            if session.status == SessionStatus.ENDED.value:
                return self._session_out(db, session)
            if session.status != SessionStatus.ACTIVE.value:
                raise _invalid_state(session_id, session.status, ["active", "ended"])
            if session.in_flight:
                raise _turn_in_progress(session_id)

            session.status = SessionStatus.ENDED.value
            session.end_reason = EndReason.USER_ENDED.value
            session.ended_at = now
            session.last_activity_at = now
            db.flush()
            return self._session_out(db, session)

    def assert_session_ended(self, session_id: str) -> None:
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            if session.status != SessionStatus.ENDED.value:
                raise AppError(
                    ErrorCode.SESSION_NOT_ENDED,
                    f"Session {session_id} has not ended.",
                    409,
                    {"session_id": session_id, "status": session.status},
                )

    def get_transcript(self, session_id: str) -> Transcript:
        with self._transaction() as db:
            session = self._load_single_session(db, session_id)
            scenario = _required(
                self.repository.get_scenario(db, session.scenario_id),
                "Scenario not found",
            )
            turns = self.repository.list_turns(db, session_id)
            return Transcript(
                session=self._session_out(db, session),
                scenario=self._scenario_out(scenario),
                turns=[_turn_out(turn) for turn in turns],
            )

    def _persist_turn(
        self,
        session_id: str,
        conversation_id: str,
        payload: TurnCreateIn,
        replies: list[RoleplayReply],
        scenario: ScenarioOut,
        old_turn_count: int,
        accepted_at: str,
    ) -> TurnSubmitOut:
        with self._transaction() as db:
            session = self.repository.get_session(db, session_id)
            if session is None:
                raise _session_not_found(session_id)
            if session.status != SessionStatus.ACTIVE.value:
                raise _not_active(session_id, session.status)
            if not session.in_flight:
                raise _turn_in_progress(session_id)

            existing_turn_count = self.repository.count_turns(db, session_id)
            now = _timestamp(self.clock())
            candidate_turn = Turn(
                id=new_id("trn_"),
                session_id=session_id,
                idx=existing_turn_count,
                speaker="candidate",
                text=payload.text,
                source=payload.source,
                speech_meta_json=(
                    payload.speech_meta.model_dump_json()
                    if payload.speech_meta is not None
                    else None
                ),
                llm_meta_json=None,
                created_at=accepted_at,
            )
            interviewer_turns = [
                Turn(
                    id=new_id("trn_"),
                    session_id=session_id,
                    idx=existing_turn_count + index + 1,
                    speaker="interviewer",
                    speaker_id=reply.speaker_id,
                    speaker_name=reply.speaker_name,
                    text=reply.text,
                    source=TurnSource.GENERATED.value,
                    speech_meta_json=None,
                    llm_meta_json=_reply_metadata(
                        reply, self.settings.model_for(LLMProfile.ROLEPLAY)
                    ),
                    created_at=now,
                )
                for index, reply in enumerate(replies)
            ]
            db.add_all([candidate_turn, *interviewer_turns])

            next_seq = self.repository.count_messages(db, conversation_id)
            messages = [
                Message(
                    id=new_id("msg_"),
                    conversation_id=conversation_id,
                    seq=next_seq,
                    role="user",
                    content=payload.text,
                    turn_id=candidate_turn.id,
                    created_at=accepted_at,
                )
            ] + [
                    Message(
                        id=new_id("msg_"),
                        conversation_id=conversation_id,
                        seq=next_seq + index + 1,
                        role="assistant",
                        content=_labeled_reply_content(reply, scenario),
                        turn_id=interviewer_turn.id,
                        created_at=now,
                    )
                    for index, (reply, interviewer_turn) in enumerate(
                        zip(replies, interviewer_turns, strict=True)
                    )
                ]
            db.add_all(messages)
            session.turn_count = old_turn_count + 1
            session.in_flight = 0
            session.last_activity_at = accepted_at
            if session.turn_count >= self._scenario_max_turns(db, session.scenario_id):
                session.status = SessionStatus.ENDED.value
                session.end_reason = EndReason.MAX_TURNS.value
                session.ended_at = now
            elif any(reply.should_end for reply in replies):
                session.status = SessionStatus.ENDED.value
                session.end_reason = EndReason.AGENT_CONCLUDED.value
                session.ended_at = now
            db.flush()
            interviewer_outputs = [_turn_out(turn) for turn in interviewer_turns]
            return TurnSubmitOut(
                candidate_turn=_turn_out(candidate_turn),
                interviewer_turn=interviewer_outputs[-1],
                session=self._session_out(db, session),
                interviewer_turns=interviewer_outputs,
            )

    def _clear_in_flight(self, session_id: str, previous_activity_at: str) -> None:
        try:
            with self._transaction() as db:
                db.execute(
                    update(Session)
                    .where(Session.id == session_id, Session.in_flight == 1)
                    .values(in_flight=0, last_activity_at=previous_activity_at)
                )
        except Exception:
            logger.exception("Could not clear the in-flight flag for session %s", session_id)

    def _load_single_session(self, db: DBSession, session_id: str) -> Session:
        now = self.clock()
        cutoff = _timestamp(now - timedelta(minutes=self.settings.session_idle_timeout_minutes))
        with self.session_factory() as sweep_db:
            with sweep_db.begin():
                sweep_db.execute(
                    update(Session)
                    .where(
                        Session.id == session_id,
                        Session.status == SessionStatus.ACTIVE.value,
                        Session.in_flight == 0,
                        Session.last_activity_at < cutoff,
                    )
                    .values(
                        status=SessionStatus.ABANDONED.value,
                        end_reason=EndReason.TIMEOUT.value,
                        ended_at=Session.last_activity_at,
                    )
                )
        session = self.repository.get_session(db, session_id)
        if session is None:
            raise _session_not_found(session_id)
        return session

    def _scenario_summary(self, scenario: Scenario) -> ScenarioSummary:
        definition = ScenarioDefinition.model_validate_json(scenario.definition_json)
        return ScenarioSummary(
            id=scenario.id,
            slug=scenario.slug,
            title=scenario.title,
            description=scenario.description,
            language="en",
            difficulty=scenario.difficulty,
            max_turns=scenario.max_turns,
            estimated_minutes=self._estimated_minutes.get(
                scenario.slug, max(1, round(scenario.max_turns * 1.25))
            ),
            personas=definition.personas,
        )

    def _scenario_out(self, scenario: Scenario) -> ScenarioOut:
        summary = self._scenario_summary(scenario)
        return ScenarioOut(
            **summary.model_dump(),
            definition=ScenarioDefinition.model_validate_json(scenario.definition_json),
        )

    def _roleplay_conversation(self, db: DBSession, session_id: str) -> Conversation:
        conversation = self.repository.get_roleplay_conversation(db, session_id)
        if conversation is None:
            raise RuntimeError(f"Roleplay conversation missing for session {session_id}.")
        return conversation

    def _session_out(self, db: DBSession, session: Session) -> SessionOut:
        conversation = self._roleplay_conversation(db, session.id)
        return SessionOut(
            id=session.id,
            scenario_id=session.scenario_id,
            status=session.status,
            end_reason=session.end_reason,
            turn_count=session.turn_count,
            max_turns=self._scenario_max_turns(db, session.scenario_id),
            roleplay_conversation_id=conversation.id,
            created_at=_parse_timestamp(session.created_at),
            started_at=(
                _parse_timestamp(session.started_at) if session.started_at is not None else None
            ),
            ended_at=(
                _parse_timestamp(session.ended_at) if session.ended_at is not None else None
            ),
        )

    def _scenario_max_turns(self, db: DBSession, scenario_id: str) -> int:
        scenario = self.repository.get_scenario(db, scenario_id)
        if scenario is None:
            raise RuntimeError(f"Scenario {scenario_id} is missing.")
        return scenario.max_turns


def _required(value: T | None, message: str) -> T:
    if value is None:
        raise RuntimeError(message)
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _turn_out(turn: Turn) -> TurnOut:
    speech_meta = (
        SpeechMeta.model_validate_json(turn.speech_meta_json)
        if turn.speech_meta_json is not None
        else None
    )
    return TurnOut(
        id=turn.id,
        session_id=turn.session_id,
        idx=turn.idx,
        speaker=turn.speaker,
        text=turn.text,
        source=turn.source,
        speech_meta=speech_meta,
        speaker_id=turn.speaker_id,
        speaker_name=turn.speaker_name,
        created_at=_parse_timestamp(turn.created_at),
    )


def _reply_metadata(reply: RoleplayReply, fallback_model: str) -> str:
    return json.dumps(
        {
            "model": reply.llm.model or fallback_model,
            "latency_ms": reply.llm.latency_ms,
            "prompt_tokens": reply.llm.prompt_tokens,
            "completion_tokens": reply.llm.completion_tokens,
        }
    )


def _llm_message(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)


def _replies(
    result: RoleplayReply | list[RoleplayReply],
) -> list[RoleplayReply]:
    replies = result if isinstance(result, list) else [result]
    if not replies:
        raise AppError(
            ErrorCode.LLM_BAD_OUTPUT,
            "The roleplay agent returned no interviewer turns.",
            502,
        )
    return replies


def _labeled_reply_content(reply: RoleplayReply, scenario: ScenarioOut) -> str:
    if reply.speaker_id is None or reply.speaker_name is None:
        return reply.text
    persona = next(
        (item for item in scenario.definition.personas if item.id == reply.speaker_id),
        None,
    )
    if persona is None:
        return f"[{reply.speaker_name}]: {reply.text}"
    return f"[{reply.speaker_name} - {persona.role_title}]: {reply.text}"


def _session_not_found(session_id: str) -> AppError:
    return AppError(
        ErrorCode.SESSION_NOT_FOUND,
        f"Session {session_id} was not found.",
        404,
        {"session_id": session_id},
    )


def _not_active(session_id: str, status: str) -> AppError:
    return AppError(
        ErrorCode.SESSION_NOT_ACTIVE,
        f"Session {session_id} is not active (status: {status}).",
        409,
        {"session_id": session_id, "status": status},
    )


def _turn_in_progress(session_id: str) -> AppError:
    return AppError(
        ErrorCode.TURN_IN_PROGRESS,
        f"A turn is already being processed for session {session_id}.",
        409,
        {"session_id": session_id},
    )


def _invalid_state(session_id: str, status: str, allowed: list[str]) -> AppError:
    return AppError(
        ErrorCode.SESSION_INVALID_STATE,
        f"Session {session_id} cannot perform this operation (status: {status}).",
        409,
        {"session_id": session_id, "status": status, "allowed": allowed},
    )


def _validate_reply(reply: RoleplayReply) -> None:
    if not reply.text.strip():
        raise AppError(
            ErrorCode.LLM_BAD_OUTPUT,
            "The roleplay agent returned an empty reply.",
            502,
        )
