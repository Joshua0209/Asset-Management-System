# Estimating the HTTP 409 rate in `stress.html` (the report never records it)

**Date:** 2026-06-02
**Source:** `load/results/stress.html` (k6 web-dashboard export, run 2026-05-31) + source review of `load/k6-stress.js`, `load/lib/flows.js`, `load/lib/auth.js`
**Question:** the HTML report shows no per-status-code breakdown. What fraction of requests were 409 (optimistic-lock conflicts)?

---

## TL;DR

- The k6 web-dashboard report (`stress.html`) records **no status-code split**. Its only failure metric is the aggregate `http_req_failed` rate, plus three custom business counters (`ams_load_*_no_candidate/no_target_total`). There is no 409, 4xx, or 5xx category anywhere in the file.
- The 409 rate can still be **inferred** from two metrics the report does carry, because of how k6 classifies responses.
- **Estimate: ~12 of 811 requests were HTTP 409 (~1.5% of all traffic, ~8% of write/mutation requests).** The headline 17% `http_req_failed` is ~91% deliberate 401 anti-enumeration probes, not real errors.
- Optimistic locking held: `checks` stayed at 100%, so zero requests returned an unexpected status under the stress ramp.

---

## What the report actually contains

The data is a gzip+base64 NDJSON blob in `<script id="data">`. Decoded cumulative metrics:

| Metric | Value |
|---|---|
| `http_reqs` | **811** |
| `iterations` | 628 |
| `vus_max` | 200 |
| `http_req_failed` | **0.17016 → ~138 requests** |
| `checks` (pass rate) | **1.0 → 100%** |
| `http_req_duration` | avg 2.17 s, med 0.89 s, p95 10.1 s, max 16.0 s |
| `ams_load_submit_repair_no_target_total` | 22 |
| `ams_load_approve_repair_no_candidate_total` | 23 |
| `ams_load_complete_repair_no_candidate_total` | 15 |

(The `http_req_duration` profile — avg 2.2 s, p95 10.1 s — confirms the positional decode is aligned correctly.)

---

## Why the 409 count can be backed out

Two facts make it recoverable:

1. **No `setResponseCallback` is set in any script.** So `http_req_failed` uses k6's default `expected_response` and counts **every** 4xx/5xx as failed — including the 401s and 409s that the `check()`s deliberately whitelist.
2. **`checks` only fails on a *non-whitelisted* status.** At 100% pass, every 4xx that occurred was a whitelisted status.

In this flow there are exactly two whitelisted-4xx sources:

- `loginFlow` (`flows.js:78–93`, weight 0.20) logs in with intentionally-wrong creds (`ProbablyWrong123`) and **401s every time** — an anti-enumeration timing probe, whitelisted as `200 || 401`.
- The four mutation flows return **409** on an optimistic-lock / duplicate-active conflict, whitelisted as `2xx || 409` (`flows.js:250, 281, 318, 360`).

Real logins via `loginManager` (cached per VU) only ever return 200 — otherwise `checks` would dip below 100%.

So: **`138 failed = (guaranteed 401 probes) + (409 conflicts)`**, with nothing else in the bucket.

---

## The probabilistic split

Each iteration draws a flow from the weighted picker in `k6-stress.js`:

```
search 0.45 · login(anon) 0.20 · submit 0.10 · approve 0.10 · complete 0.10 · register 0.05
```

The 401 count is `Binomial(628, 0.20)`; the 409 count is the 4xx remainder.

| Quantity | Estimate |
|---|---|
| 4xx/5xx total (measured) | 138 |
| Guaranteed 401 probes (0.20 × 628) | 126 ± 10 (1σ binomial) |
| **⇒ HTTP 409 conflicts** | **≈ 12 (≈2–22 at 1σ)** |
| 409 as % of all requests | **≈ 1.5%** |
| 409 as % of mutation writes (~160 POSTs¹) | **≈ 8%** |

¹ Mutation POSTs = flow selections minus the iterations that skipped the write because no
target/candidate existed (the `ams_load_*` counters: 22 + 23 + 15), plus register (never skips):
`(63−22)+(63−23)+(63−15)+31 ≈ 160`.

### Cross-checks

- **Request-volume self-consistency:** the same flow mix predicts `1.30 req/iter × 628 = 816` requests, vs the measured **811** — a <1% match, which validates the model end to end.
- **Prior agreement:** the implied 401:409 ratio (~10:1) is the same order as the Grafana 24h status split (1090:170 ≈ 6.4:1) recorded in `2026-05-31-throughput-investigation.md`. The stress flow generates 401s more aggressively (20% of iterations are the wrong-creds probe), so a higher ratio is expected.

---

## Conclusion

- The "17% failed" in `stress.html` is **not** an error signal — ~126 of the ~138 are intentional 401 probes.
- Genuine optimistic-lock **409 conflicts are ~1.5% of traffic (~8% of writes), roughly a dozen requests**, and `checks` at 100% confirms none of them were unexpected. Concurrency control held under the ramp.
- Caveat: 409 is a small difference of two larger numbers (138 − 126), so its relative uncertainty is high (±10 at 1σ). The point estimate is "order of ten, ~1–2% of traffic."

### To measure it exactly instead of inferring it

Add a one-line custom counter in `flows.js` and re-run; k6's web dashboard renders any registered metric, so it would then appear directly in the next `stress.html`:

```js
const conflict409 = new Counter("ams_load_conflict_409_total");
// inside each mutation flow, after the request:
if (res.status === 409) conflict409.add(1);
```
