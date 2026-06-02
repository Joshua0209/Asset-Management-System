# Deployment & Operations Strategy

---

## Zero-Downtime Deployment

| Phase | Strategy | Tool |
|-------|----------|------|
| Phase 1 | Restart process on single server (brief downtime acceptable for pilot) | systemd or docker restart |
| Phase 2 | Rolling update via ALB + ECS | ECS rolling deployment |
| Phase 3 | Rolling update via Kubernetes | EKS rolling deployment with readiness probes |

**Rolling update process (Phase 2-3):**
1. New container image built and pushed to ECR
2. Deployment creates new pods/tasks with new image
3. ECS container/liveness probe passes: HTTP 200 on `/health` (process is up; always 200)
4. ALB target-group/readiness probe passes: HTTP 200 on `/ready` (DB connectivity verified; returns 503 to drain the target during RDS Multi-AZ failover without killing the otherwise-fine container)
5. Old pods/tasks drained (in-flight requests complete)
6. Old pods/tasks terminated

See `CLAUDE.md` §"Health endpoints (Week 5+)" for the code-level distinction between the two probes.

**Database migration strategy:**
- Use backward-compatible migrations only (add columns, never remove or rename in the same release)
- Two-phase migration for breaking changes: (1) add new column, deploy app that writes to both, (2) migrate data, deploy app that uses only new column, (3) drop old column
- **Automation (Phase 2+):** the `migrate-database` job in `.github/workflows/cd.yml` runs `alembic upgrade head` as a one-off Fargate task against the rendered backend task definition before `deploy-backend` starts the rolling update. The deploy is blocked on the migration job's exit code, so step (1) "add new column" lands automatically pre-deploy and the new task set never boots against an unmigrated schema. The job is forward-only: a rollback to a prior schema still needs a hand-written revert migration. Manual seeding (operator-triggered, destructive) lives in a separate workflow, `.github/workflows/seed.yml`, fired only via `workflow_dispatch` after typing the `SEED` confirmation. It reuses the task definition the backend ECS service is already running (no rebuild or redeploy), so a reseed no longer drags the full quality + build + deploy chain along with it.

---

## Monitoring & Alerting

| Metric | Warning Threshold | Critical Threshold | Action |
|--------|------------------|-------------------|--------|
| API error rate (5xx) | > 1% | > 5% | Page on-call |
| API latency P95 | > 500ms | > 2000ms | Investigate |
| CPU utilization | > 70% | > 90% | Scale out |
| DB connections | > 70% max | > 90% max | Scale DB or optimize queries |
| DB replication lag | > 1s | > 5s | Investigate replica |
| Disk usage | > 70% | > 85% | Expand volume |
| Health check failure | 1 consecutive | 3 consecutive | Auto-replace node |

**Notification routing.** Each row above maps to two Grafana-managed
alert rules (warning + critical) defined under `config/grafana/alerts/`
and provisioned by `scripts/sync_grafana_cloud_dashboards.py` alongside
the dashboards. All 14 rules route to a single email contact point
(`email-default`); the recipient list is sourced from the
`GC_ALERT_EMAIL_RECIPIENTS` GitHub secret (comma-separated) so it can
change without a code PR. The complete runbook lives in
`infra/grafana-cloud/README.md` §"Alert provisioning". Warning rules
fire after `for: 5m` (10m for disk, 1m for ALB health); critical rules
fire faster (2m / 5m / 3m respectively).

The percentage/duration thresholds above map directly to the rule
expressions, except for two rows that CloudWatch reports as absolute
values rather than percentages, so the rule thresholds carry an
instance-size assumption:

- **DB connections** alert on the raw `DatabaseConnections` count at
  70% / 90% of an assumed `max_connections` ≈ 60 (i.e. 42 / 54).
- **Disk usage** alerts on `FreeStorageSpace` falling below 30% / 15%
  free of an assumed 20 GiB `AllocatedStorage` (i.e. ≈ 6 GiB / 3 GiB).

Recompute these two thresholds if the RDS instance class or allocated
storage changes; the others are size-independent.

---

## Backup & Recovery

| Phase | Backup | RPO | RTO |
|-------|--------|-----|-----|
| Phase 1 | Daily `mysqldump` to S3 | 24 hours | 4 hours (manual restore) |
| Phase 2 | RDS automated backups + snapshots | 5 minutes (PITR) | 30 minutes |
| Phase 3 | RDS automated backups + cross-region snapshot replication | 5 minutes | 15 minutes |

---

## API Hardening: CORS Allowlist (Phase 2 AWS Rollout)

The backend's CORS configuration is environment-driven (`backend/app/core/config.py` → `Settings.cors_allowed_*`). Set the following on the ECS task definition / Secrets Manager when promoting between environments. **Do not** ship a wildcard origin to anything serving real users.

| Env var | Local dev | Staging | Production |
|---|---|---|---|
| `CORS_ALLOWED_ORIGINS` | `["http://localhost:5173"]` | `["https://staging.ams.example.com"]` | `["https://ams.example.com"]` |
| `CORS_ALLOWED_METHODS` | `["GET","POST","PATCH","OPTIONS"]` | same | same |
| `CORS_ALLOWED_HEADERS` | `["Authorization","Content-Type"]` | same | same |

**Audit findings:**
- Backend has zero `@router.delete` routes — soft-deletes go through `PATCH`. `DELETE` is intentionally absent from the default allow-methods.
- Neither backend nor frontend reference `If-Match`. The header is intentionally absent from the default allow-headers; if optimistic-locking ETags are added later, broaden the env var, do not loosen the code.

When adding a new client surface (mobile webview, marketing site, etc.) the **only** change required is appending its origin to `CORS_ALLOWED_ORIGINS` in the task definition — no code or container rebuild.

---

## API Hardening: Rate Limiting (Phase 2)

The limiter (`backend/app/core/rate_limit.py`) is in-process via slowapi. Per `05-phase2-architecture.md` we explicitly skipped Redis for Phase 2 — the trade-off is that running multiple Uvicorn workers per task multiplies the effective limit (a single user can burst N× the configured rate, where N is `--workers`). Acceptable at ~4 QPS; revisit when Phase 3 lands a shared store.

**ECS task command:** keep `--workers 1` until rate limits are backed by Redis. Auto-scaling at the *task* level (not the worker level) is the supported scaling axis.

The Grafana Cloud observability work reinforces this from a second angle: the OTel SDK's `MeterProvider`, `TracerProvider`, and `LoggerProvider` are process-wide singletons installed once at startup, and `pyroscope-io`'s sampling thread is started in the main process. With `--workers 1` per task, those singletons line up one-to-one with the task and Pyroscope's thread survives without a `gunicorn --preload` / `post_fork` dance. If `WEB_CONCURRENCY` is ever bumped above 1, both the OTel exporters and `pyroscope-io` need an explicit post-fork re-init (see `infra/aws/tasks/README.md` on the `WEB_CONCURRENCY=1` invariant). Do not silently raise the worker count without that wiring.

### Behind the ALB: client-IP resolution (CRITICAL)

By default Starlette's `request.client.host` is the **immediate TCP peer** — behind an ALB that is the load-balancer's private IP, so every anonymous request would collapse into one bucket and the limiter would silently become a self-DoS (one attacker burns the global anon quota for every other user).

The mitigation is a **single trust gate** at uvicorn's edge, scoped to the ALB CIDR. Production runs gunicorn supervising `uvicorn.workers.UvicornWorker` (see `backend/Dockerfile.prod`), which reads gunicorn's `--forwarded-allow-ips` and applies it inside the uvicorn worker:

```sh
gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers ${WEB_CONCURRENCY:-1} \
  --bind 0.0.0.0:8000 \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}"
```

`--proxy-headers` is deliberately omitted: it is a uvicorn-CLI-only flag, and uvicorn's proxy-header handling is on by default under `UvicornWorker`. Adding `--proxy-headers` would either no-op or fail depending on the version — both are noisier than just relying on the default.

`--forwarded-allow-ips` is the trust gate: uvicorn's `ProxyHeadersMiddleware` only rewrites `request.client.host` from `X-Forwarded-For` when the immediate TCP peer is in this allowlist. Without it, an attacker hitting the task directly could spoof XFF and inject any IP they like into the bucket key.

In production, we set `FORWARDED_ALLOW_IPS` to `*`. The honest framing of this choice:

- **Trust scope is the VPC, not the ALB.** `*` tells uvicorn to accept `X-Forwarded-For` from any immediate TCP peer. The previous VPC-CIDR value had the same trust scope in practice (anything inside the VPC that could reach the task could already spoof XFF), so `*` does not broaden trust beyond what the CIDR form allowed — it just makes the boundary explicit.
- **The actual enforcement boundary is the Security Group.** The SG attached to the backend tasks only permits ingress from the ALB's SG on the application port. Anything else inside the VPC (a bastion, a sidecar, a future internal service) is blocked at the SG before it can even open a TCP connection, regardless of what `FORWARDED_ALLOW_IPS` is set to.

The supporting invariants that make this configuration acceptable:
1. The ECS tasks are in **private subnets** with no public IP.
2. The only entry point for external traffic is the **Application Load Balancer**.
3. Ingress to the task SG is restricted to the ALB SG (point above).

If any of those three invariants change — in particular, if the task SG is ever loosened to admit a second source — re-tighten `FORWARDED_ALLOW_IPS` at the same time. The startup WARN in `app/main.py` only catches the unset / `127.0.0.1` case; a deliberately-broadened SG does not trip it.

This avoids operational issues with CIDR notation parsing while maintaining the "fail-closed" posture described below. The image default is `127.0.0.1` so local prod-image runs behave like uvicorn's own default; production ECS task definitions MUST override `FORWARDED_ALLOW_IPS` to `*`. The startup WARN in `app/main.py` flags the default when rate limiting is enabled.

`backend/app/core/rate_limit.py` deliberately does **not** add an application-layer XFF reader on top. That would not be defense-in-depth — the two readers share a single precondition (the immediate hop is a trusted proxy), so they are one layer wearing two coats. The asymmetry matters:

- **Trust gate correct, no app-layer reader:** bucket key = real client IP. ✅
- **Trust gate broken, no app-layer reader:** every anonymous request collapses to the ALB's private IP → first user trips 429 → /auth/login starts 429-ing for everyone → monitoring alerts oncall within minutes. Fail-closed and **paged**.
- **Trust gate broken, app-layer XFF reader present:** every public client can pick their own bucket key by setting `X-Forwarded-For`. Attackers rotate keys to evade limits; a malicious key can also collide with a victim's bucket to lock them out. Silent. **Not paged.**

Deleting the app-layer reader trades a non-event under correct config for a fail-closed, observable failure under bad config. That is strictly better than the alternative.

**Verification after rollout.** Run during a rollout window (not peak hours — the check burns ~5 slots of the anonymous bucket on whatever the runner's NAT IP resolves to). Run from a host **outside the VPC** so traffic actually traverses the ALB; running from a jumpbox inside the VPC bypassing the ALB tells you nothing because no XFF header is added.

Use a rate-limited endpoint so you can read `X-RateLimit-Remaining`. **Do not use `/health`** — it is `@limiter.exempt` (`app/main.py`) and emits no `X-RateLimit-*` headers, so the check would silently always "pass". `POST /api/v1/auth/login` with a bogus body is the canonical probe: it returns 401 but the request still flows through `SlowAPIMiddleware`, which attaches the headers we need.

```bash
# 5 requests from the same source IP, each claiming a different XFF.
for i in 1 2 3 4 5; do
  curl -is -X POST -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 198.51.100.${i}" \
    -d '{"email":"verify@invalid","password":"x"}' \
    https://<api>/api/v1/auth/login | grep -i x-ratelimit-remaining
done
```

Interpretation:

| Observation | Meaning |
|---|---|
| `Remaining` decrements monotonically (e.g. `29 → 28 → 27 → 26 → 25`) | ✅ Trust gate working. uvicorn ignored the spoofed XFF; all 5 hit the same real-IP bucket. |
| `Remaining` stays flat (e.g. `29` every time) | ❌ Trust gate failing. uvicorn trusted the spoofed XFF; each request landed in a distinct bucket. **Do not serve real traffic** — fix `--forwarded-allow-ips` and re-deploy first. |
| No `X-RateLimit-*` header at all | ❌ Likely hit an exempt endpoint or the limiter is disabled. Re-check `RATE_LIMIT_ENABLED=true` and that the URL points at `/api/v1/auth/login` (not `/health`). |

### Env-var matrix

| Env var | Production default |
|---|---|
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_AUTHENTICATED` | `100/minute` |
| `RATE_LIMIT_ANONYMOUS` | `30/minute` |
| `RATE_LIMIT_IMAGES` | `300/minute` |

---

## Grafana Cloud production observability

Production telemetry runs entirely through Grafana Cloud's hosted free-tier stack named `ams`. Two complementary paths:

1. **Backend push (OTLP).** The ECS backend task pushes traces, metrics, logs, and CPU profiles direct to Grafana Cloud's hosted OTLP gateway via the OTel SDK. Configured by the `OTEL_*`, `PYROSCOPE_*`, and `ENVIRONMENT` env vars in `infra/aws/tasks/backend-task-def.json` plus the `OTEL_EXPORTER_OTLP_HEADERS`, `PYROSCOPE_AUTH_TOKEN`, and `PYROSCOPE_BASIC_AUTH_USERNAME` secrets sourced from the `ams-grafana-cloud` Secrets Manager secret.
2. **Cloud pull (CloudWatch).** Grafana Cloud's hosted CloudWatch integration assumes a read-only cross-account role (`ams-grafana-cloud-reader`) and pulls AWS-managed signals every 60s: ALB request count and target response time, RDS CPU/connections/disk queue, ECS Container Insights CPU/memory. Configured by the IAM role definition under `infra/grafana-cloud/`.

The repo-side dashboard JSONs (`config/grafana/dashboards/*.json`) are the source of truth until Grafana Cloud import is verified in production; after that, Phase 6 of `docs/plans/observability-prod-migration-plan.md` deletes them and Grafana Cloud's stored dashboards become canonical.

### Stack URL and login

The Grafana Cloud stack URL follows the pattern `https://<your-stack-slug>.grafana.net`. The slug is the name of the stack created in the GC web UI when the account was provisioned; an operator running this runbook needs to know the current slug for their team's stack. Treat the slug as a low-sensitivity operational detail (the URL is access-controlled, not secret), but do not commit it to public source so the repo stays portable across stack renames or migrations. Operators authenticate with the Grafana Cloud account credentials; no SSO is provisioned for this class project. Per-developer API keys are out of scope for this phase; a single shared publish-key in `ams-grafana-cloud` covers OTLP and Pyroscope, and a single shared admin login covers UI access. Rotate the publish-key on the schedule documented in `infra/grafana-cloud/README.md` § "Step 6: key rotation".

### `ams-grafana-cloud` AWS Secrets Manager secret

This is the only AWS-side secret introduced by the observability migration. JSON shape:

```json
{
  "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <base64(prom_instance_id:api_key)>",
  "PYROSCOPE_AUTH_TOKEN": "<grafana_cloud_api_key>",
  "PYROSCOPE_BASIC_AUTH_USERNAME": "<pyroscope_instance_id>"
}
```

The ECS task's `secrets:` block resolves all three keys at task launch. Operator creates the secret out-of-band (this is not pipeline-managed); see `infra/aws/tasks/README.md` § "`ams-grafana-cloud` secret shape" for details.

### Cross-account IAM role

The `ams-grafana-cloud-reader` role is documented in [`infra/grafana-cloud/README.md`](../../infra/grafana-cloud/README.md). The trust policy is gated by an `sts:ExternalId` from the Grafana Cloud connector UI; the inline permissions policy is read-only across CloudWatch Logs, CloudWatch Metrics, RDS describe, EC2 describe, and resource tagging. Setup is a one-shot operator action; the role is stable for the life of the Grafana Cloud stack.

### Free-tier quotas to watch

Grafana Cloud's free tier is the only observability budget. Approximate limits (verify against the GC UI's "Usage" page; these change over time):

| Signal | Free-tier ceiling | Action when approached |
|---|---|---|
| Prometheus active series | ~10,000 | Audit metric cardinality; drop high-cardinality labels (per-VU, per-request-id) at the OTel View boundary |
| Loki ingestion | ~50 GB/month | Lower log level from `INFO` to `WARNING` in production; backend already drops uvicorn access logs to JSON-only |
| Tempo ingestion | ~50 GB/month | Reduce `OTEL_TRACES_SAMPLER_ARG` (probability sampler) below `1.0` |
| Pyroscope ingestion | ~50 GB/month | Pyroscope already samples at low frequency; the `ams-backend` workload is unlikely to hit this |
| Active users | 3 | Class project: only the operator + one demo viewer typically log in |

If a quota is hit, Grafana Cloud silently drops further ingestion for that signal until the next reset window. No production alerting fires. Monitor the GC UI's "Billing & Usage" panel weekly.

### Key rotation

See [`infra/grafana-cloud/README.md`](../../infra/grafana-cloud/README.md) § "Step 6: key rotation" for the canonical procedure. Summary: generate a new API key in Grafana Cloud UI, update the `ams-grafana-cloud` Secrets Manager secret, force an ECS task redeploy, then revoke the old key.
