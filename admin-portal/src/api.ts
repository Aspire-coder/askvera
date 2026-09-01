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
const REQUEST_TIMEOUT_MS = 15_000;
const FILE_REQUEST_TIMEOUT_MS = 120_000;

type Envelope<T> = { success: boolean; data?: T; error?: { message?: string } };
export type AdminCredentials = { accessToken?: string; apiKey?: string };
type RequestOptions = RequestInit & { timeoutMs?: number };

export class AdminApi {
  constructor(private readonly credentials: AdminCredentials) {}

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { timeoutMs = REQUEST_TIMEOUT_MS, ...init } = options;
    const timeout = AbortSignal.timeout(timeoutMs);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        signal,
        headers: {
          ...(this.credentials.accessToken ? { Authorization: `Bearer ${this.credentials.accessToken}` } : {}),
          ...(this.credentials.apiKey ? { "X-Admin-Key": this.credentials.apiKey } : {}),
          ...(init.headers || {})
        }
      });
    } catch (error) {
      if (error instanceof DOMException && ["AbortError", "TimeoutError"].includes(error.name)) {
        throw new Error("The operations API did not respond in time.");
      }
      throw new Error("The operations API could not be reached.");
    }
    const payload = await response.json().catch(() => ({})) as Envelope<T> & { detail?: string };
    if (!response.ok || payload.success === false || payload.data === undefined) {
      throw new Error(payload.error?.message || payload.detail || `Request failed (${response.status})`);
    }
    return payload.data;
  }

  private async requestBlob(path: string): Promise<Blob> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        signal: AbortSignal.timeout(FILE_REQUEST_TIMEOUT_MS),
        headers: {
          ...(this.credentials.accessToken ? { Authorization: `Bearer ${this.credentials.accessToken}` } : {}),
          ...(this.credentials.apiKey ? { "X-Admin-Key": this.credentials.apiKey } : {})
        }
      });
    } catch {
      throw new Error("The export could not be downloaded from the operations API.");
    }
    if (!response.ok) throw new Error(`Export failed (${response.status})`);
    return response.blob();
  }

  config() { return this.request<AdminConfig>("/api/admin/config"); }
  marketReadiness() { return this.request<MarketReadiness>("/api/admin/market-readiness"); }
  traces() { return this.request<PipelineTrace[]>("/api/admin/traces?limit=20"); }
  overview(filters: URLSearchParams) { return this.request<AnalyticsOverview>(`/api/admin/analytics/overview?${filters}`); }
  interactions(filters: URLSearchParams) { return this.request<InteractionPage>(`/api/admin/analytics/interactions?${filters}`); }
  async exportInteractions(filters: URLSearchParams): Promise<Blob> {
    return this.requestBlob(`/api/admin/analytics/interactions.csv?${filters}`);
  }
  async exportInteractionsXlsx(filters: URLSearchParams): Promise<Blob> {
    return this.requestBlob(`/api/admin/analytics/interactions.xlsx?${filters}`);
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
  upload(formData: FormData, signal?: AbortSignal) {
    return this.request<{ jobId: string; filename: string; detectedFormat?: { format?: string; media_type?: string }; status: string; message: string }>("/api/admin/documents", {
      method: "POST",
      body: formData,
      signal,
      timeoutMs: FILE_REQUEST_TIMEOUT_MS
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
    return this.request<{ url: string }>("/api/admin/widget-assets", {
      method: "POST", body: form, timeoutMs: FILE_REQUEST_TIMEOUT_MS
    });
  }
}

export type DataMode = "live" | "demo" | "unavailable";

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

export const empty = {
  config: { ...demoConfig, countries: [], widgetCountries: [], documentTypes: [], accessScopes: [] },
  overview: {
    ...demoOverview,
    totals: {
      questions: 0, users: 0, liveSessions: 0, inputTokens: 0, outputTokens: 0, tokens: 0,
      averageConfidence: 0, unanswered: 0, helpful: 0, notHelpful: 0, helpfulRate: 0
    },
    topics: [], countries: [], languages: [], trend: []
  },
  shadowReport: {
    ...demoShadowReport,
    totals: {
      comparisons: 0, topMatches: 0, topMatchRate: 0, averageOverlap: 0,
      vnextConfidenceWins: 0, vnextConfidenceWinRate: 0, primaryConfidence: 0,
      vnextConfidence: 0, averageDurationMs: 0
    },
    countries: [], languages: [], trend: [], disagreements: []
  },
  interactions: [],
  jobs: []
};
