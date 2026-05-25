// Unit tests for createAmountValidator — the shared async Form.Item rule used
// by purchase-amount and repair-cost inputs across Asset / RepairRequest modals.
// We pass a fake `t` so assertions can match raw i18n keys rather than localized
// strings.

import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { createAmountValidator } from "@/utils/validators";

// i18next's TFunction is a heavily overloaded type (it's a callable + an
// indexed-access type for namespaces) that cannot be expressed as a simple
// (key: string) => string. For these tests we only need the key-echo
// behavior so assertions can match raw i18n keys instead of localized
// strings — the double cast keeps the stub minimal without disabling
// strict typing across the file.
const t = ((key: string) => key) as unknown as TFunction;

describe("createAmountValidator", () => {
  it("resolves on an empty value when not required", async () => {
    const validate = createAmountValidator(t);
    await expect(validate(null, "")).resolves.toBeUndefined();
    await expect(validate(null)).resolves.toBeUndefined();
    await expect(validate(null, "   ")).resolves.toBeUndefined();
  });

  it("throws validation.required on empty value when required is true", async () => {
    const validate = createAmountValidator(t, { required: true });
    await expect(validate(null, "")).rejects.toThrow("validation.required");
    await expect(validate(null)).rejects.toThrow("validation.required");
    await expect(validate(null, "   ")).rejects.toThrow("validation.required");
  });

  it("rejects values that do not match the decimal pattern with the format key", async () => {
    const validate = createAmountValidator(t);
    await expect(validate(null, "abc")).rejects.toThrow("validation.purchaseAmountFormat");
    await expect(validate(null, "1.234")).rejects.toThrow("validation.purchaseAmountFormat");
    await expect(validate(null, "-5")).rejects.toThrow("validation.purchaseAmountFormat");
    await expect(validate(null, "1,000")).rejects.toThrow("validation.purchaseAmountFormat");
  });

  it("rejects zero and zero-equivalent values with the positive key", async () => {
    const validate = createAmountValidator(t);
    await expect(validate(null, "0")).rejects.toThrow("validation.purchaseAmountPositive");
    await expect(validate(null, "0.00")).rejects.toThrow("validation.purchaseAmountPositive");
  });

  it("rejects amounts whose significant-digit count exceeds MAX_DIGITS", async () => {
    const validate = createAmountValidator(t);
    // 16 significant digits before the decimal — exceeds the 15-digit cap.
    await expect(validate(null, "1234567890123456")).rejects.toThrow(
      "validation.purchaseAmountFormat",
    );
    // Leading zeros are stripped before counting — 16 significant digits still fails.
    await expect(validate(null, "00001234567890123456")).rejects.toThrow(
      "validation.purchaseAmountFormat",
    );
  });

  it("accepts well-formed positive amounts", async () => {
    const validate = createAmountValidator(t, { required: true });
    await expect(validate(null, "1")).resolves.toBeUndefined();
    await expect(validate(null, "1.5")).resolves.toBeUndefined();
    await expect(validate(null, "12345.67")).resolves.toBeUndefined();
    // Exactly 15 significant digits — boundary case.
    await expect(validate(null, "123456789012345")).resolves.toBeUndefined();
  });

  it("uses the custom formatKey / positiveKey when provided", async () => {
    const validate = createAmountValidator(t, {
      formatKey: "validation.repairCostFormat",
      positiveKey: "validation.repairCostPositive",
    });
    await expect(validate(null, "abc")).rejects.toThrow("validation.repairCostFormat");
    await expect(validate(null, "0")).rejects.toThrow("validation.repairCostPositive");
  });

  it("accepts numeric input (not just strings)", async () => {
    const validate = createAmountValidator(t);
    await expect(validate(null, 1.5)).resolves.toBeUndefined();
    await expect(validate(null, 0)).rejects.toThrow("validation.purchaseAmountPositive");
  });
});
