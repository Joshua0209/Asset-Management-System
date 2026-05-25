"""Alembic migration vs ORM-metadata drift detector.

The journey suite builds schema via ``Base.metadata.create_all`` (see
``conftest.py``), which **does not** exercise the alembic chain. That means
a PR can ship an ORM-model change without a matching migration, and every
SQLite test will still pass — only the next real MySQL deploy will explode.

This file closes that gap. It runs the full ``alembic upgrade head``
against a live MySQL instance, then uses ``sqlalchemy.inspect``
(Inspector) to compare the resulting schema against ``Base.metadata``
table-by-table.

Why MySQL and not SQLite: migration ``20260504_0002_widen_repair_vendor``
emits ``ALTER COLUMN TYPE``, a syntax SQLite does not implement. The
migrations are written for MySQL 8 (our production target); they cannot
be run end-to-end against SQLite without rewriting every alter into
``op.batch_alter_table``. The honest answer is to exercise them against
a real MySQL.

How to run locally::

    docker compose up -d mysql
    TEST_MYSQL_URL='mysql+pymysql://root:password@127.0.0.1:3306' \\
        .venv/bin/pytest backend/tests/test_migration_schema_drift.py -v

The test creates and drops a throwaway database on each run so it never
collides with the dev/seeded ``asset_management`` database.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from typing import Any, cast

import pytest
from sqlalchemy import Column, create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine, make_url

from app.db.base import Base
from app.models import (  # noqa: F401  — register all tables on Base.metadata
    asset,
    asset_action_history,
    repair_image,
    repair_request,
    user,
)

_TEST_MYSQL_URL = os.environ.get("TEST_MYSQL_URL")
_SKIP_REASON = (
    "TEST_MYSQL_URL is not set. Migration drift can only be detected against "
    "a real MySQL server because the migration chain uses ALTER COLUMN TYPE "
    "(not supported by SQLite). Run `docker compose up -d mysql` then set "
    "TEST_MYSQL_URL='mysql+pymysql://root:password@127.0.0.1:3306'."
)


@pytest.fixture
def mysql_engine() -> Generator[Engine, None, None]:
    """Provision a throwaway MySQL database and yield an engine bound to it.

    Why a throwaway DB and not the seeded one: the inspector reports
    every table and column that exists, and the seeded
    ``asset_management`` database carries app rows + indexes from prior
    runs that could mask drift. Starting from a fresh CREATE DATABASE
    guarantees the only objects present are the ones the migration
    chain put there.
    """
    if not _TEST_MYSQL_URL:
        pytest.skip(_SKIP_REASON)

    base_url = make_url(_TEST_MYSQL_URL)
    db_name = f"ams_drift_{uuid.uuid4().hex[:8]}"
    server_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with server_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4"))

        scoped_url = base_url.set(database=db_name)
        engine = create_engine(scoped_url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        with server_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{db_name}`"))
        server_engine.dispose()


def _run_alembic_upgrade(engine: Engine) -> None:
    """Run ``alembic upgrade head`` against the given engine.

    Imports alembic lazily so the rest of the suite is not slowed down
    by the alembic config load when this test is skipped.

    Why the env-var dance: ``backend/alembic/env.py`` calls
    ``get_settings().sqlalchemy_database_url`` and overrides whatever
    URL the caller put on the Config object. Since ``conftest.py`` set
    ``DATABASE_URL=sqlite:///:memory:`` at import time, just passing the
    MySQL URL via ``cfg.set_main_option`` is silently ignored. We have
    to (1) clear the lru_cache on ``get_settings``, (2) point the env
    var at the MySQL engine for the duration of the upgrade, then
    (3) restore both — anything less and the migration runs against
    SQLite and explodes on the first ``ALTER COLUMN TYPE``.
    """
    import pathlib

    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings

    alembic_ini = pathlib.Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    # ``str(engine.url)`` masks the password as ``***`` — alembic would
    # then auth with the literal string and MySQL returns "Access denied".
    # ``render_as_string(hide_password=False)`` keeps the password intact.
    plain_url = engine.url.render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", plain_url)

    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = plain_url
    get_settings.cache_clear()
    try:
        command.upgrade(cfg, "head")
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        get_settings.cache_clear()


# Alembic itself owns the bookkeeping table ``alembic_version``; it is
# not part of the ORM model and must be excluded from the comparison.
_NON_APP_TABLES = frozenset({"alembic_version"})


_MYSQL_DIALECT = mysql.dialect()


def _normalise_type(raw_type: object) -> str:
    """Render a column type into a MySQL-comparable string.

    Both sides — Inspector results from MySQL, and ``sqlalchemy.types.*``
    instances on ORM columns — get compiled against the MySQL dialect.
    That collapses three false-positive classes that the dialect-less
    default rendering would otherwise produce:

    - ``Enum(MyEnum)`` on the ORM compiles to ``VARCHAR(N)`` under no
      dialect, but to ``ENUM('a','b',...)`` under MySQL — same value
      MySQL gives back from ``get_columns``.
    - ``Numeric(15, 2)`` renders as ``NUMERIC(15, 2)`` by default but
      as ``DECIMAL(15, 2)`` on MySQL — MySQL treats both as aliases.
    - ``Boolean`` renders as ``BOOL`` by default but as ``TINYINT(1)``
      on MySQL — same storage, different surface name.

    Compiling against ``mysql.dialect()`` makes both sides agree on the
    physical type MySQL actually stores; genuine drift (wrong length,
    wrong precision, different base type) still surfaces.
    """
    if hasattr(raw_type, "compile"):
        rendered = str(raw_type.compile(dialect=_MYSQL_DIALECT))
    else:
        rendered = str(raw_type)
    rendered = rendered.upper()
    # MySQL treats NUMERIC and DECIMAL as exact synonyms (CREATE TABLE
    # ... NUMERIC(15,2) stores identically to DECIMAL(15,2) and the
    # information_schema reports back DECIMAL). SQLAlchemy's MySQL
    # dialect keeps Numeric / DECIMAL as separate type classes, so the
    # ORM side compiles to NUMERIC while Inspector reports DECIMAL.
    # Collapse to one canonical form to avoid a false-positive drift.
    if rendered.startswith("NUMERIC"):
        rendered = "DECIMAL" + rendered[len("NUMERIC") :]
    return rendered


def _column_signature(column: object, *, source: str) -> dict[str, object]:
    """Reduce a column (DB or ORM) to a comparable signature dict.

    Two columns are considered "the same" iff their signatures are
    equal. We compare type + nullability only; primary-key membership
    is checked separately via ``get_pk_constraint`` (MySQL Inspector's
    ``get_columns`` does NOT populate the per-column ``primary_key``
    flag, so comparing it here would generate false positives on every
    PK column). Server-side defaults and column comments are also
    skipped — they drift in ways orthogonal to schema correctness.

    Parameters
    ----------
    column:
        Either a dict from ``Inspector.get_columns(...)`` (``source="db"``)
        or a ``sqlalchemy.Column`` instance (``source="orm"``).
    """
    if source == "db":
        col_dict = cast("dict[str, Any]", column)
        return {
            "type": _normalise_type(col_dict["type"]),
            "nullable": bool(col_dict["nullable"]),
        }
    orm_col = cast("Column[Any]", column)
    return {
        "type": _normalise_type(orm_col.type),
        "nullable": bool(orm_col.nullable),
    }


def test_migrations_match_orm_metadata(mysql_engine: Engine) -> None:
    """`alembic upgrade head` must yield the same schema as `Base.metadata`.

    Three drift classes this catches that no other test in the suite
    does:

    - **Model added without migration**: a new ``Column`` / table
      exists in ``app.models`` but no ``op.add_column`` /
      ``op.create_table`` lands. Reads work locally because
      ``metadata.create_all`` builds it; production explodes on the
      first query touching it.
    - **Migration drifted from model**: a hotfix ``op.alter_column``
      ran in staging but the ORM never followed. Reads still work via
      the ORM, but every write through the un-mapped column silently
      loses the new field.
    - **Type / nullability drift**: a ``String(120)`` widened to
      ``String(200)`` in one place but not the other; a
      ``nullable=False`` flipped only on one side. The next ``ALTER``
      against a populated prod table fails on the data the model
      thought it could write.

    The remediation is always "make the two sides agree" — either
    author the missing migration with ``alembic revision --autogenerate``
    or align the ORM to what the migration actually does. Never silence
    this test by changing the assertion.
    """
    _run_alembic_upgrade(mysql_engine)
    inspector = inspect(mysql_engine)

    db_tables = set(inspector.get_table_names()) - _NON_APP_TABLES
    model_tables = set(Base.metadata.tables.keys())
    missing_in_db = model_tables - db_tables
    unexpected_in_db = db_tables - model_tables
    assert not missing_in_db, (
        f"ORM declares tables that the migration chain does not create: "
        f"{sorted(missing_in_db)}. Add a migration with `op.create_table(...)`."
    )
    assert not unexpected_in_db, (
        f"Migration chain creates tables not declared in ORM models: "
        f"{sorted(unexpected_in_db)}. Either drop them or add the model."
    )

    drift: list[str] = []
    for table_name in sorted(model_tables):
        model_table = Base.metadata.tables[table_name]

        db_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        model_columns = {c.name: c for c in model_table.columns}

        missing_cols = set(model_columns) - set(db_columns)
        unexpected_cols = set(db_columns) - set(model_columns)
        if missing_cols:
            drift.append(
                f"{table_name}: ORM declares columns missing from DB: "
                f"{sorted(missing_cols)}. Add `op.add_column(...)` in a new migration."
            )
        if unexpected_cols:
            drift.append(
                f"{table_name}: DB has columns not declared in ORM: "
                f"{sorted(unexpected_cols)}. Either drop them or extend the model."
            )

        for col_name in sorted(set(model_columns) & set(db_columns)):
            db_sig = _column_signature(db_columns[col_name], source="db")
            orm_sig = _column_signature(model_columns[col_name], source="orm")
            if db_sig != orm_sig:
                drift.append(
                    f"{table_name}.{col_name}: ORM {orm_sig} != DB {db_sig}"
                )

        # Primary key membership — keep this as a second check so a
        # missing PK constraint surfaces with its own clear line rather
        # than only via per-column primary_key flags.
        db_pk = set(inspector.get_pk_constraint(table_name).get("constrained_columns", []))
        orm_pk = {c.name for c in model_table.primary_key.columns}
        if db_pk != orm_pk:
            drift.append(
                f"{table_name}: ORM PK {sorted(orm_pk)} != DB PK {sorted(db_pk)}"
            )

        # Foreign keys — match by (referred_table, constrained_columns,
        # referred_columns). We do not compare FK names because alembic
        # autogenerates names that differ from the ORM defaults and the
        # difference is not load-bearing.
        db_fks = {
            (
                fk["referred_table"],
                tuple(fk["constrained_columns"]),
                tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys(table_name)
        }
        orm_fks = {
            (
                fk.column.table.name,
                (fk.parent.name,),
                (fk.column.name,),
            )
            for fk in model_table.foreign_keys
        }
        if db_fks != orm_fks:
            drift.append(
                f"{table_name}: foreign keys differ. ORM {sorted(orm_fks)} != "
                f"DB {sorted(db_fks)}"
            )

    if drift:
        raise AssertionError(
            "Alembic migration chain and Base.metadata have drifted:\n"
            + "\n".join(f"  - {line}" for line in drift)
        )
