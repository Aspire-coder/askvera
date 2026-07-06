export class ApiRequestError extends Error {
  code?: string;
  legalVersion?: string;
  status?: number;
  correlationId?: string;

  constructor(message: string, code?: string, legalVersion?: string, status?: number, correlationId?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.legalVersion = legalVersion;
    this.status = status;
    this.correlationId = correlationId;
  }
}

export class ApiTimeoutError extends Error {
  constructor(message = "The request timed out. Please try again.") {
    super(message);
    this.name = "ApiTimeoutError";
  }
}

export class ApiNetworkError extends Error {
  constructor(message = "The API could not be reached. Please check the connection and try again.") {
    super(message);
    this.name = "ApiNetworkError";
  }
}

export class ApiValidationError extends Error {
  constructor(message = "The API request is invalid.") {
    super(message);
    this.name = "ApiValidationError";
  }
}

export class ApiUnauthorizedError extends Error {
  code?: string;
  status?: number;
  correlationId?: string;

  constructor(message = "The API request is not authorized.", code?: string, status?: number, correlationId?: string) {
    super(message);
    this.name = "ApiUnauthorizedError";
    this.code = code;
    this.status = status;
    this.correlationId = correlationId;
  }
}

export class BackendUnavailableError extends Error {
  constructor(message = "The backend is unavailable.") {
    super(message);
    this.name = "BackendUnavailableError";
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiTimeoutError) {
    return "The request timed out. Please try again in a moment.";
  }
  if (error instanceof ApiNetworkError) {
    return `The API could not be reached: ${error.message}`;
  }
  if (error instanceof ApiUnauthorizedError) {
    return error.message;
  }
  if (error instanceof BackendUnavailableError) {
    return error.message;
  }
  if (error instanceof ApiRequestError) {
    const status = error.status ? `HTTP ${error.status}` : "API error";
    return `${status}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected API error occurred.";
}
