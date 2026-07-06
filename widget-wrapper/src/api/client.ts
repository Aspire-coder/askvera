import { ApiNetworkError, ApiRequestError, ApiTimeoutError, ApiUnauthorizedError, BackendUnavailableError } from "./errors";
import type { ApiEnvelope, RequestMetadata } from "./envelope";
import { noopApiInterceptor, type ApiInterceptor } from "./apiInterceptor";

export const DEFAULT_REQUEST_TIMEOUT_MS = 30000;

export type ApiClientOptions = {
  baseUrl: string;
  timeoutMs?: number;
  interceptor?: ApiInterceptor;
  authToken?: string | (() => string | undefined);
};

export type ApiClient = {
  get<T>(path: string, metadata?: RequestMetadata): Promise<ApiEnvelope<T>>;
  post<T>(path: string, body: unknown, metadata?: RequestMetadata): Promise<ApiEnvelope<T>>;
};

export const joinUrl = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, "")}${path}`;

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw new ApiNetworkError(error instanceof Error ? error.message : undefined);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  try {
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return {
      success: false,
      correlationId: response.headers.get("x-correlation-id") || "",
      error: { code: "INVALID_RESPONSE", message: "The API returned an unreadable response." }
    };
  }
}

function createErrorFromEnvelope<T>(response: Response, envelope: ApiEnvelope<T>) {
  const correlationId = envelope.correlationId || response.headers.get("x-correlation-id") || undefined;
  const message = envelope.error?.message || `Request failed with status ${response.status}`;
  const code = envelope.error?.code;

  if (response.status === 401 || response.status === 403) {
    if (code === "CONSENT_REQUIRED") {
      return new ApiRequestError(message, code, envelope.error?.legalVersion, response.status, correlationId);
    }
    return new ApiUnauthorizedError(message, code, response.status, correlationId);
  }

  if (response.status >= 500) {
    return new BackendUnavailableError(message);
  }

  return new ApiRequestError(message, code, envelope.error?.legalVersion, response.status, correlationId);
}

export function createApiClient({
  baseUrl,
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  interceptor = noopApiInterceptor,
  authToken
}: ApiClientOptions): ApiClient {
  const request = async <T>(path: string, init: RequestInit, metadata?: RequestMetadata) => {
    const token = typeof authToken === "function" ? authToken() : authToken;
    const headers = {
      ...(metadata?.correlationId ? { "X-Correlation-ID": metadata.correlationId } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(metadata?.headers || {}),
      ...(init.headers || {})
    };
    let context: Parameters<NonNullable<ApiInterceptor["beforeRequest"]>>[0] = {
      baseUrl,
      path,
      init: { ...init, headers },
      metadata
    };
    context = (await interceptor.beforeRequest?.(context)) || context;

    let response = await fetchWithTimeout(joinUrl(context.baseUrl, context.path), context.init, timeoutMs);
    response = (await interceptor.afterResponse?.(response, context)) || response;
    const envelope = await parseEnvelope<T>(response);

    if (!response.ok || !envelope.success) {
      throw createErrorFromEnvelope(response, envelope);
    }

    return envelope;
  };

  return {
    get: <T>(path: string, metadata?: RequestMetadata) => request<T>(path, { method: "GET" }, metadata),
    post: <T>(path: string, body: unknown, metadata?: RequestMetadata) =>
      request<T>(
        path,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        },
        metadata
      )
  };
}
