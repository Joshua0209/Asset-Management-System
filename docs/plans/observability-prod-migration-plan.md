# Observability Production Migration Plan (`feat/observability`)

**Status:** Drafted 2026-05-24. Supersedes parts of `docs/plans/observability-implementation-plan.md` (Phases 3, 4, 5, and the originally-scoped Phase 6).

**Scope:** Cut over from the W6 local docker-compose Grafana stack to Grafana Cloud as the sole telemetry backend for both local dev and AWS production. The local observability overlay is fully pruned. The FastAPI backend pushes OTLP signals (traces, metrics, logs, profiles) direct to Grafana Cloud's hosted gateways from both environments. AWS-side telemetry (CloudWatch Logs, RDS Enhanced Monitoring, ALB metrics) is pulled by Grafana Cloud via a read-only cross-account IAM role. Dashboards live in Grafana Cloud only after cutover.

**Out of scope on this branch:**

- Multi-stack GC partitioning (separate `ams-local` and `ams-production` stacks). Single stack initially; revisit if free-tier quota pressure forces it.
- Per-developer GC API keys. Single shared API key in `backend/.env.example`. Acceptable because the GC stack is scoped to this class project.
- Grafana Cloud Synthetic Monitoring and managed alert routing. Smoke tests stay on the Phase 5 (formerly Phase 7) k6 surface, not GC's synthetics product.
- Migrating the IAM user pattern from PR #75. The new `ams-grafana-cloud-reader` role uses cross-account trust + external ID, replacing the long-lived access-key pattern outright.

**Reference:** The current local stack lives in `docker-compose.observability.yml` + `config/alloy/config.alloy`. The new wire is OTel SDK + OTLP push direct to GC; no Alloy in either environment after cutover.

**Locked decisions** (resolved with user 2026-05-24):

1. **Single backend:** Grafana Cloud free tier is the only Grafana, Prometheus, Loki, Tempo, and Pyroscope instance. No local stack, no AMG, no ECS-hosted Grafana.
2. **Zero Alloy in production:** Backend pushes OTLP direct to GC's hosted OTLP gateway. AWS-side telemetry is pulled by GC, not pushed.
3. **Zero observability containers locally:** Backend pushes OTLP direct to GC from the developer's laptop too. Same exporter config in both environments; only the `ENVIRONMENT` resource attribute and credentials differ.
4. **OTLP-native backend:** `prometheus_client.Counter` and `prometheus_fastapi_instrumentator` are replaced by OTel `Counter` / `Histogram` primitives with the OTLP metrics exporter. The `/metrics` endpoint is removed. Structlog logs are bridged to OTel logs via the stdlib handler.
5. **Pyroscope enabled in production.** Reverses locked decision 5 from the original plan. `WEB_CONCURRENCY=1` plus no `gunicorn --preload` means the sampling thread starts inside the worker post-fork. First production deploy verifies samples flow; fallback is the gunicorn `post_fork` hook documented in Phase 4.
6. **Dashboards live in Grafana Cloud only after Phase 6.** Repo-side `config/grafana/dashboards/*.json` is deleted only after GC import is verified working in production.
7. **cAdvisor + mysqld-exporter dashboard panels are removed, not replaced.** CloudWatch Container Insights and RDS Enhanced Monitoring give rough equivalents on the AWS side; local has no equivalent and developers fall back to `docker stats` and direct MySQL queries.

---

## Multi-session strategy

Each phase below is a self-contained session. Read `Prerequisites`, `Scope`, `Files touched`, and `Validation` for the phase you are picking up. That alone is enough to start cold.

Phases land sequentially on `feat/observability`. The two existing open PRs (#75, #84) restructure into Phase 4 and Phase 5 respectively. PR #75 closes and reopens with expanded scope (Phase 4); PR #84 rebases (Phase 5).

| # | Phase | Depends on | Existing PR |
|---|---|---|---|
| 1 | Pre-flight rebase of `feat/observability` onto `main` | — | none |
| 2 | Prune local observability stack | 1 | new branch |
| 3 | Backend OTLP refactor | 2 | new branch |
| 4 | AWS production observability via Grafana Cloud | 3 | #75 (close + reopen) |
| 5 | k6 load tests rebase (formerly Phase 7) | 3 | #84 (rebase) |
| 6 | Delete repo-side dashboard JSONs | 4, production verification | new branch |

Phases 4 and 5 are independent after both rebase onto post-Phase-3 `feat/observability`; merge order between them is interchangeable.

---

## Phase 1: Pre-flight rebase

**Session goal:** Bring `feat/observability` up to date with `main` so the five downstream phase branches don't all have to rebase twice.

### Prerequisites

- Local clone has `feat/observability` checked out, no uncommitted changes.
- Open PRs #75 and #84 acknowledged; their authors warned that a force-push to the integration branch is coming.
- Required reading: `git log --oneline main..feat/observability` (commits already on the integration branch that will be replayed).

### Scope

1. Fetch latest `main`: `git fetch origin main`.
2. Check out the integration branch: `git checkout feat/observability`.
3. Confirm clean tree: `git status`.
4. Rebase: `git rebase origin/main`.
5. Resolve conflicts if any. None are expected — the integration branch and `main` have diverged in non-overlapping files (CI workflow tweaks on `main`, observability additions on the branch).
6. Force-push with lease: `git push --force-with-lease origin feat/observability`.
7. Notify any other branch authors (yourself, for #75 and #84) that the integration branch was rebased and downstream branches must rebase before any further work.

### Files touched

None. Git history rewritten only.

### Validation

```bash
git log --oneline origin/main..feat/observability | head -20
# expect: only feat/observability's own commits, on top of latest origin/main
git merge-base main feat/observability
# expect: latest commit on main
git status
# expect: clean
```

### Known gotchas

- `--force-with-lease` refuses the push if someone else pushed to the branch between your fetch and your push. Always use this over `--force`.
- The first thing both #75 (Phase 4) and #84 (Phase 5) must do is rebase onto the new `feat/observability` head. Coordinate the order.

---

## Phase 2: Prune local observability stack

**Session goal:** Stop running the local docker-compose observability overlay. All Prom / Loki / Tempo / Pyroscope / Grafana / Alloy / cAdvisor / mysqld-exporter containers and their config files removed. The backend's `/metrics` endpoint stays in place temporarily (deleted in Phase 3). OTLP exporters default to off; no outbound network calls from a clean `docker compose up`.

### Prerequisites

- Phase 1 merged.
- Branch off latest `feat/observability` named `feat/observability-prune-local-stack`.
- Required reading: `docker-compose.observability.yml`, `config/alloy/config.alloy`, `Makefile` (the `obs-*` targets), `db/init/01-exporter-grant.sql`.

### Scope

1. Delete the overlay compose file and the configs it references:
   - `docker-compose.observability.yml`
   - `config/alloy/config.alloy`
   - `config/loki/loki.yml`
   - `config/prometheus/prometheus.yml`
   - `config/tempo/tempo.yml`
   - `config/pyroscope/pyroscope.yml`
   - `config/grafana/provisioning/datasources/datasources.yml`
   - `config/grafana/provisioning/dashboards/*` (the provisioning configs; the dashboard JSONs under `config/grafana/dashboards/` stay until Phase 6)

2. Delete the MySQL exporter init grant: `db/init/01-exporter-grant.sql`.

3. Delete the provisioning regression test: `backend/tests/test_grafana_provisioning.py`. This test pins the existence of `datasources.yml` and the dashboard provisioning config, both of which are now gone.

4. Trim `Makefile`: remove `obs-up`, `obs-down`, `obs-logs`, `obs-pull`. Keep any `k6-*` targets that PR #84 added (k6 itself is not pruned; the load tooling stays).

5. Update `.env.example` (top-level): remove `DOCKER_ROOT_DIR`. Do NOT touch `CLOUDWATCH_ACCESS_KEY` / `CLOUDWATCH_SECRET_KEY` here — those live on PR #75's branch (Phase 4) and never reach the integration branch until that PR lands.

6. Update `README.md`: drop the "Option B: docker compose with observability overlay" section. Add a one-line pointer to this migration plan and a note that local observability happens via Grafana Cloud after Phase 4 ships.

7. Update `CLAUDE.md`: drop the observability-stack docker compose conventions block (the paragraphs about `docker-compose.observability.yml`, `make obs-up`, `cAdvisor on OrbStack`, etc.). Add a "telemetry pushes to Grafana Cloud" one-liner pointing here.

8. Update `docs/plans/observability-implementation-plan.md`: at the top of each of Phases 3, 4, 5, add a `**STATUS: SUPERSEDED by observability-prod-migration-plan.md.**` line. Do not delete the content — keep it for historical context.

9. Do NOT touch `docs/roadmap.md`. The W6 milestone outcomes (M6 correlation demo) were proven against the local stack at the time it ran; that history is real and stays ticked.

### Files touched

- (deletions, listed in Scope steps 1-3)
- `Makefile`
- `.env.example`
- `README.md`
- `CLAUDE.md`
- `docs/plans/observability-implementation-plan.md`

### Validation

```bash
# Backend still boots and tests pass with no overlay
docker compose up --build -d backend
docker compose ps
# expect: only backend, frontend, mysql containers
docker compose exec backend pytest -v
curl -s http://localhost:8000/health         # 200
curl -s http://localhost:8000/metrics | head # still 200 — removed in Phase 3, not here

# Confirm no compose service still references the pruned containers
docker compose config | grep -E "alloy|loki|tempo|prometheus|grafana|pyroscope|cadvisor|mysqld-exporter" \
  && echo "FAIL: residual reference" || echo "OK: pruned"

# Confirm Makefile no longer references the overlay file
grep -E "docker-compose.observability.yml" Makefile && echo "FAIL" || echo "OK"

# Confirm provisioning test is gone
test -f backend/tests/test_grafana_provisioning.py && echo "FAIL" || echo "OK"
```

### Known gotchas

- The `backend_uploads` named volume lives in the main `docker-compose.yml`, not the overlay. Unaffected by this phase.
- If a stale local Grafana stack is still running when Phase 2 merges, `docker compose down` won't find the overlay file. Recover with: `docker compose ls` to find the project name, then `docker compose -p <name> down -v` to clear it. Document in the PR description.
- The `mysql` service in `docker-compose.yml` previously mounted `db/init/01-exporter-grant.sql` via the overlay. Once Phase 2 lands, the grant file is gone and the mysql container starts cleanly without it. On a fresh DB volume, the exporter user simply isn't created. On a re-used volume from a previous boot, the user still exists; harmless because nothing scrapes it any more.

---

## Phase 3: Backend OTLP refactor

**Session goal:** Replace `prometheus_client.Counter` + `prometheus_fastapi_instrumentator` with OTel-native metrics emitted via OTLP push. Replace structlog-to-stdout with structlog bridged to OTel logs over OTLP. Lift the Pyroscope-in-prod restriction in `maybe_setup_profiling`. Delete the `/metrics` HTTP route entirely. After this phase, the backend has no scrapeable surface; it only pushes.

### Prerequisites

- Phase 2 merged.
- Branch off latest `feat/observability` named `feat/observability-otlp-refactor`.
- Required reading:
  - `backend/app/core/observability.py` (entire file, ~485 LOC including the AccessLogMiddleware on `feat/observability`).
  - `backend/app/core/config.py` (Settings, especially `otel_*` and `pyroscope_*`).
  - `backend/app/main.py` (lines around middleware registration and the `/metrics` route mounting).
  - OpenTelemetry Python docs for `opentelemetry.sdk.metrics` and `opentelemetry.sdk._logs` (the latter is stable as of OTel 1.27+ despite the underscore module name).

### Scope

1. Update `backend/pyproject.toml`:
   - Remove `prometheus-fastapi-instrumentator>=7.0,<8.0`.
   - Audit `prometheus-client`: if any call site still imports it (e.g. an exporter helper), keep; otherwise remove.
   - Add `opentelemetry-sdk>=1.27,<2.0` with `[metrics,logs]` extras.
   - `opentelemetry-exporter-otlp-proto-grpc>=1.27,<2.0` is already present (traces).
   - Add `opentelemetry-instrumentation-logging>=0.48b0,<1.0` for the stdlib-logging integration.
   - Bump `pyroscope-io>=0.8.5,<1.0` (the basic_auth kwargs require >=0.8.5).

2. Refactor `backend/app/core/observability.py`:
   - Replace module-level `Counter` definitions with OTel counters from a module meter:
     ```python
     from opentelemetry import metrics
     _meter = metrics.get_meter("ams.backend")
     FSM_TRANSITIONS = _meter.create_counter(
         "ams_fsm_transitions_total",
         description="Successful asset / repair-request FSM transitions.",
     )
     OPTIMISTIC_CONFLICTS = _meter.create_counter(
         "ams_optimistic_conflicts_total",
         description="409 conflicts raised by mutating endpoints.",
     )
     ```
     Call sites change from `.labels(from=..., to=...).inc()` to `.add(1, attributes={"from": ..., "to": ...})`. Search for `FSM_TRANSITIONS.labels` and `OPTIMISTIC_CONFLICTS.labels` to enumerate all call sites (currently in `services/repair_request_service.py`, `api/v1/assets.py`, `api/v1/repair_requests.py`).

   - Replace `Instrumentator(...)` setup in `setup_metrics()`. Either:
     a. Use `FastAPIInstrumentor.instrument_app(app, meter_provider=<provider>)` — the existing trace integration already uses this instrumentor; passing a `MeterProvider` opts into HTTP metrics emission.
     b. Hand-roll an ASGI middleware that emits `http.server.duration` (Histogram) and `http.server.requests` (Counter).
     Pick (a) unless the auto-emitted attribute set is wrong for the dashboards.

   - Add `setup_metrics_exporter(settings)`:
     ```python
     from opentelemetry.sdk.metrics import MeterProvider
     from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
     from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
     from opentelemetry.sdk.metrics.view import View
     ```
     Apply Views renaming OTel dot-style names to Prom-style underscored names so existing dashboard queries remain portable:
     ```python
     views = [
         View(instrument_name="http.server.duration",
              name="http_server_duration_seconds"),
         View(instrument_name="http.server.requests",
              name="http_server_requests_total"),
     ]
     ```
     Set the resource: `Resource.create({"service.name": "ams-backend", "service.instance.id": settings.replica_id, "environment": settings.environment})`.

   - Add `setup_log_exporter(settings)`:
     ```python
     from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
     from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
     from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
     ```
     Register `LoggingHandler(level=logging.INFO, logger_provider=provider)` on the root stdlib logger. Structlog's existing `ProcessorFormatter` bridge already routes structlog events through stdlib, so the OTel handler picks them up downstream. The `_structlog_processor_trace_context` keeps stamping `trace_id` before the OTel hand-off.

   - `maybe_setup_profiling`: drop the "off in prod" docstring claim. Pass GC basic auth:
     ```python
     pyroscope.configure(
         application_name=f"ams-backend.{settings.replica_id}",
         server_address=settings.pyroscope_server,
         basic_auth_username=settings.pyroscope_basic_auth_username,
         auth_token=settings.pyroscope_auth_token,
     )
     ```

   - Delete the `@app.get("/metrics", ...)` route registration block in `setup_metrics`. The `prometheus_client.exposition` imports go with it.

3. Update `backend/app/core/config.py`:
   - Add settings:
     ```python
     environment: str = "local"
     otel_exporter_otlp_headers: str = ""  # "Authorization=Basic <base64(instance:apikey)>"
     pyroscope_auth_token: str = ""
     pyroscope_basic_auth_username: str = ""
     ```
   - Remove any validator that constrains `otel_endpoint` to start with `http://alloy:` (the original Phase 1 plan added a hint for `http://alloy:4317`; GC uses `https://otlp-gateway-…`).

4. Update `backend/app/main.py`:
   - Call `setup_metrics_exporter(settings)` and `setup_log_exporter(settings)` in the startup sequence, between `setup_logging` and `setup_tracing`. Order: logging → log_exporter (so the OTel handler attaches before any further log calls) → metrics → metrics_exporter → tracing → profiling.
   - Update or delete any inline comment block that referred to `/metrics` route ordering vs SlowAPIMiddleware. The route is gone, so the exemption no longer matters.
   - Audit `_enforce_single_worker_invariant`: still valid (slowapi `MemoryStorage` requires single-worker); leave it.

5. Update `backend/.env.example`:
   ```
   OTEL_ENABLED=false
   OTEL_ENDPOINT=https://otlp-gateway-prod-<region>.grafana.net/otlp
   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64 of instance_id:api_key>
   PYROSCOPE_ENABLED=false
   PYROSCOPE_SERVER=https://profiles-prod-<region>.grafana.net
   PYROSCOPE_AUTH_TOKEN=<your-gc-api-key>
   PYROSCOPE_BASIC_AUTH_USERNAME=<your-gc-pyroscope-instance-id>
   ENVIRONMENT=local
   ```
   Add a comment block above the OTEL lines: "Developers wire their own GC credentials; `OTEL_ENABLED=false` keeps the backend running with no observability for credential-less local dev."

6. Update `backend/tests/test_observability.py`:
   - Delete any test that hits `GET /metrics` (the route is gone).
   - Delete the middleware-order test that pinned `prometheus_fastapi_instrumentator` after `SlowAPIMiddleware`.
   - Add: `setup_metrics_exporter(settings)` creates a working `MeterProvider`; counters can `.add(1, attributes=...)` without raising.
   - Add: `setup_log_exporter(settings)` creates a working `LoggerProvider`. Inside a span context (use an `InMemorySpanExporter` to set up a span), emit a log line via structlog; assert the captured `LogRecord` carries the active span's `trace_id`. Use `opentelemetry.sdk._logs.InMemoryLogExporter` to capture, not the real OTLP wire.
   - Add: `maybe_setup_profiling` with `environment="production"` calls `pyroscope.configure` (mock it). Asserts the locked-decision reversal.

7. Update `backend/tests/test_rate_limit.py`:
   - Remove the test that interleaves `GET /metrics` between rate-limited requests and asserts the limiter counter is unaffected. The route is gone, so the test is meaningless.

### Files touched

- `backend/pyproject.toml`
- `backend/app/core/observability.py` (substantial refactor)
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/.env.example`
- `backend/tests/test_observability.py`
- `backend/tests/test_rate_limit.py`
- Any service or API module that referenced `Counter.labels(...).inc()` for the two custom counters

### Validation

```bash
cd backend
ruff check .
mypy app
pytest tests/test_observability.py -v
pytest --cov=app --cov-report=term   # confirm coverage stays >=80%

# Smoke against a real GC stack (set credentials in .env first):
docker compose up --build -d backend
docker compose exec backend python -c "from app.core.config import get_settings; print(get_settings().environment)"
# expect: local

# Drive one request through the full pipeline
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"ChangeMe123"}'

# Wait ~30s for the OTel periodic exporter, then in the GC web UI:
#   - Traces  (Explore → Tempo): {service.name="ams-backend", environment="local"}
#   - Metrics (Explore → Prom):   http_server_requests_total{environment="local"}
#   - Logs    (Explore → Loki):   {service.name="ams-backend", environment="local"}
#   - Profiles: select ams-backend.<replica> in the application dropdown
```

### Known gotchas

- The OTel logs SDK module path is `opentelemetry.sdk._logs` with a leading underscore. The API is stable in OTel >=1.27 despite the underscore. If a future release renames it, the imports break in one place (`setup_log_exporter`).
- Both `prometheus_fastapi_instrumentator` and the OTel `FastAPIInstrumentor` register ASGI middleware. Remove the Prom instrumentator BEFORE wiring OTel HTTP metrics on the same `FastAPIInstrumentor` instance, or both middlewares run and per-request counts double.
- The OTel SDK `View` renaming only changes the metric exposition name; the SDK's internal instrument name stays dot-style. Dashboards query the renamed series. Document the mapping in the module docstring.
- `pyroscope-io < 0.8.5` rejects `basic_auth_username` and `auth_token` kwargs. Pin >=0.8.5.
- Structlog's processor chain stamps `trace_id` via `_structlog_processor_trace_context`. The OTel `LoggingHandler` picks up the formatted record AFTER structlog runs, so `trace_id` is on the `LogRecord` already. Verified by the new test added in Scope step 6 — if that test fails, the bridge order is wrong.

---

## Phase 4: AWS production observability via Grafana Cloud

**Session goal:** Enable backend OTLP push from the ECS task. Set up GC's hosted CloudWatch Logs and Metrics integrations via a new cross-account IAM role. Import the existing 6 dashboards into the GC stack. Verify end-to-end correlation works against production traffic.

### Pre-work (one-time, before opening the branch)

- Sign up for Grafana Cloud free tier. Create a stack named `ams`. From the stack's "Connections" view, capture four endpoints (Prom remote_write, Loki push, OTLP gateway, Pyroscope push) and one API key scoped to publish all four signals. Also capture the cross-account `external_id` from the AWS connector setup wizard.
- Close PR #75 with a comment naming the scope expansion: "Phase 4: AWS production observability via Grafana Cloud (formerly Phase 6 CloudWatch datasource). The original CloudWatch DS in local Grafana is superseded by GC's hosted CloudWatch integration; the IAM user pattern is superseded by a cross-account role with external ID."
- Rename the branch locally and remotely:
  ```bash
  git checkout feat/observability-phase6-cloudwatch
  git fetch origin feat/observability
  git rebase origin/feat/observability
  git branch -m feat/observability-phase6-cloudwatch feat/observability-phase4-aws
  git push origin :feat/observability-phase6-cloudwatch
  git push -u origin feat/observability-phase4-aws
  ```
- Reopen a new PR titled "Phase 4: AWS production observability via Grafana Cloud" against `feat/observability`. Reference the closed #75 in the description.

### Prerequisites

- Phase 3 merged.
- Branch `feat/observability-phase4-aws` checked out, rebased onto post-Phase-3 `feat/observability`.
- AWS account access with permission to create IAM roles and Secrets Manager secrets.
- Grafana Cloud stack `ams` exists.
- Required reading:
  - `infra/ecs/backend-task-def.json`
  - `docs/system-design/08-deployment-operations.md` (any existing observability section, written for PR #75; supersede with this phase's content).
  - GC docs: "Connect AWS CloudWatch metrics" and "Connect AWS CloudWatch Logs."

### Scope

1. Create AWS Secrets Manager secret `ams-grafana-cloud` (via console or CLI; not committed). JSON keys:
   ```json
   {
     "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <base64(prom_instance_id:api_key)>",
     "PYROSCOPE_AUTH_TOKEN": "<api_key>",
     "PYROSCOPE_BASIC_AUTH_USERNAME": "<pyroscope_instance_id>"
   }
   ```

2. Update `infra/ecs/backend-task-def.json`:
   - `environment` additions:
     ```json
     {"name": "OTEL_ENABLED", "value": "true"},
     {"name": "OTEL_ENDPOINT", "value": "https://otlp-gateway-prod-<region>.grafana.net/otlp"},
     {"name": "PYROSCOPE_ENABLED", "value": "true"},
     {"name": "PYROSCOPE_SERVER", "value": "https://profiles-prod-<region>.grafana.net"},
     {"name": "ENVIRONMENT", "value": "production"}
     ```
   - `secrets` additions:
     ```json
     {"name": "OTEL_EXPORTER_OTLP_HEADERS", "valueFrom": "arn:aws:secretsmanager:__REGION__:__ACCOUNT_ID__:secret:ams-grafana-cloud:OTEL_EXPORTER_OTLP_HEADERS::"},
     {"name": "PYROSCOPE_AUTH_TOKEN", "valueFrom": "arn:aws:secretsmanager:__REGION__:__ACCOUNT_ID__:secret:ams-grafana-cloud:PYROSCOPE_AUTH_TOKEN::"},
     {"name": "PYROSCOPE_BASIC_AUTH_USERNAME", "valueFrom": "arn:aws:secretsmanager:__REGION__:__ACCOUNT_ID__:secret:ams-grafana-cloud:PYROSCOPE_BASIC_AUTH_USERNAME::"}
     ```
   - Ensure `taskRoleArn` policy includes `secretsmanager:GetSecretValue` for the new secret ARN.

3. Create `infra/grafana-cloud/iam-role-trust-policy.json`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"AWS": "arn:aws:iam::008923505280:root"},
       "Action": "sts:AssumeRole",
       "Condition": {"StringEquals": {"sts:ExternalId": "<external-id-from-gc-ui>"}}
     }]
   }
   ```
   The principal account ID is GC's published AWS account at time of writing; verify against `https://grafana.com/docs/grafana-cloud/monitor-infrastructure/aws/cloudwatch/` before committing.

4. Create `infra/grafana-cloud/iam-role-permissions.json` (read-only inline policy):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "logs:FilterLogEvents",
         "logs:DescribeLogGroups",
         "logs:GetLogEvents",
         "cloudwatch:GetMetricData",
         "cloudwatch:GetMetricStatistics",
         "cloudwatch:ListMetrics",
         "tag:GetResources",
         "rds:DescribeDBInstances",
         "ec2:DescribeRegions",
         "ec2:DescribeInstances"
       ],
       "Resource": "*"
     }]
   }
   ```

5. Create `infra/grafana-cloud/README.md`. Runbook contents:
   - Step 1: create the IAM role via `aws iam create-role` + `aws iam put-role-policy` using the two JSON files above.
   - Step 2: in GC UI, Connections → Add new connection → AWS. Paste the role ARN. Click "Test connection."
   - Step 3: enable the CloudWatch Logs integration; select the `/ecs/ams-backend` log group (already created by the existing `awslogs` log driver).
   - Step 4: enable the CloudWatch Metrics integration; select namespaces `AWS/ECS`, `AWS/ApplicationELB`, `AWS/RDS`, `AWS/ECS/ContainerInsights`.
   - Step 5: wait ~5 min for the first metrics and logs to populate in the stack.
   - Step 6: key rotation procedure. Generate a new API key in GC UI, update the Secrets Manager secret, force an ECS task redeploy (`aws ecs update-service --force-new-deployment`). Revoke the old key after the new task is healthy.

6. Update `infra/ecs/README.md`: document the `ams-grafana-cloud` secret, its expected JSON keys, and a one-line pointer to `infra/grafana-cloud/README.md` for the IAM role setup.

7. Update existing `config/grafana/dashboards/*.json` (6 files: `00-start-here`, `01-operations-overview`, `02-service-drilldown`, `03-repair-journey`, `04-logs-traces-profiles`, `05-mysql`):
   - Add an `$environment` template variable to every dashboard with options `local` and `production`. Wire each panel's query to filter on `environment="$environment"`.
   - Drop cAdvisor-sourced panels in dashboards 01 and 02. Replace with ECS Container Insights equivalents via GC's CloudWatch DS (namespace `AWS/ECS/ContainerInsights`, metrics `CpuUtilized`, `MemoryUtilized`).
   - Drop mysqld-exporter-sourced panels in dashboard 05. Replace with RDS Enhanced Monitoring panels (namespace `AWS/RDS`, metrics `CPUUtilization`, `DatabaseConnections`, `DiskQueueDepth`).
   - Audit any panel that previously referenced the local CloudWatch DS UID (from the closed PR #75); rewire to GC's CloudWatch DS UID.

8. Create `scripts/sync_grafana_cloud_dashboards.py` (one-shot, deleted in Phase 6):
   - Reads `config/grafana/dashboards/*.json`.
   - POSTs each to `https://<stack>.grafana.net/api/dashboards/db` with bearer auth from `GRAFANA_CLOUD_API_KEY` env var.
   - Idempotent: upserts by dashboard UID.

9. Update `docs/system-design/08-deployment-operations.md`:
   - Add `§ Grafana Cloud production observability` with: GC stack URL and login procedure; the `ams-grafana-cloud` secret shape; pointer to `infra/grafana-cloud/README.md` for IAM setup; free-tier quotas to monitor and recovery actions when a quota is hit.
   - Supersede any existing "Observability stack: CloudWatch reader" content from PR #75 (long-lived IAM user pattern is gone; cross-account role is in).

10. Update `docs/plans/observability-implementation-plan.md`: at the top of Phase 6 (CloudWatch DS), add `**STATUS: SUPERSEDED by observability-prod-migration-plan.md Phase 4.**`.

### Files touched

- `infra/ecs/backend-task-def.json`
- `infra/ecs/README.md`
- `infra/grafana-cloud/iam-role-trust-policy.json` (new)
- `infra/grafana-cloud/iam-role-permissions.json` (new)
- `infra/grafana-cloud/README.md` (new)
- `scripts/sync_grafana_cloud_dashboards.py` (new, transient — deleted in Phase 6)
- `config/grafana/dashboards/00-start-here.json` through `05-mysql.json` (modify all 6)
- `docs/system-design/08-deployment-operations.md`
- `docs/plans/observability-implementation-plan.md`

### Validation

Pre-deploy (local):
```bash
python -m json.tool infra/grafana-cloud/iam-role-trust-policy.json > /dev/null
python -m json.tool infra/grafana-cloud/iam-role-permissions.json > /dev/null
python -m json.tool infra/ecs/backend-task-def.json > /dev/null
python scripts/sync_grafana_cloud_dashboards.py --dry-run   # parse, no POST
```

Post-deploy (after CI/CD ships the new task def):
```bash
# 1. Confirm task def has the new env vars and secrets
aws ecs describe-task-definition --task-definition ams-backend \
  --query 'taskDefinition.containerDefinitions[0].{env: environment, secrets: secrets}'

# 2. Confirm rollout completed
aws ecs describe-services --cluster ams-prod --services ams-backend \
  --query 'services[0].deployments[0].rolloutState'
# expect: "COMPLETED"

# 3. Drive a real request to seed signals
curl -X POST https://<ALB-DNS>/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"ChangeMe123"}'

# 4. In GC's Explore pane, verify within 30s:
#    Traces:   {service.name="ams-backend", environment="production"}
#    Metrics:  http_server_requests_total{environment="production"}
#    Logs:     {service="ams-backend", environment="production"}
#    Profiles: application = ams-backend.<replica>
```

Dashboard import + cutover:
```bash
GRAFANA_CLOUD_API_KEY=<key> python scripts/sync_grafana_cloud_dashboards.py
# Open GC UI, navigate to each of the 6 dashboards, switch $environment to production.
# Confirm every panel renders. Screenshot for the M6 demo deck.
```

Pyroscope-in-prod verification:
```bash
# Open GC's Pyroscope flamegraph view; filter application = ams-backend.<replica>.
# Within 60s of the first request, the flamegraph should populate.
# If empty: implement the gunicorn post_fork fallback (see Known gotchas).
```

### Known gotchas

- The cross-account trust policy needs `sts:ExternalId`. Without it, GC's "Test connection" still succeeds (because they assume from their own console), but AWS Security Hub flags it as a finding. Always require the external ID.
- GC's hosted CloudWatch Metrics integration polls AWS at 60s intervals by default. For dashboards that want sub-minute resolution, use the OTLP-pushed Prom metrics from the app, not CloudWatch.
- If Pyroscope samples don't appear within 60s in production, the sampling thread didn't survive the gunicorn worker fork. Fallback: create `backend/gunicorn.conf.py` with:
  ```python
  def post_fork(server, worker):
      from app.core.config import get_settings
      from app.core.observability import maybe_setup_profiling
      maybe_setup_profiling(get_settings())
  ```
  Add `--config /app/gunicorn.conf.py` to the gunicorn command in `backend/Dockerfile.prod`. This guarantees Pyroscope starts inside the worker, regardless of `WEB_CONCURRENCY`.
- The OTel SDK's `OTLPMetricExporter` and `OTLPLogExporter` default to gRPC on 4317. GC's gateway accepts both gRPC (`https://otlp-gateway-…:443`) and HTTP (`https://otlp-gateway-…/otlp/v1/<signal>`). Stay on gRPC for consistency with the existing traces wire. The endpoint URL in `OTEL_ENDPOINT` is the gRPC base; the SDK suffixes the signal path itself.
- `environment` as a Prom label vs as an OTel resource attribute: the OTel SDK maps resource attributes to Prom labels at the remote_write boundary. Verify with `curl https://prometheus-prod-<region>.grafana.net/api/v1/labels` that `environment` shows up. If not, add an explicit `View` instrument-attribute to surface it.
- GC's CloudWatch DS does not carry a native `environment` label (AWS doesn't tag metrics that way). For dashboard panels sourced from CloudWatch, filter by ECS service / cluster name instead and hide the panel when `$environment=local` (use Grafana's panel visibility rule).

---

## Phase 5: k6 load tests rebase (formerly Phase 7)

**Session goal:** Rebase PR #84 (k6 load + stress scripts, traffic generator, AccessLogMiddleware) onto post-Phase-3 `feat/observability` head. Resolve conflicts from the deleted compose overlay and the OTLP refactor. Verify access log lines emit `trace_id` and flow through to GC Loki.

### Prerequisites

- Phase 3 merged.
- PR #84's branch `feat/observability-phase7-k6` checked out.
- Required reading: PR #84 description; the current `backend/app/core/observability.py` on `feat/observability` post-Phase-3 (specifically the OTel logs bridge surface); `load/lib/auth.js`, `load/k6-load.js`.

### Scope

1. Rebase the branch:
   ```bash
   git fetch origin feat/observability
   git checkout feat/observability-phase7-k6
   git rebase origin/feat/observability
   ```

2. Resolve conflicts:
   - `backend/app/core/observability.py`: PR #84's `AccessLogMiddleware` lands on top of the OTLP-native shape. The middleware emits via `structlog.get_logger("app.access")`; since Phase 3 bridges structlog to OTel logs, access log lines flow to GC automatically. No middleware code change; just resolve the merge conflict.
   - `docker-compose.observability.yml`: deleted in Phase 2. Drop the conflicting hunks during rebase.
   - `docker-compose.yml`: small env var adjustments (e.g. `RATE_LIMIT_ENABLED` default). Re-apply.
   - `Makefile`: Phase 2 removed `obs-*` targets. PR #84's k6 targets survive. Keep the k6 targets, drop any `obs-*` references that re-appeared via the rebase.
   - `config/grafana/dashboards/*.json`: PR #84's dashboard hygiene fixes (commit 9fdfe9a) survive into the rebased branch. Phase 4 layers the `$environment` template variable on top later; do not pre-apply here.

3. Update the k6 scripts (`load/k6-load.js`, `k6-stress.js`, `k6-spike.js`, `k6-steady.js`, `k6-smoke.js`, `k6-consistent.js`):
   - The `--out experimental-prometheus-rw` flag previously pointed at local `prometheus:9090`. Switch to GC's Prom remote_write endpoint. Read `K6_PROMETHEUS_RW_SERVER_URL`, `K6_PROMETHEUS_RW_USERNAME`, `K6_PROMETHEUS_RW_PASSWORD` from env.
   - Update `load/README.md` with the new invocation, including how to source the three env vars from a developer's `.env`.
   - Document that the backend's own metrics still flow via the OTLP pipeline; k6's remote_write is just for k6's own per-request metrics.

4. Verify the access-log round trip: start the backend locally with `OTEL_ENABLED=true` pointing at GC, run `load/k6-smoke.js`, then in GC Loki query `{service.name="ams-backend", environment="local"}` and confirm every access log line carries a non-empty `trace_id` that resolves to a Tempo span.

5. Force-push the rebased branch:
   ```bash
   git push --force-with-lease origin feat/observability-phase7-k6
   ```

6. Update PR #84 description: note the rebase, the OTLP-native backend it sits on top of, and the new k6 remote_write env variables.

### Files touched

- (rebase-only conflict resolution, no new files)
- `load/k6-load.js`, `k6-stress.js`, `k6-spike.js`, `k6-steady.js`, `k6-smoke.js`, `k6-consistent.js`
- `load/README.md`

### Validation

```bash
# 1. Rebase produced a clean tree
git status
git log --oneline origin/feat/observability..HEAD | head -20  # PR #84's commits atop Phase 3

# 2. Backend tests still pass
cd backend && pytest -v

# 3. k6 smoke against local backend pushing to GC
cd ..
docker compose up -d backend mysql
K6_PROMETHEUS_RW_SERVER_URL=<gc_prom_url> \
K6_PROMETHEUS_RW_USERNAME=<gc_prom_instance_id> \
K6_PROMETHEUS_RW_PASSWORD=<gc_api_key> \
k6 run --out experimental-prometheus-rw load/k6-smoke.js

# 4. In GC Explore (Loki): {service.name="ams-backend", environment="local"}
#    Expect: access log lines from the k6 run, each with trace_id and route.
#    Click trace_id → Tempo opens the matching span.
```

### Known gotchas

- The `AccessLogMiddleware` reads `route_template = getattr(route, "path", scope.get("path", ""))`. This survives the rebase. But if the structlog → OTel bridge strips structured fields, the `route` field may be missing from the OTel `LogRecord`. Verify the round trip in step 4. If `route` is dropped, register it as a resource attribute via `LoggingHandler(... , attributes_filter=...)`.
- `experimental-prometheus-rw` output requires k6 >= 0.46. PR #84 already pins 0.54.0.
- k6's remote_write to GC has the same per-series cardinality limits as the app. If k6 emits per-VU labels (e.g. `vu=42`), that's bounded by the run's VU count; safe. But avoid per-iteration labels or any high-cardinality dimension.

---

## Phase 6: Delete repo-side dashboard JSONs

**Session goal:** Remove the `config/grafana/dashboards/*.json` files and the one-shot sync script. Grafana Cloud becomes the sole source of truth for dashboard JSON. Document the export procedure for ad-hoc backups.

### Prerequisites

- Phase 4 merged AND production cutover verified: operator confirms all 6 dashboards render correctly in GC with `environment=production`, AND Pyroscope samples are flowing in production.
- Branch off latest `feat/observability` named `feat/observability-dashboards-gc-only`.
- Required reading: `infra/grafana-cloud/README.md` (Phase 4 runbook).

### Scope

1. Delete `config/grafana/dashboards/00-start-here.json` through `05-mysql.json` (all 6 files).
2. Delete `scripts/sync_grafana_cloud_dashboards.py` (one-shot tool from Phase 4, no longer needed).
3. Update `docs/system-design/08-deployment-operations.md`:
   - Update the "Grafana Cloud production observability" section to note GC is the source of truth for dashboards.
   - Document the GC API export procedure for ad-hoc backups:
     ```bash
     # List all dashboards
     curl -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
       "https://<stack>.grafana.net/api/search?type=dash-db" | jq

     # Export one
     curl -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
       "https://<stack>.grafana.net/api/dashboards/uid/<uid>" \
       | jq '.dashboard' > "backup-<uid>.json"
     ```
4. Update `docs/plans/observability-implementation-plan.md`: at the top of Phase 5 (dashboards), add `**STATUS: SUPERSEDED by observability-prod-migration-plan.md Phase 6 — dashboards live in Grafana Cloud only.**`.

### Files touched

- (deletions, Scope steps 1-2)
- `docs/system-design/08-deployment-operations.md`
- `docs/plans/observability-implementation-plan.md`

### Validation

```bash
# Confirm no JSON files left
ls config/grafana/dashboards/ 2>/dev/null && echo "FAIL: residual JSONs" || echo "OK"
test -d config/grafana/dashboards && echo "FAIL: dir still exists" || echo "OK"

# Confirm sync script is gone
test -f scripts/sync_grafana_cloud_dashboards.py && echo "FAIL" || echo "OK"

# Confirm GC still has all 6 dashboards
curl -s -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
  "https://<stack>.grafana.net/api/search?type=dash-db" | jq 'length'
# expect: 6
```

### Known gotchas

- After this phase merges, dashboard edits happen only in the GC UI. If version-controlled dashboards matter, set up a parallel `grafana-dashboard-backups` repo and a scheduled export job before merging Phase 6.
- If the GC free tier expires or the stack is deleted, the dashboard JSONs are gone for good. Take an export immediately before any major GC account change.

---

## Risk register (this plan)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OTel metrics refactor loses fidelity vs `prometheus_fastapi_instrumentator` (attribute set differs, dashboard queries break) | Medium | High | Use OTel SDK `View` to re-shape names; allocate full 6-9 h to Phase 3; explicit test in `test_observability.py` |
| structlog → OTel logs bridge silently drops `trace_id` | Medium | High | Phase 3 includes a test that emits inside a span and asserts trace_id on the captured LogRecord |
| Pyroscope sampling thread doesn't survive `WEB_CONCURRENCY=1` worker fork | Medium | Medium | Phase 4 cutover step verifies via GC UI; fallback documented (`gunicorn.conf.py post_fork` hook) |
| GC free-tier quota exhausted by combined local + prod traffic (10k Prom series, 50 GB logs/traces, 14-day retention, 3 active users) | Low | Medium | Audit cardinality before enabling; consider separate GC stacks for `local` and `production` if quota tightens |
| Phase 5 rebase hits unresolvable conflict because PR #84's surface drifted too far from Phase 3's refactor | Low | Medium | Apply Phase 5 rebase as soon as Phase 3 stabilises; resolve conflicts in small commits |
| Local dev without GC credentials becomes harder; new contributors need an onboarding step | Medium | Low | Document in CLAUDE.md; `OTEL_ENABLED=false` continues to work for credential-less dev |
| Closing PR #75 and reopening loses inline-review history | Low | Low | Confirmed no review activity on PR #75 at planning time |
| Phase 6 deletion of repo-side dashboards means future dashboard edits are unversioned | Medium | Low | Document GC API export procedure; consider parallel backup repo |
| Cross-account IAM role principal ID drifts (GC publishes a new account number) | Low | Medium | `infra/grafana-cloud/README.md` includes the GC docs URL to verify the principal ID at setup time |

---

## Estimated complexity

- Phase 1 (pre-flight rebase): Low (30 min)
- Phase 2 (prune local stack): Low (2-3 h), mostly deletions
- Phase 3 (OTLP refactor): High (6-9 h), substantial backend changes plus tests
- Phase 4 (AWS production via GC): Medium-High (5-7 h, plus deploy verification wall time)
- Phase 5 (k6 rebase): Medium (2-4 h)
- Phase 6 (dashboard JSON deletion): Low (30 min)

**Total:** 16-24 hours of focused work. Fits inside W7 buffer.
