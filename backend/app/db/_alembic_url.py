"""Escape a SQLAlchemy URL for `alembic.config.Config.set_main_option`.

`Config` is backed by `configparser.ConfigParser` with `BasicInterpolation`
enabled. A literal `%` in the value (e.g. a URL-encoded `%` in an
RDS-rotated password) raises `InterpolationSyntaxError` on the next
read. Doubling `%` survives interpolation as a single `%` and SQLAlchemy
URL-decodes it back to the original character.

Lives outside `backend/alembic/env.py` so the escape can be imported by
the regression test without triggering alembic's migration entrypoint at
import time. If alembic ever switches to `RawConfigParser` (no
interpolation), delete this helper and the test will fail loud as the
intended signal to revisit env.py's call site.
"""

from __future__ import annotations


def escape_for_configparser(url: str) -> str:
    return url.replace("%", "%%")
