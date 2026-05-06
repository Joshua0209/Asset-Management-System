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
3. Health check passes (HTTP 200 on `/health`)
4. Old pods/tasks drained (in-flight requests complete)
5. Old pods/tasks terminated

**Database migration strategy:**
- Use backward-compatible migrations only (add columns, never remove or rename in the same release)
- Two-phase migration for breaking changes: (1) add new column, deploy app that writes to both, (2) migrate data, deploy app that uses only new column, (3) drop old column

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

**Audit findings** (W4):
- Backend has zero `@router.delete` routes — soft-deletes go through `PATCH`. `DELETE` is intentionally absent from the default allow-methods.
- Neither backend nor frontend reference `If-Match`. The header is intentionally absent from the default allow-headers; if optimistic-locking ETags are added later, broaden the env var, do not loosen the code.

When adding a new client surface (mobile webview, marketing site, etc.) the **only** change required is appending its origin to `CORS_ALLOWED_ORIGINS` in the task definition — no code or container rebuild.

---

## API Hardening: Rate Limiting (Phase 2)

The limiter (`backend/app/core/rate_limit.py`) is in-process via slowapi. Per `05-phase2-architecture.md` we explicitly skipped Redis for Phase 2 — the trade-off is that running multiple Uvicorn workers per task multiplies the effective limit (a single user can burst N× the configured rate, where N is `--workers`). Acceptable at ~4 QPS; revisit when Phase 3 lands a shared store.

**ECS task command:** keep `--workers 1` until rate limits are backed by Redis. Auto-scaling at the *task* level (not the worker level) is the supported scaling axis.

| Env var | Production default |
|---|---|
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_AUTHENTICATED` | `100/minute` |
| `RATE_LIMIT_ANONYMOUS` | `30/minute` |
| `RATE_LIMIT_IMAGES` | `300/minute` |
