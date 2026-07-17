import { demoCachedTrace, demoConfig, demoInteractions, demoJobs, demoOverview, demoTrace } from "./demoData";
import type { AdminConfig, AnalyticsOverview, IngestionJob, Interaction, PipelineTrace } from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "";

type Envelope<T> = { success: boolean; data?: T; error?: { message?: string } };

export class AdminApi {
  constructor(private readonly apiKey: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "X-Admin-Key": this.apiKey,
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
  ingestions() { return this.request<IngestionJob[]>("/api/admin/ingestions?limit=50"); }
  upload(formData: FormData) {
    return this.request<{ jobId: string; filename: string; status: string; message: string }>("/api/admin/documents", {
      method: "POST",
      body: formData
    });
  }
}

export type DataMode = "live" | "demo";

export async function withDemoFallback<T>(live: () => Promise<T>, fallback: T): Promise<{ data: T; mode: DataMode }> {
  try {
    return { data: await live(), mode: "live" };
  } catch {
    return { data: fallback, mode: "demo" };
  }
}

export const demo = {
  config: demoConfig,
  traces: [demoTrace, demoCachedTrace],
  overview: demoOverview,
  interactions: demoInteractions,
  jobs: demoJobs
};
