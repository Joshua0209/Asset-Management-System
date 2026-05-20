# ECS task definitions

These JSON files are the source of truth for the production ECS task
configuration. The deploy jobs in `.github/workflows/ci.yml` render them
with the new image tag on each push to `main` (after the test, SCA, and
SonarQube gates pass), then register the new revision and wait for the
ECS service to reach steady state.

## Placeholders

The committed files contain placeholders that are dynamically substituted during
the deployment pipeline in `.github/workflows/ci.yml`. This keeps sensitive
identifiers like account IDs out of source control and lets the same templates
work across environments.

| Placeholder              | Source (GitHub Actions)                                                                  |
|--------------------------|------------------------------------------------------------------------------------------|
| `__ACCOUNT_ID__`         | `${{ secrets.AWS_ACCOUNT_ID }}`                                                          |
| `__REGION__`             | `${{ vars.AWS_REGION }}`                                                                 |
| `PLACEHOLDER_IMAGE`      | Replaced by `aws-actions/amazon-ecs-render-task-definition`                              |
| `__REPAIR_S3_BUCKET__`   | `${{ vars.REPAIR_S3_BUCKET }}`                                                           |
| `__DATABASE_URL_SECRET_NAME__` | `${{ vars.DATABASE_URL_SECRET_NAME }}` (application secret name for DATABASE_URL, must include 6-char ARN suffix) |
| `__APP_SECRET_NAME__`    | `${{ vars.APP_SECRET_NAME }}` (application secret name, must include 6-char ARN suffix — see below) |
| `__BOOTSTRAP_MANAGER_EMAIL__` | `${{ vars.BOOTSTRAP_MANAGER_EMAIL }}` (email of the seeded first manager)           |
| `__GC_OTLP_ENDPOINT__`   | `${{ secrets.GC_OTLP_ENDPOINT }}` (Grafana Cloud OTLP gateway URL, e.g. `https://otlp-gateway-prod-eu-west-3.grafana.net/otlp`) |
| `__GC_PYROSCOPE_ENDPOINT__` | `${{ secrets.GC_PYROSCOPE_ENDPOINT }}` (Grafana Cloud Pyroscope endpoint, e.g. `https://profiles-prod-eu-west-3.grafana.net`) |
| `__GC_SECRET_NAME__`     | `${{ vars.GC_SECRET_NAME }}` (Grafana Cloud credentials secret name in AWS Secrets Manager, must include 6-char ARN suffix) |

### Placeholder convention (read before adding new ones)

Substitution lives in the composite action at
[`.github/actions/render-task-def/action.yml`](../../.github/actions/render-task-def/action.yml),
called by both `deploy-backend` and `deploy-frontend`. Adding a placeholder is a
two-touch change: add `__NAME__` in the task-def JSON, then add `NAME` to that
job's `required-vars:` list (and to its `env:` block, mapping to the matching
GitHub secret or variable).

1. **Use `__NAME__` sentinels**, not bare `NAME`. Bare tokens collide with
   real values in the JSON: `{"name": "REPAIR_S3_BUCKET", "value": "REPAIR_S3_BUCKET"}` would
   rewrite the env-var **name** as well as the value, and the container would
   not see `REPAIR_S3_BUCKET` at all. The double-underscore wrapper makes the placeholder
   unambiguous. The action substitutes `__NAME__` from the env var named `NAME`,
   so the names must match exactly.
2. **Use `|` as the `sed` delimiter**, not `/`. Several injected values
   legitimately contain `/`: secret paths (`ams/prod/app`). `/` as delimiter
   breaks `sed` parsing. The action uses `|` for this reason; do not change it.
3. **Reference values via `env:`**, not inline `${{ ... }}` expressions. Avoids
   GitHub Actions expression-injection patterns and keeps the script auditable.
   The action reads via `${!name}` indirect expansion, so the caller's `env:`
   block is the only entry point for values.
4. The action ends with a `grep '__[A-Z_]+__'` guard that fails the build
   if any placeholder slipped through. Always update the JSON and the
   caller's `required-vars:` together; the guard will catch one-sided changes.

### Secret-name vars must include the AWS-side suffix (CRITICAL)

AWS Secrets Manager appends a 6-character random suffix to every secret
ARN (e.g. `ams/prod/app-AbCdEf`). The task definition references the
full ARN, so `vars.DATABASE_URL_SECRET_NAME` and `vars.APP_SECRET_NAME` MUST be
set to the name **with** the suffix. Looking up a secret by bare name
(`ams/prod/app`) yields a `ResourceNotFoundException` at task launch.

The suffix is visible in the AWS console (Secret details → ARN) or via
`aws secretsmanager describe-secret --secret-id ams/prod/app --query
'ARN'`. Example correct value: `ams/prod/app-Xy12Ab`.

`DB_PORT` is intentionally not parameterised. When using `DATABASE_URL` (the
production default), the port is included in the secret string. If a future
need arises for individual components, ensure `DB_PORT` is pinned to MySQL's
default `3306` in `backend/app/core/config.py` or overridden in the task-def.

`WEB_CONCURRENCY=1` is set explicitly in the task definition even though
the image default also pins it — operators reading the task-def should
not have to cross-reference the Dockerfile to see the single-worker
invariant. Scaling axis through Phase 2 is the ECS service
`desiredCount`, not gunicorn `--workers`; see
`docs/system-design/08-deployment-operations.md` §"API Hardening: Rate
Limiting" for why.

## Required secrets and variables

Configure under `Settings -> Secrets and variables -> Actions`:

### Repository secrets

| Secret               | Purpose                                                  |
|----------------------|----------------------------------------------------------|
| `AWS_ACCOUNT_ID`     | Your AWS account number (12 digits)                      |
| `AWS_DEPLOY_ROLE_ARN`| OIDC role the workflow assumes (no long-lived keys)      |
| `GC_OTLP_ENDPOINT`   | Grafana Cloud OTLP gateway URL (region-scoped; copy from the GC stack's "OpenTelemetry" connection page). Stored as a *secret* rather than a variable: the embedded stack slug + region narrow attacker target-identification if combined with a leaked GC API key, so defense-in-depth keeps the URL out of public-repo visibility |
| `GC_PYROSCOPE_ENDPOINT` | Grafana Cloud Pyroscope endpoint (region-scoped; copy from the GC stack's "Pyroscope" connection page). Same secret-vs-variable rationale as `GC_OTLP_ENDPOINT` |
| `GC_STACK_URL`       | Grafana Cloud stack URL, e.g. `https://<your-stack-slug>.grafana.net`. Consumed by the `sync-dashboards` CD job to upsert `config/grafana/dashboards/*.json` via the dashboards-DB API. **Not** the same as `GC_OTLP_ENDPOINT` — the OTLP gateway is for telemetry ingest, the stack URL is for Grafana's HTTP control plane. Same secret-vs-variable rationale as the other GC endpoints |
| `GRAFANA_CLOUD_API_KEY` | Grafana Cloud API key with **dashboards write** scope. Create at `https://grafana.com/orgs/<org>/api-keys` (separate token from the OTLP/Pyroscope credentials in the AWS `ams-grafana-cloud` secret — those ingest telemetry; this one mutates dashboards). Consumed by `sync-dashboards` only |
| `NVD_API_KEY`        | Optional, raises OWASP Dependency-Check rate limit       |
| `SONAR_TOKEN`        | Already configured for the existing SonarCloud job       |

### Repository variables

| Variable              | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `AWS_REGION`          | e.g. `ap-northeast-1`                            |
| `REPAIR_S3_BUCKET`    | Name of the S3 bucket for repair images          |
| `ECR_REPOSITORY_BACKEND`  | e.g. `ams-backend`                           |
| `ECR_REPOSITORY_FRONTEND` | e.g. `ams-frontend`                          |
| `ECS_CLUSTER`         | e.g. `ams-prod`                                  |
| `ECS_SERVICE_BACKEND` | e.g. `ams-backend`                               |
| `ECS_SERVICE_FRONTEND`| e.g. `ams-frontend`                              |
| `DATABASE_URL_SECRET_NAME` | Name of the database secret, **including the 6-char ARN suffix** (e.g. `ams/prod/db-AbCdEf`) |
| `APP_SECRET_NAME`     | Name of the application secret, **including the 6-char ARN suffix** (e.g. `ams/prod/app-Xy12Ab`) |
| `BOOTSTRAP_MANAGER_EMAIL` | Email of the seeded first manager (e.g. `admin@ams.example.com`) |
| `VITE_API_BASE_URL`   | Optional. Build-time API base for the frontend bundle. Defaults to `/api/v1` (same-origin via ALB path routing) — override only if FE and BE are on separate domains |
| `GC_SECRET_NAME`      | Name of the `ams-grafana-cloud` secret in AWS Secrets Manager, **including the 6-char ARN suffix** (e.g. `ams-grafana-cloud-Xy12Ab`) |

> Note: `GC_OTLP_ENDPOINT` and `GC_PYROSCOPE_ENDPOINT` previously lived
> under *Repository variables*. They were promoted to *Repository secrets*
> as a defense-in-depth measure — the URLs reveal the GC stack slug and
> region, which combined with a leaked GC API key would narrow the
> attack surface. If you are setting up a fresh repo, configure them
> under *Settings → Secrets and variables → Actions → Secrets*, not
> *Variables*. If you are upgrading, delete the existing entries from
> the *Variables* tab and recreate them as *Secrets* with the same value.

**GitHub vs AWS secrets.** Items in *Repository secrets* and *Repository
variables* tables live in GitHub Actions settings. `DATABASE_URL_SECRET_NAME` /
`APP_SECRET_NAME` / `GC_SECRET_NAME` only carry the *names* of secrets that
live in **AWS Secrets Manager** — the credentials themselves never enter
GitHub. The task-def's `secrets:` block resolves those names to live values
at task launch using the execution role's `secretsmanager:GetSecretValue`
permission.

### `ams-grafana-cloud` secret shape

The `__GC_SECRET_NAME__` placeholder resolves to the AWS Secrets Manager
secret that holds Grafana Cloud OTLP / Pyroscope credentials. Create the
secret out-of-band (it is operator-managed, not deploy-pipeline-managed)
with this exact JSON shape so the three `secrets:` entries in the task
def resolve cleanly:

```json
{
  "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <base64(prom_instance_id:api_key)>",
  "PYROSCOPE_AUTH_TOKEN": "<grafana_cloud_api_key>",
  "PYROSCOPE_BASIC_AUTH_USERNAME": "<pyroscope_instance_id>"
}
```

The Grafana Cloud-side IAM role that the hosted CloudWatch integrations
assume is a separate setup; see
[`infra/grafana-cloud/README.md`](../grafana-cloud/README.md) for the
cross-account role creation and the GC connector wiring.

**Execution role must have `secretsmanager:GetSecretValue`.** The
`AmazonECSTaskExecutionRolePolicy` managed policy includes this against
all secrets the account owns, so attaching that policy to
`ams-ecs-task-execution` is sufficient. If the execution role uses a
scoped inline policy instead, extend the `Resource:` list to include the
`ams-grafana-cloud-*` ARN alongside the existing RDS and app secret
ARNs (the role reads secrets at task launch; the *task* role does not
need this permission).

## OIDC trust policy snippet

The `AWS_DEPLOY_ROLE_ARN` role must trust GitHub's OIDC provider. Minimal
example (substitute your account ID and repo path):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:Joshua0209/Asset-Management-System:ref:refs/heads/main"
      }
    }
  }]
}
```

The `sub` condition restricts the role to runs from the `main` branch
of this exact repo - critical to prevent a fork or feature branch from
assuming production credentials. Use `StringEquals` (not `StringLike`):
the value contains no wildcards, and `StringLike` would silently honour
any `*` a future operator pasted in (e.g. broadening to all branches by
mistake).

## Identity policy for the deploy role

The trust policy above only controls *who* can assume the role. The
*identity* policy (attached to the same role) controls what the role
can do once assumed. Minimum permissions for this pipeline:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:DescribeImageScanFindings"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSDeploy",
      "Effect": "Allow",
      "Action": [
        "ecs:RegisterTaskDefinition",
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTasks",
        "ecs:DescribeTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassTaskRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::ACCOUNT_ID:role/ams-ecs-task-execution",
        "arn:aws:iam::ACCOUNT_ID:role/ams-backend-task",
        "arn:aws:iam::ACCOUNT_ID:role/ams-frontend-task"
      ],
      "Condition": {
        "StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}
      }
    }
  ]
}
```

The `iam:PassRole` permission is required because
`ecs:RegisterTaskDefinition` includes the task and execution role ARNs;
without `PassRole`, the API call fails. The `PassedToService`
condition prevents the deploy role from handing those ARNs to anything
other than ECS tasks (e.g. attaching them to an EC2 instance).

## Required: enable deployment circuit breaker on each ECS service

The deploy workflow uses `wait-for-service-stability: true` with
`wait-for-minutes: 10`. That only times out the *workflow* if the new
task set crash-loops past 10 minutes — ECS itself keeps trying to
launch the broken task definition indefinitely, draining service
capacity. Configure auto-rollback **on the service**, not the task
definition:

```bash
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service ams-backend \
  --deployment-configuration '{"deploymentCircuitBreaker":{"enable":true,"rollback":true},"maximumPercent":200,"minimumHealthyPercent":100}'
```

Repeat for `ams-frontend`. With this setting, a deployment that fails
to reach steady state is automatically reverted to the previous task
definition — closing the gap where a red CI run leaves a broken
revision serving traffic.

## Health check note

The container-level health check is distinct from the ALB target group
health check; both must pass for the ALB to route traffic.

- **Backend container check**: `GET /ready` (DB connectivity probe).
  Aligned with the ALB target group so an RDS Multi-AZ failover drains
  the unhealthy task instead of letting ECS report it healthy while the
  ALB marks it unhealthy.
- **Frontend container check**: `wget -S --spider ... | grep '200 OK'`.
  Drops the previous `-q` flag so non-200 responses, DNS errors, and
  connection refusals surface in container stderr (visible via
  `aws ecs describe-tasks` and CloudWatch).

`startPeriod` covers cold-start: 30s for the backend (gunicorn + DB
ping), 10s for the frontend (nginx).

## CloudWatch log group bootstrap

The `logConfiguration.options` block sets `"awslogs-create-group":
"true"` so the first task launch auto-creates the log group instead of
failing with `ResourceNotFoundException`. This requires the execution
role to have `logs:CreateLogGroup` in addition to the standard
`AmazonECSTaskExecutionRolePolicy` (which only grants `CreateLogStream`
+ `PutLogEvents`). Attach an inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "logs:CreateLogGroup",
    "Resource": [
      "arn:aws:logs:REGION:ACCOUNT_ID:log-group:/ecs/ams-backend",
      "arn:aws:logs:REGION:ACCOUNT_ID:log-group:/ecs/ams-frontend"
    ]
  }]
}
```

Alternative: pre-create the two log groups out-of-band (Terraform / CDK
/ console) and remove the `awslogs-create-group` option. Then the
standard managed policy is sufficient.

## Architecture pinning

Both task definitions set `runtimePlatform` to `LINUX/X86_64`
explicitly. Without it Fargate defaults to the same values, but a
`docker buildx` from Apple Silicon without `--platform linux/amd64`
silently produces an ARM64 image that fails task launch with `exec
format error`. The explicit block fails the build earlier.
