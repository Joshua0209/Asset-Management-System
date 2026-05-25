"""Add required Grafana 10+ CloudWatch panel target fields.

Newer Grafana versions require ``metricEditorMode``, ``metricQueryType``, and
``queryMode`` on every CloudWatch metric query target. Without them, panels
uploaded via the dashboard API render "No data" even when the data exists
and the same target works in Explore. Manual Save via the UI silently
injects the missing fields, which is why "open in edit mode, click Apply"
fixes the panel — and why anyone debugging without this knowledge tends to
spin in circles for hours.

The fix is a surgical sed-like insertion: every CloudWatch panel target
has ``"refId":`` as its last field, indented in the multi-line dashboard
JSON. We append the three required fields immediately before the closing
``}`` of the same target so the rest of the file's formatting (compact
arrays, single-line short objects) stays byte-for-byte identical.

Run with ``--check`` to list pending edits; ``--write`` to apply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DASHBOARDS_DIR = Path(__file__).resolve().parent.parent / "config" / "grafana" / "dashboards"

# The three fields the UI emits on save but the API-shape dashboards in
# this repo omit. Adding them on disk is what unblocks the renderer.
_REQUIRED_FIELDS = ("metricEditorMode", "metricQueryType", "queryMode")
_REQUIRED_LITERALS = {
    "metricEditorMode": "0",  # JSON number literal
    "metricQueryType": "0",
    "queryMode": "\"Metrics\"",
}


def _collect_targets_to_fix(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return CW targets missing any required field, in document order."""
    out: list[dict[str, Any]] = []
    for panel in panels:
        for target in panel.get("targets") or []:
            ds_type = (target.get("datasource") or {}).get("type")
            if ds_type != "cloudwatch":
                continue
            if any(field not in target for field in _REQUIRED_FIELDS):
                out.append(target)
        out.extend(_collect_targets_to_fix(panel.get("panels") or []))
    return out


def _make_block(indent: str, target: dict[str, Any]) -> str:
    """Render the three required fields as a JSON snippet keyed at ``indent``."""
    lines = []
    for field in _REQUIRED_FIELDS:
        if field in target:
            continue
        lines.append(f"{indent}\"{field}\": {_REQUIRED_LITERALS[field]}")
    return ",\n".join(lines)


def _patch_target_in_source(raw: str, target: dict[str, Any]) -> str | None:
    """Inject missing fields before the target's closing ``}``.

    Anchors on the unique combination of metricName + statistic + refId
    inside one target's JSON object. The closing brace we patch is the one
    that matches the OPENING brace right before the anchored ``metricName``
    line — found by counting depth from the anchor forward.
    """
    metric_name = target.get("metricName")
    statistic = target.get("statistic")
    ref_id = target.get("refId")
    if not (metric_name and statistic and ref_id):
        return None

    # The repo's dashboards always indent target keys at 10 spaces (panel
    # is at 6, targets array at 8, target object body at 10). Anchor a regex
    # that matches the unique metric+statistic+refId triple within ONE
    # target object so we can locate its closing brace.
    pattern = re.compile(
        rf'(?m)^( *)"metricName": "{re.escape(metric_name)}",\n'
        rf'\1"statistic": "{re.escape(statistic)}",.*?^\1"refId": "{re.escape(ref_id)}"\n',
        re.DOTALL,
    )
    match = pattern.search(raw)
    if not match:
        return None

    indent = match.group(1)
    # The next non-blank line after the matched ``"refId"`` is the closing
    # brace of the same target. The brace is indented two spaces less than
    # the key indent.
    after = match.end()
    closing_indent = indent[:-2] if len(indent) >= 2 else ""
    close_pattern = re.compile(rf"^{re.escape(closing_indent)}\}}", re.MULTILINE)
    close_match = close_pattern.search(raw, after)
    if not close_match:
        return None

    block = _make_block(indent, target)
    if not block:
        return None

    # Insert a comma after the ``refId`` line, then the three new key lines,
    # immediately before the closing brace. The trailing newline already in
    # the source (between the previous field and ``}``) is preserved, so we
    # don't append another one and create a blank line.
    insertion = f",\n{block}"
    return raw[: close_match.start() - 1] + insertion + raw[close_match.start() - 1 :]


def _process(path: Path, *, write: bool) -> int:
    raw = path.read_text()
    dashboard = json.loads(raw)
    targets = _collect_targets_to_fix(dashboard.get("panels") or [])
    if not targets:
        print(f"  {path.name}: all CloudWatch targets already complete")
        return 0

    new_raw = raw
    changed = 0
    for target in targets:
        patched = _patch_target_in_source(new_raw, target)
        if patched is None:
            print(
                f"  WARN {path.name}: could not locate target "
                f"metric={target.get('metricName')} refId={target.get('refId')} in source"
            )
            continue
        new_raw = patched
        changed += 1
        if not write:
            missing = [f for f in _REQUIRED_FIELDS if f not in target]
            print(
                f"    - {path.name} target refId={target.get('refId')} "
                f"metric={target.get('metricName')} adds={missing}"
            )

    if changed == 0:
        return 0

    if write:
        # Validate the patched source still parses as JSON before writing.
        json.loads(new_raw)
        path.write_text(new_raw)
        print(f"  {path.name}: rewrote {changed} target(s)")
    else:
        print(f"  {path.name}: would rewrite {changed} target(s)")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="diff only, no write")
    parser.add_argument("--write", action="store_true", help="apply changes in place")
    args = parser.parse_args()
    if not (args.check or args.write):
        parser.error("pass --check or --write")

    print(f"Scanning {DASHBOARDS_DIR}")
    total = 0
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        total += _process(path, write=args.write)
    print(f"Total CloudWatch targets {'rewritten' if args.write else 'pending rewrite'}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
