export type View = "flow" | "knowledge" | "insights";

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
  created_at: string;
  rating: number | null;
  comment: string | null;
};
