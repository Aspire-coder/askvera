export type View = "overview" | "flow" | "knowledge" | "readiness" | "insights" | "support" | "users" | "widget";

export type TraceStage = {
  stage: string;
  status: "complete" | "error" | "active";
  duration_ms: number;
  timestamp: string;
  metadata: Record<string, unknown>;
};

export type PipelineTrace = {
  correlation_id: string;
  country: string;
  language: string;
  session_id: string;
  question_preview: string;
  started_at: string;
  completed_at: string;
  stages: TraceStage[];
};

export type OperationsStatus = {
  status: "healthy" | "degraded";
  checked_at: string;
  services: Record<string, { status: string; detail: string }>;
  knowledge_sync: { status: string; active_jobs: number; failed_jobs: number; last_change_at: string; expiring_documents: number; low_coverage_documents: number };
  assigned_actions: Array<{ label: string; owner: string; reason: string }>;
  versions: Record<string, string>;
  metrics: { cache_hit_ratio: number; retrieval_failure_rate: number; validation_failures: number; audit_queue_depth: number };
};

export type CacheResetResult = {
  country: string;
  mode: "exact" | "exact_and_semantic";
  exact_deleted: number;
  semantic_deleted: number;
  total_deleted: number;
  completed_at: string;
  duration_ms: number;
};

export type MarketLanguage = { code: string; name: string };
export type Market = { code: string; name: string; languages: MarketLanguage[] };

export type AdminConfig = {
  countries: Market[];
  widgetCountries?: Market[];
  documentTypes: string[];
  accessScopes: string[];
  maxUploadBytes: number;
  rbacEnabled?: boolean;
  userManagementEnabled?: boolean;
  widgetConfigEnabled?: boolean;
  principal?: {
    role: string;
    status: string;
    scopes: AdminScope[];
    sections: string[];
  };
};

export type AdminScope = { market: string; section: string; permission: string };

export type ReadinessCheckStatus = "pass" | "warning" | "not_configured" | "not_verified";
export type MarketReadinessCheck = {
  key: string;
  label: string;
  status: ReadinessCheckStatus;
  detail: string;
};
export type MarketReadinessLanguage = {
  code: string;
  name: string;
  policy_published: boolean;
};
export type MarketReadinessMarket = {
  code: string;
  name: string;
  overall: ReadinessCheckStatus;
  languages: MarketReadinessLanguage[];
  checks: MarketReadinessCheck[];
  owner_email: string;
  deadline: string;
};
export type MarketReadiness = {
  checked_at: string;
  summary: { total: number; ready: number; needs_review: number; not_configured: number };
  markets: MarketReadinessMarket[];
};

export type AdminUser = {
  id: string;
  email: string;
  role: string;
  status: "invited" | "active" | "disabled";
  last_login: string | null;
  created_at: string;
  updated_at: string;
  disabled_at: string | null;
  invite_expires_at: string | null;
  access_review_due_at: string | null;
  access_certified_at: string | null;
  access_certified_by: string;
  mfa_status: "enrolled" | "not_enrolled" | "unknown";
  scopes: AdminScope[];
};

export type SupportRoute = {
  country: string;
  country_name: string;
  department: string;
  email: string;
  fallback_department: string;
  fallback_email: string;
  enabled: boolean;
  updated_at: string | null;
  updated_by: string;
};

export type AdminAuditEvent = {
  event_id: string;
  actor_sub: string;
  action: string;
  target_type: string;
  target_id: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};

export type WidgetConfig = {
  id: string;
  name: string;
  customer: string;
  allowed_origins: string[];
  markets: string[];
  languages: string[];
  default_market: string;
  default_language: string;
  display_name: string;
  greeting: string;
  accent_color: string;
  logo_url: string;
  position: "bottom-right" | "bottom-left";
  legal_version: string;
  rate_limit_tier: string;
  usage_cap: number | null;
  public_key: string;
  key_version: number;
  previous_public_key: string;
  previous_key_expires_at: string | null;
  has_draft?: boolean;
  status: "active" | "disabled";
  embed_code: string;
  created_at: string;
  updated_at: string;
};

export type IngestionJob = {
  job_id: string;
  filename: string;
  country: string;
  language: string;
  document_type: string;
  access_scope: string;
  document_version: string;
  effective_date?: string;
  expiry_date?: string;
  malware_scan_status?: "pending" | "clean" | "blocked" | "not_required";
  status: string;
  progress: number;
  section_count: number;
  source_uri: string;
  logical_document_id?: string;
  document_owner?: string;
  approval_reference?: string;
  review_before_publish?: boolean;
  error_message: string;
  created_at: string;
  updated_at: string;
};

export type IngestionChunkPreview = {
  id: string;
  sectionId: string;
  title: string;
  page: string;
  endPage: string;
  content: string;
  sourceFile: string;
  country: string;
  language: string;
};

export type IngestionPreview = {
  job: IngestionJob;
  summary: {
    chunk_count: number;
    preview_count: number;
    page_count: number;
    pages: string[];
    average_chars: number;
    largest_chars: number;
    empty_chunks: number;
    oversized_chunks: number;
    duplicate_chunks: number;
    warnings: string[];
  };
  chunks: IngestionChunkPreview[];
  can_publish: boolean;
};

export type IngestionPreviewTest = {
  job: IngestionJob;
  message: string;
  matches: Array<{ score: number; sectionId: string; title: string; page: string; excerpt: string }>;
  matchCount: number;
};

export type KnowledgeGeneration = {
  ingestion_id: string;
  status: string;
  filename: string;
  document_version: string;
  section_count: number;
  effective_date: string;
  expiry_date: string;
  malware_scan_status: string;
  activated_at: string;
  retired_at: string;
  activated_by: string;
  created_at: string;
};

export type AnalyticsOverview = {
  rangeDays: number;
  totals: {
    questions: number;
    users: number;
    liveSessions: number;
    inputTokens: number;
    outputTokens: number;
    tokens: number;
    averageConfidence: number;
    unanswered: number;
    helpful: number;
    notHelpful: number;
    helpfulRate: number;
  };
  topics: Array<{ label: string; value: number }>;
  countries: Array<{ label: string; value: number }>;
  languages: Array<{ label: string; value: number }>;
  trend: Array<{ date: string; questions: number; users: number; tokens: number }>;
};

export type ModelRoutingReport = {
  rangeDays: number;
  mode: "off" | "shadow" | "live" | string;
  models: { primary: string; fast: string; complex: string };
  totals: {
    questions: number;
    evaluated: number;
    cached: number;
    unclassified: number;
    proposedFast: number;
    proposedComplex: number;
    fastShare: number;
    averageGenerationLatencyMs: number;
  };
  cost: {
    baselineUsd: number;
    currentUsd: number;
    projectedUsd: number;
    projectedDeltaUsd: number;
    projectedSavingsUsd: number;
    savingsRate: number;
    pricingLabel: string;
  };
  targets: Array<{
    target: "fast" | "complex";
    questions: number;
    input_tokens: number;
    output_tokens: number;
    average_latency_ms: number;
  }>;
  actualModels: Array<{ label: string; value: number }>;
  reasons: Array<{ label: string; value: number }>;
  countries: Array<{ label: string; evaluated: number; fast: number; complex: number }>;
  trend: Array<{ date: string; fast: number; complex: number; cached: number }>;
};

export type Interaction = {
  correlation_id: string;
  session_id: string;
  country: string;
  language: string;
  question: string;
  answer: string;
  topic: string;
  confidence: number;
  source_count: number;
  tokens: number;
  fallback: boolean;
  failure_layer: string;
  traffic_source: string;
  created_at: string;
  rating: number | null;
  comment: string | null;
  expected_answer?: string | null;
  expected_answer_present?: boolean;
  review_status?: "open" | "investigating" | "resolved" | null;
  assignee_email?: string | null;
  resolution_notes?: string | null;
  review_updated_at?: string | null;
};

export type AnalyticsSavedView = {
  id: string;
  name: string;
  filters: Record<string, string>;
  schedule: "none" | "daily" | "weekly";
  report_email: string;
  alert_not_helpful_threshold: number | null;
  last_sent_at: string | null;
  next_run_at: string | null;
};

export type InteractionPage = {
  items: Interaction[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

