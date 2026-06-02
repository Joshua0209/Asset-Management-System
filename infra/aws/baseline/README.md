# AWS Infrastructure Baseline (Reference)

This directory contains sanitized exports of the manually provisioned AWS infrastructure for the Asset Management System, captured on **2026-05-20** against the `ap-east-2` (Taipei) region. These files serve as a point-in-time reference for the production environment and can be used to audit configurations or assist in recreating the environment.

## Files

| File | Description |
|------|-------------|
| `alb.json` | Application Load Balancer configuration (Scheme, DNS, SGs). |
| `alb-listeners.json` | HTTPS and HTTP listener rules and default actions. |
| `target-groups.json` | Backend and Frontend target group settings (Health checks, Ports). |
| `rds.json` | RDS MySQL instance configuration (Instance class, Storage, Backups). |
| `ecr.json` | ECR Repository definitions for backend and frontend images. |
| `security-groups.json` | Security Group rules for ALB, App Tasks, and RDS. |
| `ecs-cluster-cfn.json` | CloudFormation template used to bootstrap the ECS Cluster. |
| `iam/` | Exported IAM roles and inline policy documents. |

## Sanitization

All sensitive and account-specific identifiers have been replaced with placeholders:

- `__ACCOUNT_ID__`: 12-digit AWS Account Number.
- `__VPC_ID__`: The primary production VPC.
- `__SG_*_ID__`: Security Group identifiers (including `DEFAULT`, `ALB`, `BACKEND`, `FRONTEND`, `RDS`, `REDIS`).
- `__SUBNET_*__`: Subnet identifiers.
- `__ALB_DNS_NAME__`: The public-facing ALB endpoint.
- `__ALB_RESOURCE_ID__`: The unique resource ID of the ALB.
- `__LISTENER_ID__`: Unique identifier for ALB listeners.
- `__CERTIFICATE_ID__`: Unique identifier for the ACM certificate.
- `__TG_BACKEND_ID__`: Unique identifier for the backend Target Group.
- `__TG_FRONTEND_ID__`: Unique identifier for the frontend Target Group.
- `__RDS_ENDPOINT__`: The private database endpoint.
- `__RDS_MASTER_USERNAME__`: RDS administrator username.
- `__RDS_KMS_KEY_ID__`: KMS key identifier for RDS storage encryption.
- `__ROLE_ID__`: Unique identifier for IAM roles.
- `__TIMESTAMP__`: Generic timestamp placeholder.
- `__REPAIR_S3_BUCKET__`: The S3 bucket for repair image storage.

## Usage

These JSON files are intended for **reference only**. They are not currently linked to an automated IaC tool (like Terraform or CloudFormation). When performing manual updates via the AWS Console or CLI, consult these files to ensure consistency with the established baseline.
