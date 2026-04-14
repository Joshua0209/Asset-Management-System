# Usage Estimates

---

## Assumptions

- **App type:** Tool-type application (not content-heavy)
- **PV per user per day:** 2 (average, range 1-3)
- **Read:Write ratio:** 80:20 (frequent queries, fewer modifications)
- **Single machine QPS (assumed):** 500 QPS for stateless API server (to be validated by stress testing)

---

## Phase 1 — Pilot (初期)

| Metric | Value | Calculation |
|--------|-------|-------------|
| **DAU** | 300 | Single company pilot |
| **PV/user/day** | 2 | Tool-type app |
| **Daily PV** | 600 | 300 × 2 |
| **Average QPS** | 0.007 | 600 / 86,400 |
| **Peak QPS** | 0.028 | 0.007 × 4 (80/20 rule) |
| **Total assets** | ~2,000 | Small company inventory |
| **Repair requests/year** | ~1,200 | ~5/day × 240 working days |
| **DB storage (1 year)** | < 1 GB | Structured data is small |
| **Image storage (1 year)** | ~6 GB | ~1,200 requests × 2 images × 2.5 MB avg |
| **AP machines** | 1 | 0.028 / 500 << 1 |

**Conclusion:** A single server handles all traffic trivially. No scaling needed.

---

## Phase 2 — Growth (成長期)

| Metric | Value | Calculation |
|--------|-------|-------------|
| **DAU** | 30,000 | Multi-branch enterprise |
| **PV/user/day** | 3 | Slightly higher engagement (more branches, more assets) |
| **Daily PV** | 90,000 | 30,000 × 3 |
| **Average QPS** | ~1.04 | 90,000 / 86,400 |
| **Peak QPS** | ~4.2 | 1.04 × 4 |
| **Total assets** | ~200,000 | Multi-branch, ~70K per large branch |
| **Repair requests/year** | ~120,000 | ~500/day × 240 working days |
| **DB storage (3 years)** | ~5 GB | Structured data grows modestly |
| **Image storage (3 years)** | ~600 GB | 360K requests × 2 imgs × 2.5 MB |
| **AP machines** | 1 (+ 1 standby) | 4.2 / 500 << 1 but need redundancy |

**Conclusion:** QPS is still low. The primary driver for architecture change is **availability** (no single point of failure) and **data volume** (200K assets need good indexing). Two AP nodes behind a load balancer, read replica on DB for HA.

---

## Phase 3 — SaaS Platform (高流量)

| Metric | Value | Calculation |
|--------|-------|-------------|
| **DAU** | 3,000,000 | Multi-tenant SaaS serving many organizations |
| **PV/user/day** | 2 | Tool-type app, back to baseline |
| **Daily PV** | 6,000,000 | 3,000,000 × 2 |
| **Average QPS** | ~69.4 | 6,000,000 / 86,400 |
| **Peak QPS** | ~278 | 69.4 × 4 |
| **Total assets** | ~20,000,000 | Thousands of tenant organizations |
| **Repair requests/year** | ~6,000,000 | ~25,000/day × 240 working days |
| **DB storage (3 years)** | ~50 GB | 20M assets + 18M requests + metadata |
| **Image storage (3 years)** | ~45 TB | 18M requests × 2 imgs × 2.5 MB |
| **AP machines** | 2 (+ 1 redundancy) | 278 / 500 = 0.56 → 1, but 2 for HA + 1 spare = 3 |
| **3-year repair rows** | 18,000,000 | 6M/year × 3 |
| **Table shards (repair)** | 1 | 18M / 40M < 1, no sharding needed yet |

**Conclusion:** Peak QPS of ~278 is still moderate. The real challenges are **multi-tenancy isolation**, **image storage at scale (45 TB)**, **search performance across 20M assets**, and **operational complexity**. Database read/write separation becomes important. A caching layer (Redis) reduces DB load for frequent asset queries.

> **Note on QPS:** Asset management is a tool-type app with inherently low QPS even at 3M DAU. The architecture decisions for Phase 3 are driven more by data volume, multi-tenancy, and operational requirements than raw throughput.
