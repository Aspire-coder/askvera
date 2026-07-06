export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

export const ApiErrorCodes = {
  CONSENT_REQUIRED: "CONSENT_REQUIRED",
  INVALID_RESPONSE: "INVALID_RESPONSE",
  NETWORK_ERROR: "NETWORK_ERROR",
  RATE_LIMITED: "RATE_LIMITED",
  WIDGET_AUTH_REQUIRED: "WIDGET_AUTH_REQUIRED"
} as const;

export type ApiErrorCode = (typeof ApiErrorCodes)[keyof typeof ApiErrorCodes];
