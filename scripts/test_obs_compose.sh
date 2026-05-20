#!/usr/bin/env bash
# Phase 3 regression test: observability overlay parses and declares the expected services.
#
# Acts as the TDD gate for the Phase 3 compose overlay. Runs offline — no images
# need to be pulled. Fails loudly if the overlay file is missing, doesn't parse,
# or omits a required service / volume / port.

set -euo pipefail

cd "$(dirname "$0")/.."

OVERLAY="docker-compose.observability.yml"
BASE="docker-compose.yml"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[ -f "$BASE" ]    || fail "$BASE not found"
[ -f "$OVERLAY" ] || fail "$OVERLAY not found (Phase 3 overlay missing)"

# `docker compose config` resolves variables and merges overlay onto base. If it
# exits non-zero, the YAML is malformed or the merge is invalid.
RENDERED=$(docker compose -f "$BASE" -f "$OVERLAY" config 2>&1) \
  || fail "docker compose config did not parse:\n$RENDERED"
pass "overlay parses"

REQUIRED_SERVICES=(grafana prometheus loki tempo pyroscope alloy cadvisor mysqld-exporter)
for svc in "${REQUIRED_SERVICES[@]}"; do
  echo "$RENDERED" | grep -qE "^  ${svc}:" \
    || fail "service '${svc}' missing from rendered config"
done
pass "all 8 observability services declared"

# The backend service must be augmented with OTEL/Pyroscope envs by the overlay
# (locked decision 5 + Phase 1 toggles).
for env in OTEL_ENABLED OTEL_ENDPOINT PYROSCOPE_ENABLED LOG_FORMAT REPLICA_ID; do
  echo "$RENDERED" | grep -q "${env}:" \
    || fail "backend missing required env override '${env}'"
done
pass "backend observability envs wired"

# mysqld-exporter must declare DATA_SOURCE_NAME so it can connect.
echo "$RENDERED" | grep -q "DATA_SOURCE_NAME" \
  || fail "mysqld-exporter DATA_SOURCE_NAME not set"
pass "mysqld-exporter DSN wired"

# Named volumes per the plan: each backend writes to its own named volume so
# data survives `docker compose down` (but not `down -v`).
for vol in grafana-data prometheus-data loki-data tempo-data pyroscope-data alloy-data; do
  echo "$RENDERED" | grep -qE "^  ${vol}:" \
    || fail "named volume '${vol}' missing"
done
pass "observability volumes declared"

# Grafana must expose 3000 so the operator can hit the UI.
echo "$RENDERED" | grep -qE 'published: "?3000"?' \
  || fail "grafana port 3000 not published"
pass "grafana port published"

# Alloy must expose 4317 (OTLP gRPC), 4318 (OTLP HTTP), 12345 (Alloy UI).
for port in 4317 4318 12345; do
  echo "$RENDERED" | grep -qE "published: \"?${port}\"?" \
    || fail "alloy port ${port} not published"
done
pass "alloy ports published"

# MySQL grant SQL must be present in db/init/ and the directory must be mounted
# into /docker-entrypoint-initdb.d/ so the exporter user is created on first
# MySQL boot. Compose renders the bind mount as a directory target.
[ -f db/init/01-exporter-grant.sql ] \
  || fail "db/init/01-exporter-grant.sql missing"
echo "$RENDERED" | grep -q "target: /docker-entrypoint-initdb.d" \
  || fail "db/init not bind-mounted into mysql initdb dir"
pass "mysqld-exporter grant SQL mounted"

echo
echo "OK: docker-compose.observability.yml passes Phase 3 invariants."
