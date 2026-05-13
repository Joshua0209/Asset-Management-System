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

**Audit findings:**
- Backend has zero `@router.delete` routes — soft-deletes go through `PATCH`. `DELETE` is intentionally absent from the default allow-methods.
- Neither backend nor frontend reference `If-Match`. The header is intentionally absent from the default allow-headers; if optimistic-locking ETags are added later, broaden the env var, do not loosen the code.

When adding a new client surface (mobile webview, marketing site, etc.) the **only** change required is appending its origin to `CORS_ALLOWED_ORIGINS` in the task definition — no code or container rebuild.

---

## API Hardening: Rate Limiting (Phase 2)

The limiter (`backend/app/core/rate_limit.py`) is in-process via slowapi. Per `05-phase2-architecture.md` we explicitly skipped Redis for Phase 2 — the trade-off is that running multiple Uvicorn workers per task multiplies the effective limit (a single user can burst N× the configured rate, where N is `--workers`). Acceptable at ~4 QPS; revisit when Phase 3 lands a shared store.

**ECS task command:** keep `--workers 1` until rate limits are backed by Redis. Auto-scaling at the *task* level (not the worker level) is the supported scaling axis.

### Behind the ALB: client-IP resolution (CRITICAL)

By default Starlette's `request.client.host` is the **immediate TCP peer** — behind an ALB that is the load-balancer's private IP, so every anonymous request would collapse into one bucket and the limiter would silently become a self-DoS (one attacker burns the global anon quota for every other user).

The mitigation is a **single trust gate** at uvicorn's edge. Run uvicorn with proxy-headers enabled, scoped to the ALB CIDR:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="<ALB-VPC-CIDR>"
```

`--forwarded-allow-ips` is the trust gate: uvicorn's `ProxyHeadersMiddleware` only rewrites `request.client.host` from `X-Forwarded-For` when the immediate TCP peer is in this allowlist. Without it, an attacker hitting the task directly could spoof XFF and inject any IP they like into the bucket key. Use the **VPC CIDR of the ALB subnets** (e.g. `10.0.0.0/16`), not `*` and not the public ALB IP — public IPs rotate, the VPC CIDR is stable.

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
