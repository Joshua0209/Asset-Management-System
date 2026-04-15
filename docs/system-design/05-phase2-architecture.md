# Phase 2 Architecture — Growth (30,000 DAU)

---

## Design Philosophy

Eliminate single points of failure. The system now serves a real enterprise with multi-branch operations. Downtime costs real money. Focus on: HA, monitoring, zero-downtime deployment, and proper image storage.

---

## What Changed (Bottlenecks Measured)

| Problem | Symptom | Solution |
|---------|---------|----------|
| Single server = SPOF | Any failure = total outage | Add load balancer + 2 AP nodes |
| DB = SPOF | DB crash = total outage | RDS Multi-AZ (automatic failover) |
| Image storage on local disk | Disk full; images lost on server failure | Migrate to S3 |
| No monitoring | Learn about outages from user complaints | Add CloudWatch + alerting |
| Manual deployment | Downtime during deploys | Containerize + rolling updates |
| Search slowing on 200K assets | Queries > 200ms with complex filters | Add composite indexes on `(status, category)`, `(department, location)` — sufficient at 4 QPS peak (see Caching Strategy) |

---

## Application Architecture

**Pattern:** Modular Monolith (unchanged, but containerized)

The monolith is still appropriate. At ~4 QPS peak, there is no throughput reason to split into microservices. The modules remain the same, but the deployment model changes.

---

## System Architecture

```
                         ┌──────────┐
                         │  Users   │
                         │ (Browser)│
                         └────┬─────┘
                              │ HTTPS
                         ┌────▼──────┐
                         │ Route 53  │  DNS
                         └────┬──────┘
                              │
                         ┌────▼──────┐
                         │   ALB     │  Application Load Balancer
                         │ (AWS ELB) │  (health checks, SSL termination)
                         └────┬──────┘
                       ┌──────┴─────┐
                  ┌────▼────┐  ┌────▼────┐
                  │  EC2-1  │  │  EC2-2  │   Stateless AP nodes
                  │  (App)  │  │  (App)  │   (Docker containers)
                  └────┬────┘  └────┬────┘
                       │            │
              ┌────────┴────────────┴────────┐
              │                              │
         ┌────▼────┐                   ┌─────▼────┐
         │  RDS    │                   │    S3    │
         │  MySQL  │                   │  (images)│
         │ Multi-AZ│                   └──────────┘
         │ (primary│
         │+standby)│
         └─────────┘
```

```mermaid
flowchart TD
    Client([Users Browser]) -->|HTTPS| Route53[Amazon Route 53]
    Route53 --> ALB[Application Load Balancer]

    subgraph "VPC - Public/Private Subnets"
        subgraph "Availability Zone A"
            App1[App Node 1 / ECS Container]
        end

        subgraph "Availability Zone B"
            App2[App Node 2 / ECS Container]
        end

        ALB --> App1
        ALB --> App2

        subgraph "Data Tier"
            RDS_P[(RDS MySQL Primary)]
            RDS_S[(RDS MySQL Standby)]
            RDS_P -.->|Auto Sync| RDS_S
        end

        App1 --> RDS_P
        App2 --> RDS_P

        App1 -->|IAM Role| S3[Amazon S3 - Image Storage]
        App2 -->|IAM Role| S3
    end
    
    %% Monitoring
    App1 -.-> CW([CloudWatch Logs & Metrics])
    App2 -.-> CW
    ALB -.-> CW
    RDS_P -.-> CW
```

---

## Database Architecture

**RDS MySQL Multi-AZ** provides:
- Automatic failover to standby (typically < 60 seconds)
- Automated daily backups with point-in-time recovery
- No read replica yet (QPS too low to justify the cost)

**Indexes added for Phase 2 query patterns:**
- `assets`: composite index on `(status, category)`, `(department, location)`, `(responsible_person_id)`
- `repair_requests`: composite index on `(status, created_at)`, `(asset_id, status)`

---

## Caching Strategy

**Decision: No Redis in Phase 2.** Optimize SQL queries and indexes instead.

### Why Redis Is Not Needed

At 30,000 DAU (~4 QPS peak, ~1 QPS average), the database alone handles all query patterns comfortably:

| Factor | Phase 2 Value | Why It Rules Out Redis |
|--------|--------------|------------------------|
| Peak QPS | ~4.2 | A single FastAPI process handles 500+ QPS. Two nodes provide >1,000 QPS capacity — utilization is under 1%. |
| Dataset size | ~5 GB (3 years) | Fits entirely in the InnoDB buffer pool (db.t4g.medium ≈ 4 GB RAM). MySQL already serves repeated reads from memory. |
| Query latency | <10 ms | Composite indexes on `(status, category)`, `(department, location)`, etc. cover every filter combination exposed by the API. |
| Cache hit rate | Estimated <10% | With 5 filter fields × sort options × pagination, the key space is large relative to 4 QPS. Most cached entries would expire before a second identical request arrives. |

**In short:** MySQL's buffer pool is already acting as an in-memory cache of the working set. Adding Redis would cache data that is already cached, while introducing operational complexity (invalidation logic, monitoring, failover) and ~$50/month in ElastiCache cost (25% of the Phase 2 budget).

### Non-Caching Use Cases Considered

| Use Case | Status | Rationale |
|----------|--------|-----------|
| Rate limiting | **Not needed** | At 4 QPS total, no user approaches the 100 req/min limit. Per-node in-memory enforcement (`slowapi`) is sufficient. |
| Session storage | **Not needed** | JWT-based auth is stateless. Short-lived tokens (1–2 h) with DB-backed refresh tokens avoid shared session state. |
| Distributed locks | **Not needed** | Optimistic locking via the `version` column handles concurrent writes at the database level. |
| Pub/Sub (notifications) | **Out of scope** | Real-time notifications are deferred per design decision Q14. |
| Job queue | **Not needed** | No background processing defined. Image uploads go directly to S3 without post-processing. |

### When to Revisit (Triggers for Adding Redis)

Do not add Redis proactively. Add it only when **measured data** shows one of these:

1. **Slow queries in production** — Enable MySQL slow query log (`long_query_time = 0.1s`). If any endpoint consistently exceeds 100 ms, fix with an index first; only consider caching if indexes are insufficient.
2. **QPS exceeds ~500 peak** — This would indicate 100× growth beyond Phase 2 estimates, at which point the system should be transitioning to Phase 3 architecture anyway.
3. **Dataset exceeds buffer pool** — If the active working set no longer fits in RAM, frequently-read data benefits from an external cache.
4. **Dashboard/aggregation endpoints added** — If a manager dashboard polls `COUNT GROUP BY status` on every page load across all users, caching aggregations with 30–60 s TTL becomes sensible.

Redis is introduced naturally in **Phase 3** (3M DAU, SOA, EKS) where multiple services share a database, the dataset reaches tens of millions of rows, and rate limiting must be enforced across many pods.

---

## Zero-Downtime Deployment

**Strategy:** Rolling update via ECS (Elastic Container Service) or a simple blue-green with ALB target groups.

```
Deployment Flow:
1. Build new Docker image, push to ECR
2. ECS service creates new task with new image
3. ALB health check passes on new task
4. ALB drains connections from old task
5. Old task terminates
6. Zero downtime achieved
```

---

## Monitoring & Observability

| Component | Tool | Purpose |
|-----------|------|---------|
| Metrics | CloudWatch | CPU, memory, disk, request count, latency |
| Logs | CloudWatch Logs | Centralized application logs |
| Alerts | CloudWatch Alarms + SNS | CPU > 80%, error rate > 1%, health check fail |
| Health Check | ALB target group health check | `/health` endpoint on each AP node |
| Uptime | CloudWatch Synthetics (optional) | Periodic canary checks |

---

## AWS Infrastructure & Cost Estimate

| Resource | Service | Spec | Monthly Cost |
|----------|---------|------|-------------|
| AP nodes (×2) | EC2 | t4g.medium (2 vCPU, 4 GB) | ~$62 |
| Load Balancer | ALB | 1 ALB | ~$22 |
| Database | RDS MySQL | db.t4g.medium, Multi-AZ | ~$95 |
| Storage (DB) | EBS gp3 | 50 GB | ~$4 |
| Image storage | S3 | ~200 GB (growing) | ~$5 |
| DNS | Route 53 | 1 hosted zone | ~$0.50 |
| Monitoring | CloudWatch | Basic metrics + alarms | ~$10 |
| Container Registry | ECR | 1 repo | ~$1 |
| **Total** | | | **~$200/month** |
