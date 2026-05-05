import type { TFunction } from 'i18next';

import { ApiError } from '../api';

export function getApiErrorMessage(apiError: ApiError, t: TFunction): string {
  switch (apiError.code) {
    case 'unauthorized':
      return t('errors.unauthorized');
    case 'forbidden':
      return t('errors.forbidden');
    case 'not_found':
      return t('errors.notFound');
    case 'conflict':
      return t('errors.conflict');
    case 'duplicate_request':
      return t('errors.duplicateRequest');
    case 'invalid_transition':
      return t('errors.invalidTransition');
    case 'validation_error':
      return t('errors.validationError');
    case 'payload_too_large':
      return t('errors.payloadTooLarge');
    case 'unsupported_media_type':
      return t('errors.unsupportedMediaType');
    case 'rate_limit_exceeded':
      return t('errors.rateLimitExceeded');
    default:
      return apiError.message || t('errors.serverError');
  }
}
