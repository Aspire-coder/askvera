import {
  demoCachedTrace,
  demoConfig,
  demoInteractions,
  demoJobs,
  demoOverview,
  demoShadowReport,
  demoTrace
} from "./demoData";
import type {
  AdminConfig,
  AdminAuditEvent,
  AdminScope,
  AdminUser,
  AnalyticsOverview,
  IngestionJob,
  IngestionPreview,
  IngestionPreviewTest,
  InteractionPage,
  MarketReadiness,
  PipelineTrace,
  ShadowReport,
  SupportRoute,
  WidgetConfig
} from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "";
const ALLOW_DEMO = import.meta.env.DEV || import.meta.env.VITE_ALLOW_DEMO === "true";

type Envelope<T> = { success: boolean; data?: T; error?: { message?: string } };
export type AdminCredentials = { accessToken?: string; apiKey?: string };

export class AdminApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "AdminApiError";
  }
}

const signalExpiredSession = (response: Response) => {
  if (response.status === 401) window.dispatchEvent(new Event("askvera:auth-expired"));
};

const responseError = async (response: Response, fallback: string): Promise<AdminApiError> => {
  signalExpiredSession(response);
  const text = await response.text();
  let message = "";
  if (text) {
    try {
      const payload = JSON.parse(text) as Envelope<unknown> & { detail?: string };
      message = payload.error?.message || payload.detail || "";
    } catch {
      message = "";
    }
  }
  return new AdminApiError(message || `${fallback} (${response.status})`, response.status);
};

export class AdminApi {
  constructor(private readonly credentials: AdminCredentials) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(this.credentials.accessToken ? { Authorization: `Bearer ${this.credentials.accessToken}` } : {}),
        ...(this.credentials.apiKey ? { "X-Admin-Key": this.credentials.apiKey } : {}),
        ...(init?.headers || {})
      }
    });
    if (!response.ok) throw await responseError(response, "Request failed");
    const text = await response.text();
    let payload: Envelope<T> & { detail?: string };
    try {
      payload = JSON.parse(text) as Envelope<T> & { detail?: string };
    } catch {
      throw new AdminApiError("The service returned an invalid response.", response.status);
    }
    if (!response.ok || payload.success === false || payload.data === undefined) {
      throw new AdminApiError(payload.error?.message || payload.detail || `Request failed (${response.status})`, response.status);
    }
    return payload.data;
  }

  config() { return this.request<AdminConfig>("/api/admin/config"); }
  marketReadiness() { return this.request<MarketReadiness>("/api/admin/market-readiness"); }
  traces() { return this.request<PipelineTrace[]>("/api/admin/traces?limit=20"); }
  overview(filters: URLSearchParams) { return this.request<AnalyticsOverview>(`/api/admin/analytics/overview?${filters}`); }
  interactions(filters: URLSearchParams) { return this.request<InteractionPage>(`/api/admin/analytics/interactions?${filters}`); }
  async exportInteractions(filters: URLSearchParams): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/admin/analytics/interactions.csv?${filters}`, {
      headers: {
        ...(this.credentials.accessToken ? { Authorization: `Bearer ${this.credentials.accessToken}` } : {}),
        ...(this.credentials.apiKey ? { "X-Admin-Key": this.credentials.apiKey } : {})
      }
    });
    if (!response.ok) throw await responseError(response, "Export failed");
    return response.blob();
  }
  async exportInteractionsXlsx(filters: URLSearchParams): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/admin/analytics/interactions.xlsx?${filters}`, {
      headers: {
        ...(this.credentials.accessToken ? { Authorization: `Bearer ${this.credentials.accessToken}` } : {}),
        ...(this.credentials.apiKey ? { "X-Admin-Key": this.credentials.apiKey } : {})
      }
    });
    if (!response.ok) throw await responseError(response, "Excel export failed");
    return response.blob();
  }
  retrievalShadow(filters: URLSearchParams) {
    return this.request<ShadowReport>(`/api/admin/analytics/retrieval-shadow?${filters}`);
  }
  ingestions() { return this.request<IngestionJob[]>("/api/admin/ingestions?limit=50"); }
  ingestionPreview(jobId: string, limit = 12) {
    return this.request<IngestionPreview>(`/api/admin/ingestions/${encodeURIComponent(jobId)}/preview?limit=${limit}`);
  }
  testIngestionPreview(jobId: string, message: string) {
    return this.request<IngestionPreviewTest>(`/api/admin/ingestions/${encodeURIComponent(jobId)}/preview-test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });
  }
  publishIngestion(jobId: string) {
    return this.request<{ job: IngestionJob; publishedCount: number }>(`/api/admin/ingestions/${encodeURIComponent(jobId)}/publish`, { method: "POST" });
  }
  deleteIngestion(jobId: string) {
    return this.request<{ job: IngestionJob; message: string }>(`/api/admin/ingestions/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  }
  upload(formData: FormData, signal?: AbortSignal) {
    return this.request<{ jobId: string; filename: string; detectedFormat?: { format?: string; media_type?: string }; status: string; message: string }>("/api/admin/documents", {
      method: "POST",
      body: formData,
      signal
    });
  }
  users() { return this.request<AdminUser[]>("/api/admin/users"); }
  auditEvents() { return this.request<AdminAuditEvent[]>("/api/admin/audit-events"); }
  createUser(body: { email: string; role: string; scopes: AdminScope[] }) {
    return this.request<AdminUser>("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }
  updateUser(id: string, body: { role: string; scopes: AdminScope[] }) {
    return this.request<AdminUser>(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }
  setUserEnabled(id: string, enabled: boolean) {
    return this.request<AdminUser>(`/api/admin/users/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" });
  }
  resendInvite(id: string) {
    return this.request<AdminUser>(`/api/admin/users/${id}/resend-invite`, { method: "POST" });
  }
  supportRoutes() { return this.request<SupportRoute[]>("/api/admin/support-routes"); }
  updateSupportRoute(country: string, body: { department: string; email: string; enabled: boolean }) {
    return this.request<SupportRoute>(`/api/admin/support-routes/${country}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
  }
  widgetConfigs() { return this.request<WidgetConfig[]>("/api/admin/widget-configs"); }
  createWidgetConfig(body: Omit<WidgetConfig, "id" | "public_key" | "key_version" | "status" | "embed_code" | "created_at" | "updated_at">) {
    return this.request<WidgetConfig>("/api/admin/widget-configs", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
  }
  updateWidgetConfig(id: string, body: Omit<WidgetConfig, "id" | "public_key" | "key_version" | "status" | "embed_code" | "created_at" | "updated_at">) {
    return this.request<WidgetConfig>(`/api/admin/widget-configs/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
  }
  rotateWidgetKey(id: string) {
    return this.request<WidgetConfig>(`/api/admin/widget-configs/${id}/rotate-key`, { method: "POST" });
  }
  disableWidgetConfig(id: string) {
    return this.request<WidgetConfig>(`/api/admin/widget-configs/${id}/disable`, { method: "POST" });
  }
  uploadWidgetLogo(file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request<{ url: string }>("/api/admin/widget-assets", { method: "POST", body: form });
  }
}

export type DataMode = "live" | "demo";

export async function withDemoFallback<T>(live: () => Promise<T>, fallback: T): Promise<{ data: T; mode: DataMode }> {
  try {
    return { data: await live(), mode: "live" };
  } catch (error) {
    if (!ALLOW_DEMO) throw error;
    return { data: fallback, mode: "demo" };
  }
}

export const demo = {
  config: demoConfig,
  traces: [demoTrace, demoCachedTrace],
  overview: demoOverview,
  shadowReport: demoShadowReport,
  interactions: demoInteractions,
  jobs: demoJobs
};
