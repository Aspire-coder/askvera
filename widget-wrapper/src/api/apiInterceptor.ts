import type { RequestMetadata } from "./envelope";

export type ApiRequestContext = {
  baseUrl: string;
  path: string;
  init: RequestInit;
  metadata?: RequestMetadata;
};

export type ApiInterceptor = {
  beforeRequest?: (context: ApiRequestContext) => ApiRequestContext | Promise<ApiRequestContext>;
  afterResponse?: (response: Response, context: ApiRequestContext) => Response | Promise<Response>;
};

export const noopApiInterceptor: ApiInterceptor = {};
