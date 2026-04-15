# Phase 1 Architecture — Pilot (300 DAU)

---

## Design Philosophy

Ship fast. Monolith. Single server. Minimize operational overhead. The architecture does not matter at this scale — feature completeness and correctness do.

---

## Application Architecture

**Pattern:** Modular Monolith (Layered Architecture)

```
┌─────────────────────────────────────────────┐
│              Frontend (SPA)                 │
│           React + Vite (SPA)                │
├─────────────────────────────────────────────┤
│              Backend (Monolith)             │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
│  │  Auth   │  │  Asset   │  │  Repair    │  │
│  │ Module  │  │  Module  │  │  Request   │  │
│  │         │  │          │  │  Module    │  │
│  └─────────┘  └──────────┘  └────────────┘  │
│  ┌─────────┐  ┌──────────┐                  │
│  │  Image  │  │  Search  │                  │
│  │ Upload  │  │  Module  │                  │
│  └─────────┘  └──────────┘                  │
├─────────────────────────────────────────────┤
│         ORM / Data Access Layer             │
├─────────────────────────────────────────────┤
│              MySQL (Single DB)              │
└─────────────────────────────────────────────┘
```

Internal modules are separated by domain (Auth, Asset, Repair, Image, Search) but deployed as a single process. This enables future extraction into services if needed.

---

## System Architecture

```
                    ┌──────────┐
                    │  Users   │
                    │ (Browser)│
                    └────┬─────┘
                         │ HTTPS
                    ┌────▼─────┐
                    │  Single  │
                    │  EC2     │
                    │          │
                    │ ┌──────┐ │
                    │ │Nginx │ │  (reverse proxy + static files)
                    │ └──┬───┘ │
                    │ ┌──▼───┐ │
                    │ │ App  │ │  (API server)
                    │ └──┬───┘ │
                    │ ┌──▼───┐ │
                    │ │MySQL │ │  (single DB)
                    │ └──────┘ │
                    │          │
                    │ /uploads │  (local filesystem for images)
                    └──────────┘
```

---

## Database Architecture

**Single MySQL instance** on the same server (or separate EBS volume).

No read/write separation. No caching layer. At 300 DAU with 0.03 peak QPS, any database handles this trivially.

---

## AWS Infrastructure & Cost Estimate

| Resource | Service | Spec | Monthly Cost |
|----------|---------|------|-------------|
| Application + DB server | EC2 | t4g.medium (2 vCPU, 4 GB) | ~$31 |
| Storage | EBS gp3 | 30 GB (OS + app + DB + images) | ~$2.40 |
| Domain + DNS | Route 53 | 1 hosted zone | ~$0.50 |
| **Total** | | | **~$34/month** |

> Alternative: Use a single RDS db.t4g.micro ($11.52/mo) for managed DB with automated backups, bringing the total to ~$46/month. This is recommended for data safety even at this scale.

---

## Key Decisions

- **Image storage:** Local filesystem (`/uploads/`). At 6 GB/year this is fine. Migrate to S3 in Phase 2.
- **Search:** SQL `LIKE` queries with proper indexes. At 2,000 assets, full-table scans are sub-millisecond.
- **i18n:** Use a frontend i18n library (e.g., `react-i18next`) from day one. Low cost to implement early, expensive to retrofit.
- **Concurrency control:** Optimistic locking via `version` column on `assets` and `repair_requests` tables from day one. This is a schema decision, not an infrastructure one.
