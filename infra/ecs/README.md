# ECS task definitions

These JSON files are the source of truth for the production ECS task
configuration. The deploy jobs in `.github/workflows/ci.yml` render them
with the new image tag on each push to `main` (after the test, SCA, and
SonarQube gates pass), then register the new revision and wait for the
ECS service to reach steady state.

## Placeholders

The committed files contain placeholders that are dynamically substituted during the
deployment pipeline in `.github/workflows/ci.yml`. This ensures that sensitive
identifiers like Account IDs are kept out of source control and allows the same
templates to be used across different environments.

| Placeholder         | Source (GitHub Actions)                                                                  |
|---------------------|------------------------------------------------------------------------------------------|
| `ACCOUNT_ID`        | `${{ secrets.AWS_ACCOUNT_ID }}`                                                          |
| `REGION`            | `${{ vars.AWS_REGION }}`                                                                 |
| `PLACEHOLDER_IMAGE` | Replaced by `aws-actions/amazon-ecs-render-task-definition`                              |
| `REPAIR_S3_BUCKET`  | `${{ vars.REPAIR_S3_BUCKET }}`                                                           |
| `ALB_VPC_CIDR`      | `${{ vars.ALB_VPC_CIDR }}` (becomes `FORWARDED_ALLOW_IPS`)                               |

The CI/CD pipeline uses `sed` to hydrate these values before rendering the final
task definition and deploying to ECS.

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
