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
| `__RDS_SECRET_NAME__`    | `${{ vars.RDS_SECRET_NAME }}` (system-managed RDS secret name)                           |
| `__APP_SECRET_NAME__`    | `${{ vars.APP_SECRET_NAME }}` (application secret name, e.g. `ams/prod/app`)             |
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
| `RDS_SECRET_NAME`     | Name of the managed RDS secret                   |
| `APP_SECRET_NAME`     | e.g. `ams/prod/app`                              |
| `BOOTSTRAP_MANAGER_EMAIL` | Email of the seeded first manager (e.g. `admin@ams.example.com`) |

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
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:Joshua0209/Asset-Management-System:ref:refs/heads/main"
      }
    }
  }]
}
```

The `sub` condition restricts the role to runs from the `main` branch
of this exact repo - critical to prevent a fork or feature branch from
assuming production credentials.

## Health check note

The container-level health check above runs *inside* the task. It is
distinct from the ALB target group health check, which hits `/ready`
on the backend (DB connectivity probe) and `/` on the frontend. Both
must pass for the ALB to route traffic.
