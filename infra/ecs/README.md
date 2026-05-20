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
| `__ALB_VPC_CIDR__`       | `${{ vars.ALB_VPC_CIDR }}` (becomes `FORWARDED_ALLOW_IPS`)                               |
| `__DB_HOST__`            | `${{ vars.DB_HOST }}` (RDS endpoint)                                                     |
| `__DB_NAME__`            | `${{ vars.DB_NAME }}` (database name, e.g. `ams`)                                        |
| `__RDS_SECRET_NAME__`    | `${{ vars.RDS_SECRET_NAME }}` (system-managed RDS secret name, must include 6-char ARN suffix — see below) |
| `__APP_SECRET_NAME__`    | `${{ vars.APP_SECRET_NAME }}` (application secret name, must include 6-char ARN suffix — see below) |
| `__BOOTSTRAP_MANAGER_EMAIL__` | `${{ vars.BOOTSTRAP_MANAGER_EMAIL }}` (email of the seeded first manager)           |

### Placeholder convention (read before adding new ones)

1. **Use `__NAME__` sentinels**, not bare `NAME`. Bare tokens collide with
   real values in the JSON: `{"name": "DB_HOST", "value": "DB_HOST"}` would
   rewrite the env-var **name** as well as the value, and the container would
   not see `DB_HOST` at all. The double-underscore wrapper makes the placeholder
   unambiguous.
2. **Use `|` as the `sed` delimiter**, not `/`. Several injected values
   legitimately contain `/`: CIDRs (`10.0.0.0/16`), secret paths
   (`ams/prod/app`). `/` as delimiter breaks `sed` parsing.
3. **Reference values via `env:`**, not inline `${{ ... }}` expressions. Avoids
   GitHub Actions expression-injection patterns and keeps the script auditable.
4. The deploy step ends with a `grep '__[A-Z_]+__'` guard that fails the build
   if any placeholder slipped through. Always update both the JSON and the
   workflow together; the guard will catch one-sided changes.

### Secret-name vars must include the AWS-side suffix (CRITICAL)

AWS Secrets Manager appends a 6-character random suffix to every secret
ARN (e.g. `ams/prod/app-AbCdEf`). The task definition references the
full ARN, so `vars.RDS_SECRET_NAME` and `vars.APP_SECRET_NAME` MUST be
set to the name **with** the suffix. Looking up a secret by bare name
(`ams/prod/app`) yields a `ResourceNotFoundException` at task launch.

The suffix is visible in the AWS console (Secret details → ARN) or via
`aws secretsmanager describe-secret --secret-id ams/prod/app --query
'ARN'`. Example correct value: `ams/prod/app-Xy12Ab`.

`DB_PORT` is intentionally not parameterised — it is pinned to MySQL's default
`3306` in `backend/app/core/config.py`. If a future RDS instance uses a non-
default port, add `DB_PORT` to the task-def `environment` block (no secret
indirection needed) and to the placeholder list above.

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
| `NVD_API_KEY`        | Optional, raises OWASP Dependency-Check rate limit       |
| `SONAR_TOKEN`        | Already configured for the existing SonarCloud job       |

### Repository variables

| Variable              | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `AWS_REGION`          | e.g. `ap-northeast-1`                            |
| `REPAIR_S3_BUCKET`    | Name of the S3 bucket for repair images          |
| `ALB_VPC_CIDR`        | VPC CIDR of the ALB subnets (e.g. `10.0.0.0/16`) |
| `ECR_REPOSITORY_BACKEND`  | e.g. `ams-backend`                           |
| `ECR_REPOSITORY_FRONTEND` | e.g. `ams-frontend`                          |
| `ECS_CLUSTER`         | e.g. `ams-prod`                                  |
| `ECS_SERVICE_BACKEND` | e.g. `ams-backend`                               |
| `ECS_SERVICE_FRONTEND`| e.g. `ams-frontend`                              |
| `DB_HOST`             | RDS instance endpoint                            |
| `DB_NAME`             | e.g. `ams`                                       |
| `RDS_SECRET_NAME`     | Name of the managed RDS secret, **including the 6-char ARN suffix** (e.g. `rds!db-AbCdEf`) |
| `APP_SECRET_NAME`     | Name of the application secret, **including the 6-char ARN suffix** (e.g. `ams/prod/app-Xy12Ab`) |
| `BOOTSTRAP_MANAGER_EMAIL` | Email of the seeded first manager (e.g. `admin@ams.example.com`) |
| `VITE_API_BASE_URL`   | Optional. Build-time API base for the frontend bundle. Defaults to `/api/v1` (same-origin via ALB path routing) — override only if FE and BE are on separate domains |

**GitHub vs AWS secrets.** Items in *Repository secrets* and *Repository
variables* tables live in GitHub Actions settings. `RDS_SECRET_NAME` /
`APP_SECRET_NAME` only carry the *names* of secrets that live in **AWS
Secrets Manager** — the credentials themselves never enter GitHub. The
task-def's `secrets:` block resolves those names to live values at task
launch using the execution role's `secretsmanager:GetSecretValue`
permission.

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
