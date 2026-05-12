"""Guard against multiple-head alembic migration trees.

Multi-head migration trees only break at runtime when `alembic upgrade head`
is run against a real database, with the error "Multiple head revisions are
present". The SQLite-only test suite builds schema via Base.metadata.create_all
and never exercises the alembic chain, so multi-head bugs slip past every
other test.

This structural test loads the alembic script directory directly and asserts
that the chain is linear. Add it to CI and a future parallel-migration bug
will be caught at PR time instead of at deploy time.
"""

from __future__ import annotations

import pathlib

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = pathlib.Path(__file__).parent.parent / "alembic.ini"


def test_alembic_has_single_head() -> None:
    config = Config(str(ALEMBIC_INI))
    # alembic.ini uses a relative script_location; resolve it so the test
    # passes regardless of the pytest working directory.
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"Alembic migration chain has multiple heads: {heads}. "
        "This breaks `alembic upgrade head` at runtime. To fix, change one "
        "of the competing migrations' down_revision to chain after the other."
    )
