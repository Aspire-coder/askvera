import type { ApiClient } from "./client";

export type HealthResponseData = {
  status: string;
  [key: string]: unknown;
};

export function healthCheck(client: ApiClient) {
  return client.get<HealthResponseData>("/health");
}

export function deepHealthCheck(client: ApiClient) {
  return client.get<HealthResponseData>("/health/deep");
}
