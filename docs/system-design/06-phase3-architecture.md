# Phase 3 Architecture — SaaS Platform (3,000,000 DAU)

---

## Design Philosophy

The system is now a multi-tenant SaaS platform serving many organizations. Key challenges shift to: **tenant isolation**, **data volume (20M assets, 45 TB images)**, **search at scale**, **operational automation**, and **cost optimization**. QPS remains moderate (~278 peak) because this is a tool-type app.

---

## What Changed (Bottlenecks Measured)

| Problem | Symptom | Solution |
|---------|---------|----------|
| Single-tenant schema | Cannot onboard new orgs without code changes | Add tenant isolation (shared DB, tenant_id column or schema-per-tenant) |
| Search slow on 20M assets | Multi-filter queries > 500ms | Introduce Elasticsearch for search |
| Image storage 45 TB | S3 costs rising; need lifecycle policies | S3 Intelligent-Tiering + CDN for frequent access |
| DB write contention | Lock waits during peak repair request processing | Read/write separation (read replicas) |
| Monolith deploy risk | Single bug can take down entire system | Decompose into 2-3 services (not fine-grained microservices) |
| Manual operations at scale | Too many orgs to manage manually | Kubernetes (EKS) for orchestration |

---

## Application Architecture

**Pattern:** Service-Oriented Architecture (SOA) — 3 services, not microservices

Following the Taobao evolution principle, we decompose only when the monolith creates measurable problems. At this scale, the team likely has 5-10 developers, justifying 3 services:

```
┌─────────────────────────────────────────────────────────┐
│                      API Gateway                        │
│              (Kong / AWS API Gateway)                   │
│         Rate limiting, auth, routing, tenant ID         │
└───────┬──────────────────┬──────────────────┬───────────┘
        │                  │                  │
  ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
  │   Auth    │    │   Asset     │    │   Repair    │
  │  Service  │    │   Service   │    │   Request   │
  │           │    │             │    │   Service   │
  │ - Login   │    │ - CRUD      │    │ - Workflow  │
  │ - Register│    │ - Search    │    │ - History   │
  │ - RBAC    │    │ - Assign    │    │ - Images    │
  └─────┬─────┘    └──────┬──────┘    └──────┬──────┘
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐      ┌───────────┐      ┌───────────┐
   │ User DB │      │ Asset DB  │      │ Repair DB │
   │ (shared │      │ (R/W split│      │ (R/W split│
   │  or own)│      │  + Redis) │      │  + Redis) │
   └─────────┘      └───────────┘      └───────────┘
```

**Why 3 services, not more:**
- Compound failure: 3 services at 99.9% each = 99.7% system reliability (acceptable)
- 10 services at 99.9% each = 99.0% (drops below three nines)
- Each service maps to a clear business domain
- Small team cannot effectively operate more than 3-5 services

---

## System Architecture

```
                              ┌──────────┐
                              │  Users   │
                              │(Browser/ │
                              │ Mobile)  │
                              └────┬─────┘
                                   │ HTTPS
                              ┌────▼──────┐
                              │ Route 53  │
                              └────┬──────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
               ┌────▼──────┐                 ┌────▼─────┐
               │ CloudFront│                 │   ALB    │
               │   (CDN)   │                 │          │
               │  static + │                 └────┬─────┘
               │  images   │                      │
               └────┬──────┘              ┌───────┴───────┐
                    │                     │               │
               ┌────▼──────┐        ┌─────▼─────┐  ┌─────▼─────┐
               │    S3     │        │ API GW /  │  │  EKS      │
               │  (images) │        │ Kong      │  │  Cluster  │
               └───────────┘        └─────┬─────┘  │           │
                                          │        │ ┌───────┐ │
                                          │        │ │ Auth  │ │
                                          ├────────│ │ ×2    │ │
                                          │        │ ├───────┤ │
                                          │        │ │ Asset │ │
                                          ├────────│ │ ×3    │ │
                                          │        │ ├───────┤ │
                                          │        │ │Repair │ │
                                          └────────│ │ ×3    │ │
                                                   │ └───────┘ │
                                                   └─────┬─────┘
                                                         │
                              ┌───────────┬──────────────┼──────────────┐
                              │           │              │              │
                         ┌────▼────┐ ┌────▼────┐  ┌─────▼─────┐ ┌───────▼───────┐
                         │  RDS    │ │  RDS    │  │   Redis   │ │ Elasticsearch │
                         │ Primary │ │ Read    │  │ElastiCache│ │   (search)    │
                         │ (write) │ │ Replica │  │ (cache)   │ │               │
                         └─────────┘ └─────────┘  └───────────┘ └───────────────┘
```

---

## Database Architecture

**Level 2: Read/Write Separation**

```
                    ┌──────────────┐
                    │  App Server  │
                    │              │
                    │  Write ──────┼──── RDS Primary (db.t3.large)
                    │              │         │
                    │  Read ───────┼──── RDS Read Replica (db.t3.large)
                    │              │
                    └──────────────┘
```

**Why not sharding (yet):**
- 3-year repair request rows: 18M (well under MySQL 40M/table threshold)
- 3-year asset rows: 20M (under 40M threshold)
- Sharding adds significant application complexity for marginal benefit at this data volume

**When to shard:** If/when a single table exceeds 40M rows or write QPS exceeds single-master capacity (~2,000 writes/sec). At ~56 write QPS peak (278 × 0.2), this is far away.

**Multi-tenancy strategy:**

| Approach | Description | Recommended |
|----------|------------|-------------|
| Shared DB, shared schema | `tenant_id` column on every table | Yes (Phase 3 start) |
| Shared DB, separate schema | One schema per tenant | For large tenants later |
| Separate DB per tenant | Full isolation | Enterprise tier only |

Start with shared schema + `tenant_id`. Every query includes `WHERE tenant_id = ?`. Add composite indexes prefixed with `tenant_id`.

---

## Caching Strategy (Redis)

| Cache Target | Key Pattern | TTL | Invalidation |
|-------------|-------------|-----|-------------|
| Asset detail | `asset:{tenant}:{id}` | 5 min | On update |
| Asset list (per page) | `assets:{tenant}:page:{n}:filter:{hash}` | 60 sec | On any asset write in tenant |
| User session | `session:{token}` | 24 hr | On logout |
| Repair request | `repair:{tenant}:{id}` | 2 min | On update |

---

## Search Architecture (Elasticsearch)

At 20M assets, multi-dimensional search (by ID, name, model, location, person, status, department) requires a dedicated search engine.

```
Write path:  App → MySQL (source of truth) → async sync → Elasticsearch
Read path:   App → Elasticsearch (search/filter queries)
Detail path: App → Redis cache → MySQL (single record by ID)
```

**Sync strategy:** Application writes to MySQL, then publishes an event. A background worker consumes events and updates Elasticsearch. Eventual consistency window: < 2 seconds.

---

## Image Storage & CDN

```
Upload:   Client → Presigned S3 URL → S3 bucket (organized by tenant/year/month)
Read:     Client → CloudFront CDN → S3 origin

S3 Lifecycle:
- 0-90 days:   S3 Standard
- 90-365 days:  S3 Standard-IA (Infrequent Access)
- >365 days:    S3 Glacier Instant Retrieval
```

**Cost optimization:** At 45 TB, S3 Standard costs ~$1,035/month. With lifecycle policies, older images (majority) move to cheaper tiers, reducing to ~$400-500/month.

---

## AWS Infrastructure & Cost Estimate

| Resource | Service | Spec | Monthly Cost |
|----------|---------|------|-------------|
| EKS Cluster | EKS | 1 cluster | ~$73 |
| Worker nodes (×4) | EC2 | t4g.large (2 vCPU, 8 GB) | ~$249 |
| Load Balancer | ALB | 1 ALB | ~$22 |
| API Gateway | Kong on EKS (or AWS API GW) | Included in EKS | $0 (self-hosted) |
| Primary DB | RDS MySQL | db.t3.large, Multi-AZ | ~$196 |
| Read Replica | RDS MySQL | db.t3.large | ~$98 |
| DB Storage | EBS gp3 | 200 GB | ~$16 |
| Cache | ElastiCache Redis | cache.t4g.medium | ~$50 |
| Search | OpenSearch (managed ES) | t3.medium.search ×2 | ~$140 |
| Image storage | S3 | ~15 TB (year 1, with lifecycle) | ~$400 |
| CDN | CloudFront | ~5 TB transfer/month | ~$425 |
| DNS | Route 53 | 1 hosted zone + queries | ~$5 |
| Monitoring | CloudWatch + X-Ray | Enhanced | ~$50 |
| Container Registry | ECR | Multiple repos | ~$5 |
| **Total** | | | **~$1,729/month** |

> Note: Costs scale with actual usage. S3 and CloudFront dominate at this phase due to image volume. The compute and DB costs remain modest because this is a low-QPS tool app.
