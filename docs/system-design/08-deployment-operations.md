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
