# AMS k6 load + stress tests

This directory holds the load-generation scripts the W6 / M6 observability
milestone needs:

| Script              | Purpose                                                            | Default duration   |
| ------------------- | ------------------------------------------------------------------ | ------------------ |
| `k6-smoke.js`       | One-pass sanity check across every critical flow.                  | 1 minute           |
| `k6-steady.js`      | Sustained moderate read/write mix to fill dashboards.              | 5 minutes          |
| `k6-spike.js`       | Burst from 5 → 50 VUs to exercise the saturation panel.            | 100 seconds        |
| `k6-load.js`        | Constant-arrival-rate, six AMS critical flows, weighted.           | 10 minutes         |
| `k6-stress.js`      | Ramping VUs to find the per-process breakpoint.                    | ~7 minutes         |
| `k6-consistent.js`  | Long-running per-flow constant-arrival-rate traffic generator.     | 30 minutes (env)   |

Shared logic lives under `lib/`:

- `lib/auth.js` — per-VU JWT cache, seed-account credentials, eviction
  helpers for long runs that outlive the JWT TTL.
- `lib/flows.js` — the six critical-flow exec functions + helpers
  (search, my-assets, list-repairs, submit, approve, complete, register,
  health). Every request carries low-cardinality `tags` so dashboards keep
  their route templates stable.
- `lib/fixtures.js` — tiny 1×1 JPEG used as the multipart payload for
  `submit_repair`.

## Running

The local docker-compose observability overlay was removed during the
Grafana Cloud migration; k6 no longer ships as a compose service. Run it on
the host or via a one-shot `docker run`.

### Prerequisites

- Backend reachable on `http://localhost:8000` (`docker compose up -d
  backend mysql`).
- Bootstrap manager seeded — `backend/scripts/seed_demo_data.py` (the
  host path) runs once unattended via `docker compose run --rm -e
  AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py` (the
  container path, since `/app` is `backend/`).
- `k6 >= 0.46` on PATH (`brew install k6`, or use the official image).
  0.46 is the floor at which `experimental-prometheus-rw` is supported;
  any newer release works without changes.

### Direct invocation

```bash
# Smoke run, host k6, default localhost backend.
k6 run load/k6-smoke.js

# Spike / steady / stress / consistent — same shape.
k6 run load/k6-spike.js
k6 run load/k6-steady.js
k6 run load/k6-load.js
k6 run load/k6-stress.js
k6 run load/k6-consistent.js

# Different backend URL (e.g. against a deployed environment).
BASE_URL=https://api.example.com k6 run load/k6-smoke.js
```

### Container-run k6

```bash
docker run --rm -i --network host \
  -v "$PWD/load:/scripts" \
  grafana/k6:0.54.0 run /scripts/k6-smoke.js
```

On Docker Desktop / OrbStack (no `--network host` support for Linux
containers), point at the host via `host.docker.internal`:

```bash
docker run --rm -i \
  -e BASE_URL=http://host.docker.internal:8000 \
  -v "$PWD/load:/scripts" \
  grafana/k6:0.54.0 run /scripts/k6-smoke.js
```

## Streaming k6 metrics to Grafana Cloud

The backend's own RED metrics + traces + logs + profiles all flow to
Grafana Cloud via OTLP push (W6 Phase 3). k6 emits a separate per-iteration
metric family (`http_req_duration`, `http_req_failed`, `iterations`, …)
that's only visible to the operator unless you remote-write it somewhere.
Point `--out experimental-prometheus-rw` at GC's Prom endpoint to surface
the run on the dashboards under the `k6_*` series:

```bash
K6_PROMETHEUS_RW_SERVER_URL=https://prometheus-prod-<region>.grafana.net/api/prom/push \
K6_PROMETHEUS_RW_USERNAME=<gc-prom-instance-id> \
K6_PROMETHEUS_RW_PASSWORD=<gc-api-key> \
k6 run --out experimental-prometheus-rw load/k6-load.js
```

The three env vars (`K6_PROMETHEUS_RW_SERVER_URL`, `K6_PROMETHEUS_RW_USERNAME`,
`K6_PROMETHEUS_RW_PASSWORD`) are read by k6's built-in remote-write output
and do not require any script-side change. Source them from your
`.env`-style file when invoking, e.g. `set -a; source .env.gc; set +a` then
the `k6 run` above.

The Grafana Cloud Prom gateway accepts the `application/x-protobuf`
payload k6 sends by default; no `--out` sub-options are needed beyond
the URL/auth env. The `k6 >= 0.46` floor is repeated in the
Prerequisites section above.

## Tuning rates without rebuilding

`k6-consistent.js` reads each flow's rate from `*_PER_MIN` env vars. Set
any rate to `0` to drop that scenario:

```bash
SEARCH_PER_MIN=120 SUBMIT_PER_MIN=0 k6 run load/k6-consistent.js
```

`k6-load.js` takes a single `K6_TOTAL_RPM` knob that is then split across
the six flows by the plan's weights.

`k6-stress.js` takes `K6_MAX_VUS` (default 200) and `K6_RAMP` (default
`5m`).

## Stress runs and the rate limiter

The backend's slowapi limiter caps anonymous traffic at `30/minute` and
authenticated traffic at `100/minute` (`backend/app/core/config.py`). A
stress test that exceeds these will measure the **limiter**, not the app —
it'll look like the stack collapses at the cap.

Disable the limiter for the run by restarting the backend with the env
override (`docker-compose.yml` honours `RATE_LIMIT_ENABLED` via
`${RATE_LIMIT_ENABLED:-true}`):

```bash
# Restart backend with the limiter off, run the stress, restart back on
# so the rest of the demo keeps its hardening.
docker compose stop backend
RATE_LIMIT_ENABLED=false docker compose up -d backend
k6 run load/k6-stress.js
# When done:
docker compose up -d backend
```

The `setup()` block of `k6-stress.js` prints the same reminder on every
invocation.

## Seed account credentials

`lib/auth.js` defaults to:

- `MANAGER_EMAIL = admin@example.com` / `MANAGER_PASSWORD = ChangeMe123`
  — matches `BOOTSTRAP_MANAGER_EMAIL` / `BOOTSTRAP_MANAGER_PASSWORD` in
  `backend/.env.example`. Override via `MANAGER_EMAIL` / `MANAGER_PASSWORD`
  env when your seed used different bootstrap creds.
- `HOLDER_EMAIL = holder1@example.com` / `HOLDER_PASSWORD = Password123`
  — matches `backend/scripts/seed_demo_data.py`'s first holder.

If login keeps 401-ing, those defaults don't match your seed. `lib/auth.js`
calls `fail()` so the run aborts immediately rather than reporting bogus
"app is broken" failures. Long runs (stress, consistent) handle
mid-run JWT expiry by evicting the cached token and re-logging eagerly
on a 401; the `ams_load_token_evictions` counter on the k6 summary surfaces
the rate.

## Capturing the breakpoint

After a `k6 run load/k6-stress.js` run, the breakpoint is:

> The arrival rate at which the `http_req_duration` p(95) crossed 3 s **or**
> `http_req_failed` exceeded 1% on the AMS flows.

Read it from the terminal summary (k6 prints `http_req_duration{flow:...}`
per scenario) or from Grafana Cloud — the `03 Repair Journey` and
`01 Operations Overview` dashboards both surface p(95) per route. Record
the number in `docs/system-design/09-testing-strategy.md` so the team can
compare across runs.

## Captured results

`results/` holds the artifacts from the load-test campaign run against the
deployed stack:

| File | What it is |
| ---- | ---------- |
| `results/consistent.html` | k6 web-dashboard export from a `k6-consistent.js` run. |
| `results/spike.html` | k6 web-dashboard export from a `k6-spike.js` run. |
| `results/stress.html` | k6 web-dashboard export from a `k6-stress.js` run (the breakpoint ramp). |
| `results/2026-05-31-throughput-investigation.md` | Why the stress test tops out at ~8 QPS per task — a CPU/GIL ceiling on a 0.5-vCPU single-worker service, not a code defect. Concludes no change is needed for Phases 1–2. |
| `results/2026-06-02-stress-409-estimate.md` | Infers the HTTP 409 (optimistic-lock conflict) rate the k6 report omits: ~1.5% of traffic, with optimistic locking holding at 100% checks under the ramp. |

Open the `.html` files in a browser. The two write-ups summarize the headline
findings the presentation deck (`docs/slides/index.html`) charts.
