# Grafana Cloud: AWS observability integration

Runbook for wiring AWS-side telemetry (CloudWatch Logs and Metrics) into the
Grafana Cloud stack used by AMS. The backend pushes traces, metrics, logs, and
profiles to Grafana Cloud over OTLP directly from the ECS task (see
`infra/aws/tasks/backend-task-def.json` and `infra/aws/tasks/README.md`); this directory
covers the complementary path where Grafana Cloud *pulls* AWS-managed signals
(ALB metrics, RDS metrics, CloudWatch log groups) via a cross-account IAM role.

Files in this directory:

| File | Purpose |
|------|---------|
| `iam-role-trust-policy.json` | Trust policy: lets Grafana Cloud's AWS account assume `ams-grafana-cloud-reader`, gated by an `sts:ExternalId` from the GC UI. |
| `iam-role-permissions.json`  | Inline identity policy: read-only access to the AWS APIs Grafana Cloud's hosted integrations need. |
| `README.md`                  | This runbook. |

The two JSON files contain placeholders (`__GC_AWS_ACCOUNT_ID__`,
`__GC_EXTERNAL_ID__`) that the operator substitutes by hand at role-creation
time. They are **not** rendered by `.github/actions/render-task-def` because
role creation is a one-shot operator action, not part of the deploy pipeline.

## Prerequisites

- A Grafana Cloud stack named `ams` exists. From the stack's "Connections"
  view, the AWS connector wizard has surfaced two values:
  - Grafana Cloud's AWS account ID (the principal that will assume the role).
  - A per-stack `external_id` (rotates if the connector is recreated).
- Local AWS CLI configured against the AMS production account with permission
  to create IAM roles and put inline role policies.
- `jq` installed for shell parsing.

## Step 1: create the cross-account IAM role

Substitute the two placeholders in `iam-role-trust-policy.json` with the
values from the GC connector wizard, then create the role:

```bash
ROLE_NAME=ams-grafana-cloud-reader

# Substitute placeholders into a temp file (do NOT commit the rendered file).
TMP=$(mktemp)
sed -e "s|__GC_AWS_ACCOUNT_ID__|<paste-from-gc-wizard>|" \
    -e "s|__GC_EXTERNAL_ID__|<paste-from-gc-wizard>|" \
    infra/grafana-cloud/iam-role-trust-policy.json > "$TMP"

aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document "file://$TMP" \
  --description "Read-only role assumed by Grafana Cloud's hosted CloudWatch integrations" \
  --max-session-duration 3600

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name ams-grafana-cloud-reader-inline \
  --policy-document "file://infra/grafana-cloud/iam-role-permissions.json"

rm "$TMP"

aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text
# Capture this ARN for Step 2.
```

The `sts:ExternalId` condition is mandatory. Without it the trust policy
would still work (GC's UI test succeeds because it assumes from its own
console), but the role is then vulnerable to the AWS confused-deputy
pattern and AWS Security Hub flags it. Always require the external ID.

## Step 2: register the role in Grafana Cloud

In the GC web UI:

1. Connections → Add new connection → AWS.
2. Paste the role ARN from Step 1 and the same `external_id` that was
   substituted into the trust policy.
3. Click "Test connection". Expect a green check inside a few seconds.

If the test fails with `AccessDenied`, the external ID was probably
re-rotated between substitution and "Test connection". Re-render the
trust policy with the current value from the wizard and update the role:

```bash
aws iam update-assume-role-policy \
  --role-name ams-grafana-cloud-reader \
  --policy-document "file://$TMP"
```

## Step 3: enable the CloudWatch Logs integration

Still in the AWS connection in GC:

1. CloudWatch Logs → Enable.
2. Select the `/ecs/ams-backend` log group (already auto-created by the
   `awslogs-create-group` option on `infra/aws/tasks/backend-task-def.json`).
3. Optionally add `/ecs/ams-frontend` to surface nginx access logs.

Logs land in the GC stack's Loki under the label
`{service_name="ams-backend"}` within 30 to 60 seconds.

## Step 4: enable the CloudWatch Metrics integration

In the same AWS connection:

1. CloudWatch Metrics → Enable.
2. Select namespaces:
   - `AWS/ECS` (task-level CPU and memory)
   - `AWS/ApplicationELB` (request count, target response time, 4xx/5xx)
   - `AWS/RDS` (CPUUtilization, DatabaseConnections, FreeableMemory)
   - `AWS/ECS/ContainerInsights` (per-container CPU and memory, throttling)
3. Default polling interval is 60s. Sub-minute granularity is not available
   from the CloudWatch path; use the OTLP-pushed Prometheus metrics from
   the application for finer resolution.

## Step 4b: capture the CloudWatch datasource UID

The AWS connector creates a Grafana datasource whose UID is auto-generated
per stack (e.g. `cfmzw3p1ziebkb`). The dashboard JSONs in
`config/grafana/dashboards/` reference the placeholder UID `cloudwatch`;
`scripts/sync_grafana_cloud_dashboards.py` rewrites it to the real UID at
sync time. Without this step, every CloudWatch panel renders empty even
though the connector is healthy.

1. In Grafana → Connections → Data sources, click the AWS CloudWatch
   datasource created in Step 4.
2. Copy the UID shown in the URL or in the "Settings" tab.
3. Store it as a repository variable named `GC_CLOUDWATCH_UID` (Settings
   → Secrets and variables → Actions → Variables → New repository
   variable). The `sync-dashboards` job reads it from `vars`.

The hosted Prometheus / Loki / Tempo / Pyroscope datasources use the
GC-standard UIDs (`grafanacloud-prom`, `grafanacloud-logs`,
`grafanacloud-traces`, `grafanacloud-profiles`) and need no per-stack
override. Override them via `GC_PROMETHEUS_UID` / `GC_LOKI_UID` /
`GC_TEMPO_UID` / `GC_PYROSCOPE_UID` only if your stack rebinds them.

## Step 5: wait for the first data

Allow about five minutes after enabling each integration for the first
samples to surface in the GC stack. Verify with these PromQL queries in
Explore:

```promql
# Backend task CPU (CloudWatch via GC integration)
aws_ecs_cpu_utilization_average{cluster_name="ams-prod"}

# Application-pushed request rate (OTLP)
rate(http_server_requests_total{environment="production"}[5m])
```

If only the first query returns data, the OTLP push from the ECS task
is misconfigured (check `OTEL_ENABLED`, `OTEL_ENDPOINT`, and the
`OTEL_EXPORTER_OTLP_HEADERS` secret). If only the second returns data,
the CloudWatch integration is misconfigured (check the role ARN, external
ID, and that the namespaces were selected in Step 4).

## Step 6: key rotation

The `ams-grafana-cloud` AWS Secrets Manager secret carries the GC API
key used by the OTLP and Pyroscope exporters. Rotate at least every
**90 days**, or immediately on suspected compromise. Rotation is
operator-driven:

1. In the GC UI, generate a new API key with the same scopes as the old
   one (publish for `metrics`, `logs`, `traces`, `profiles`).
2. Update the `ams-grafana-cloud` Secrets Manager secret in AWS:

   ```bash
   aws secretsmanager put-secret-value \
     --secret-id ams-grafana-cloud \
     --secret-string '{
       "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <new-base64(instance:api_key)>",
       "PYROSCOPE_AUTH_TOKEN": "<new-api-key>",
       "PYROSCOPE_BASIC_AUTH_USERNAME": "<pyroscope_instance_id>"
     }'
   ```

3. Force an ECS task redeploy so the new task pulls the rotated values
   (the existing task continues using the cached values until restart):

   ```bash
   aws ecs update-service \
     --cluster "$ECS_CLUSTER" \
     --service ams-backend \
     --force-new-deployment
   ```

4. Wait for `wait-for-service-stability` to confirm the new task is
   healthy in the ECS console, then revoke the old API key in the GC UI.

The cross-account IAM role and external ID do not rotate as part of this
flow; they are stable for the life of the GC stack. Recreate the GC AWS
connector only if compromise is suspected, then redo Steps 1 through 4.

## Known gotchas

- **Grafana Cloud's AWS account ID is published** at
  <https://grafana.com/docs/grafana-cloud/monitor-infrastructure/aws/cloudwatch/>.
  Verify the value the wizard shows matches the published account ID before
  substituting it into the trust policy; a UI spoofing attack could otherwise
  trick an operator into trusting a third-party account.
- **`max-session-duration 3600`** matches GC's documented assume-role TTL. A
  longer duration is rejected by GC's connector with no error message in the
  UI (the test succeeds but no data flows).
- **The role is read-only on purpose.** Do not extend the inline policy with
  write actions even if a future GC feature requests them. The role is
  assumable by a third-party account; widening permissions widens the blast
  radius.
- **`/ecs/ams-backend` log group must exist** before Step 3 can find it. The
  ECS task auto-creates it on first launch via `awslogs-create-group`; if you
  enable the integration before the first task deploy, the log group dropdown
  will be empty. Either deploy the task first or pre-create the group out of
  band.

## Accepted IAM `Resource: "*"` exposure

`iam-role-permissions.json` carries two statements scoped to `Resource: "*"`.
AWS Security Hub will flag both; documenting why each is unavoidable here so a
future audit doesn't relitigate the trade-off.

| Statement | Actions on `Resource: "*"` | Why it can't be narrowed |
|-----------|---------------------------|--------------------------|
| `LogQueryControl` | `logs:DescribeLogGroups`, `logs:GetQueryResults`, `logs:StopQuery` | `DescribeLogGroups` operates over the account-wide list and AWS does not support resource-level conditions on it. `GetQueryResults` / `StopQuery` reference CloudWatch Logs Insights query IDs that AWS does not bind to a log-group ARN at IAM-evaluation time; scoping to `arn:aws:logs:*:*:log-group:/ecs/ams-*:*` returns AccessDenied for legitimate GC queries. `logs:StartQuery` in the `ScopedLogReads` block stays scoped to `/ecs/ams-*`, so a query can only be *started* against AMS-owned log groups in the first place. |
| `CloudWatchMetricsRead` | `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics`, `cloudwatch:ListMetrics`, `tag:GetResources`, `rds:DescribeDBInstances`, `ec2:DescribeRegions` | None of the `cloudwatch:*` Get/List actions support resource-level permissions per AWS docs (the IAM evaluator can scope metric *namespace* via condition keys, not Resource ARNs, and GC's integration needs to discover dimensions per-region). `rds:DescribeDBInstances` and `ec2:DescribeRegions` are explicitly listed as not supporting resource-level permissions in the AWS IAM reference. Tag-based scoping via `tag:GetResources` is similarly account-wide. |

**Residual risk (accepted):** Grafana Cloud's AWS account can enumerate all
RDS instance metadata in this account (instance classes, engine versions,
endpoint DNS names, subnet IDs) and read every CloudWatch metric and Insights
query result across every namespace. For the AMS class project the blast
radius is bounded by the small surface (one RDS instance, one ECS cluster,
no cross-tenant data), but a future production hand-off should:

1. Adopt the more granular [Grafana Cloud private connectivity](https://grafana.com/docs/grafana-cloud/account-management/private-connectivity/)
   path so reads happen through a VPC endpoint rather than a cross-account
   role with `*` resources.
2. Place AMS-sensitive RDS instances in a separate AWS account so the
   broad-Describe surface above can't enumerate them.

Until that hand-off, treat the GC stack itself as part of the production
trust boundary and rotate the GC API key per the schedule in Step 6.

## Alert provisioning

The same `scripts/sync_grafana_cloud_dashboards.py` script also provisions
the email-based alerting setup described in
`docs/system-design/08-deployment-operations.md`:

- One contact point (`email-default`) defined in
  `config/grafana/alerts/contact-points.json`.
- One root notification policy in
  `config/grafana/alerts/notification-policy.json`.
- 14 alert rules (7 thresholds × warning + critical) under
  `config/grafana/alerts/rules/`.

Recipient configuration: the email addresses are NOT committed. The sync
script reads them from the `GC_ALERT_EMAIL_RECIPIENTS` GitHub secret
(comma-separated for multiple recipients) and substitutes them into the
contact-point template at deploy time. Local runs can pass `--recipients
<csv>` to override.

**Folder prerequisite:** all rules reference `folderUID: "ams-production"`.
Create this folder once before the first sync (via the GC UI: Alerting →
Alert rules → New folder → set UID = `ams-production`). The script does
not create folders; missing folder = 404 on every alert-rule POST.

**Runbook command** (the `--targets all` flag is required — the
script's default is `dashboards` for backward compatibility with
pre-alerts operator runs):

```bash
GRAFANA_CLOUD_API_KEY=<grafana-cloud-api-key> \
GC_CLOUDWATCH_UID=<see-step-5> \
GC_ALERT_EMAIL_RECIPIENTS="ops@example.com,oncall@example.com" \
  python scripts/sync_grafana_cloud_dashboards.py \
    --targets all \
    --stack-url https://<your-stack-slug>.grafana.net
```

To re-sync only alerts (skip dashboards) after editing a threshold:

```bash
... python scripts/sync_grafana_cloud_dashboards.py \
    --targets alerts --stack-url https://<your-stack-slug>.grafana.net
```

**Changing the recipients without a code PR:** update the
`GC_ALERT_EMAIL_RECIPIENTS` GitHub Actions secret (Settings → Secrets and
variables → Actions) and either wait for the next push to `main` that
touches `config/grafana/**` or trigger the deploy workflow manually
(`gh workflow run cd.yml`; `ci.yml` is PR-only and has no `workflow_dispatch`,
and the `sync-dashboards` job lives in `cd.yml`). The contact point is upserted on every run
so the new address list lands within one workflow.
