from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import DBAPIError, OperationalError

from alembic import context
from app.core.config import get_settings
from app.db._alembic_url import escape_for_configparser
from app.db.base import Base
from app.models import (  # noqa: F401
    asset,
    asset_action_history,
    repair_image,
    repair_request,
    user,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Escape literal `%` so configparser's BasicInterpolation does not raise
# InterpolationSyntaxError on the next read of sqlalchemy.url (e.g.
# through engine_from_config). The escape itself lives in
# app/db/_alembic_url.py so the regression test can import it directly
# rather than mirror it inline — see that module's docstring for the
# full rationale and the negative-case tripwire.
config.set_main_option(
    "sqlalchemy.url", escape_for_configparser(settings.sqlalchemy_database_url)
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    import sys

    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    except (OperationalError, DBAPIError) as exc:
        # Only rewrite connection-class errors with the operator-friendly
        # message. Programming errors (TypeError on a bad import, model-
        # mapper misconfiguration) propagate with their native traceback
        # instead of being mislabelled as "DATABASE_URL unreachable".
        print(
            "Migration failed. Ensure DATABASE_URL is set and the server is reachable. "
            f"Error: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
