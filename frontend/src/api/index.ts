// Top-level barrel for the API layer. Subdomains live in sibling folders
// (./auth, ./assets, ./repair-requests…) and follow the same shape:
//   - types.ts    request/response types
//   - keys.ts     endpoint paths / cache keys
//   - queries.ts  pure fetch functions
//   - index.ts    barrel re-exports
// New domains should add a folder here, then re-export below.

export { API_BASE, ApiError, apiClient, createApiClient, request } from "./base-client";
export type { ErrorDetail } from "./base-client";

export * as authApi from "./auth";
export * as assetsApi from "./assets";
export * as usersApi from "./users";
export * as repairRequestsApi from "./repair-requests";
