import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models import Base


def test_database_schema_has_checks_and_required_indexes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with engine.connect() as connection:
        index_names = {
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
        }
    engine.dispose()

    assert "uq_conv_roleplay_per_session" in index_names


def test_evaluation_conversation_id_is_unique() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insert_base_rows(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO evaluations "
                "(id,session_id,conversation_id,attempt,status,rubric_version,created_at) "
                "VALUES ('evl1','ses1','cnv1',1,'pending','1.0','now')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO evaluations "
                    "(id,session_id,conversation_id,attempt,status,rubric_version,created_at) "
                    "VALUES ('evl2','ses1','cnv1',2,'pending','1.0','now')"
                )
            )
    engine.dispose()


def test_partial_unique_index_allows_one_roleplay_conversation_per_session() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insert_base_rows(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO conversations "
                "(id,session_id,agent_role,system_prompt,model,created_at) "
                "VALUES ('cnv-rp-2','ses1','roleplay','prompt','model','now')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO conversations "
                    "(id,session_id,agent_role,system_prompt,model,created_at) "
                    "VALUES ('cnv-rp-3','ses1','roleplay','prompt','model','now')"
                )
            )
    engine.dispose()


def test_sqlite_check_constraints_are_enforced() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    insert_base_rows(engine)

    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO sessions "
                "(id,scenario_id,status,turn_count,in_flight,created_at,last_activity_at) "
                "VALUES ('ses-bad','scn1','invalid',0,0,'now','now')"
            )
        )
    engine.dispose()


def insert_base_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO scenarios "
                "(id,slug,title,description,language,difficulty,max_turns,definition_json,"
                "created_at,updated_at) "
                "VALUES ('scn1','scenario','Title','Desc','en',1,8,'{}','now','now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sessions "
                "(id,scenario_id,status,turn_count,in_flight,created_at,last_activity_at) "
                "VALUES ('ses1','scn1','created',0,0,'now','now')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conversations "
                "(id,session_id,agent_role,system_prompt,model,created_at) "
                "VALUES ('cnv1','ses1','evaluation','prompt','model','now')"
            )
        )
