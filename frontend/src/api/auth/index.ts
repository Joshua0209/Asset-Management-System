// Public surface of the auth API domain.
// State management (session persistence + React context) lives in src/auth/.

export * from "./types";
export { AUTH_PATHS } from "./keys";
export { fetchMe, login, register } from "./queries";
