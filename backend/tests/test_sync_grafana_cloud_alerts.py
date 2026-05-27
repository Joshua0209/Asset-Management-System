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
