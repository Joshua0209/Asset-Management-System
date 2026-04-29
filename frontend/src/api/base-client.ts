// Shared HTTP client for the AMS REST API.
//
// Per docs/system-design/12-api-design.md:
//   - Base URL: /api/v1
//   - Bearer-token auth in `Authorization` header
//   - Error envelope: { error: { code, message, details? } }
//
// Auth + 401 handling
//   - Request interceptor reads the current token from auth/storage on every
//     request, so callers don't have to thread it through.
//   - Response interceptor catches 401 on requests that *had* a token attached
//     (i.e. session expired mid-flight) and clears the session + dispatches
//     UNAUTHORIZED_EVENT so AuthContext can react. Login/register 401s are
//     untouched because those calls have no token.

import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";
import { UNAUTHORIZED_EVENT, clearSession, getToken } from "../auth/storage";

export const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");

export interface ErrorDetail {
  field: string;
  message: string;
  code: string;
}

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

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: ErrorDetail[];
  };
}

function fromAxiosError(error: AxiosError<ErrorEnvelope>): ApiError {
  const status = error.response?.status ?? 0;
  const envelope = error.response?.data?.error;
  const code = envelope?.code ?? (status === 0 ? "network_error" : "error");
  const message =
    envelope?.message ??
    error.message ??
    (status === 0 ? "Network error" : "Request failed");
  return new ApiError(status, code, message, envelope?.details ?? []);
}

export function createApiClient(baseURL: string = API_BASE): AxiosInstance {
  const client = axios.create({
    baseURL,
    headers: { "Content-Type": "application/json" },
  });

  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getToken();
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError<ErrorEnvelope>) => {
      const hadAuth = Boolean(error.config?.headers?.get?.("Authorization"));
      if (error.response?.status === 401 && hadAuth) {
        clearSession();
        window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
      }
      return Promise.reject(error);
    },
  );

  return client;
}

export const apiClient = createApiClient();

/**
 * Thin wrapper around an AxiosInstance that:
 *   - Returns the response body directly (`data`)
 *   - Normalizes axios errors into `ApiError` so callers only catch one shape
 */
export async function request<T>(
  config: AxiosRequestConfig,
  client: AxiosInstance = apiClient,
): Promise<T> {
  try {
    const response = await client.request<T>(config);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw fromAxiosError(error as AxiosError<ErrorEnvelope>);
    }
    throw error;
  }
}
