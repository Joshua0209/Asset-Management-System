# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository is a **course homework project** for a cloud computing / software engineering class. The ultimate goal is to design and implement an **Asset Management System (資產管理系統)** as defined in `docs/requirements.md`.

## Codebase Structure

```
docs/                          # Project documentation hub
  requirements.md              # System requirements — source of truth for the domain
  roadmap.md                   # Implementation roadmap (5-person team, Apr 14 – Jun 2, FastAPI + React/Vite)
  system-design/               # Full design document set (read in numbered order)
    README.md                  # Index of all design documents
    00-user-study.md           # Raw user research notes
    01-user-story.md           # User stories and acceptance criteria
    02-requirements.md         # Functional & non-functional requirements
    03-usage-estimates.md      # QPS, storage, and machine count estimates
    04-phase1-architecture.md  # Pilot: monolith on single EC2 (~$34/mo)
    05-phase2-architecture.md  # Growth: ALB + 2 nodes + RDS Multi-AZ (~$200/mo)
    06-phase3-architecture.md  # SaaS: EKS + SOA + Redis + Elasticsearch (reference)
    07-database-design.md      # ER diagram, schema, optimistic locking, indexes
    08-deployment-operations.md# Zero-downtime deploy, monitoring, backup & recovery
    09-testing-strategy.md     # Test pyramid, coverage targets, load/chaos testing
    10-design-decisions.md     # Resolved team decisions on stack and scope
    11-asset-fsm.md            # Asset finite state machine — states and transitions
    12-api-design.md           # REST API contract — endpoints, RBAC, error codes
    13-design-tokens.md        # UI design tokens — colors, typography, spacing, motion
    14-sequence-diagrams.md    # Sequence diagrams — repair lifecycle, optimistic locking conflict
```

## Domain

**Two target users:**
- **資產持有者 (Asset Holder)** — submits repair requests, queries own assets and request status
- **資產管理人員 (Asset Manager)** — handles procurement, registration, assignment, repair approval, completion

**Core modules:**
1. Asset basic info management (registration, classification, procurement, status tracking)
2. Request management (repair application → review → in-repair → completion workflow)
