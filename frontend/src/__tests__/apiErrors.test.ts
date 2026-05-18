import { describe, expect, it } from "vitest";

import { ApiError } from "@/api";
import { getApiErrorMessage } from "@/utils/apiErrors";

const t = ((key: string) => key) as Parameters<typeof getApiErrorMessage>[1];

describe("getApiErrorMessage", () => {
  const codes = [
    "unauthorized",
    "forbidden",
    "not_found",
    "conflict",
    "duplicate_request",
    "invalid_transition",
    "validation_error",
    "payload_too_large",
    "unsupported_media_type",
    "rate_limit_exceeded",
  ];

  it.each(codes)("maps known error code %s to a translation key", (code) => {
    const error = new ApiError(400, code, "ignored");
    expect(getApiErrorMessage(error, t)).toMatch(/^errors\./);
  });

  it("falls back to error.message when code is unknown", () => {
    const error = new ApiError(500, "unknown_code", "boom");
    expect(getApiErrorMessage(error, t)).toBe("boom");
  });

  it("falls back to errors.serverError when message is empty", () => {
    const error = new ApiError(500, "unknown_code", "");
    expect(getApiErrorMessage(error, t)).toBe("errors.serverError");
  });
});
