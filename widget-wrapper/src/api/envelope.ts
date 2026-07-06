export type ApiErrorBody = {
  code: string;
  message: string;
  legalVersion?: string;
};

export type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: ApiErrorBody;
  correlationId: string;
};

export type RequestMetadata = {
  correlationId?: string;
  headers?: Record<string, string>;
};

export type ApiResponse<T> = {
  envelope: ApiEnvelope<T>;
  correlationId: string;
};
