# Grafana Cloud: AWS observability integration

Runbook for wiring AWS-side telemetry (CloudWatch Logs and Metrics) into the
Grafana Cloud stack used by AMS. The backend pushes traces, metrics, logs, and
profiles to Grafana Cloud over OTLP directly from the ECS task (see
`infra/ecs/backend-task-def.json` and `infra/ecs/README.md`); this directory
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
   `awslogs-create-group` option on `infra/ecs/backend-task-def.json`).
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
