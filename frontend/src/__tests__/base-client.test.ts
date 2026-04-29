import { afterEach, describe, expect, it, vi } from "vitest";
import { AxiosError, AxiosHeaders, type AxiosInstance, type AxiosResponse } from "axios";
import { ApiError, createApiClient, request } from "../api/base-client";
import { UNAUTHORIZED_EVENT, saveSession } from "../auth/storage";
import type { AuthSession } from "../api/auth";

function fakeClient() {
  const requestFn = vi.fn();
  return { client: { request: requestFn } as unknown as AxiosInstance, requestFn };
}

function axiosErrorWith(
  status: number,
  data: unknown,
  hadAuthHeader = false,
): AxiosError {
  const headers = new AxiosHeaders();
  if (hadAuthHeader) headers.set("Authorization", "Bearer x");
  const config = { headers, url: "/x", method: "get" };
  const response = { status, data, headers: {}, config, statusText: "" } as AxiosResponse;
  return new AxiosError("axios failure", "ERR", config, undefined, response);
}

const validSession = (): AuthSession => ({
  token: "t-1",
  expiresAt: new Date(Date.now() + 60_000).toISOString(),
  user: { id: "u", email: "a@b.c", name: "A", role: "holder" },
});

describe("ApiError", () => {
  it("captures status, code, message, and details", () => {
    const err = new ApiError(422, "validation_error", "Bad input", [
      { field: "email", message: "invalid", code: "format" },
    ]);
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(422);
    expect(err.code).toBe("validation_error");
    expect(err.message).toBe("Bad input");
    expect(err.details).toHaveLength(1);
  });

  it("defaults details to an empty array", () => {
    expect(new ApiError(500, "x", "y").details).toEqual([]);
  });
});

describe("request<T>", () => {
  it("returns response.data on success", async () => {
    const { client, requestFn } = fakeClient();
    requestFn.mockResolvedValueOnce({ data: { hello: "world" } });
    await expect(request({ method: "GET", url: "/x" }, client)).resolves.toEqual({
      hello: "world",
    });
  });

  it("normalizes a 4xx axios error into ApiError using the error envelope", async () => {
    const { client, requestFn } = fakeClient();
    requestFn.mockRejectedValueOnce(
      axiosErrorWith(422, {
        error: {
          code: "validation_error",
          message: "Bad input",
          details: [{ field: "email", message: "invalid", code: "format" }],
        },
      }),
    );
    await expect(request({ method: "POST", url: "/x" }, client)).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      code: "validation_error",
      message: "Bad input",
      details: [{ field: "email" }],
    });
  });

  it("falls back to generic code/message when the envelope is missing", async () => {
    const { client, requestFn } = fakeClient();
    requestFn.mockRejectedValueOnce(axiosErrorWith(500, undefined));
    const error = await request({ method: "GET", url: "/x" }, client).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
    expect((error as ApiError).code).toBe("error");
  });

  it("rethrows non-axios errors unchanged", async () => {
    const { client, requestFn } = fakeClient();
    const boom = new Error("boom");
    requestFn.mockRejectedValueOnce(boom);
    await expect(request({ method: "GET", url: "/x" }, client)).rejects.toBe(boom);
  });
});

describe("createApiClient interceptors", () => {
  afterEach(() => {
    globalThis.localStorage.clear();
  });

  it("attaches Bearer token from storage on outbound requests", async () => {
    saveSession(validSession());
    const client = createApiClient("http://test.local");
    const seen: { auth?: string } = {};
    client.defaults.adapter = async (config) => {
      seen.auth = config.headers?.get("Authorization") as string | undefined;
      return {
        data: {},
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    await client.get("/x");
    expect(seen.auth).toBe("Bearer t-1");
  });

  it("dispatches UNAUTHORIZED_EVENT when an authenticated request returns 401", async () => {
    saveSession(validSession());
    const client = createApiClient("http://test.local");
    client.defaults.adapter = async () => {
      throw axiosErrorWith(401, { error: { code: "unauthorized" } }, true);
    };

    const handler = vi.fn();
    globalThis.addEventListener(UNAUTHORIZED_EVENT, handler);
    await client.get("/x").catch(() => undefined);
    globalThis.removeEventListener(UNAUTHORIZED_EVENT, handler);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(globalThis.localStorage.getItem("ams-auth")).toBeNull();
  });

  it("does NOT dispatch UNAUTHORIZED_EVENT for 401 on a request without a token (e.g. login)", async () => {
    // No saveSession — request goes out with no Authorization header.
    const client = createApiClient("http://test.local");
    client.defaults.adapter = async () => {
      throw axiosErrorWith(401, { error: { code: "unauthorized" } }, false);
    };

    const handler = vi.fn();
    globalThis.addEventListener(UNAUTHORIZED_EVENT, handler);
    await client.post("/auth/login").catch(() => undefined);
    globalThis.removeEventListener(UNAUTHORIZED_EVENT, handler);

    expect(handler).not.toHaveBeenCalled();
  });
});
