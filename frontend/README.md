# Frontend Implementation Specification

This file is the implementation contract for future frontend changes.

It documents the refactor completed in PR #59 and defines how new features should be added so architecture remains consistent.

## 1. Scope and goals

- Stack: React 18 + Vite + TypeScript strict + React Router v6 + Ant Design v6.
- Translation: `react-i18next` with `zh-TW` and `en` locale files.
- This README is normative for:
  - folder placement
  - routing and role boundaries
  - page decomposition pattern
  - shared constants/utilities usage
  - import style and API module layout

Use MUST/SHOULD in the strict RFC sense.

## 2. Current source layout

```text
src/
├── api/
│   ├── base-client.ts
│   ├── index.ts
│   └── {auth,assets,users,repair-requests}/
│       ├── index.ts
│       ├── keys.ts
│       ├── queries.ts
│       └── types.ts
├── auth/
│   ├── AuthContext.tsx
│   ├── ProtectedRoute.tsx
│   ├── PublicOnlyRoute.tsx
│   ├── RoleLandingRedirect.tsx
│   └── storage.ts
├── components/
│   ├── AuthImage.tsx
│   ├── LanguageSwitcher.tsx
│   ├── layout/MainLayout.tsx
│   ├── assets/
│   └── repair-requests/constants.ts
├── hooks/
│   ├── useAssetList.ts
│   └── useSubmitAction.ts
├── i18n/
│   ├── index.ts
│   └── locales/{en.json,zh-TW.json}
├── pages/
│   ├── auth/{Login.tsx,Register.tsx}
│   ├── holder/
│   ├── manager/
│   │   └── ReviewDetail/
│   ├── AssetDetail/
│   └── Forbidden.tsx
├── utils/{apiErrors.ts,format.ts,validators.ts}
├── App.tsx
└── main.tsx
```

## 3. Route and role boundaries (MUST)

Routes are defined in `src/App.tsx` and are role-segmented:

- Public only:
  - `/auth/login`
  - `/auth/register`
- Shared authenticated:
  - `/` (role landing redirect)
  - `/forbidden`
  - `/assets/:id`
- Holder only:
  - `/my-assets`
  - `/repairs`
  - `/repairs/new`
  - `/repairs/:id`
- Manager only:
  - `/dashboard`
  - `/assets`
  - `/reviews`
  - `/reviews/:id`

Placement rule:

- Holder-only pages MUST live under `src/pages/holder/`.
- Manager-only pages MUST live under `src/pages/manager/`.
- Shared authenticated pages MUST live in `src/pages/` root or a shared subfolder (for example `AssetDetail/`).
- Public auth pages MUST live under `src/pages/auth/`.

When adding/changing routes, update `src/App.tsx` as the source of truth.

## 4. Complex page decomposition pattern (MUST)

For pages with high interaction complexity (multiple actions/modals), use folder decomposition:

```text
pages/SomePage/
├── index.tsx
├── useSomePageActions.ts
└── SomeModal.tsx (one or more)
```

Responsibilities:

- `index.tsx` (container):
  - fetch data
  - own page-level loading/error state
  - own modal open/close state
  - wire submit handlers
- `useSomePageActions.ts`:
  - define domain action callbacks
  - invoke API functions
  - pass through optimistic-lock `version` values unchanged
  - delegate submit boilerplate to `useSubmitAction`
- `*Modal.tsx`:
  - own local `Form` instance
  - run `validateFields()`
  - call `onSubmit(values)` and let parent close on `true`

Do not re-introduce large single-file pages with duplicated try/catch submit logic.

## 5. Submit-action contract (MUST)

`src/hooks/useSubmitAction.ts` is the standard action execution pipeline.

Required behavior for action hooks:

- Track and expose `isSubmitting` from `useSubmitAction`.
- Run API request through `run(...)`.
- On success: reload data and show success notification.
- On API conflict (`code === "conflict"`):
  - show conflict modal
  - keep form modal open
  - reload on conflict modal OK
- Return `Promise<boolean>` and let container decide close behavior.

If adding a new page-level actions hook, reuse this pattern.

## 6. Shared constants and formatting utilities (MUST)

Single source of truth modules:

- Repair status colors: `src/components/repair-requests/constants.ts`
- Asset status colors/constants: `src/components/assets/constants.ts`
- Date and cost formatting: `src/utils/format.ts`
- API error message mapping: `src/utils/apiErrors.ts`

Do not duplicate status-color maps or local date/cost helper variants in page files.

### Existing behavior alignment

Repair request status color mapping is intentionally unified and MUST stay consistent across holder and manager views:

- `pending_review` -> `processing` (blue)
- `under_repair` -> `warning` (yellow)

## 7. API module conventions (MUST)

Each domain under `src/api/` follows the 4-file shape:

- `types.ts`: request/response and domain types
- `keys.ts`: cache/query keys (if needed)
- `queries.ts`: transport-level API functions
- `index.ts`: domain barrel export

`src/api/index.ts` exports shared API symbols for app-level imports.

When adding a new domain, follow the same structure.

## 8. Import conventions (MUST)

Use `@/` alias for cross-folder imports:

- Alias configuration is defined in both:
  - `tsconfig.json` (`compilerOptions.baseUrl` + `paths`)
  - `vite.config.ts` (`resolve.alias`)

Rules:

- Cross-feature imports SHOULD use `@/...`.
- Same-feature close siblings MAY use `../...` when it improves cohesion/readability.
- If alias config changes, update both files in the same commit.

## 9. i18n requirements (MUST)

Any new user-visible text MUST be added to both locale files:

- `src/i18n/locales/en.json`
- `src/i18n/locales/zh-TW.json`

Do not hardcode UI strings in components/pages except temporary debug-only output.

## 10. Testing and quality gates (MUST)

Before opening a PR for frontend changes, run:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Notes:

- Node version is pinned to 22.x (`package.json` + `check:node`).
- TypeScript strict mode is required.
- Vitest reads `vite.config.ts`; alias behavior must work in tests too.

## 11. Feature implementation checklist for LLMs

For any new feature:

1. Place files in role-appropriate folder.
2. Add/update route in `src/App.tsx` with correct guard.
3. If page is complex, create folderized page with `index.tsx + useXxxActions.ts + modal components`.
4. Reuse existing shared helpers (`useSubmitAction`, `utils/format`, `utils/apiErrors`, constants).
5. Keep API payload shape aligned with backend schema; do not add extra fields.
6. Add translations in both locales.
7. Add or update tests in `src/__tests__/`.
8. Run lint/typecheck/tests/build.

## 12. Out-of-scope cleanup candidates (future PRs)

These are known improvements but not part of the refactor contract itself:

- Further split `src/pages/manager/AssetList.tsx` into folderized container/actions/modals.
- Consolidate date helper variants into a dedicated date utility module.
- Consider renaming top-level `src/auth/` if naming overlap with `src/pages/auth/` causes confusion.

---

If this README conflicts with implementation, treat `src/App.tsx` route guards and existing shared hooks/util modules as the primary code truth, then update this document in the same change.
