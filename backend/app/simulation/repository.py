from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import sessionmaker

from app.models.entities import Conversation, Message, Scenario, Session, Turn


class SimulationRepository:
    def __init__(self, session_factory: sessionmaker[DBSession]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def transaction(self) -> Iterator[DBSession]:
        with self.session_factory() as db:
            with db.begin():
                yield db

    @staticmethod
    def get_scenario(db: DBSession, scenario_id: str) -> Scenario | None:
        return db.get(Scenario, scenario_id)

    @staticmethod
    def get_scenario_by_slug(db: DBSession, slug: str) -> Scenario | None:
        return db.scalar(select(Scenario).where(Scenario.slug == slug))

    @staticmethod
    def list_scenarios(db: DBSession) -> list[Scenario]:
        return list(db.scalars(select(Scenario).order_by(Scenario.slug)).all())

    @staticmethod
    def get_session(db: DBSession, session_id: str) -> Session | None:
        return db.get(Session, session_id)

    @staticmethod
    def get_roleplay_conversation(db: DBSession, session_id: str) -> Conversation | None:
        return db.scalar(
            select(Conversation).where(
                Conversation.session_id == session_id,
                Conversation.agent_role == "roleplay",
            )
        )

    @staticmethod
    def list_messages(db: DBSession, conversation_id: str) -> list[Message]:
        return list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.seq)
            ).all()
        )

    @staticmethod
    def count_messages(db: DBSession, conversation_id: str) -> int:
        return (
            db.scalar(
                select(func.count()).select_from(Message).where(
                    Message.conversation_id == conversation_id
                )
            )
            or 0
        )

    @staticmethod
    def count_turns(db: DBSession, session_id: str) -> int:
        return (
            db.scalar(
                select(func.count()).select_from(Turn).where(Turn.session_id == session_id)
            )
            or 0
        )

    @staticmethod
    def list_turns(db: DBSession, session_id: str) -> list[Turn]:
        return list(
            db.scalars(
                select(Turn).where(Turn.session_id == session_id).order_by(Turn.idx)
            ).all()
        )

    @staticmethod
    def list_sessions(
        db: DBSession,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Session], int]:
        query = select(Session)
        count_query = select(func.count()).select_from(Session)
        if status is not None:
            query = query.where(Session.status == status)
            count_query = count_query.where(Session.status == status)
        total = db.scalar(count_query) or 0
        sessions = list(
            db.scalars(
                query.order_by(Session.created_at.desc(), Session.id)
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return sessions, total
