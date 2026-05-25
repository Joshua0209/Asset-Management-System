import type { ParseKeys, TFunction } from 'i18next';

const AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;
const MAX_DIGITS = 15;

export interface AmountValidatorOptions {
  required?: boolean;
  allowZero?: boolean;
  formatKey?: ParseKeys;
  positiveKey?: ParseKeys;
}

export function createAmountValidator(
  t: TFunction,
  opts: AmountValidatorOptions = {},
) {
  const formatKey: ParseKeys = opts.formatKey ?? 'validation.purchaseAmountFormat';
  const positiveKey: ParseKeys = opts.positiveKey ?? 'validation.purchaseAmountPositive';

  return async (_: unknown, value?: string | number) => {
    const raw = value === undefined || value === null ? '' : String(value).trim();
    if (raw === '') {
      if (opts.required) {
        throw new Error(t('validation.required'));
      }
      return;
    }
    if (!AMOUNT_PATTERN.test(raw)) {
      throw new Error(t(formatKey));
    }
    const numeric = Number.parseFloat(raw);
    const isInvalidAmount = opts.allowZero ? numeric < 0 : numeric <= 0;
    if (!Number.isFinite(numeric) || isInvalidAmount) {
      throw new Error(t(positiveKey));
    }
    const digitCount = raw.replace('.', '').replace(/^0+/, '').length;
    if (digitCount > MAX_DIGITS) {
      throw new Error(t(formatKey));
    }
  };
}
