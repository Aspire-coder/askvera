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
  Interaction,
  PipelineTrace,
  ShadowReport,
  WidgetConfig
} from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "";
const ALLOW_DEMO = import.meta.env.DEV || import.meta.env.VITE_ALLOW_DEMO === "true";

type Envelope<T> = { success: boolean; data?: T; error?: { message?: string } };
export type AdminCredentials = { accessToken?: string; apiKey?: string };

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
    const payload = await response.json() as Envelope<T> & { detail?: string };
    if (!response.ok || payload.success === false || payload.data === undefined) {
      throw new Error(payload.error?.message || payload.detail || `Request failed (${response.status})`);
    }
    return payload.data;
  }

  config() { return this.request<AdminConfig>("/api/admin/config"); }
  traces() { return this.request<PipelineTrace[]>("/api/admin/traces?limit=20"); }
  overview(filters: URLSearchParams) { return this.request<AnalyticsOverview>(`/api/admin/analytics/overview?${filters}`); }
  interactions(filters: URLSearchParams) { return this.request<Interaction[]>(`/api/admin/analytics/interactions?${filters}`); }
  retrievalShadow(filters: URLSearchParams) {
    return this.request<ShadowReport>(`/api/admin/analytics/retrieval-shadow?${filters}`);
  }
  ingestions() { return this.request<IngestionJob[]>("/api/admin/ingestions?limit=50"); }
  upload(formData: FormData) {
    return this.request<{ jobId: string; filename: string; status: string; message: string }>("/api/admin/documents", {
      method: "POST",
      body: formData
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
