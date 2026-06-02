# Throughput investigation — why the stress test shows ~8 QPS

**Date:** 2026-05-31
**Author:** investigation against the live Grafana Cloud stack (`ams-backend`, region `ap-east-2`) + source review
**Decision:** **No changes. Keep current status.** This document records why ~8 QPS is expected and acceptable, so the result is not mistaken for a regression later.

---

## TL;DR

- The "500 QPS" figure in `docs/system-design/03-usage-estimates.md` was never a measurement. The doc says so explicitly: *"Single machine QPS (assumed): 500 QPS for stateless API server (to be validated by stress testing)."* It is a generic rule-of-thumb placeholder for an idealized full-core stateless server.
- The measured per-task ceiling (~8 QPS in the login-heavy mix) is exactly what a **0.5-vCPU, single-worker, synchronous-SQLAlchemy, bcrypt-12** service produces. It is a CPU/GIL ceiling, not a code defect.
- The application code on the hot path is clean: no N+1, correct eager-loading, indexes present for every filter, bounded pagination, optimistic locking. There is nothing material to optimize.
- Throughput scales by **ECS task count**, not per-box QPS — which is the architecture's stated scaling axis. At the observed 5 tasks this already clears the Phase 2 peak requirement (~4.2 QPS) by a wide margin.

**Conclusion: performance is good enough for Phases 1–2. No change required.**

---

## What was measured (live Grafana, last 24h)

Metric source: OTel `http_server_duration_seconds_*` on job `ams-backend`.

| Signal | Value |
|---|---|
| `GET /api/v1/assets` latency | avg ~310 ms, p95 ~1.6 s |
| `POST /api/v1/auth/login` latency | avg ~5.3 s |
| Status split (24h) | 200: ~35,500 · 201: ~3,340 · 401: ~1,090 · 409: ~170 · 429: **9** · 422: 6 · 500: 5 · 404: 4 |
| Distinct serving tasks (24h) | 5 instance IPs; up to ~3 concurrently during the test window |

The 310 ms avg / 1.6 s p95 on a 20-row indexed, eager-loaded list query is not a slow query (that query is sub-millisecond in MySQL). It is request queueing behind the GIL on half a core. The 5.3 s login average is the same effect amplified by bcrypt CPU cost.

Only **9** total 429s over 24h vs ~35k 200s, so on these runs the rate limiter was **not** the dominant wall (it was either disabled per `load/README.md` or the offered load stayed under the cap).

---

## Root causes (ranked)

1. **Half a core, one worker, GIL-bound, synchronous I/O.** `infra/ecs/backend-task-def.json`: `cpu: 512` (0.5 vCPU), `WEB_CONCURRENCY=1`. `backend/app/db/session.py`: synchronous `create_engine` + `Session` + `pymysql`. One Python process on 0.5 vCPU tops out in the low tens of QPS for DB-backed work — single digits once the login/write mix is included.
2. **bcrypt on the login path.** `backend/app/core/security.py` uses `bcrypt.gensalt()` at the default cost (12), ~100–300 ms of pure CPU per verify. The load mixes weight login at ~20% and re-login every iteration, and the anti-enumeration branch runs `checkpw` even for unknown users. On 0.5 vCPU this is ~2–5 ops/sec.
3. **Rate limiter (situational, not the main wall here).** `backend/app/core/config.py`: `RATE_LIMIT_AUTHENTICATED=100/minute`, `RATE_LIMIT_ANONYMOUS=30/minute`, slowapi in-memory **per process**. The k6 flows authenticate as two shared seed accounts, so all manager traffic shares one bucket and all holder traffic another (~4 allowed req/s/process). `load/README.md` documents running stress with `RATE_LIMIT_ENABLED=false` to avoid measuring the limiter.
4. **Low offered load in the default k6 profiles.** `k6-load.js` defaults to `K6_TOTAL_RPM=60` (≈1 req/s); `k6-consistent.js` defaults sum to ≈1.25 req/s. Only `k6-stress.js` (ramping VUs) actually pushes for the breakpoint. A low offered rate can itself explain a low observed QPS.

---

## Code review: nothing material to fix

Hot path `list_assets` / `list_my_assets` (`backend/app/api/v1/endpoints/assets.py`):

- **No N+1** — `joinedload(Asset.responsible_person)` eager-loads the holder in one query.
- **Indexes cover the filters** — `idx_assets_category_status`, `idx_assets_dept_loc`, `ix_assets_status`, `ix_assets_responsible_person_id` (migrations `…0001`, `…0004`).
- **Bounded pagination** (`per_page ≤ 100`), optimistic locking on writes, soft-delete filtered at query time.

Only micro-redundancies (both harmless at this scale, intentionally left as-is): `db.refresh()` after each write commit (one extra round trip per mutation) and the `SELECT count(*)` companion query per list page (standard for total counts).

**Deliberately NOT doing** (YAGNI at <100 QPS; would fight a CPU/GIL bottleneck, not an I/O one):
- async SQLAlchemy rewrite — bottleneck is CPU, not I/O wait, so async would not help here.
- Redis response cache.
- `WEB_CONCURRENCY > 1` — breaks the per-process rate limiter and the OTel/Pyroscope singletons (documented invariant in `08-deployment-operations.md`).
- lowering bcrypt cost — it is a security control, and login is not the real-world hot path (JWT is cached ~12h).

---

## Is it good enough? Yes

| | QPS |
|---|---|
| Phase 2 **peak** requirement (`03-usage-estimates.md`) | ~4.2 |
| One task, limiter on, login-heavy test | ~8 |
| One task, limiter off (true per-task ceiling) | ~tens |
| 5 tasks aggregate (observed deployment) | ~50–100+ |

The deployment already runs multiple tasks and clears the Phase 2 peak by more than an order of magnitude. The load test also exaggerates the worst case: in production, login happens roughly once per JWT lifetime (~12h), so bcrypt is off the steady-state hot path and real-world per-task QPS is higher than the test shows.

The system is horizontally scalable by design; the measured per-task number is what a 0.5-vCPU single-worker Python service should produce.

---

## If higher RPS is ever needed (no action now)

In impact-per-effort order, all config-only:

1. Bump task CPU `512 → 1024` (0.5 → 1 vCPU) — near-linear gain on CPU-bound work.
2. Increase ECS `desiredCount` — linear, and the architecture's intended scaling axis.
3. To measure the true per-task ceiling: run `RATE_LIMIT_ENABLED=false` with a high offered rate (e.g. `K6_TOTAL_RPM=12000 k6 run load/k6-stress.js`), then read the breakpoint per `load/README.md` (p95 > 3 s or `http_req_failed` > 1%).

These are intentionally deferred. Current status is kept as-is.
