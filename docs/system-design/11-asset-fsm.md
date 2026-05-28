# Asset Finite State Machine

## State Diagram

```mermaid
stateDiagram-v2
    [*] --> In_Stock : [Manager]Register Asset

    In_Stock --> In_Use       : [Manager]Assign to Holder
    In_Stock --> Disposed     : [Manager]Scrap Asset
    Disposed --> [*]

    In_Use --> Pending_Repair  : [Holder]Submit Repair Request
    In_Use --> In_Stock        : [Manager]Unassign / Reclaim

    Pending_Repair --> Under_Repair : [Manager]Approve Repair Request
    Pending_Repair --> In_Use       : [Manager]Reject Repair Request
    Under_Repair --> In_Use    : [Manager]Repair Completed
```

## State Transition Table

| # | Current State | Valid Action / Trigger | Next State | Validation Rules |
|---|--------------|----------------------|------------|-----------------|
| T1 | — (new) | **Register Asset** *(Manager)* | `In_Stock` | Required fields present (name, model, category, supplier, purchase date, amount). `responsible_person_id` must be NULL. Asset code auto-generated. |
| T2 | `In_Stock` | **Assign to Holder** *(Manager)* | `In_Use` | Target user exists and has role `holder`. `responsible_person_id` is currently NULL. |
| T3 | `In_Stock` | **Scrap Asset** *(Manager)* | `Disposed` | No active repair requests linked. `responsible_person_id` is NULL. Disposal reason provided. |
| T4 | `In_Use` | **Submit Repair Request** *(Holder)* | `Pending_Repair` | Asset has no existing `pending_review` or `under_repair` repair request (no duplicates). Fault description and asset code required. |
| T5 | `In_Use` | **Unassign / Reclaim** *(Manager)* | `In_Stock` | No active repair requests (`pending_review` or `under_repair`). Reason provided. `responsible_person_id` cleared. |
| T6 | `Pending_Repair` | **Approve Repair Request** *(Manager)* | `Under_Repair` | Repair request exists in `pending_review` status. Asset and repair request updated atomically in one transaction. |
| T7 | `Pending_Repair` | **Reject Repair Request** *(Manager)* | `In_Use` | Rejection reason provided. Repair request marked `rejected` atomically. Asset returns to normal use. |
| T8 | `Under_Repair` | **Repair Completed** *(Manager)* | `In_Use` | Repair details filled (date, fault, plan, cost, vendor). Repair request marked `completed` atomically. `responsible_person_id` unchanged. |

**Forbidden transitions** (rejected at service layer): `Pending_Repair → In_Stock`, `Under_Repair → In_Stock`, `In_Stock → Pending_Repair`, `Disposed → *` (any), self-transitions.

### Department / location invariant (issue #97)

`assets.department` (owning department) is mutated only by:

1. **T1 — Register Asset.** Initial values supplied by the manager.
2. **`PATCH /assets/{id}` — Edit Asset.** Manager updates explicitly (e.g. cost-center transfer).

`assets.location` (registered physical location) is mutated by:

1. **T1 — Register Asset.** Initial value supplied by the manager.
2. **`PATCH /assets/{id}` — Edit Asset.** Manager updates explicitly (e.g. physical relocation).
3. **T2 — Assign to Holder.** Manager confirms the asset's registered location after hand-off.
4. **T5 — Unassign / Reclaim.** Manager confirms the asset's registered location after reclaim.

No FSM transition derives these fields from the holder. T2/T5 never update `assets.department`, and no transition reads a `holder.location` because `users.location` does not exist. This preserves cost-center continuity for accounting and audit purposes, and decouples the holder's organizational department (`users.department`) from the asset's owning department. See `07-database-design.md` "Department / location semantics" and `10-design-decisions.md` Q21.
