// Shared HTTP client for the AMS REST API.
//
// Per docs/system-design/12-api-design.md the backend uses:
//   - Base URL: /api/v1
//   - Bearer-token auth in `Authorization` header
//   - Error envelope: { error: { code, message, details? } }

// VITE_API_BASE_URL is treated as the full API base (prefix included).
// Defaults to the backend's /api/v1 mount on localhost.
export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];

  constructor(status: number, code: string, message: string, details: ErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface ErrorDetail {
  field: string;
  message: string;
  code: string;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: ErrorDetail[];
  };
}

async function readError(response: Response): Promise<ApiError> {
  let code = "error";
  let message = response.statusText || "Request failed";
  let details: ErrorDetail[] = [];
  try {
    const body = (await response.json()) as ErrorEnvelope;
    if (body.error) {
      if (body.error.code) code = body.error.code;
      if (body.error.message) message = body.error.message;
      if (body.error.details) details = body.error.details;
    }
  } catch {
    // body is not JSON; fall back to status text
  }
  return new ApiError(response.status, code, message, details);
}

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  json?: unknown;
  token?: string | null;
}

/**
 * Thin wrapper over fetch that:
 *   - Prefixes API_BASE
 *   - Sets JSON content-type when `json` is provided
 *   - Attaches `Authorization: Bearer <token>` when `token` is provided
 *   - Parses the project error envelope and throws ApiError on non-2xx
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { json, token, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  if (json !== undefined) finalHeaders.set("Content-Type", "application/json");
  if (token) finalHeaders.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
