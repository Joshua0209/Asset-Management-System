# ECS task definitions

These JSON files are the source of truth for the production ECS task
configuration. The `deploy.yml` workflow renders them with the new image
tag on each push to `main`, then registers the new revision and waits
for the ECS service to reach steady state.

## Placeholders

The committed files have placeholders that must be substituted before the
first real deploy:

| Placeholder        | Where to set it                                     |
|--------------------|-----------------------------------------------------|
| `ACCOUNT_ID`       | Your AWS account number (12 digits)                 |
| `REGION`           | e.g. `ap-northeast-1`                               |
| `PLACEHOLDER_IMAGE`| Replaced at deploy time by `aws-actions/amazon-ecs-render-task-definition` |

The image-tag substitution is automatic. The other two are deliberately
left as placeholders so you commit a real account ID/region exactly once
(after `terraform apply`) instead of relying on every CI run to inject
them.

## Required secrets and variables

Configure under `Settings -> Secrets and variables -> Actions`:

### Repository secrets

| Secret               | Purpose                                                  |
|----------------------|----------------------------------------------------------|
| `AWS_DEPLOY_ROLE_ARN`| OIDC role the workflow assumes (no long-lived keys)      |
| `NVD_API_KEY`        | Optional, raises OWASP Dependency-Check rate limit       |
| `SONAR_TOKEN`        | Already configured for the existing SonarCloud job       |

### Repository variables

| Variable              | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `AWS_REGION`          | e.g. `ap-northeast-1`                            |
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
