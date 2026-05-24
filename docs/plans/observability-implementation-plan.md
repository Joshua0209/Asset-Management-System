# Observability Implementation Plan (`feat/observability`)

**Status:** Drafted 2026-05-20. Branch state at draft time: clean — no diff vs `main`.

**Scope:** Stand up the W6 Grafana observability stack (Prometheus + Loki + Tempo + Pyroscope + Alloy + cAdvisor + `mysqld-exporter` + Grafana) for AMS, wired to FastAPI and the nginx-served Vite frontend, with k6 load/stress tests, the live correlation demo from M6 (Loki log line → Tempo trace → Pyroscope flamegraph in one click), and a CloudWatch datasource that surfaces the deployed ECS service in the same Grafana.

**Out of scope on this branch:**

- DESIGN.md theme application (W5 carry, owned by the one dev seat in W6, separate branch).
- Playwright E2E suite (W5 carry, owned by the QA seat, separate branch).
- AWS provisioning smoke test of PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) — already merged on `main`; the `workflow_dispatch` smoke test runs against the deployed environment and is not a code change.

**Reference lab:** `../2025-05-observability-demo/` (sibling local checkout). The compose layout, Alloy config, and dashboards are the closest working precedent. AMS is structurally simpler (single FastAPI + single MySQL + nginx-served SPA, not three replicas of each), so the AMS plan trims rather than copies.

**Locked decisions** (per `docs/roadmap.md` § Week 6 refinements):

1. Backend stays `gunicorn --workers 1`; aggregate across tasks at scrape time. The `_enforce_single_worker_invariant` guard in `backend/app/main.py` already refuses to boot with >1 worker while rate limiting is on.
2. Add `prom/mysqld-exporter` as a compose sidecar. Closes the DB-server-metrics gap.
3. Frontend logs via nginx `log_format json_combined`, not an Express runtime. Prod image is `nginx:alpine`.
4. cAdvisor labels via Alloy `discovery.docker` relabel on `com.docker.compose.service`, not per-service `cgroup_parent` in compose.
5. Pyroscope: stay on `pyroscope-io` Python SDK. Lazy-imported. **Off by default in prod image** (gunicorn fork interaction), on in local demo.
6. CloudWatch as a second Grafana datasource (not replaced, not just ECS log sink). Read-only IAM user, region `ap-east-2`.

**Plan-time decisions resolved with user (2026-05-20):**

7. **CloudWatch (Phase 6)** uses a long-lived IAM user (`ams-grafana-reader`), not OIDC federation. Trade-off accepted: one more credential to rotate, in exchange for native Grafana support without an assume-role refresh shim.
8. **`mysqld-exporter` local credentials** stay hardcoded as `exporter:exporter` in `db/init/01-exporter-grant.sql` and `docker-compose.observability.yml`. Compose-only, no parameterisation. The Phase 3 grant explicitly limits this user to `PROCESS, REPLICATION CLIENT, SELECT` so the blast radius is read-only metrics.
9. **`make obs-pull`** is added to a pre-rehearsal checklist in `docs/system-design/08-deployment-operations.md` § "Observability stack" (Phase 9).

---

## Multi-session strategy

Each phase below is a self-contained session. Read `Prerequisites`, `Scope`, `Files touched`, and `Validation` for the phase you are picking up — that alone is enough to start cold.

Phase order respects dependencies, but Phases 1, 2, 5, 6, 7 can be parallelised if more than one session runs concurrently. Phases 3 and 4 must come before Phase 5.

| # | Phase | Depends on |
|---|---|---|
| 1 | Backend instrumentation | — |
| 2 | Frontend instrumentation | — |
| 3 | Observability stack overlay (compose) | — |
| 4 | Alloy + collector configs | 3 |
| 5 | Grafana dashboards | 3, 4 |
| 6 | CloudWatch datasource + IAM | 3 |
| 7 | k6 load + stress tests | 1, 2, 3, 4 |
| 8 | Middleware-order regression test | 1 |
| 9 | Verification + correlation demo + docs | 1–7 |

---

## Phase 1 — Backend instrumentation

**Session goal:** FastAPI exposes `/metrics`, emits OTLP traces, writes structured JSON logs with `trace_id`, and can optionally emit Pyroscope profiles in the local demo image.

### Prerequisites

- None on the branch (no prior phase required).
- Required reading: `backend/app/main.py` (lines 33–170 cover the middleware ordering and the `_enforce_single_worker_invariant` guard — do NOT break either).
- Required reading: `docs/system-design/08-deployment-operations.md` § "API Hardening: Rate Limiting" — explains why `--workers 1` is load-bearing for slowapi's `MemoryStorage`.

### Scope

1. **Add deps to `backend/pyproject.toml`** (under `[project] dependencies`):
   - `prometheus-fastapi-instrumentator>=7.0,<8.0`
   - `opentelemetry-api>=1.27,<2.0`
   - `opentelemetry-sdk>=1.27,<2.0`
   - `opentelemetry-instrumentation-fastapi>=0.48b0,<1.0`
   - `opentelemetry-instrumentation-sqlalchemy>=0.48b0,<1.0`
   - `opentelemetry-exporter-otlp-proto-grpc>=1.27,<2.0`
   - `structlog>=24.1,<26.0`
   - Add to optional `[project.optional-dependencies] prod` (separate from runtime since it's lazy-loaded): `pyroscope-io>=0.8,<1.0`

2. **`backend/app/core/observability.py` (new)** — central wiring, called from `app.main` AFTER middleware setup but BEFORE `app.include_router`. Functions:
   - `setup_metrics(app)` — mounts `/metrics`. Must `.expose(app, include_in_schema=False, should_gzip=True)` and the `/metrics` route must be exempt from rate limiting (`@limiter.exempt`) and from auth. Custom counters: `ams_fsm_transitions_total{from,to,asset_kind}`, `ams_optimistic_conflicts_total{endpoint,code}`. Increment from the two places that already raise 409 (audit log writer + repair-request FSM service) — wrap the existing call paths, do not duplicate transition logic.
   - `setup_tracing(app, settings)` — `TracerProvider` with `service.name=ams-backend`, `service.instance.id=$HOSTNAME`, OTLP gRPC exporter to `settings.otel_endpoint` (default `http://alloy:4317`), `BatchSpanProcessor`. Calls `FastAPIInstrumentor.instrument_app(app)` and `SQLAlchemyInstrumentor().instrument(engine=engine)`. Adds a structlog processor that pulls the active span's trace_id into the log record.
   - `setup_logging(settings)` — replaces uvicorn's default access log with a structlog JSON renderer. Fields: `level`, `service`, `replica`, `method`, `path`, `status`, `duration_ms`, `trace_id`. Override uvicorn's `access` logger to silence its plaintext line so we don't double-log.
   - `maybe_setup_profiling(settings)` — if `settings.pyroscope_enabled`, lazy-import `pyroscope` and call `configure(application_name=f"ams-backend.{settings.replica_id}", server_address=settings.pyroscope_server)`. Wrap in try/except ImportError so missing-package in prod is a logged warning, not a crash.

3. **`backend/app/core/config.py`** — extend `Settings` with optional fields (default safe-off):
   - `otel_enabled: bool = False`, `otel_endpoint: str = "http://alloy:4317"`
   - `pyroscope_enabled: bool = False`, `pyroscope_server: str = "http://pyroscope:4040"`
   - `replica_id: str = os.environ.get("HOSTNAME", "ams-backend-0")`
   - `log_format: str = "json"` (so `pytest` can set `text` for readable test logs)

4. **`backend/app/main.py` integration:**
   - Call `setup_logging(settings)` very early (before logger.warning calls in `_enforce_single_worker_invariant` so they land as JSON).
   - Call `setup_metrics(app)` after `SlowAPIMiddleware` is registered. **Verify Prometheus middleware comes after slowapi** — slowapi must see and rate-limit `/metrics` traffic if it ever leaks, but we then `@limiter.exempt` the route. Document the order with a comment, since the existing middleware code has paragraph-length explanations.
   - Call `setup_tracing(app, settings)` after the engine is created (`from app.db.session import engine` already imports it).
   - Call `maybe_setup_profiling(settings)`.

5. **Increment counters at the existing 409 + transition sites:**
   - `backend/app/services/repair_request_service.py` (FSM transitions): increment `ams_fsm_transitions_total` on each successful state change.
   - `backend/app/api/v1/assets.py` + `backend/app/api/v1/repair_requests.py`: increment `ams_optimistic_conflicts_total{endpoint, code}` in the `except StaleDataError`/`raise HTTPException(409, ...)` branches. Code label uses the existing granular codes (`duplicate_request`, `invalid_transition`, `version_conflict`, ...).

### Files touched

- `backend/pyproject.toml` (deps)
- `backend/app/core/observability.py` (new)
- `backend/app/core/config.py` (Settings additions)
- `backend/app/main.py` (wire it up, comment middleware order)
- `backend/app/services/repair_request_service.py` (FSM counter)
- `backend/app/api/v1/assets.py` (conflict counter)
- `backend/app/api/v1/repair_requests.py` (conflict counter)
- `backend/tests/test_observability.py` (new) — smoke tests:
  - `GET /metrics` returns 200 and contains a process_resident_memory_bytes line (instrumentator default).
  - `GET /metrics` is exempt from rate limiting (hit it 200 times, expect 200s).
  - After a 409 conflict, the corresponding `ams_optimistic_conflicts_total` line in `/metrics` increments.
  - Log capture asserts the structlog JSON renderer emits `trace_id` when a span is active.

### Validation

```bash
cd backend
ruff check .
mypy app
pytest tests/test_observability.py -v
pytest --cov=app --cov-report=term  # confirm 80% threshold survives
docker compose up --build backend  # /metrics reachable on 8000
curl http://localhost:8000/metrics | head -30
```

### Known gotchas

- `FastAPIInstrumentor.instrument_app` must be called **after** the routes are added if you want their attributes on spans; reading `app.routes` before the include is fine because the middleware works dynamically. The reference lab calls it before the router include — match that.
- `prometheus-fastapi-instrumentator` reads metrics labels from the matched route's `path` template (not the raw URL), so high-cardinality path-param explosion is already prevented. Do not override `instrument()` with a path-extractor.
- `pyroscope-io` starts a sampling thread inside `configure()`. Gunicorn forks workers *after* `app` import, so the thread dies in the child. This is why the prod image keeps `PYROSCOPE_ENABLED=false`. In local demo (uvicorn `--reload`, single process) it works.

---

## Phase 2 — Frontend instrumentation

**Session goal:** Production nginx writes structured JSON access logs to stdout (and so to Docker's JSON file driver). The browser emits OTLP traces for page loads + fetches to Alloy's HTTP endpoint.

### Prerequisites

- Phase 3 not required, but easier to validate after the overlay is up. Either order works.
- Required reading: `frontend/nginx.conf` (current production server block).
- Required reading: `frontend/Dockerfile.prod`.

### Scope

1. **`frontend/nginx.conf`** — add to the `http {}` block:
   ```nginx
   log_format json_combined escape=json
     '{'
       '"timestamp":"$time_iso8601",'
       '"remote_addr":"$remote_addr",'
       '"method":"$request_method",'
       '"path":"$request_uri",'
       '"status":$status,'
       '"bytes":$body_bytes_sent,'
       '"referer":"$http_referer",'
       '"user_agent":"$http_user_agent",'
       '"request_time_ms":$request_time,'
       '"upstream_time_ms":"$upstream_response_time"'
     '}';
   access_log /var/log/nginx/access.log json_combined;
   error_log  /var/log/nginx/error.log warn;
   ```
   Default nginx images already symlink `/var/log/nginx/access.log` → `/dev/stdout`. Verify in `frontend/Dockerfile.prod` — if not, add the symlink lines.

2. **`frontend/package.json`** — add deps:
   - `@opentelemetry/sdk-trace-web@^1.27.0`
   - `@opentelemetry/auto-instrumentations-web@^0.42.0`
   - `@opentelemetry/exporter-trace-otlp-http@^0.55.0`
   - `@opentelemetry/resources@^1.27.0`
   - `@opentelemetry/semantic-conventions@^1.27.0`

3. **`frontend/src/observability.ts` (new)** — initialised from `main.tsx` *before* `createRoot(...).render(...)`. Reads `VITE_OTEL_ENDPOINT` (default `http://localhost:4318/v1/traces`). Sets `service.name=ams-frontend`. Registers `getWebAutoInstrumentations()` with `instrumentation-fetch` and `instrumentation-document-load` enabled, `instrumentation-xml-http-request` disabled (the app uses fetch only). Configures `propagateTraceHeaderCorsUrls` to match the backend origin.

4. **`frontend/src/main.tsx`** — `import './observability'` at the top, gated on `import.meta.env.VITE_OTEL_ENABLED === 'true'` so the dev local-only build is unaffected.

5. **`frontend/.env.example`** — document `VITE_OTEL_ENABLED` and `VITE_OTEL_ENDPOINT`.

6. **`docker-compose.yml`** (NOT the prod compose) — when the overlay (Phase 3) is layered on top, the frontend will receive `VITE_OTEL_ENABLED=true` and `VITE_OTEL_ENDPOINT=http://localhost:4318/v1/traces` (browser → Alloy direct, demo only). In production, do NOT set these — the prod image stays unset and the browser never tries to reach Alloy.

### Files touched

- `frontend/nginx.conf`
- `frontend/Dockerfile.prod` (if access-log symlink is missing)
- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/observability.ts` (new)
- `frontend/src/main.tsx`
- `frontend/.env.example`

### Validation

```bash
cd frontend
npm install
npm run build  # tsc + vite build both green
npm run typecheck
npm run lint
# After Phase 3 overlay is up:
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
# Hit the frontend in a browser; check Alloy logs:
docker compose logs alloy | grep otlp
# Open Grafana, query Tempo for service.name=ams-frontend
```

### Known gotchas

- nginx's `$request_time` is **seconds**, not ms, despite the field name we use. Either rename or multiply at dashboard time. The reference lab does the multiply at dashboard time — match that.
- Browser OTLP requires CORS on Alloy's `:4318` endpoint. Alloy's `otelcol.receiver.otlp` HTTP block must include `cors { allowed_origins = ["http://localhost:5173", "http://localhost:8080"] }`. Add this in Phase 4.
- `OTEL_EXPORTER_OTLP_ENDPOINT` env var on the browser side does not work the same way as on Node — it must be passed in code, not env, because Vite freezes env values at build time. That's why `VITE_OTEL_ENDPOINT` is used and read inside `observability.ts`.

---

## Phase 3 — Observability stack compose overlay

**STATUS: SUPERSEDED by [observability-prod-migration-plan.md](observability-prod-migration-plan.md).** The local docker-compose observability overlay was pruned in Phase 2 of that plan; telemetry now flows from both local dev and production directly to Grafana Cloud. The content below is kept for historical context.

**Session goal:** `docker compose -f docker-compose.yml -f docker-compose.observability.yml up` brings up the full stack alongside the existing `mysql + backend + frontend`.

### Prerequisites

- None. Phase 1 and Phase 2 are not required to bring the stack up; without them, dashboards just look empty.
- Required reading: `../2025-05-observability-demo/docker-compose.yml` (the layout to mirror).

### Scope

1. **`docker-compose.observability.yml` (new)** — overlay file. Services:
   - `grafana` (`grafana/grafana:11.3.1`) — port `3000:3000`, env `GF_SECURITY_ADMIN_USER=admin`, `GF_SECURITY_ADMIN_PASSWORD=admin`, `GF_FEATURE_TOGGLES_ENABLE=traceqlEditor correlations traceToProfiles`. Volumes: `./config/grafana/provisioning:/etc/grafana/provisioning:ro`, `./config/grafana/dashboards:/var/lib/grafana/dashboards:ro`, named `grafana-data:/var/lib/grafana`.
   - `prometheus` (`prom/prometheus:v2.55.1`) — port `9090:9090`, command flags include `--web.enable-remote-write-receiver` and `--web.enable-lifecycle`. Volume: `./config/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro` + named `prometheus-data:/prometheus`.
   - `loki` (`grafana/loki:3.2.1`) — port `3100:3100`. Volume: `./config/loki/loki.yml:/etc/loki/loki.yml:ro` + named `loki-data:/loki`.
   - `tempo` (`grafana/tempo:2.6.1`) — port `3200:3200`. Volume: `./config/tempo/tempo.yml:/etc/tempo/tempo.yml:ro` + named `tempo-data:/var/tempo`.
   - `pyroscope` (`grafana/pyroscope:1.9.0`) — port `4040:4040`. Volume: `./config/pyroscope/pyroscope.yml:/etc/pyroscope/pyroscope.yml:ro` + named `pyroscope-data:/var/lib/pyroscope`.
   - `alloy` (`grafana/alloy:v1.5.1`) — ports `12345:12345`, `4317:4317`, `4318:4318`. Volumes: `./config/alloy/config.alloy:/etc/alloy/config.alloy:ro`, `${DOCKER_ROOT_DIR:-/var/lib/docker}/containers:/var/lib/docker/containers:ro`, `/var/run/docker.sock:/var/run/docker.sock:ro`, named `alloy-data:/var/lib/alloy/data`.
   - `cadvisor` (`gcr.io/cadvisor/cadvisor:v0.49.1`) — privileged, mounts `/`, `/var/run`, `/sys`, `${DOCKER_ROOT_DIR:-/var/lib/docker}/`, `/dev/disk/`. No host port — only Alloy scrapes it.
   - `mysqld-exporter` (`prom/mysqld-exporter:v0.15.1`) — connects via env `DATA_SOURCE_NAME=exporter:exporter@(mysql:3306)/`. Depends on `mysql` healthy.

2. **Augment the existing `backend` service in `docker-compose.yml`** (overlay override block, NOT in the main compose file — keep dev untouched by default):
   - In `docker-compose.observability.yml`, add an override block for `backend`:
     - `environment` adds `OTEL_ENABLED=true`, `OTEL_ENDPOINT=http://alloy:4317`, `PYROSCOPE_ENABLED=true`, `PYROSCOPE_SERVER=http://pyroscope:4040`, `LOG_FORMAT=json`, `REPLICA_ID=ams-backend-1`.
     - `labels` adds `com.docker.compose.service: backend` (defaults provide this anyway; declare for clarity in Alloy relabel rules).
   - Same pattern for `frontend`: `VITE_OTEL_ENABLED=true`, `VITE_OTEL_ENDPOINT=http://localhost:4318/v1/traces`.

3. **`.env.example` (top-level, new or augment)** — document `DOCKER_ROOT_DIR` (rootless Docker users). Default `/var/lib/docker`.

4. **`Makefile` (new or augment)** — convenience targets:
   ```makefile
   obs-up:   ; docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
   obs-down: ; docker compose -f docker-compose.yml -f docker-compose.observability.yml down
   obs-logs: ; docker compose -f docker-compose.yml -f docker-compose.observability.yml logs -f $${SERVICE:-alloy}
   obs-pull: ; docker compose -f docker-compose.yml -f docker-compose.observability.yml pull
   ```

5. **MySQL grant for `mysqld-exporter`** — `db/init/01-exporter-grant.sql` (new). Mount into the `mysql` service via `docker-compose.yml`'s existing volumes config (the overlay overrides the mysql service to add the mount only when the overlay is layered):
   ```sql
   CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED BY 'exporter' WITH MAX_USER_CONNECTIONS 3;
   GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
   ```
   MySQL 8.4 auto-runs files under `/docker-entrypoint-initdb.d/` on first boot. Document that `docker compose down -v` is required to re-seed if the user already exists from a previous boot.

### Files touched

- `docker-compose.observability.yml` (new)
- `.env.example` (top-level, new or augment)
- `Makefile` (new or augment)
- `db/init/01-exporter-grant.sql` (new)
- `config/prometheus/prometheus.yml` (new — minimal: just remote-write receiver enabled)
- `config/loki/loki.yml` (new — copy from reference)
- `config/tempo/tempo.yml` (new — copy from reference, single-tenant)
- `config/pyroscope/pyroscope.yml` (new — copy from reference)
- `config/grafana/provisioning/` (placeholders; filled in Phase 5/6)
- `config/grafana/dashboards/` (placeholders; filled in Phase 5)
- `config/alloy/config.alloy` (placeholder; filled in Phase 4)

### Validation

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml config  # parse only
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
docker compose ps                              # all services healthy
curl -s http://localhost:3000/api/health        # grafana up
curl -s http://localhost:9090/-/healthy         # prom up
curl -s http://localhost:3100/ready             # loki ready
curl -s http://localhost:3200/ready             # tempo ready
curl -s http://localhost:4040/ready             # pyroscope ready
curl -s http://localhost:12345/-/ready          # alloy ready
docker compose exec mysql mysql -uexporter -pexporter -e "SHOW DATABASES;"
```

### Known gotchas

- Bind-mounting `/var/lib/docker/containers` on macOS Docker Desktop requires Settings → Resources → File Sharing to include the path. On Linux, no extra step. Reference lab's `make up` autodetects via `docker info -f '{{.DockerRootDir}}'`; the Makefile target can do the same.
- cAdvisor on Apple Silicon needs `platform: linux/amd64` in the compose entry — Docker Desktop emulates. Document this in the Makefile help if any teammate runs an M1/M2/M3 Mac.
- Alloy 1.5.x renamed several stage blocks vs. 1.3.x. If you copy from the reference lab and hit "unknown block" errors, check the Alloy 1.5 docs at `https://grafana.com/docs/alloy/latest/`.

---

## Phase 4 — Alloy + collector configs

**STATUS: SUPERSEDED by [observability-prod-migration-plan.md](observability-prod-migration-plan.md).** Alloy was removed from both environments by Phase 2 of that plan; the FastAPI backend now pushes OTLP signals direct to Grafana Cloud's hosted gateways (Phase 3 of the new plan refactors the backend to OTLP-native). The content below is kept for historical context.

**Session goal:** Alloy scrapes backend `/metrics`, cAdvisor, and `mysqld-exporter`; receives OTLP from backend + browser; discovers Docker container logs and relabels with low-cardinality `service` / `replica` / `log_format` labels via `com.docker.compose.service`; forwards everything to the right backend.

### Prerequisites

- Phase 3 stack must be running (so you can iterate without restarting everything).
- Required reading: `../2025-05-observability-demo/config/alloy/config.alloy`.

### Scope

1. **`config/alloy/config.alloy`** — sections:
   - `prometheus.remote_write "local"` → `http://prometheus:9090/api/v1/write`.
   - `prometheus.scrape "ams_backend"` → target `backend:8000`, path `/metrics`, labels `service=backend, replica=ams-backend-1`.
   - `prometheus.scrape "cadvisor"` → target `cadvisor:8080`.
   - `prometheus.scrape "mysqld_exporter"` → target `mysqld-exporter:9104`, labels `service=mysql, replica=ams-mysql`.
   - `otelcol.receiver.otlp "apps"` — gRPC on `:4317`, HTTP on `:4318`. HTTP block must include `cors { allowed_origins = ["http://localhost:5173", "http://localhost:8080"] }` for the browser SDK.
   - `otelcol.processor.batch "traces"` → `otelcol.exporter.otlp "tempo"` → `tempo:4317` insecure.
   - `discovery.docker "containers"` and `discovery.relabel "logs"` — relabel `com.docker.compose.service` → `service`, `__meta_docker_container_name` → `replica`. Add an optional `com.observability.log_format` rule with a default of `json` so the dashboard's log-format dropdown works.
   - `loki.source.docker "containers"` → forward via `loki.process` (JSON stage extracts `trace_id`, `level`, `path`, etc.) → `loki.write` to `http://loki:3100/loki/api/v1/push`.
   - Skip the file-tail `local.file_match` path entirely — `loki.source.docker` reads from the Docker daemon directly and is what current Alloy docs recommend.

2. **`config/prometheus/prometheus.yml`** — minimal: `global.scrape_interval: 15s`. No scrape jobs; Alloy does all scraping and remote-writes.

### Files touched

- `config/alloy/config.alloy` (filled in)
- `config/prometheus/prometheus.yml` (refined)

### Validation

```bash
docker compose exec alloy alloy fmt /etc/alloy/config.alloy   # parse only
# Wait 30s for scrape
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq '.data.result[] | {job: .metric.job, value: .value[1]}'
# Expect: ams_backend=1, cadvisor=1, mysqld_exporter=1
curl -s 'http://localhost:3100/loki/api/v1/labels' | jq
# Expect: service, replica, log_format among labels
# Generate a trace from the browser, then:
curl -s 'http://localhost:3200/api/search?service.name=ams-backend' | jq
```

### Known gotchas

- Alloy's River syntax is whitespace-tolerant but block names are not aliases — `loki.source.docker` and `loki.source.file` are different components. Use `loki.source.docker` for the Docker daemon path; the reference lab uses `loki.source.file` because it predates the daemon block being stable.
- The `loki.process` JSON stage needs `expressions = { trace_id = "trace_id" }` to surface `trace_id` as a *derived* (not indexed) field. Indexed labels would explode cardinality.

---

## Phase 5 — Grafana dashboards

**STATUS: SUPERSEDED by [observability-prod-migration-plan.md](observability-prod-migration-plan.md).** Dashboards now live in Grafana Cloud as the source of truth; Phase 4 of the new plan imports them, Phase 6 deletes the repo-side JSONs. The content below is kept for historical context.

**Session goal:** Six provisioned dashboards exist and load against the live data:
`00 Start Here`, `01 Operations Overview`, `02 Service Drilldown`, `03 Repair Journey`, `04 Logs/Traces/Profiles`, `05 MySQL`.

### Prerequisites

- Phase 3, 4 stack up with traffic (use Phase 7's k6 if available; otherwise hit `/api/v1/assets` manually a few times).
- Required reading: `../2025-05-observability-demo/config/grafana/dashboards/student/`.

### Scope

1. **Datasource provisioning — `config/grafana/provisioning/datasources/datasources.yml`:**
   - Prometheus → `http://prometheus:9090`, default.
   - Loki → `http://loki:3100`. **Derived field**: `trace_id` → Tempo datasource (so a log line click jumps to Tempo).
   - Tempo → `http://tempo:3200`. **traceToLogs** → Loki, filter by `service`. **traceToProfiles** → Pyroscope, default profile type `process_cpu:cpu:nanoseconds:cpu:nanoseconds`.
   - Pyroscope → `http://pyroscope:4040`.

2. **Dashboard provisioning — `config/grafana/provisioning/dashboards/dashboards.yml`:**
   - Provider `default` reads from `/var/lib/grafana/dashboards/*.json`, `allowUiUpdates: false`, `foldersFromFilesStructure: true`.

3. **Dashboards (`config/grafana/dashboards/*.json`):**
   - **`00-start-here.json`** — markdown panel with the demo walkthrough + links to the other dashboards. Mirrors the reference lab.
   - **`01-operations-overview.json`** — RED (rate, error %, p50/p95/p99) and the 4 Golden Signals (latency, traffic, errors, saturation). Two extra panels at the bottom for ECS Container Insights and ALB (filled in Phase 6 with CloudWatch datasource).
   - **`02-service-drilldown.json`** — `service` + `replica` template variables. Per-replica latency histograms, error rates, CPU/mem from cAdvisor. Logs panel filtered by selected `service`/`replica`.
   - **`03-repair-journey.json`** — AMS-specific. Panels:
     - FSM transitions per minute by `(from, to)` — from `ams_fsm_transitions_total`.
     - Conflicts per minute by `code` — from `ams_optimistic_conflicts_total`.
     - p95 latency for each of the 6 critical flows (HTTP route templates `POST /repair-requests`, `PATCH /repair-requests/{id}/review`, ...).
     - Repair-request count by status (`pending_review`, `under_repair`, ...) — derived from FSM counter, or one-off promQL against status enum.
   - **`04-logs-traces-profiles.json`** — single-pane correlation example. Top: a logs panel; middle: a trace view; bottom: a flamegraph. Pre-set the time range to "last 15 minutes" so the panels share data.
   - **`05-mysql.json`** — community dashboard ID `7362` trimmed to demo-relevant panels: InnoDB buffer-pool hit rate, queries/sec, slow queries, connections, lock waits. Use the `mysqld-exporter` job label.

### Files touched

- `config/grafana/provisioning/datasources/datasources.yml` (new)
- `config/grafana/provisioning/dashboards/dashboards.yml` (new)
- `config/grafana/dashboards/00-start-here.json` (new)
- `config/grafana/dashboards/01-operations-overview.json` (new)
- `config/grafana/dashboards/02-service-drilldown.json` (new)
- `config/grafana/dashboards/03-repair-journey.json` (new)
- `config/grafana/dashboards/04-logs-traces-profiles.json` (new)
- `config/grafana/dashboards/05-mysql.json` (new)

### Validation

- Restart Grafana (`docker compose restart grafana`) or hit `POST /api/admin/provisioning/dashboards/reload`.
- Open `http://localhost:3000` (admin/admin). Each dashboard renders without `No data`.
- On `04 Logs/Traces/Profiles`: pick a log line, click the `trace_id` derived field → Tempo opens with the matching trace; on a span, click the profile link → Pyroscope flamegraph opens for the same window.

### Known gotchas

- Dashboard JSON `__inputs` and `__elements` blocks must be **removed** before committing — they only exist for Grafana's UI-driven export. Use `jq 'del(.__inputs, .__elements)'` if exporting from the UI. Or hand-author from the reference lab versions.
- `traceToProfiles` requires the `traceToProfiles` feature toggle (already set in Phase 3 compose entry).

---

## Phase 6 — CloudWatch datasource + IAM

**Session goal:** Grafana's `01 Operations Overview` shows ECS Container Insights and ALB metrics for the deployed AMS service alongside the local Prom panels.

### Prerequisites

- AWS account with the deployed AMS environment (post-PR #63).
- AWS CLI configured locally so we can mint the IAM user.

### Scope

1. **IAM user `ams-grafana-reader` (manual, document in this plan)** — attach `CloudWatchReadOnlyAccess`. Generate an access-key pair, store in a Secrets Manager entry `ams/prod/grafana-cloudwatch-reader` for reference; for local Grafana, set them via env in `docker-compose.observability.yml` (NOT committed — fed via `.env` which is git-ignored).

2. **`config/grafana/provisioning/datasources/cloudwatch.yml`** — datasource block with `authType: keys`, `defaultRegion: ap-east-2`, `accessKey: ${CLOUDWATCH_ACCESS_KEY}`, `secretKey: ${CLOUDWATCH_SECRET_KEY}` (Grafana env-var substitution).

3. **Augment `01-operations-overview.json`** with two new panels (placeholders existed from Phase 5):
   - ECS Container Insights: `AWS/ECS/ContainerInsights`, metrics `CpuUtilized` + `MemoryUtilized`, dimensions `ServiceName=ams-backend|ams-frontend`, `ClusterName=ams-prod`.
   - ALB: `AWS/ApplicationELB`, metrics `RequestCount`, `TargetResponseTime` (statistic p95), `HTTPCode_Target_5XX_Count`. Dimension `LoadBalancer=<ALB-name>` filled from a template variable.

4. **`.env.example` (top-level)** — document `CLOUDWATCH_ACCESS_KEY` and `CLOUDWATCH_SECRET_KEY` as optional. Without them, the panels show "No data" but the rest of the dashboard works.

### Files touched

- `config/grafana/provisioning/datasources/cloudwatch.yml` (new)
- `config/grafana/dashboards/01-operations-overview.json` (augment)
- `.env.example` (augment)
- `docs/system-design/08-deployment-operations.md` (document the IAM user; do NOT commit the keys)

### Validation

- With the keys set in a local `.env`, restart Grafana: the two CloudWatch panels populate.
- Without the keys, the panels show "no data" but Grafana itself does not error.
- IAM user has zero write permissions: `aws iam list-attached-user-policies --user-name ams-grafana-reader` shows only `CloudWatchReadOnlyAccess`.

### Known gotchas

- ECS Container Insights metric `CpuUtilized` is the **task-level** number (sum across containers). For per-container, switch to `AWS/ECS` (without Container Insights). Decide which the demo audience cares about — task-level matches the slide story.
- The Grafana CloudWatch datasource caches metric metadata for 24h. If panels look empty right after creating the IAM user, wait or restart Grafana.

---

## Phase 7 — k6 load + stress tests

**Session goal:** Constant-arrival-rate traffic across the 6 critical AMS flows hits the local stack; results land in Prometheus via k6's `--out experimental-prometheus-rw`. Two scripts: `k6-load.js` (sustained 10 min peak) and `k6-stress.js` (ramp until P95 > 3s or error rate > 1%).

### Prerequisites

- Phase 1–4 done so traffic produces metrics + traces + logs.
- Seed data: realistic users (manager + holder) and at least one asset assigned to the holder so the repair-submit flow has a valid target.

### Scope

1. **`load/k6-load.js` (new)** — constant-arrival-rate scenarios for 6 flows:
   - `login` → `POST /api/v1/auth/login`
   - `submit_repair` → `POST /api/v1/repair-requests` (multipart, one image)
   - `approve_repair` → `PATCH /api/v1/repair-requests/{id}/review`
   - `complete_repair` → `PATCH /api/v1/repair-requests/{id}/complete`
   - `register_asset` → `POST /api/v1/assets`
   - `search_assets` → `GET /api/v1/assets?status=...&category=...&q=...`
   - Mixed weights: search 40%, login 20%, submit 15%, approve 10%, complete 10%, register 5%. 10-min duration. Thresholds: `http_req_duration{expected_response:true} p(95)<3000`, `http_req_failed rate<0.01`.

2. **`load/k6-stress.js` (new)** — ramp the same flows from 1 VU/s to 50 VU/s over 5 min, observing breakpoint.

3. **`load/lib/auth.js` (new)** — shared helper: login once per VU, cache the JWT, reuse for the run.

4. **`load/README.md` (new)** — how to run:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.observability.yml run --rm k6 run \
     --out experimental-prometheus-rw \
     -e K6_PROMETHEUS_RW_SERVER_URL=http://prometheus:9090/api/v1/write \
     /scripts/k6-load.js
   ```
   Document that `RATE_LIMIT_ENABLED=false` must be set on the backend service for the duration of the stress test, or the test measures the rate limiter rather than the app.

5. **`docker-compose.observability.yml`** — add a `k6` service profile-gated (`profiles: ["tools"]`) so it doesn't run by default. Image `grafana/k6:0.54.0`, mounts `./load:/scripts:ro`.

### Files touched

- `load/k6-load.js`, `load/k6-stress.js`, `load/lib/auth.js` (new)
- `load/README.md` (new)
- `docker-compose.observability.yml` (k6 service entry)

### Validation

- A 10-min `k6-load` run finishes with p(95) reported in the terminal.
- Grafana's `03 Repair Journey` and `01 Operations Overview` show the traffic spike.
- Stress test breakpoint is captured: at which arrival rate did P95 cross 3s? Note in `docs/system-design/09-testing-strategy.md`.

### Known gotchas

- k6's `experimental-prometheus-rw` output is **experimental** in 0.54 but stable enough for a demo. If a future k6 release stabilises it, drop the `experimental-` prefix.
- Multipart upload in k6 needs `http.file` + `FormData` — keep the test fixture image small (~10 KB) so we don't measure network IO.

---

## Phase 8 — Middleware-order regression test

**Session goal:** One pinned test asserts that `prometheus-fastapi-instrumentator` and `slowapi` cooperate: the rate-limit counter increments exactly once per request, even with `/metrics` scrapes happening in parallel.

### Prerequisites

- Phase 1 complete.
- Required reading: `backend/tests/test_rate_limit.py` (existing rate-limit suite).

### Scope

1. **`backend/tests/test_rate_limit.py`** — augment with a new test:
   - Build a `TestClient` against `app.main:app`.
   - Hit any rate-limited route N times; assert `X-RateLimit-Remaining` decrements by exactly 1 per request.
   - Interleave a `GET /metrics` between every two requests; assert it does NOT affect the rate-limit counter (because `@limiter.exempt` is on the route).
   - Assert `/metrics` itself returns 200 after exceeding the per-minute cap on a normal route (because `/metrics` is exempt).

2. **`backend/app/main.py`** — leave a comment block at the middleware-registration site explaining the order and pointing to the test. (Comment only; no behavior change.)

### Files touched

- `backend/tests/test_rate_limit.py` (augment)
- `backend/app/main.py` (comment-only)

### Validation

```bash
cd backend
pytest tests/test_rate_limit.py -v
mypy app
ruff check .
```

---

## Phase 9 — Verification, correlation demo, docs

**Session goal:** End-to-end verification of the M6 outcomes and the supporting documentation update.

### Prerequisites

- Phases 1–8 done.

### Scope

1. **Run the correlation demo end-to-end:**
   - `make obs-up`.
   - Run `k6-load.js` for 2 minutes to seed the time range.
   - Open Grafana `01 Operations Overview`. Click a high-latency request panel → drilldown → `02 Service Drilldown`.
   - In Service Drilldown, click a log line in the logs panel. The `trace_id` derived field appears. Click → Tempo opens with the trace.
   - In the trace view, expand a span. Click "Profiles for this span" (the traceToProfiles link). Pyroscope flamegraph opens for the same time window.
   - Take screenshots for the slides.

2. **`docs/system-design/08-deployment-operations.md`** — add a § "Observability stack" with:
   - The stack diagram (mermaid or ascii, matching the architecture).
   - How to bring it up locally (`make obs-up`).
   - Which env vars on `backend` / `frontend` toggle the per-component instrumentation.
   - The CloudWatch datasource setup steps from Phase 6.

3. **`docs/system-design/09-testing-strategy.md`** — add a § "Load + stress testing" with:
   - The k6 scenarios.
   - The captured breakpoint from Phase 7.
   - How to disable rate limiting for stress runs.

4. **`README.md`** — top-of-file status line: bump to reflect M6 progress. Add a "Observability" subsection under Quick Start with the `make obs-up` one-liner.

5. **`docs/roadmap.md`** — tick the M6 checkboxes that this branch completes.

### Files touched

- `docs/system-design/08-deployment-operations.md`
- `docs/system-design/09-testing-strategy.md`
- `README.md`
- `docs/roadmap.md`

### Validation

- The five M6 milestone outcomes this branch owns are checked off in `docs/roadmap.md`:
  - [ ] Backend instrumented: `/metrics`, OTLP traces, structured JSON logs, Pyroscope profiles
  - [ ] Frontend instrumented: browser OTLP + nginx JSON access logs
  - [ ] `mysqld-exporter` sidecar scraping compose MySQL
  - [ ] CloudWatch Grafana datasource provisioned
  - [ ] Grafana stack runs via overlay compose
  - [ ] At least five dashboards provisioned
  - [ ] End-to-end correlation demo works live
  - [ ] k6 load + stress reports captured

---

## Risk register (this branch)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Backend instrumentation breaks `_enforce_single_worker_invariant` boot guard | Low | High | Phase 1 explicitly does not touch the guard; Phase 8 regression test pins ordering |
| Middleware order breaks slowapi rate-limit accounting | Medium | Medium | Phase 8 regression test |
| Browser → Alloy `:4318` CORS misconfig blocks all browser traces | Medium | Low (local-only) | Phase 4 includes the `cors { allowed_origins }` block; Phase 2 documents it |
| Stack image size > 2 GB on demo laptop | Medium | Low | Overlay file keeps stack out of routine dev; `make obs-pull` pre-rehearsal |
| `loki.source.docker` permissions vary across macOS / Linux / rootless | Medium | Medium | `DOCKER_ROOT_DIR` env override + autodetect in Makefile |
| Pyroscope sampling thread dies under gunicorn fork in any image we accidentally enable | Low | Low | Locked decision 5: off by default in prod image; Phase 1 wraps `configure()` in try/except |
| Test coverage drops below 80% from new uncovered observability code paths | Medium | Medium | Phase 1 ships `test_observability.py`; Phase 8 adds rate-limit regression; coverage measured in validation step |

---

## Estimated complexity

- Phase 1: **Medium** (4–6 h) — most risky integration.
- Phase 2: **Low** (2–3 h) — well-isolated.
- Phase 3: **Medium** (3–4 h) — lots of config files.
- Phase 4: **Medium** (3–4 h) — Alloy 1.5 syntax surface.
- Phase 5: **High** (5–7 h) — six dashboards is a lot of JSON.
- Phase 6: **Low** (2 h once the IAM user exists).
- Phase 7: **Medium** (3–4 h) — multipart upload flow is fiddly in k6.
- Phase 8: **Low** (1 h).
- Phase 9: **Low** (2 h docs + 1 h capturing screenshots).

**Total:** ~30–40 hours of focused work. Comfortably fits in the W6 infra budget (2 people × 5 days, minus the AWS smoke-test sliver).
