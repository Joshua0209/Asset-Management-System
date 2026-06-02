# Backend Test Strategy

This file is the single source of truth for **what we test, why, and how**. If
you can't answer "what regression does this assertion catch?", revisit this
page; the categories below should give you the vocabulary.

- **Where it lives:** `backend/tests/*.py` — flat, one file per topic.
- **What it runs against:** FastAPI `TestClient` + SQLite `:memory:` (via
  `StaticPool`). DB is dropped and recreated around every test by the
  `autouse` fixture `db_tables` in [conftest.py](conftest.py).
- **What it covers today:** 850 tests, ~96% line coverage. `pytest -n auto` (pytest-xdist) runs the full suite in ~30 s.

## The 6 categories every integration test falls into

Every test below is here for **one** of these reasons. When you write a new
test, pick a category first, then write the assertion — that order keeps you
from writing "vibes-based" tests that pass but don't prove anything.

### 1. Happy path — does the main flow actually work?

The thing must work for the typical input from the right user, persist
correctly, and return the expected response shape. One test per endpoint
minimum; one test per multi-step flow (= "journey test").

| Where to look | Why this example |
|---|---|
| `test_assets.py::TestRegisterAsset::test_registers_asset` | One endpoint, one transition |
| `test_repair_lifecycle_journey.py::test_submit_approve_complete_happy_path` | Full FSM walk over HTTP — the demo path |
| `test_asset_lifecycle_journey.py::test_register_assign_unassign_dispose_full_lifecycle` | Asset cradle-to-grave |

### 2. Negative input — does bad data get the right error envelope?

422 with field-level messages for validation failures, 4xx with our
`{"error": {"code", "message"}}` envelope for everything else. *Never*
the raw FastAPI `{"detail": ...}` shape.

| Where to look | What's wrong with the input |
|---|---|
| `test_repair_requests.py::TestRepairWorkflowValidation::test_repair_details_rejects_negative_cost` | Business-rule validation |
| `test_assets.py::TestAssetCreateSchema::test_future_purchase_date_raises_validation_error` | Pydantic-level validation |
| `test_repair_requests.py::TestSubmitRepairRequest::test_json_validation_error_uses_project_error_envelope` | Envelope shape itself |

### 3. Authorization — does RBAC hold across every endpoint?

- Anonymous → 401 with our envelope.
- Wrong role → 403 with our envelope.
- Right role → 200/201 + can only see/edit own resources where scoped.

| Where to look | Boundary it tests |
|---|---|
| `test_auth_deps.py` | The RBAC dependency itself (401/403 matrix) |
| `test_repair_requests.py::TestRepairWorkflowRBAC` | Domain-level role checks |
| `test_repair_requests.py::TestListRepairRequests::test_holder_cannot_filter_to_another_requester` | Scoping: holder can only see own |
| `test_repair_lifecycle_journey.py::test_holder_cannot_short_circuit_manager_steps_with_own_token` | RBAC across multiple steps in one journey (approve / reject / complete all 403 for holder) |
| `test_repair_lifecycle_journey.py::test_holder_cannot_submit_repair_for_someone_elses_asset` | Cross-holder scoping on submit — only this test covers the 403 path |
| `test_auth_to_action_journey.py::test_register_silently_ignores_client_supplied_role` | Decision A2: client-supplied `role` must be silently dropped (anti-self-elevation) |

### 4. State machine — are invalid transitions blocked?

For every FSM transition documented in `docs/system-design/11-asset-fsm.md`,
there should be:

- a test that the legal transition works (covered by category 1), and
- at least one test that an illegal entry state returns 409.

| Where to look | FSM rule being defended |
|---|---|
| `test_repair_requests.py::TestRepairWorkflowFSMGuards::test_approve_rejects_request_already_under_repair` | Can't double-approve |
| `test_assets.py::TestAssetTransition409ErrorCodes` | Per-transition 409 catalogue |
| `test_asset_lifecycle_journey.py::test_active_repair_blocks_unassign_until_completed` | Cross-resource FSM guard (journey form) |
| `test_asset_lifecycle_journey.py::test_rejected_repair_does_not_block_unassign` | Counter-test: only *active* repairs block; terminal ones don't |

### 5. Concurrency — does optimistic locking actually protect us?

Every mutable table has a `version` column. Tests must prove the API
rejects writes that carry a stale token, AND that the rejected write left
no side effects.

| Where to look | The race it represents |
|---|---|
| `test_repair_requests.py::TestRepairWorkflowStaleVersion::test_approve_returns_conflict_on_stale_version` | Single client, stale token |
| `test_repair_lifecycle_journey.py::test_concurrent_managers_only_one_approval_wins` | Two managers race on the same request — only one's reviewer_id ends up persisted |

### 6. Atomicity + 409 cleanliness — do failed writes leave zero footprints?

When a transaction fails mid-flight (DB error, FSM guard, stale version),
**no row may be half-updated**. This is the category where bugs are most
expensive in production and hardest to spot in code review.

| Where to look | The leak it prevents |
|---|---|
| `test_repair_requests.py::TestRepairWorkflowAtomicity::test_approve_rolls_back_both_rows_on_commit_failure` | DB error mid-update doesn't leave asset out of sync |
| `test_asset_lifecycle_journey.py::test_active_repair_blocks_unassign_until_completed` | After 409, the asset's row is unchanged (status, owner, version) |
| `test_repair_requests.py::TestSubmitRepairRequest::test_returns_503_when_storage_backend_save_fails` | Image upload fails → no orphan DB row, no orphan file |

## "Journey tests" — a *shape*, not a category

Files ending `_lifecycle_journey.py` / `_to_action_journey.py` chain
multiple HTTP calls and thread the response from one into the next
(captured ids, advanced versions). Each one still belongs to one of the 6
categories above — they're just **larger** integration tests that prove
the *sequencing* between transitions is coherent, not just each transition
in isolation.

Why bother writing them when categories 1–6 already cover the parts?
Because line coverage cannot see chain-level bugs:

- "approve returns the wrong version field, breaking /complete" — line
  coverage still hits 100% on approve.
- "complete works in isolation but corrupts responsible_person_id when
  it runs right after approve" — single-step tests can't see this.
- "two managers approving the same request simultaneously" — needs two
  sequential HTTP calls in one test to demonstrate.

## How to write a new integration test (checklist)

1. **Pick a category** from §1–§6. If you can't, the test probably isn't
   integration — it's a unit test or it's a vibe.
2. **Name it after the behaviour, not the function**: `test_holder_cannot_approve_own_request`,
   not `test_approve_403`.
3. **Arrange / Act / Assert** — three visual blocks, no comment markers
   needed. Setup, the request under test, then assertions.
4. Use the existing fixtures from [conftest.py](conftest.py):
   `client`, `db_session`, `make_user`, `auth_headers`.
5. **Assert response + DB state**. Response only proves "the API said so";
   `db_session.refresh(...)` (or `db_session.get(...)`) proves the row
   actually changed. Bugs love the gap between these two.
6. **For 4xx tests, verify the DB did NOT change**. "Returned 409" and
   "didn't write" are two separate claims — assert both.
7. **For multi-step tests, thread the response forward**. Capture the
   returned `version` from one call, pass it to the next. Never read it
   from the DB — that hides the bug where the response had the wrong
   version but the row was right.

## Adversarial review (run this on every new test before pushing)

Stolen from Joshua's PR comments, with permission:

1. **Time coupling** — any hardcoded date close to today? Will it still
   prove what it claims a year from now?
2. **Mock blast radius** — every `patch` / `mock` scoped as tight as
   possible? Module-globals are last resort.
3. **Operational value** — for each assertion, name the production bug
   it catches. Can't name one → delete it.
4. **Log assertion gotchas** — using `caplog`? Did you `set_level()`?
5. **Three "false-pass" regressions** — list three bugs that would let
   production break but this test still go green. Then add assertions
   to close each one. (Best forcing function in this rubric.)
6. **Cross-file duplication** — if the same setup appears in ≥2 files,
   extract to `conftest.py` or a shared helper. Within one file is fine.
7. **Weird casts / hacks** — comment them, or your future self will
   "tidy" them into a bug.

## Running

```bash
.venv/bin/pytest                              # full suite
.venv/bin/pytest tests/test_<topic>.py        # one file
.venv/bin/pytest --cov=app --cov-report=term  # with coverage
.venv/bin/pytest -n auto                      # parallel (pytest-xdist)
.venv/bin/pytest -k "journey"                 # all journey tests
```

## Out of scope (don't try to fit here)

- **Frontend integration tests.** The frontend has no in-memory boundary
  equivalent to SQLite — its real boundary is the network. The component
  tests under `frontend/src/__tests__/` mock at the api-client layer
  (correct for component tests); true frontend↔backend integration is
  the job of Playwright E2E in Week 6.
- **Real MySQL behaviour.** SQLite trades fidelity for speed. MySQL-only
  bugs (collation, true row locking, `ON UPDATE CURRENT_TIMESTAMP`) need
  to surface in the staging deploy or in the Week 6 E2E layer against
  a real MySQL container.
- **Performance / load.** Out of scope for this layer. k6 in Week 6.
