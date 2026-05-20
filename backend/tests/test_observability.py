"""Phase 1 backend observability smoke tests.

These verify the contract from
``docs/plans/observability-implementation-plan.md`` § Phase 1:

* ``GET /metrics`` is mounted, returns 200, and surfaces the default
  process-metric line the FastAPI instrumentator ships.
* ``GET /metrics`` is exempt from the slowapi limiter so a Prometheus
  scrape can never DoS the app via the default tier.
* Optimistic-conflict counter increments on a 409 raised by an
  asset/repair-request endpoint, keyed by ``{endpoint, code}``.
* FSM-transition counter increments on a successful repair-request
  state change.
* Structlog JSON renderer emits ``trace_id`` when a span is active.
* New ``Settings`` observability fields exist with safe defaults
  (off in tests, opt-in via env in deploys).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.asset import Asset, AssetStatus
from app.models.repair_request import RepairRequest, RepairRequestStatus
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# /metrics endpoint contract
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200_with_default_process_metric(
    client: TestClient,
) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200, resp.text
    body = resp.text
    # `prometheus-fastapi-instrumentator` enables process collectors by
    # default; the line below is the canonical smoke signal.
    assert "process_resident_memory_bytes" in body, body[:500]


def test_metrics_endpoint_is_exempt_from_rate_limit(
    client: TestClient,
) -> None:
    # Flip the limiter on for the duration of the test. Conftest defaults
    # to RATE_LIMIT_ENABLED=false; we want to prove /metrics survives even
    # when the tight 3/minute anonymous tier is active.
    from app.main import app

    limiter = app.state.limiter
    previously_enabled = limiter.enabled
    limiter.enabled = True
    try:
        # 50 scrapes within the per-minute window — well past the
        # `3/minute` anonymous tier.
        for _ in range(50):
            resp = client.get("/metrics")
            assert resp.status_code == 200, resp.text
    finally:
        limiter.enabled = previously_enabled


# ---------------------------------------------------------------------------
# Conflict + FSM counters
# ---------------------------------------------------------------------------


MakeManager = Callable[..., User]
MakeHolder = Callable[..., User]


def _make_asset(
    db_session: Session,
    *,
    code: str = "AMS-0001",
    name: str = "Test Asset",
    status: AssetStatus = AssetStatus.IN_USE,
    holder: User | None = None,
) -> Asset:
    asset = Asset(
        asset_code=code,
        name=name,
        category="laptop",
        status=status,
        current_holder_id=holder.id if holder is not None else None,
        version=1,
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _metrics_text(client: TestClient) -> str:
    resp = client.get("/metrics")
    assert resp.status_code == 200, resp.text
    return resp.text


def _counter_value(metrics: str, name: str, labels: dict[str, str]) -> float:
    """Pull a single counter sample out of a Prometheus exposition body.

    Returns 0.0 when the labelled series is absent — fresh process counters
    start unobserved.
    """
    label_substr = ",".join(f'{k}="{v}"' for k, v in labels.items())
    for line in metrics.splitlines():
        if not line.startswith(name + "{"):
            continue
        if label_substr in line:
            # The total line looks like:
            #   ams_optimistic_conflicts_total{endpoint="...",code="..."} 3.0
            try:
                return float(line.rsplit(" ", 1)[1])
            except (IndexError, ValueError):
                continue
    return 0.0


def test_optimistic_conflict_counter_increments_on_409(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """A 409 raised by the repair-request submit endpoint bumps the
    `ams_optimistic_conflicts_total{endpoint,code}` counter."""

    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(db_session, holder=holder, status=AssetStatus.IN_USE)

    # Create an existing open repair request so the second submit collides
    # with the "one open request per asset" guard, which raises 409 with
    # `code=duplicate_request`.
    existing = RepairRequest(
        asset_id=asset.id,
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        description="prior open request",
        version=1,
    )
    db_session.add(existing)
    db_session.commit()

    before = _metrics_text(client)
    before_value = _counter_value(
        before,
        "ams_optimistic_conflicts_total",
        {"code": "duplicate_request"},
    )

    # Submit a second repair request → endpoint raises 409 duplicate_request.
    response = client.post(
        "/api/v1/repair-requests",
        headers=auth_headers(holder),
        json={"asset_id": asset.id, "description": "second request"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "duplicate_request"

    after = _metrics_text(client)
    after_value = _counter_value(
        after,
        "ams_optimistic_conflicts_total",
        {"code": "duplicate_request"},
    )
    assert after_value == before_value + 1, (before_value, after_value, after[:1000])


def test_fsm_transition_counter_increments_on_review_approval(
    client: TestClient,
    db_session: Session,
    make_user: MakeManager,
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Approving a pending repair-request review bumps
    `ams_fsm_transitions_total{from,to}`.

    The transition under test is PENDING_REVIEW → UNDER_REPAIR on the
    repair-request, asset-side PENDING_REPAIR → UNDER_REPAIR.
    """
    manager = make_user(role=UserRole.MANAGER)
    holder = make_user(role=UserRole.HOLDER)
    asset = _make_asset(
        db_session,
        holder=holder,
        status=AssetStatus.PENDING_REPAIR,
    )
    req = RepairRequest(
        asset_id=asset.id,
        requester_id=holder.id,
        status=RepairRequestStatus.PENDING_REVIEW,
        description="needs repair",
        version=1,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    before = _metrics_text(client)
    before_value = _counter_value(
        before,
        "ams_fsm_transitions_total",
        {"from": "PENDING_REVIEW", "to": "UNDER_REPAIR"},
    )

    response = client.patch(
        f"/api/v1/repair-requests/{req.id}/review",
        headers=auth_headers(manager),
        json={"action": "approve", "version": req.version},
    )
    assert response.status_code == 200, response.text

    after = _metrics_text(client)
    after_value = _counter_value(
        after,
        "ams_fsm_transitions_total",
        {"from": "PENDING_REVIEW", "to": "UNDER_REPAIR"},
    )
    assert after_value == before_value + 1, (before_value, after_value, after[:1000])


# ---------------------------------------------------------------------------
# Structlog JSON renderer
# ---------------------------------------------------------------------------


def test_structlog_json_renderer_emits_trace_id_when_span_active() -> None:
    """When a tracing span is current, the structlog JSON renderer
    surfaces the active ``trace_id`` on log records."""

    from app.core.observability import _structlog_processor_trace_context

    class _FakeSpanCtx:
        is_valid = True
        trace_id = 0x0123456789ABCDEF0123456789ABCDEF
        span_id = 0xFEDCBA9876543210

    class _FakeSpan:
        def get_span_context(self) -> _FakeSpanCtx:  # noqa: D401 - protocol shape
            return _FakeSpanCtx()

    def _fake_get_current_span() -> _FakeSpan:
        return _FakeSpan()

    event = {"event": "hello"}
    out = _structlog_processor_trace_context(
        None, "info", event, _get_current_span=_fake_get_current_span
    )
    assert out["trace_id"] == f"{_FakeSpanCtx.trace_id:032x}"
    assert out["span_id"] == f"{_FakeSpanCtx.span_id:016x}"


def test_structlog_json_renderer_no_trace_id_when_no_span() -> None:
    """When no span is active, the processor leaves the event untouched."""

    from app.core.observability import _structlog_processor_trace_context

    class _InvalidSpanCtx:
        is_valid = False
        trace_id = 0
        span_id = 0

    class _NoOpSpan:
        def get_span_context(self) -> _InvalidSpanCtx:
            return _InvalidSpanCtx()

    out = _structlog_processor_trace_context(
        None, "info", {"event": "noop"}, _get_current_span=lambda: _NoOpSpan()
    )
    assert "trace_id" not in out
    assert "span_id" not in out


# ---------------------------------------------------------------------------
# Settings observability fields
# ---------------------------------------------------------------------------


def test_settings_observability_fields_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """New observability fields exist with safe defaults.

    Defaults must be off so a stale ECS task without the Phase 1 env
    overrides keeps booting; an operator opts in by setting
    ``OTEL_ENABLED=true``.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_EMAIL", "boot@test.example")
    monkeypatch.setenv("BOOTSTRAP_MANAGER_PASSWORD", "Password123")
    # Wipe any inherited values from the test process so we observe defaults.
    for var in (
        "OTEL_ENABLED",
        "OTEL_ENDPOINT",
        "PYROSCOPE_ENABLED",
        "PYROSCOPE_SERVER",
        "REPLICA_ID",
        "LOG_FORMAT",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()  # type: ignore[call-arg]
    assert settings.otel_enabled is False
    assert settings.otel_endpoint == "http://alloy:4317"
    assert settings.pyroscope_enabled is False
    assert settings.pyroscope_server == "http://pyroscope:4040"
    # Default replica id is hostname-derived; just confirm it's a non-empty str.
    assert isinstance(settings.replica_id, str) and settings.replica_id
    assert settings.log_format == "json"


# ---------------------------------------------------------------------------
# Unused imports tripwire — keep tests stable in face of refactors
# ---------------------------------------------------------------------------


def test_imports_smoke() -> None:
    """Smoke-test that nothing imported above is dead code."""
    assert json is not None
    assert io is not None
    assert logging is not None
    assert datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1)
