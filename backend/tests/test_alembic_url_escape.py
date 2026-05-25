"""Regression test for the `%` escape applied in ``backend/alembic/env.py``.

``alembic.config.Config`` is backed by ``configparser.ConfigParser`` with
``BasicInterpolation`` enabled. Any literal ``%`` in a value passed to
``set_main_option`` raises ``InterpolationSyntaxError`` on the next read
(e.g. through ``engine_from_config``). RDS-rotated passwords can contain
URL-encoded ``%`` sequences, which is exactly the failure mode the
in-env.py escape exists to prevent.

This test imports ``escape_for_configparser`` from
``app/db/_alembic_url.py`` — the same helper ``env.py`` uses — so a
future refactor that drops the escape either deletes the function (test
fails to import) or changes its behaviour (the round-trip assertion
breaks). Importing from ``backend/alembic/env.py`` directly is unsafe
because that module runs migrations at module-import time.
"""

from __future__ import annotations

import pytest
from alembic.config import Config

from app.db._alembic_url import escape_for_configparser


def test_set_main_option_with_percent_in_password_round_trips() -> None:
    """`%` in the URL must survive a Config write+read cycle."""
    url = "mysql+pymysql://user:p%40ss%25word@host:3306/db"
    config = Config()
    config.set_main_option("sqlalchemy.url", escape_for_configparser(url))
    assert config.get_main_option("sqlalchemy.url") == url


def test_set_main_option_without_percent_unchanged() -> None:
    """The escape must be a no-op when the URL contains no `%`."""
    url = "mysql+pymysql://user:password@host:3306/db"
    config = Config()
    config.set_main_option("sqlalchemy.url", escape_for_configparser(url))
    assert config.get_main_option("sqlalchemy.url") == url


def test_unescaped_percent_raises_at_set_time() -> None:
    """Sanity check: the unescaped form really does break ConfigParser.

    BasicInterpolation validates at write time via ``before_set``, so
    the failure surfaces on ``set_main_option`` itself rather than on
    a later read. Asserts on ``ValueError`` (which alembic re-raises
    the underlying ``InterpolationSyntaxError`` as) without matching on
    message text — wording is owned by stdlib configparser and could
    drift across Python versions. If a future alembic switches to
    ``RawConfigParser`` (no interpolation) this assertion would fail
    and the escape could be removed — that's a deliberate signal, not
    a flake.
    """
    url = "mysql+pymysql://user:p%40ss@host:3306/db"
    config = Config()
    with pytest.raises(ValueError):
        config.set_main_option("sqlalchemy.url", url)
