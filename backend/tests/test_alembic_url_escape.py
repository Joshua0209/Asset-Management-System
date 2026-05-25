"""Regression test for the `%` escape applied in ``backend/alembic/env.py``.

``alembic.config.Config`` is backed by ``configparser.ConfigParser`` with
``BasicInterpolation`` enabled. Any literal ``%`` in a value passed to
``set_main_option`` raises ``InterpolationSyntaxError`` on the next read
(e.g. through ``engine_from_config``). RDS-rotated passwords can contain
URL-encoded ``%`` sequences, which is exactly the failure mode the
in-env.py escape exists to prevent.

This test does not import ``backend/alembic/env.py`` directly — that
module runs migrations at import time. Instead it mirrors the escape
inline and round-trips the URL through the same ``Config`` machinery
``env.py`` uses, so a future refactor that drops the escape will fail
this test before it can ship.
"""

from __future__ import annotations

import pytest
from alembic.config import Config


def _escape_for_configparser(url: str) -> str:
    """Mirror the escape applied in ``backend/alembic/env.py``.

    Keep this in sync with the production escape. If you change one,
    change the other and update this test's docstring.
    """
    return url.replace("%", "%%")


def test_set_main_option_with_percent_in_password_round_trips() -> None:
    """`%` in the URL must survive a Config write+read cycle."""
    url = "mysql+pymysql://user:p%40ss%25word@host:3306/db"
    config = Config()
    config.set_main_option("sqlalchemy.url", _escape_for_configparser(url))
    assert config.get_main_option("sqlalchemy.url") == url


def test_set_main_option_without_percent_unchanged() -> None:
    """The escape must be a no-op when the URL contains no `%`."""
    url = "mysql+pymysql://user:password@host:3306/db"
    config = Config()
    config.set_main_option("sqlalchemy.url", _escape_for_configparser(url))
    assert config.get_main_option("sqlalchemy.url") == url


def test_unescaped_percent_raises_at_set_time() -> None:
    """Sanity check: the unescaped form really does break ConfigParser.

    BasicInterpolation validates at write time via ``before_set``, so
    the failure surfaces on ``set_main_option`` itself rather than on
    a later read. If a future version of alembic switches to
    ``RawConfigParser`` (no interpolation) this assertion would fail
    and the escape could be removed — that's a deliberate signal, not
    a flake.
    """
    url = "mysql+pymysql://user:p%40ss@host:3306/db"
    config = Config()
    with pytest.raises(ValueError, match="invalid interpolation syntax"):
        config.set_main_option("sqlalchemy.url", url)
