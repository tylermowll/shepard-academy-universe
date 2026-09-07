"""On-disk SQLite integration gates for T01 (D004).

Every test uses an isolated temporary database file with the production
connection settings. Mocked SQL and in-memory-only fixtures do not satisfy
these gates.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from math_tutor import cli, settings
from math_tutor.adapters.db.base import Base
from math_tutor.adapters.db.engine import (
    create_engine_for_url,
    verify_connection_settings,
)
from math_tutor.adapters.db.models import Learner, PracticeSession, ProblemInstance

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
HEAD_REVISION = "0011_photo_deletion"


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point DATABASE_URL at an isolated temporary file for one test."""

    url = f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}"
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, url)
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    """Engine with the production connection settings for one test."""

    eng = create_engine_for_url(db_url)
    try:
        yield eng
    finally:
        eng.dispose()


def alembic_config(db_url: str) -> Config:
    """Config wired to the test database without touching operator settings."""

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def upgrade(db_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(db_url), revision)


def make_session(learner_id: uuid.UUID | None = None) -> PracticeSession:
    learner = Learner(id=learner_id or uuid.uuid4(), alias="Synthetic", eligibility="unknown")
    return PracticeSession(
        id=uuid.uuid4(),
        learner_id=learner.id,
        learner=learner,
        status="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_problem(session_id: uuid.UUID, position: int = 0) -> ProblemInstance:
    now = datetime.now(UTC)
    return ProblemInstance(
        id=uuid.uuid4(),
        session_id=session_id,
        template_id="fraction_add",
        template_version=1,
        skill_id="fractions.add",
        seed=7,
        position=position,
        parameters={"a": "1/2", "b": "1/3"},
        problem_text="1/2 + 1/3",
        expected_result={"value": "5/6"},
        format_constraints={"simplest_form": True},
        status="assigned",
        created_at=now,
        updated_at=now,
    )


def table_columns(engine: Engine) -> dict[str, set[str]]:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names: list[str] = inspector.get_table_names()
        return {name: {column["name"] for column in inspector.get_columns(name)} for name in names}


def test_empty_file_migration_reaches_head(engine: Engine, db_url: str) -> None:
    upgrade(db_url)

    columns = table_columns(engine)
    assert set(columns) == {
        "practice_session",
        "problem_instance",
        "administrator",
        "device_session",
        "alembic_version",
        "learner",
        "pairing_request",
        "submission",
        "evaluation",
        "tutor_turn",
        "progress_event",
        "job",
        "worker_heartbeat",
        "tutor_profile_version",
        "provider_probe",
        "route_selection",
        "model_call",
        "interpretation",
        "deletion_tombstone",
        "audit_event",
        "phone_upload",
        "photo_deletion",
    }
    assert columns["practice_session"] >= {"id", "learner_id", "status", "created_at"}
    assert columns["problem_instance"] >= {
        "id",
        "session_id",
        "parameters",
        "problem_text",
        "expected_result",
    }
    with engine.connect() as connection:
        version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert version == HEAD_REVISION


@pytest.mark.parametrize("key", ["", "../private", "a" * 63, "A" * 64, "g" * 64])
def test_photo_cleanup_migration_rejects_invalid_storage_keys(
    engine: Engine, db_url: str, key: str
) -> None:
    upgrade(db_url)
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.exec_driver_sql(
            "INSERT INTO photo_deletion(image_key, created_at) VALUES (?, datetime('now'))",
            (key,),
        )


def test_migration_matches_model_metadata(engine: Engine, db_url: str, tmp_path: Path) -> None:
    upgrade(db_url)

    model_url = f"sqlite+pysqlite:///{tmp_path / 'model.sqlite3'}"
    model_engine = create_engine_for_url(model_url)
    try:
        Base.metadata.create_all(model_engine)
        migrated = table_columns(engine)
        from_models = table_columns(model_engine)
    finally:
        model_engine.dispose()

    assert set(migrated) == set(from_models) | {"alembic_version"}
    for table in from_models:
        assert migrated[table] == from_models[table], f"migration drift on {table}"
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    model_engine = create_engine_for_url(model_url)
    try:
        for table in from_models:
            for method in ("get_check_constraints", "get_unique_constraints", "get_foreign_keys"):
                actual = getattr(inspect(engine), method)(table)
                expected = getattr(inspect(model_engine), method)(table)
                assert sorted(actual, key=str) == sorted(expected, key=str), (table, method)
    finally:
        model_engine.dispose()


def test_failed_migration_preserves_revision_schema_and_data(
    engine: Engine, db_url: str, tmp_path: Path
) -> None:
    upgrade(db_url)
    with Session(engine) as db:
        db.add(make_session())
        db.commit()
    migrations = tmp_path / "failing_migrations"
    shutil.copytree(MIGRATIONS_DIR, migrations)
    (migrations / "versions/review_failure.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = 'review_failure'\n"
        f"down_revision = {HEAD_REVISION!r}\n"
        "def upgrade():\n"
        "    op.create_table('partial', sa.Column('value', sa.Integer()))\n"
        "    op.execute(\"UPDATE practice_session SET status = 'completed'\")\n"
        "    raise RuntimeError('synthetic migration failure')\n"
    )
    config = alembic_config(db_url)
    config.set_main_option("script_location", str(migrations))
    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        command.upgrade(config, "head")
    with engine.connect() as connection:
        assert "partial" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql("SELECT status FROM practice_session").scalar() == "open"
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
            == HEAD_REVISION
        )


def test_production_connection_settings_on_every_connection(engine: Engine) -> None:
    with engine.connect() as first, engine.connect() as second:
        assert verify_connection_settings(first) == {
            "journal_mode": "wal",
            "foreign_keys": "1",
            "busy_timeout": "5000",
            "synchronous": "FULL",
        }
        assert first.connection.driver_connection is not second.connection.driver_connection
        assert verify_connection_settings(second)["foreign_keys"] == "1"


def test_ddl_and_savepoint_roll_back_with_outer_transaction(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.exec_driver_sql("CREATE TABLE rolled_back (value INTEGER)")
        transaction.rollback()
        assert "rolled_back" not in inspect(connection).get_table_names()
        connection.rollback()
        with connection.begin():
            connection.exec_driver_sql("CREATE TABLE savepoint_test (value INTEGER)")
        transaction = connection.begin()
        with connection.begin_nested():
            connection.exec_driver_sql("INSERT INTO savepoint_test VALUES (1)")
        transaction.rollback()
        assert connection.exec_driver_sql("SELECT count(*) FROM savepoint_test").scalar() == 0


def test_read_transaction_keeps_a_consistent_snapshot(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE snapshot_test (value INTEGER)")
        connection.exec_driver_sql("INSERT INTO snapshot_test VALUES (1)")
    with engine.connect() as reader, engine.begin() as writer:
        assert reader.exec_driver_sql("SELECT value FROM snapshot_test").scalar() == 1
        writer.exec_driver_sql("UPDATE snapshot_test SET value = 2")
        writer.commit()
        assert reader.exec_driver_sql("SELECT value FROM snapshot_test").scalar() == 1
        reader.rollback()
        assert reader.exec_driver_sql("SELECT value FROM snapshot_test").scalar() == 2


def test_relative_engine_url_uses_resolved_private_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "private"
    monkeypatch.setenv(settings.DATA_DIR_ENV_VAR, str(private))
    monkeypatch.chdir(tmp_path)
    eng = create_engine_for_url("sqlite:///relative.sqlite3")
    try:
        with eng.connect() as connection:
            connection.exec_driver_sql("CREATE TABLE permissions_test (value INTEGER)")
            actual = connection.exec_driver_sql("PRAGMA database_list").one()[2]
            assert Path(actual) == private / "relative.sqlite3"
            assert private.stat().st_mode & 0o777 == 0o700
            for suffix in ("", "-wal", "-shm"):
                assert Path(actual + suffix).stat().st_mode & 0o777 == 0o600
    finally:
        eng.dispose()


@pytest.mark.parametrize(
    "url",
    ["sqlite:///:memory:", "sqlite://", "sqlite:///file:test?mode=memory&uri=true"],
)
def test_engine_itself_rejects_non_file_databases(url: str) -> None:
    with pytest.raises(ValueError):
        create_engine_for_url(url)


def test_default_path_does_not_depend_on_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(settings.DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(settings.DATABASE_URL_ENV_VAR, raising=False)
    original = settings.database_path()
    monkeypatch.chdir(tmp_path)
    assert settings.database_path() == original


def test_downgrade_removes_tables_and_reupgrade_recovers(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    with Session(engine) as active:
        active.add(make_session())
        active.commit()

    command.downgrade(alembic_config(db_url), "base")
    assert set(table_columns(engine)) == {"alembic_version"}

    upgrade(db_url)
    assert set(table_columns(engine)) >= {"practice_session", "problem_instance"}


def test_foreign_key_check_and_unique_constraints(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    with Session(engine) as active:
        active.add(make_session())
        active.commit()

    with Session(engine) as active:
        orphan = make_problem(uuid.uuid4())
        active.add(orphan)
        with pytest.raises(IntegrityError):
            active.flush()
        active.rollback()

        target = active.query(PracticeSession).one()
        active.add(make_problem(target.id, position=0))
        active.flush()
        active.add(make_problem(target.id, position=0))
        with pytest.raises(IntegrityError):
            active.flush()
        active.rollback()

        bad_status = make_problem(target.id, position=1)
        bad_status.status = "graded"
        active.add(bad_status)
        with pytest.raises(IntegrityError):
            active.flush()
        active.rollback()

        bad_version = make_problem(target.id, position=1)
        bad_version.template_version = 0
        active.add(bad_version)
        with pytest.raises(IntegrityError):
            active.flush()
        active.rollback()

        assert active.query(ProblemInstance).count() == 0


def test_failed_transaction_rolls_back(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    with Session(engine) as active:
        active.add(make_session())
        active.add(make_problem(uuid.uuid4()))
        with pytest.raises(IntegrityError):
            active.commit()
        active.rollback()
        assert active.query(PracticeSession).count() == 0
        assert active.query(ProblemInstance).count() == 0


def test_data_survives_engine_reopen(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    learner = uuid.uuid4()
    with Session(engine) as active:
        session = make_session(learner)
        active.add(session)
        active.add(make_problem(session.id))
        active.commit()
    engine.dispose()

    reopened = create_engine_for_url(db_url)
    try:
        with Session(reopened) as active:
            stored = active.query(PracticeSession).one()
            problem = active.query(ProblemInstance).one()
            assert stored.learner_id == learner
            assert problem.session_id == stored.id
            assert problem.parameters == {"a": "1/2", "b": "1/3"}
            assert problem.expected_result == {"value": "5/6"}
            assert isinstance(problem.id, uuid.UUID)
            assert problem.created_at.tzinfo is not None
    finally:
        reopened.dispose()


def test_utc_adapter_rejects_naive_and_normalizes_zones(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    with Session(engine) as active:
        target = make_session()
        target.created_at = datetime(2026, 9, 6, 12, 0)  # naive: no tzinfo
        active.add(target)
        with pytest.raises(StatementError) as exc_info:
            active.flush()
        assert isinstance(exc_info.value.orig, ValueError)
        active.rollback()

    offset = timezone(timedelta(hours=2))
    with Session(engine) as active:
        target = make_session()
        target.created_at = datetime(2026, 9, 6, 12, 0, tzinfo=offset)
        active.add(target)
        active.commit()
        stored_id = target.id

    with Session(engine) as active:
        stored = active.get(PracticeSession, stored_id)
        assert stored is not None
        assert stored.created_at == datetime(2026, 9, 6, 10, 0, tzinfo=UTC)


def test_uuid_adapter_round_trips_and_rejects_garbage(engine: Engine, db_url: str) -> None:
    upgrade(db_url)
    with Session(engine) as active:
        target = make_session()
        active.add(target)
        active.commit()
        assert isinstance(target.learner_id, uuid.UUID)

    with Session(engine) as active:
        target = make_session(uuid.uuid4())
        active.add(target)
        active.flush()
        raw = active.execute(
            sqlalchemy.text("SELECT learner_id FROM practice_session WHERE id = :id"),
            {"id": str(target.id)},
        ).scalar()
        assert raw == str(target.learner_id)
        active.rollback()

    with Session(engine) as active:
        broken = PracticeSession()
        broken.learner_id = "not-a-uuid"  # type: ignore[assignment]
        active.add(broken)
        with pytest.raises(StatementError) as exc_info:
            active.flush()
        assert isinstance(exc_info.value.orig, ValueError)
        active.rollback()


def test_settings_resolve_one_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "sub" / "app.sqlite3"
    url = f"sqlite+pysqlite:///{db_file}"
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, url)

    assert settings.database_path() == db_file.absolute()

    monkeypatch.chdir(tmp_path)
    assert settings.database_path() == db_file.absolute()


def test_settings_reject_non_sqlite_and_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, "postgresql://db/app")
    with pytest.raises(ValueError, match="only local SQLite"):
        settings.database_path()

    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, "sqlite:///:memory:")
    with pytest.raises(ValueError, match="file-backed"):
        settings.database_path()


def test_settings_default_uses_private_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(settings.DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv(settings.DATA_DIR_ENV_VAR, str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)

    assert settings.database_path() == (tmp_path / "data" / settings.DEFAULT_DB_FILENAME)


def test_sqlite_runtime_meets_floor() -> None:
    assert settings.require_supported_sqlite() >= settings.MIN_SQLITE_VERSION


def test_cli_db_validates_temporary_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_file = tmp_path / "cli.sqlite3"
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, f"sqlite+pysqlite:///{db_file}")

    assert cli.main(["db"]) == 0
    assert db_file.exists()
    assert "journal_mode: wal" in capsys.readouterr().out


def test_cli_db_rejects_unsupported_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(settings.DATABASE_URL_ENV_VAR, "postgresql://db/app")

    assert cli.main(["db"]) == 1
    assert "error" in capsys.readouterr().err


def test_serialized_problem_holds_no_hidden_answer_on_reopen(engine: Engine, db_url: str) -> None:
    """Persistence keeps the hidden answer while the public schema hides it."""

    from math_tutor.api.schemas import ProblemInstancePublic

    upgrade(db_url)
    with Session(engine) as active:
        session = make_session()
        active.add(session)
        active.add(make_problem(session.id))
        active.commit()
    engine.dispose()

    reopened = create_engine_for_url(db_url)
    try:
        with Session(reopened) as active:
            problem = active.query(ProblemInstance).one()
            assert problem.expected_result == {"value": "5/6"}
            dumped: dict[str, Any] = ProblemInstancePublic.model_validate(problem).model_dump()
            assert "expected_result" not in dumped
    finally:
        reopened.dispose()
