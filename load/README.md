# AMS k6 load + stress tests (Phase 7)

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

- `lib/auth.js` — per-VU JWT cache, seed-account credentials.
- `lib/flows.js` — the six critical-flow exec functions + helpers
  (search, my-assets, list-repairs, submit, approve, complete, register,
  health). Every request carries low-cardinality `tags` so dashboards keep
  their route templates stable.
- `lib/fixtures.js` — tiny 1×1 JPEG used as the multipart payload for
  `submit_repair`.

## Running

The compose overlay (`docker-compose.observability.yml`) ships a profile-gated
`k6` service. The convenience targets in the repo root `Makefile` drive it:

```bash
# Seed once (if you haven't already) so submit/approve/complete have targets.
docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py

# Bring up the dev stack + observability overlay.
make obs-up

# Run scenarios:
make load-smoke
make load-steady
make load-spike
make load-load
make load-stress
make load-consistent

# Long-running background traffic for demos:
make traffic-start    # uses the `traffic` profile
make traffic-status
make traffic-logs
make traffic-stop
```

Pass extra k6 arguments via `K6_ARGS=`:

```bash
# Push results into Prometheus via remote-write (rendered on the dashboards
# under the `k6_*` metric family).
make load-load K6_ARGS="--out experimental-prometheus-rw \
  -e K6_PROMETHEUS_RW_SERVER_URL=http://prometheus:9090/api/v1/write"
```

## Tuning rates without rebuilding

`k6-consistent.js` reads each flow's rate from `*_PER_MIN` env vars; the
`traffic-generator` compose service forwards them through. Set any rate to
`0` to drop that scenario:

```bash
SEARCH_PER_MIN=120 SUBMIT_PER_MIN=0 make traffic-start
```

`k6-load.js` takes a single `K6_TOTAL_RPM` knob that is then split across the
six flows by the plan's weights.

`k6-stress.js` takes `K6_MAX_VUS` (default 200) and `K6_RAMP` (default `5m`).

## Stress runs and the rate limiter

The backend's slowapi limiter caps anonymous traffic at `30/minute` and
authenticated traffic at `100/minute` (`backend/app/core/config.py`). A
stress test that exceeds these will measure the **limiter**, not the app —
it'll look like the stack collapses at the cap.

Disable the limiter for the run:

```bash
# Restart the backend with the limiter off, run the stress, then restart it
# back on so the rest of the demo keeps its hardening.
docker compose -f docker-compose.yml -f docker-compose.observability.yml \
  stop backend
RATE_LIMIT_ENABLED=false docker compose -f docker-compose.yml \
  -f docker-compose.observability.yml up -d backend
make load-stress
# When done:
docker compose -f docker-compose.yml -f docker-compose.observability.yml \
  up -d backend
```

The `setup()` block of `k6-stress.js` prints the same reminder on every
invocation.

## Seed account credentials

`lib/auth.js` defaults to:

- `MANAGER_EMAIL = manager@example.com` / `MANAGER_PASSWORD = ChangeMe123!`
  — matches `BOOTSTRAP_MANAGER_EMAIL` / `BOOTSTRAP_MANAGER_PASSWORD` in
  `.env.example`. Override via `MANAGER_EMAIL` / `MANAGER_PASSWORD` env
  when your seed used different bootstrap creds.
- `HOLDER_EMAIL = holder1@example.com` / `HOLDER_PASSWORD = Password123`
  — matches `scripts/seed_demo_data.py`'s first holder.

If login keeps 401-ing, those defaults don't match your seed. `lib/auth.js`
calls `fail()` so the run aborts immediately rather than reporting bogus
"app is broken" failures.

## Capturing the breakpoint

After a `make load-stress` run, the breakpoint is:

> The arrival rate at which the `http_req_duration` p(95) crossed 3 s **or**
> `http_req_failed` exceeded 1% on the AMS flows.

Read it from the terminal summary (k6 prints `http_req_duration{flow:...}`
per scenario) or from Grafana — the `03 Repair Journey` and `01 Operations
Overview` dashboards both surface p(95) per route. Record the number in
`docs/system-design/09-testing-strategy.md` so the team can compare across
runs.
