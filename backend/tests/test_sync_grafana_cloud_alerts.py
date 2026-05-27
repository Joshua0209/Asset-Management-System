"""Unit tests for the alerts pass of the Grafana Cloud sync script.

Same script under test as `test_sync_grafana_cloud_dashboards.py`
(`scripts/sync_grafana_cloud_dashboards.py`) — split here only because
the dashboard test file is at the 800-line soft cap. The alerts pass
adds: `load_alert_resources`, `resolve_recipients`,
`apply_recipients_to_contact_point`, `post_contact_point`,
`post_notification_policy`, `post_alert_rule`, plus a `--targets` flag
on `main()` so existing callers keep working.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

sync_module = pytest.importorskip(
    "sync_grafana_cloud_dashboards",
    reason="sync script not yet implemented",
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_CONTACT_POINT_TEMPLATE: dict[str, Any] = {
    "uid": "email-default",
    "name": "email-default",
    "type": "email",
    "settings": {"addresses": "__PLACEHOLDER__"},
    "disableResolveMessage": False,
}

_NOTIFICATION_POLICY: dict[str, Any] = {
    "receiver": "email-default",
    "group_by": ["alertname", "severity"],
    "group_wait": "30s",
    "group_interval": "5m",
    "repeat_interval": "4h",
}


def _make_rule(uid: str, severity: str = "warning") -> dict[str, Any]:
    """Minimal alert-rule object matching the Grafana provisioning shape."""
    return {
        "uid": uid,
        "title": f"Test rule {uid}",
        "ruleGroup": severity,
        "folderUID": "ams-production",
        "condition": "C",
        "for": "5m",
        "noDataState": "NoData",
        "execErrState": "OK",
        "orgID": 1,
        "data": [
            {
                "refId": "A",
                "datasourceUid": "grafanacloud-prom",
                "model": {"expr": "up", "refId": "A"},
                "relativeTimeRange": {"from": 600, "to": 0},
            }
        ],
        "labels": {"severity": severity},
        "annotations": {},
        "notification_settings": {"receiver": "email-default"},
    }


def _write_alerts_layout(
    alerts_dir: Path,
    *,
    contact_point: dict[str, Any] | None = _CONTACT_POINT_TEMPLATE,
    notification_policy: dict[str, Any] | None = _NOTIFICATION_POLICY,
    rule_files: dict[str, dict[str, Any] | str] | None = None,
) -> Path:
    """Write a complete alerts layout under ``alerts_dir``.

    ``rule_files`` maps filename → either a dict (will be JSON-serialised)
    or a raw string (written verbatim, for malformed-JSON tests). Default
    creates a single ``rules/default.json`` with one rule.
    """
    alerts_dir.mkdir(parents=True, exist_ok=True)
    if contact_point is not None:
        (alerts_dir / "contact-points.json").write_text(json.dumps(contact_point))
    if notification_policy is not None:
        (alerts_dir / "notification-policy.json").write_text(
            json.dumps(notification_policy)
        )
    rules_dir = alerts_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    if rule_files is None:
        rule_files = {"default.json": {"rules": [_make_rule("ams-default-warning")]}}
    for name, payload in rule_files.items():
        path = rules_dir / name
        if isinstance(payload, str):
            path.write_text(payload)
        else:
            path.write_text(json.dumps(payload))
    return alerts_dir


# ---------------------------------------------------------------------------
# Cycle 1: load_alert_resources
# ---------------------------------------------------------------------------


def test_load_alert_resources_reads_all_required_files(tmp_path: Path) -> None:
    """Happy path: contact point + policy + rules from rules/*.json land
    on the returned AlertResources, no malformed entries."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={
            "backend-error-rate.json": {
                "rules": [
                    _make_rule("ams-backend-error-rate-warning", "warning"),
                    _make_rule("ams-backend-error-rate-critical", "critical"),
                ]
            }
        },
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert malformed == []
    assert resources.contact_point is not None
    assert resources.contact_point["uid"] == "email-default"
    assert resources.notification_policy is not None
    assert resources.notification_policy["receiver"] == "email-default"
    rule_uids = {r["uid"] for r in resources.rules}
    assert rule_uids == {
        "ams-backend-error-rate-warning",
        "ams-backend-error-rate-critical",
    }


def test_load_alert_resources_reports_missing_contact_points_as_malformed(
    tmp_path: Path,
) -> None:
    """``contact-points.json`` is required; absence is reported, not raised.

    Same graceful-degradation contract as ``load_dashboards``: a missing
    required file becomes a malformed-list entry that ``main()`` surfaces
    in the final summary, so the operator sees the actual cause instead
    of a bare stacktrace."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts", contact_point=None
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert resources.contact_point is None
    assert "contact-points.json" in malformed


def test_load_alert_resources_reports_missing_notification_policy_as_malformed(
    tmp_path: Path,
) -> None:
    """``notification-policy.json`` is required; absence is reported."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts", notification_policy=None
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert resources.notification_policy is None
    assert "notification-policy.json" in malformed


def test_load_alert_resources_reports_malformed_rule_json_as_malformed(
    tmp_path: Path,
) -> None:
    """A rule file with invalid JSON is reported but does NOT abort the
    load — valid rules from sibling files still come through.

    Mirrors the dashboard sync's behaviour (see
    ``test_load_dashboards_reports_malformed_json_as_malformed``)."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={
            "good.json": {"rules": [_make_rule("ams-good-warning")]},
            "bad.json": "{ not valid json",
        },
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert "bad.json" in malformed
    assert len(resources.rules) == 1
    assert resources.rules[0]["uid"] == "ams-good-warning"


def test_load_alert_resources_reports_rule_file_without_rules_key(
    tmp_path: Path,
) -> None:
    """Each rule file must wrap its rules in a top-level ``rules`` array.

    Defends against accidental flat-list files that would parse as JSON
    but expose no iterable for the publish loop, silently dropping the
    file's rules without a summary line."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={
            "broken.json": {"not_rules": []},
            "good.json": {"rules": [_make_rule("ams-good-warning")]},
        },
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert "broken.json" in malformed
    assert len(resources.rules) == 1


def test_load_alert_resources_aggregates_rules_from_multiple_files(
    tmp_path: Path,
) -> None:
    """All rules from every ``rules/*.json`` file land in ``resources.rules``."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={
            "a.json": {
                "rules": [
                    _make_rule("rule-a-warning"),
                    _make_rule("rule-a-critical", "critical"),
                ]
            },
            "b.json": {"rules": [_make_rule("rule-b-warning")]},
        },
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert malformed == []
    rule_uids = {r["uid"] for r in resources.rules}
    assert rule_uids == {"rule-a-warning", "rule-a-critical", "rule-b-warning"}


def test_load_alert_resources_rejects_rule_missing_uid(tmp_path: Path) -> None:
    """Each individual rule must carry a ``uid`` for idempotent upsert.

    Without this guard, a rule missing ``uid`` would either crash the
    publish loop or — worse — get re-created on every sync run because
    the script has no key to recognise it. Treat the whole file as
    malformed: the operator's editor is the right place to catch this,
    not GC's API."""
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={
            "missing-uid.json": {
                "rules": [{"title": "rule without uid", "data": []}]
            },
        },
    )

    resources, malformed = sync_module.load_alert_resources(alerts_dir)

    assert "missing-uid.json" in malformed
    assert resources.rules == ()


# ---------------------------------------------------------------------------
# Cycle 2: resolve_recipients + apply_recipients_to_contact_point
# ---------------------------------------------------------------------------


def test_resolve_recipients_cli_takes_priority_over_env() -> None:
    """CLI flag wins over the env var — operator's per-run override."""
    recipients = sync_module.resolve_recipients(
        cli="ops@example.com",
        env={"GC_ALERT_EMAIL_RECIPIENTS": "ignored@example.com"},
        dry_run=False,
    )

    assert recipients == ["ops@example.com"]


def test_resolve_recipients_falls_back_to_env() -> None:
    """No CLI flag: the env var supplies the list (CI path)."""
    recipients = sync_module.resolve_recipients(
        cli=None,
        env={"GC_ALERT_EMAIL_RECIPIENTS": "ops@example.com"},
        dry_run=False,
    )

    assert recipients == ["ops@example.com"]


def test_resolve_recipients_splits_csv_and_strips_whitespace() -> None:
    """Comma-separated input → list, with surrounding whitespace trimmed.

    Operators paste "ops@example.com, oncall@example.com" with a space
    after the comma; the script must not propagate that whitespace into
    the contact point or GC rejects the address as malformed."""
    recipients = sync_module.resolve_recipients(
        cli="ops@example.com, oncall@example.com ,  alerts@example.com",
        env={},
        dry_run=False,
    )

    assert recipients == [
        "ops@example.com",
        "oncall@example.com",
        "alerts@example.com",
    ]


def test_resolve_recipients_drops_empty_entries() -> None:
    """A trailing comma must not produce an empty recipient.

    ``"ops@example.com, "`` and ``"ops@example.com,,oncall@example.com"``
    are common typos. Both should yield only the real addresses without
    blank entries that GC would reject."""
    recipients = sync_module.resolve_recipients(
        cli="ops@example.com,,oncall@example.com,",
        env={},
        dry_run=False,
    )

    assert recipients == ["ops@example.com", "oncall@example.com"]


def test_resolve_recipients_validates_minimal_email_shape() -> None:
    """An entry that obviously isn't an email exits 2 with a clear error.

    Full RFC 5322 validation is overkill — the goal is to catch the
    common operator mistake of pasting a name or URL instead of an
    address. Anything matching ``*@*.*`` is accepted."""
    with pytest.raises(SystemExit) as exc_info:
        sync_module.resolve_recipients(
            cli="not-an-email",
            env={},
            dry_run=False,
        )

    assert exc_info.value.code == 2


def test_resolve_recipients_dry_run_tolerates_absence() -> None:
    """``--dry-run`` returns an empty list when no recipients are set.

    PR-side CI runs ``--dry-run`` without access to the
    ``GC_ALERT_EMAIL_RECIPIENTS`` secret. Forcing recipients in dry-run
    would block every fork PR. Return empty so the CI gate is purely
    structural (parses JSON, walks placeholders)."""
    recipients = sync_module.resolve_recipients(
        cli=None,
        env={},
        dry_run=True,
    )

    assert recipients == []


def test_resolve_recipients_live_mode_exits_when_missing() -> None:
    """Live mode without recipients exits 2 with a clear error.

    A live sync that silently sends to no addresses would leave the
    contact point in a "no recipients" state — alerts would fire but
    nobody would be paged. Fail fast instead."""
    with pytest.raises(SystemExit) as exc_info:
        sync_module.resolve_recipients(
            cli=None,
            env={},
            dry_run=False,
        )

    assert exc_info.value.code == 2


def test_resolve_recipients_blank_env_treated_as_unset() -> None:
    """Whitespace-only env var must not satisfy the live-mode requirement.

    Same defence as ``test_build_uid_remap_treats_blank_env_as_unset``
    in the dashboard tests — a frequent CI misconfiguration is a secret
    that resolves to empty/whitespace."""
    with pytest.raises(SystemExit):
        sync_module.resolve_recipients(
            cli=None,
            env={"GC_ALERT_EMAIL_RECIPIENTS": "   "},
            dry_run=False,
        )


def test_apply_recipients_to_contact_point_joins_with_semicolons() -> None:
    """Grafana's email contact point expects ``settings.addresses`` as a
    single semicolon-delimited string, not a JSON array."""
    template = {
        "uid": "email-default",
        "type": "email",
        "settings": {"addresses": "__PLACEHOLDER__"},
    }

    applied = sync_module.apply_recipients_to_contact_point(
        template, ["ops@example.com", "oncall@example.com"]
    )

    assert applied["settings"]["addresses"] == "ops@example.com;oncall@example.com"


def test_apply_recipients_to_contact_point_does_not_mutate_template() -> None:
    """Caller keeps the pre-substitution template around for dry-run
    output. Mutating in place would corrupt it on the second call."""
    template = {
        "uid": "email-default",
        "type": "email",
        "settings": {"addresses": "__PLACEHOLDER__"},
    }

    sync_module.apply_recipients_to_contact_point(template, ["a@b.co"])

    assert template["settings"]["addresses"] == "__PLACEHOLDER__"


def test_apply_recipients_to_contact_point_preserves_other_settings() -> None:
    """Sibling settings (e.g. ``subject``, ``message``) survive substitution."""
    template = {
        "uid": "email-default",
        "type": "email",
        "settings": {
            "addresses": "__PLACEHOLDER__",
            "subject": "[AMS] {{ .CommonLabels.alertname }}",
            "singleEmail": False,
        },
    }

    applied = sync_module.apply_recipients_to_contact_point(template, ["a@b.co"])

    assert applied["settings"]["subject"] == "[AMS] {{ .CommonLabels.alertname }}"
    assert applied["settings"]["singleEmail"] is False


# ---------------------------------------------------------------------------
# Cycle 3: UID remap covers the alert-rule shape (data[].datasourceUid)
# ---------------------------------------------------------------------------


def test_collect_placeholder_uids_walks_alert_rule_data_array() -> None:
    """Alert rules carry their datasource as a flat ``data[].datasourceUid``
    string, not a nested ``datasource.uid`` object (the Grafana
    provisioning API's alert-rule shape predates the dashboard
    convention). ``collect_placeholder_uids`` must recognise both."""
    rule = {
        "uid": "ams-cpu-warning",
        "data": [
            {
                "refId": "A",
                "datasourceUid": "cloudwatch",
                "model": {"refId": "A"},
            },
            {
                "refId": "B",
                "datasourceUid": "prometheus",
                "model": {"refId": "B"},
            },
        ],
    }

    found = sync_module.collect_placeholder_uids(rule)

    assert found == {"cloudwatch", "prometheus"}


def test_collect_placeholder_uids_walks_mixed_shapes_in_one_object() -> None:
    """An object can carry both shapes (e.g. a rule with a server-side
    expression that points back at a query via ``datasource.uid``). The
    walker must catch placeholders in both."""
    rule = {
        "uid": "ams-mixed",
        "data": [
            {"refId": "A", "datasourceUid": "cloudwatch"},
            {
                "refId": "B",
                "datasource": {"type": "__expr__", "uid": "__expr__"},
                "model": {"expression": "A"},
            },
        ],
    }

    found = sync_module.collect_placeholder_uids(rule)

    # ``__expr__`` is Grafana's server-side-expression sentinel — it is
    # NOT one of our placeholders so it must NOT be returned. Only
    # ``cloudwatch`` qualifies.
    assert found == {"cloudwatch"}


def test_remap_datasource_uids_rewrites_alert_rule_datasourceUid() -> None:
    """The flat ``data[].datasourceUid`` field is rewritten the same way
    the nested ``datasource.uid`` field is."""
    rule = {
        "uid": "ams-cpu-warning",
        "data": [
            {"refId": "A", "datasourceUid": "cloudwatch", "model": {}},
            {"refId": "B", "datasourceUid": "prometheus", "model": {}},
        ],
    }

    remapped = sync_module.remap_datasource_uids(
        rule,
        {"cloudwatch": "stack-specific-cw", "prometheus": "grafanacloud-prom"},
    )

    assert remapped["data"][0]["datasourceUid"] == "stack-specific-cw"
    assert remapped["data"][1]["datasourceUid"] == "grafanacloud-prom"


def test_remap_datasource_uids_does_not_mutate_alert_rule_input() -> None:
    """Same immutability contract as the dashboard test — caller keeps
    the pre-remap object for dry-run output."""
    rule = {
        "uid": "ams-cpu-warning",
        "data": [{"refId": "A", "datasourceUid": "cloudwatch", "model": {}}],
    }

    sync_module.remap_datasource_uids(rule, {"cloudwatch": "stack-specific-cw"})

    assert rule["data"][0]["datasourceUid"] == "cloudwatch"


def test_remap_datasource_uids_leaves_non_placeholder_datasourceUid_alone() -> None:
    """A ``datasourceUid`` already pointing at a real UID (e.g. an
    operator-edited rule file) must pass through unchanged."""
    rule = {
        "uid": "ams-pre-resolved",
        "data": [{"refId": "A", "datasourceUid": "grafanacloud-prom", "model": {}}],
    }

    remapped = sync_module.remap_datasource_uids(
        rule, {"cloudwatch": "stack-specific-cw"}
    )

    assert remapped["data"][0]["datasourceUid"] == "grafanacloud-prom"


def test_build_uid_remap_aggregates_across_dashboards_and_alert_rules() -> None:
    """``build_uid_remap`` accepts any iterable of resource dicts —
    dashboards and alert rules are both walked the same way, so a
    mixed batch resolves all placeholders in one pass."""
    dashboard = {
        "uid": "ams-dash",
        "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}}],
    }
    rule = {
        "uid": "ams-rule",
        "data": [{"refId": "A", "datasourceUid": "loki", "model": {}}],
    }

    remap = sync_module.build_uid_remap([dashboard, rule], env={})

    assert remap == {
        "prometheus": "grafanacloud-prom",
        "loki": "grafanacloud-logs",
    }


# ---------------------------------------------------------------------------
# Cycle 4: post_* helpers + main() orchestration
# ---------------------------------------------------------------------------


def _mock_opener_returning(status: int) -> MagicMock:
    """Build a mock opener whose ``open()`` returns a response with ``.status``.

    Matches how ``post_dashboard`` reads the urlopen result. Returned as
    a MagicMock so callers can assert ``open`` call args/kwargs."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_opener = MagicMock()
    mock_opener.open = MagicMock(return_value=mock_response)
    return mock_opener


def _mock_opener_returning_sequence(*statuses: int) -> MagicMock:
    """Like ``_mock_opener_returning`` but rotates through statuses for
    each call — drives the POST-then-PUT upsert dance."""
    responses = []
    for status in statuses:
        response = MagicMock()
        response.status = status
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        responses.append(response)
    mock_opener = MagicMock()
    mock_opener.open = MagicMock(side_effect=responses)
    return mock_opener


def _raise_http_error(code: int) -> Any:
    """Build an open() side-effect that raises an HTTPError with ``code``.

    Mirrors how the no-redirect opener turns 3xx and the API's 409 into
    HTTPError instances that the post_* helpers' exception arm catches.
    """
    import urllib.error

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            url="https://x.grafana.net/api/v1/provisioning/...",
            code=code,
            msg="Conflict" if code == 409 else "Error",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )

    return _raise


def test_post_contact_point_uses_provisioning_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``post_contact_point`` issues a POST to the provisioning API path.

    Uses the same no-redirect opener as ``post_dashboard`` so a 3xx
    auth-redirect surfaces as a hard failure rather than silently
    succeeding."""
    mock_opener = _mock_opener_returning(200)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    status = sync_module.post_contact_point(
        "https://x.grafana.net",
        "tok",
        {"uid": "email-default", "type": "email", "settings": {}},
    )

    assert status == 200
    request = mock_opener.open.call_args.args[0]
    assert request.full_url.endswith("/api/v1/provisioning/contact-points")


def test_post_contact_point_falls_back_to_put_on_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 409 from the create endpoint means the contact point already
    exists — retry as PUT against ``/contact-points/{uid}`` for upsert.

    Without this fallback, every sync after the first would fail with a
    confusing 409 line in the summary; with it, the script is idempotent
    in steady state (PUT runs once a sync against a populated GC stack).
    """
    call_count = {"n": 0}

    def _open(*_args: Any, **_kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            _raise_http_error(409)()
        response = MagicMock()
        response.status = 202
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    mock_opener = MagicMock()
    mock_opener.open = MagicMock(side_effect=_open)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    status = sync_module.post_contact_point(
        "https://x.grafana.net",
        "tok",
        {"uid": "email-default", "type": "email", "settings": {}},
    )

    assert status == 202
    assert mock_opener.open.call_count == 2
    second_request = mock_opener.open.call_args_list[1].args[0]
    assert second_request.method == "PUT"
    assert second_request.full_url.endswith(
        "/api/v1/provisioning/contact-points/email-default"
    )


def test_post_notification_policy_uses_put_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The root notification policy is a singleton; PUT replaces it."""
    mock_opener = _mock_opener_returning(202)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    status = sync_module.post_notification_policy(
        "https://x.grafana.net", "tok", {"receiver": "email-default"}
    )

    assert status == 202
    request = mock_opener.open.call_args.args[0]
    assert request.method == "PUT"
    assert request.full_url.endswith("/api/v1/provisioning/policies")


def test_post_alert_rule_tries_post_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First-run upsert: POST creates with the supplied uid, returns 201."""
    mock_opener = _mock_opener_returning(201)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    rule = _make_rule("ams-rule-warning")
    status = sync_module.post_alert_rule("https://x.grafana.net", "tok", rule)

    assert status == 201
    request = mock_opener.open.call_args.args[0]
    assert request.method == "POST"
    assert request.full_url.endswith("/api/v1/provisioning/alert-rules")


def test_post_alert_rule_falls_back_to_put_on_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Steady-state upsert: POST 409 → PUT /alert-rules/{uid}."""
    call_count = {"n": 0}

    def _open(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            _raise_http_error(409)()
        response = MagicMock()
        response.status = 200
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    mock_opener = MagicMock()
    mock_opener.open = MagicMock(side_effect=_open)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    rule = _make_rule("ams-rule-warning")
    status = sync_module.post_alert_rule("https://x.grafana.net", "tok", rule)

    assert status == 200
    assert mock_opener.open.call_count == 2
    second_request = mock_opener.open.call_args_list[1].args[0]
    assert second_request.method == "PUT"
    assert second_request.full_url.endswith(
        "/api/v1/provisioning/alert-rules/ams-rule-warning"
    )


def test_post_alert_rule_returns_real_status_on_non_409_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 4xx other than 409 (e.g. 401 unauthorized) is a real failure —
    DO NOT retry with PUT. Return the raw status so main()'s exit code
    reflects the real auth/permission issue."""
    call_count = {"n": 0}

    def _open(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        _raise_http_error(401)()

    mock_opener = MagicMock()
    mock_opener.open = MagicMock(side_effect=_open)
    monkeypatch.setattr(sync_module, "_NO_REDIRECT_OPENER", mock_opener)

    rule = _make_rule("ams-rule-warning")
    status = sync_module.post_alert_rule("https://x.grafana.net", "tok", rule)

    assert status == 401
    # Only one call — must NOT retry with PUT on 401.
    assert mock_opener.open.call_count == 1


# ---------- main() orchestration with --targets flag ----------


def test_main_targets_dashboards_only_skips_alerts_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--targets dashboards`` (the pre-extension default) must NOT
    touch alert resources, even if an alerts dir exists. Keeps existing
    operator workflows working unchanged."""
    dashboards_dir = tmp_path / "dashboards"
    dashboards_dir.mkdir()
    (dashboards_dir / "d.json").write_text(
        json.dumps({"uid": "ams-d", "title": "D", "panels": []})
    )
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")

    mock_dash = MagicMock(return_value=200)
    mock_cp = MagicMock(return_value=201)
    mock_pol = MagicMock(return_value=202)
    mock_rule = MagicMock(return_value=201)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_dash)
    monkeypatch.setattr(sync_module, "post_contact_point", mock_cp)
    monkeypatch.setattr(sync_module, "post_notification_policy", mock_pol)
    monkeypatch.setattr(sync_module, "post_alert_rule", mock_rule)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")

    exit_code = sync_module.main(
        [
            "--targets",
            "dashboards",
            "--dashboards-dir",
            str(dashboards_dir),
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    assert mock_dash.call_count == 1
    mock_cp.assert_not_called()
    mock_pol.assert_not_called()
    mock_rule.assert_not_called()


def test_main_targets_alerts_only_skips_dashboards_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--targets alerts`` skips dashboards entirely — lets an operator
    re-sync only alerts without re-uploading every dashboard."""
    dashboards_dir = tmp_path / "dashboards"
    dashboards_dir.mkdir()
    (dashboards_dir / "d.json").write_text(
        json.dumps({"uid": "ams-d", "title": "D", "panels": []})
    )
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")

    mock_dash = MagicMock(return_value=200)
    mock_cp = MagicMock(return_value=201)
    mock_pol = MagicMock(return_value=202)
    mock_rule = MagicMock(return_value=201)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_dash)
    monkeypatch.setattr(sync_module, "post_contact_point", mock_cp)
    monkeypatch.setattr(sync_module, "post_notification_policy", mock_pol)
    monkeypatch.setattr(sync_module, "post_alert_rule", mock_rule)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.setenv("GC_ALERT_EMAIL_RECIPIENTS", "ops@example.com")

    exit_code = sync_module.main(
        [
            "--targets",
            "alerts",
            "--dashboards-dir",
            str(dashboards_dir),
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    mock_dash.assert_not_called()
    assert mock_cp.call_count == 1
    assert mock_pol.call_count == 1
    assert mock_rule.call_count == 1  # default rule fixture has one rule


def test_main_targets_all_runs_both_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--targets all`` (the CI-side opt-in) runs dashboards THEN alerts.

    The default remains ``dashboards`` for backward compatibility with
    existing operator runs and pre-alerts tests; CI explicitly passes
    ``--targets all``."""
    dashboards_dir = tmp_path / "dashboards"
    dashboards_dir.mkdir()
    (dashboards_dir / "d.json").write_text(
        json.dumps({"uid": "ams-d", "title": "D", "panels": []})
    )
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")

    mock_dash = MagicMock(return_value=200)
    mock_cp = MagicMock(return_value=201)
    mock_pol = MagicMock(return_value=202)
    mock_rule = MagicMock(return_value=201)
    monkeypatch.setattr(sync_module, "post_dashboard", mock_dash)
    monkeypatch.setattr(sync_module, "post_contact_point", mock_cp)
    monkeypatch.setattr(sync_module, "post_notification_policy", mock_pol)
    monkeypatch.setattr(sync_module, "post_alert_rule", mock_rule)
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.setenv("GC_ALERT_EMAIL_RECIPIENTS", "ops@example.com")

    exit_code = sync_module.main(
        [
            "--targets",
            "all",
            "--dashboards-dir",
            str(dashboards_dir),
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    assert mock_dash.call_count == 1
    assert mock_cp.call_count == 1
    assert mock_pol.call_count == 1
    assert mock_rule.call_count == 1


def test_main_alerts_pass_substitutes_recipients_into_contact_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The contact point shipped to GC must carry the resolved
    recipients in ``settings.addresses``, NOT the placeholder."""
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")
    mock_cp = MagicMock(return_value=201)
    monkeypatch.setattr(sync_module, "post_contact_point", mock_cp)
    monkeypatch.setattr(
        sync_module, "post_notification_policy", MagicMock(return_value=202)
    )
    monkeypatch.setattr(sync_module, "post_alert_rule", MagicMock(return_value=201))
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.setenv(
        "GC_ALERT_EMAIL_RECIPIENTS", "ops@example.com,oncall@example.com"
    )

    exit_code = sync_module.main(
        [
            "--targets",
            "alerts",
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    posted_cp = mock_cp.call_args.args[2]
    assert posted_cp["settings"]["addresses"] == "ops@example.com;oncall@example.com"


def test_main_alerts_pass_remaps_cloudwatch_uid_in_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: an alert rule with ``datasourceUid="cloudwatch"`` is
    rewritten to the stack-specific UID before being shipped to GC."""
    rule = _make_rule("ams-cw-warning")
    rule["data"] = [
        {
            "refId": "A",
            "datasourceUid": "cloudwatch",
            "model": {"refId": "A"},
            "relativeTimeRange": {"from": 600, "to": 0},
        }
    ]
    alerts_dir = _write_alerts_layout(
        tmp_path / "alerts",
        rule_files={"cw.json": {"rules": [rule]}},
    )
    mock_rule = MagicMock(return_value=201)
    monkeypatch.setattr(sync_module, "post_alert_rule", mock_rule)
    monkeypatch.setattr(sync_module, "post_contact_point", MagicMock(return_value=201))
    monkeypatch.setattr(
        sync_module, "post_notification_policy", MagicMock(return_value=202)
    )
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.setenv("GC_ALERT_EMAIL_RECIPIENTS", "ops@example.com")
    monkeypatch.setenv("GC_CLOUDWATCH_UID", "stack-specific-cw")

    exit_code = sync_module.main(
        [
            "--targets",
            "alerts",
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    posted_rule = mock_rule.call_args.args[2]
    assert posted_rule["data"][0]["datasourceUid"] == "stack-specific-cw"


def test_main_alerts_dry_run_lists_resources_without_posting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--dry-run`` on the alerts pass must NOT POST and must NOT
    require ``GC_ALERT_EMAIL_RECIPIENTS`` (PR-side CI path)."""
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")
    mock_cp = MagicMock()
    mock_pol = MagicMock()
    mock_rule = MagicMock()
    monkeypatch.setattr(sync_module, "post_contact_point", mock_cp)
    monkeypatch.setattr(sync_module, "post_notification_policy", mock_pol)
    monkeypatch.setattr(sync_module, "post_alert_rule", mock_rule)
    monkeypatch.delenv("GC_ALERT_EMAIL_RECIPIENTS", raising=False)

    exit_code = sync_module.main(
        [
            "--targets",
            "alerts",
            "--alerts-dir",
            str(alerts_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    mock_cp.assert_not_called()
    mock_pol.assert_not_called()
    mock_rule.assert_not_called()
    out = capsys.readouterr().out
    assert "email-default" in out  # contact point uid surfaced in dry-run output
    assert "ams-default-warning" in out  # rule uid surfaced


def test_main_alerts_live_run_requires_recipients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live alerts sync without GC_ALERT_EMAIL_RECIPIENTS exits non-zero
    so the operator catches the misconfiguration before GC sees a
    contact point with no addresses."""
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")
    monkeypatch.setattr(sync_module, "post_contact_point", MagicMock(return_value=201))
    monkeypatch.setattr(
        sync_module, "post_notification_policy", MagicMock(return_value=202)
    )
    monkeypatch.setattr(sync_module, "post_alert_rule", MagicMock(return_value=201))
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.delenv("GC_ALERT_EMAIL_RECIPIENTS", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        sync_module.main(
            [
                "--targets",
                "alerts",
                "--alerts-dir",
                str(alerts_dir),
                "--stack-url",
                "https://x.grafana.net",
            ]
        )

    assert exc_info.value.code == 2


def test_main_combined_summary_reports_dashboard_and_alert_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When both passes run successfully the final summary mentions
    both — operator scanning CI output should not have to grep for OK
    lines to confirm both surfaces landed."""
    dashboards_dir = tmp_path / "dashboards"
    dashboards_dir.mkdir()
    (dashboards_dir / "d.json").write_text(
        json.dumps({"uid": "ams-d", "title": "D", "panels": []})
    )
    alerts_dir = _write_alerts_layout(tmp_path / "alerts")
    monkeypatch.setattr(sync_module, "post_dashboard", MagicMock(return_value=200))
    monkeypatch.setattr(sync_module, "post_contact_point", MagicMock(return_value=201))
    monkeypatch.setattr(
        sync_module, "post_notification_policy", MagicMock(return_value=202)
    )
    monkeypatch.setattr(sync_module, "post_alert_rule", MagicMock(return_value=201))
    monkeypatch.setenv("GRAFANA_CLOUD_API_KEY", "tok")
    monkeypatch.setenv("GC_ALERT_EMAIL_RECIPIENTS", "ops@example.com")

    exit_code = sync_module.main(
        [
            "--targets",
            "all",
            "--dashboards-dir",
            str(dashboards_dir),
            "--alerts-dir",
            str(alerts_dir),
            "--stack-url",
            "https://x.grafana.net",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dashboard" in out.lower()
    assert "alert" in out.lower()
