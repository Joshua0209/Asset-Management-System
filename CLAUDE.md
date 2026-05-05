# CLAUDE.md

Guidance for Claude Code when working in this repository. README.md is the human-facing overview (progress, quick start, scripts); this file captures orientation and conventions that are not obvious from the code.

## Project nature

Course homework for a cloud computing / software engineering class. The target is an **Asset Management System (資產管理系統)**; the domain source of truth is `docs/requirements.md` (Traditional Chinese — the UI is bilingual zh-TW / en).

## Source-of-truth map

When a question can be answered from one of these, read it before guessing:

| Question | Authoritative file |
|----------|-------------------|
| What does the system do? | `docs/requirements.md` |
| Team, timeline, scope per week | `docs/roadmap.md` |
| Architecture per growth phase | `docs/system-design/04-…` → `06-…` |
| DB schema, indexes, locking | `docs/system-design/07-database-design.md` |
| REST contract + RBAC + error codes | `docs/system-design/12-api-design.md` |
| Asset state machine | `docs/system-design/11-asset-fsm.md` |
| Design system (colors, typography, spacing, motion) | `docs/designs/DESIGN.md` + `docs/designs/design-tokens.json` |
| Resolved team decisions | `docs/system-design/10-design-decisions.md` |

The full index is `docs/system-design/README.md`; docs are numbered and meant to be read in order.

## Domain quick-reference

Two roles:
- **資產持有者** (Asset Holder) — submits repair requests, queries own assets/requests
- **資產管理人員** (Asset Manager) — procurement, registration, assignment, repair review/completion

Core modules: asset basic-info management, and the repair request workflow (apply → review → in-repair → complete). Transitions must match `11-asset-fsm.md`.

## Stack conventions

- **Backend**: FastAPI + SQLAlchemy + Alembic + MySQL 8. Mutable tables carry a `version` column — use **optimistic locking**, not `SELECT … FOR UPDATE`, for concurrent writes.
- **Frontend**: React 18 + Vite + TypeScript strict + React Router v6. i18n is `react-i18next` with a browser language detector; locale files live in `frontend/src/i18n/locales/`. Any new user-visible string must have zh-TW + en entries.
- **UI library: Ant Design v6** (`antd` + `@ant-design/icons`). Dark/light mode via `ConfigProvider`. TSMC visual direction (palette, typography, spacing) is defined in `docs/designs/DESIGN.md` — follow those constraints when building components on top of Ant Design defaults.

## Local dev environment (docker compose)

`docker-compose.yml` runs the full dev stack — `mysql` + `backend` + `frontend` — and is the recommended local workflow (README "Option A"). Conventions worth knowing before touching it:

- **Both app images are dev-only.** Backend uses `pip install -e '.[dev]'` then `uvicorn --reload`; frontend uses `npm ci --ignore-scripts` then `vite --host`. There is no `Dockerfile.prod` yet — production ECS images per `docs/system-design/05-phase2-architecture.md` will get separate multi-stage Dockerfiles when Phase 2 deployment lands. Don't preemptively add prod stages to the dev images; keep them lean and reload-friendly.
- **Bind mount + editable install** is what makes hot-reload work. The image installs the package so the `.pth` lives in site-packages, then compose mounts `./backend` over `/app` at runtime. Source edits flow through; dependency edits (`pyproject.toml`, `package.json`) need `docker compose build <service>`.
- **Frontend `node_modules`** is preserved by an anonymous volume on `/app/node_modules`. If you ever change the bind-mount layout, keep that volume — without it the host bind mount will mask the image's installed deps and the container will fail to start.
- **Backend command runs migrations only — never the seed.** `scripts/seed_demo_data.py` is destructive (wipes all four tables before re-seeding) and gated behind `AMS_SEED_CONFIRM=1`, so it must stay a one-shot: `docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py`. The "idempotent bootstrap manager" note under "Auth conventions" describes the *upsert inside the seed*, not the seed itself.
- **Frontend's `prepare` script** is a `git config core.hooksPath` shim that fails inside the container (no git repo). The Dockerfile uses `npm ci --ignore-scripts` to skip it. If you add a real `prepare` step that the container needs, you'll have to find another way.
- **`/app/uploads`** is a named volume (`backend_uploads`) so repair-image uploads survive `docker compose down`. They are wiped by `docker compose down -v`.

## CI + tooling gotchas

- GitHub Actions are **pinned to commit SHAs** with a `# vX` comment. If you add an action, fetch the real SHA via `gh api repos/<owner>/<repo>/git/refs/tags/<tag>` — don't invent one. A previous bug used a non-existent SHA and blocked the reviewer-assign workflow.
- Reviewer assignment is **workflow-based**, not CODEOWNERS. See `.github/workflows/assign-reviewers.yml`. `CODEOWNERS` only covers `/.github/`.
- SonarQube runs against **SonarCloud**; the host URL is hardcoded in the workflow. Only `SONAR_TOKEN` is required as a secret.
- CI has five jobs: `backend`, `frontend`, `secrets` (gitleaks), `sast` (Semgrep OWASP top-10), `sonarqube`. A red `sast` or `secrets` job usually means a real issue — do not bypass.
- `mypy` runs in `--strict` mode; `tsc` runs with TypeScript strict. Don't loosen either to make errors go away.
- Local pre-commit is configured (gitleaks + ruff + hygiene). Never commit with `--no-verify` unless the user explicitly asks.

## Auth conventions (Week 2+)

Non-obvious patterns established in the Week 2 Auth API — read before touching auth or adding new protected endpoints:

- **RBAC deps** live in `backend/app/api/deps.py`. Three `Annotated` aliases — `CurrentUser`, `ManagerUser`, `HolderUser` — compose `get_current_user` with an optional role check. Use these in route signatures; don't inline JWT decoding.
- **Password policy** is enforced by `validate_password_policy` in `app/core/security.py` (≥8 chars, ≥1 letter, ≥1 digit). Reuse this function everywhere a password is accepted — don't duplicate the rule.
- **Anti-enumeration**: `POST /auth/login` returns an identical 401 body whether the email is unknown or the password is wrong. When the user doesn't exist the endpoint still runs `bcrypt.verify` against a dummy hash to prevent timing-based user discovery.
- **Bootstrap manager**: `scripts/seed_demo_data.py` always idempotently upserts a manager from `BOOTSTRAP_MANAGER_*` env vars. This is the only way to get the first manager into a fresh database — `POST /auth/register` always creates holders.
- **Error envelope**: all 4xx/5xx responses use `{"error": {"code": "...", "message": "..."}}` via a global `HTTPException` handler in `app/main.py`. Don't return raw `{"detail": ...}` FastAPI defaults.

## Image storage conventions (Week 3+)

Repair-request images are persisted via a small abstraction in `app/services/image_storage.py`:

- **`ImageStorage` Protocol** — narrow interface (`save`, `open`, `cleanup`) so a future S3 backend drops in without touching call sites.
- **`LocalImageStorage`** — current concrete impl, rooted at `REPAIR_UPLOAD_DIR` (default `uploads/repair-requests/`, git-ignored).
- **`repair_images.image_url`** stores a **backend storage key** (`"<rr-id>/<img-id>.<ext>"`), NOT a public URL. The public URL `/api/v1/images/<id>` is computed in `RepairImageRead.url` (a Pydantic `computed_field`). When migrating to S3 in Week 5, write a new storage impl, swap `get_image_storage()`, and no DB rows need to be rewritten.
- The `POST /repair-requests` endpoint owns the multipart parsing inline; the storage service only handles bytes-in / bytes-out plus rollback. If a DB flush fails after files are written, the endpoint's `finally` block calls `storage.cleanup(saved_keys)` to avoid orphans.

## Working preferences

- Prefer editing existing files over adding new ones; this is an early-stage project and file sprawl is not wanted.
- When a task changes behavior described in `docs/system-design/`, update the relevant design doc in the same change.
- Do not duplicate the README's progress tables here — keep this file focused on orientation and conventions.
