"""Startup-time invariants enforced by app.main.

Currently covers the multi-worker hard-fail (P2). Per
``docs/system-design/08-deployment-operations.md`` §"API Hardening: Rate
Limiting", multi-worker deploys multiply the effective rate-limit cap by N
because slowapi's MemoryStorage is per-process. Phase 2 mandates
``--workers 1`` until Phase 3 introduces Redis-backed shared storage.

Two env-var conventions are checked:

* ``WEB_CONCURRENCY`` — tiangolo / uvicorn-gunicorn-fastapi convention.
* ``GUNICORN_WORKERS`` — the convention this repo's ``Dockerfile.prod``
  used historically; the prod image now defaults to ``WEB_CONCURRENCY=1``
  but old task definitions in the wild may still set ``GUNICORN_WORKERS``.

Either one above 1 trips the same hard-fail.
"""

from __future__ import annotations

import pytest


def test_invariant_passes_when_workers_is_one() -> None:
    """The default deploy shape (single worker) must not raise."""
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    # Explicit single worker: no raise.
    _enforce_single_worker_invariant(settings, web_concurrency_raw="1")


def test_invariant_passes_when_workers_unset() -> None:
    """Unset WEB_CONCURRENCY defaults to single-worker → no raise.

    The default Phase 1 deployment (single uvicorn process under docker
    compose) does not set WEB_CONCURRENCY at all. Must not regress to
    a startup error in dev.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    _enforce_single_worker_invariant(settings, web_concurrency_raw=None)


@pytest.mark.parametrize("workers", ["2", "4", "16"])
def test_invariant_hard_fails_when_web_concurrency_gt_one(workers: str) -> None:
    """The load-bearing case: WEB_CONCURRENCY > 1 + rate-limit enabled → RuntimeError.

    Multi-worker MemoryStorage means a user's effective per-minute cap is
    N× the configured value. Per CLAUDE.md "no silent failures" and
    08-deployment-operations.md §"keep --workers 1", we refuse to boot.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    with pytest.raises(RuntimeError) as excinfo:
        _enforce_single_worker_invariant(settings, web_concurrency_raw=workers)

    # Message must tell the operator what to do, not just that something is wrong.
    msg = str(excinfo.value)
    assert "WEB_CONCURRENCY" in msg
    assert "--workers 1" in msg or "single worker" in msg.lower()


@pytest.mark.parametrize("workers", ["2", "4", "16"])
def test_invariant_hard_fails_when_gunicorn_workers_gt_one(workers: str) -> None:
    """Same hard-fail must trigger for GUNICORN_WORKERS.

    Historical Dockerfile.prod and ECS task definitions set
    ``GUNICORN_WORKERS=2``. The invariant must catch this convention too,
    not just WEB_CONCURRENCY, or operators with a stale task-def boot a
    silently-broken rate limiter.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    with pytest.raises(RuntimeError) as excinfo:
        _enforce_single_worker_invariant(
            settings,
            web_concurrency_raw=None,
            gunicorn_workers_raw=workers,
        )

    msg = str(excinfo.value)
    assert "GUNICORN_WORKERS" in msg
    assert "--workers 1" in msg or "single worker" in msg.lower()


def test_invariant_hard_fails_when_one_of_two_violates() -> None:
    """If either env var is > 1, refuse to boot — even when the other is sane.

    Operator edits ``GUNICORN_WORKERS=4`` but leaves ``WEB_CONCURRENCY=1``;
    gunicorn obeys the higher value. The invariant must trip on the
    violating var rather than silently passing because the other is 1.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    with pytest.raises(RuntimeError) as excinfo:
        _enforce_single_worker_invariant(
            settings,
            web_concurrency_raw="1",
            gunicorn_workers_raw="4",
        )

    # Error message must name the offending env var so the operator knows
    # which knob to turn.
    assert "GUNICORN_WORKERS" in str(excinfo.value)


def test_invariant_passes_when_both_vars_set_to_one() -> None:
    """Belt-and-suspenders: task-def setting both to "1" must still boot."""
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    _enforce_single_worker_invariant(
        settings,
        web_concurrency_raw="1",
        gunicorn_workers_raw="1",
    )


def test_invariant_silent_when_rate_limit_disabled_even_with_many_workers() -> None:
    """If rate limiting is off, the multi-worker concern is moot.

    Edge case: a load-test environment intentionally runs RATE_LIMIT_ENABLED=false
    with multiple workers to measure raw throughput. The invariant must
    not block that — RATE_LIMIT_ENABLED=false already triggers its own
    loud WARN (per commit 9f5dfde / S3), which is the appropriate signal.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=False,
    )

    # No raise even though WEB_CONCURRENCY=8.
    _enforce_single_worker_invariant(settings, web_concurrency_raw="8")


def test_invariant_tolerates_malformed_values() -> None:
    """Garbled values should not crash startup with ValueError.

    ECS task definitions are operator-edited; a stray ``WEB_CONCURRENCY=auto``
    or empty string should degrade gracefully (treat as unset = single worker)
    rather than producing a confusing ValueError that looks unrelated to
    rate limiting. Same applies to GUNICORN_WORKERS.
    """
    from app.core.config import Settings
    from app.main import _enforce_single_worker_invariant

    settings = Settings(
        database_url="sqlite:///:memory:",
        jwt_secret="x" * 32,  # noqa: S106
        rate_limit_enabled=True,
    )

    # Each of these would have crashed `int(...)` — invariant must absorb them.
    for bad in ["", "auto", "  ", "not-a-number"]:
        _enforce_single_worker_invariant(settings, web_concurrency_raw=bad)
        _enforce_single_worker_invariant(
            settings, web_concurrency_raw=None, gunicorn_workers_raw=bad
        )
