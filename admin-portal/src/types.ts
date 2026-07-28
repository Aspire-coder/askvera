export type View = "flow" | "knowledge" | "insights" | "users" | "widget";

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

export type MarketLanguage = { code: string; name: string };
export type Market = { code: string; name: string; languages: MarketLanguage[] };

export type AdminConfig = {
  countries: Market[];
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

export type AdminUser = {
  id: string;
  email: string;
  role: string;
  status: "invited" | "active" | "disabled";
  last_login: string | null;
  created_at: string;
  updated_at: string;
  scopes: AdminScope[];
};

export type AdminAuditEvent = {
  event_id: string;
  actor_sub: string;
  action: string;
  target_type: string;
  target_id: string;
  created_at: string;
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
  position: "bottom-right" | "bottom-left";
  legal_version: string;
  rate_limit_tier: string;
  usage_cap: number | null;
  public_key: string;
  key_version: number;
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
  status: string;
  progress: number;
  section_count: number;
  source_uri: string;
  error_message: string;
  created_at: string;
  updated_at: string;
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
};

export type ShadowDisagreement = {
  correlation_id: string;
  country: string;
  language: string;
  primary_top_id: string;
  vnext_top_id: string;
  primary_confidence: number;
  vnext_confidence: number;
  result_overlap: number;
  duration_ms: number;
  created_at: string;
};

export type ShadowReport = {
  rangeDays: number;
  totals: {
    comparisons: number;
    topMatches: number;
    topMatchRate: number;
    averageOverlap: number;
    vnextConfidenceWins: number;
    vnextConfidenceWinRate: number;
    primaryConfidence: number;
    vnextConfidence: number;
    averageDurationMs: number;
  };
  countries: Array<{ label: string; comparisons: number; matchRate: number }>;
  languages: Array<{ label: string; comparisons: number; matchRate: number }>;
  trend: Array<{ date: string; comparisons: number; topMatches: number; averageOverlap: number }>;
  disagreements: ShadowDisagreement[];
};
