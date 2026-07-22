import type { AdminConfig, AnalyticsOverview, IngestionJob, Interaction, PipelineTrace } from "./types";

const now = new Date();
const iso = (offsetSeconds: number) => new Date(now.getTime() - offsetSeconds * 1000).toISOString();

export const demoTrace: PipelineTrace = {
  correlation_id: "demo-7f4c2e",
  country: "BE",
  language: "nl",
  session_id: "demo-session",
  question_preview: "Wat gebeurt er als ik mijn actieve Case Credits deze maand niet behaal?",
  started_at: iso(14),
  completed_at: iso(11),
  stages: [
    { stage: "request_received", status: "complete", duration_ms: 12, timestamp: iso(14), metadata: { country: "BE", language: "nl", role: "FBO", transport: "HTTPS" } },
    { stage: "governance", status: "complete", duration_ms: 84, timestamp: iso(13.8), metadata: { provider: "Bedrock Guardrails", action: "ALLOW", riskLevel: "LOW" } },
    { stage: "cache_lookup", status: "complete", duration_ms: 9, timestamp: iso(13.4), metadata: { provider: "Amazon ElastiCache for Valkey", cacheHit: false, tokensSaved: 0 } },
    { stage: "retrieval", status: "complete", duration_ms: 476, timestamp: iso(13.1), metadata: { provider: "OpenSearch Hybrid", sourceCount: 4, confidence: 0.91 } },
    { stage: "prompt_build", status: "complete", duration_ms: 7, timestamp: iso(12.5), metadata: { promptVersion: "2026-07", sourceCount: 4, hasConversation: true, systemCharacters: 11842, contextCharacters: 7230 } },
    { stage: "model_generate", status: "complete", duration_ms: 1380, timestamp: iso(11.8), metadata: { provider: "Claude via Bedrock", model: "Claude Haiku 4.5", sourceCount: 4, inputTokens: 3428, outputTokens: 286, finishReason: "end_turn" } },
    { stage: "validation", status: "complete", duration_ms: 21, timestamp: iso(11.4), metadata: { validatorCount: 7, issueCount: 0, highestSeverity: "PASS", valid: true } },
    { stage: "response_build", status: "complete", duration_ms: 8, timestamp: iso(11.2), metadata: { responseSource: "model", citationCount: 1, confidence: 0.91 } },
    { stage: "response_delivered", status: "complete", duration_ms: 16, timestamp: iso(11), metadata: { source_count: 1, confidence: 0.91, provider: "claude", inputTokens: 3428, outputTokens: 286 } }
  ]
};

export const demoCachedTrace: PipelineTrace = {
  correlation_id: "demo-cache-91b8",
  country: "BE",
  language: "en",
  session_id: "demo-cache-session",
  question_preview: "How do I become a Supervisor?",
  started_at: iso(48),
  completed_at: iso(47.8),
  stages: [
    { stage: "request_received", status: "complete", duration_ms: 9, timestamp: iso(48), metadata: { country: "BE", language: "en", role: "FBO", transport: "HTTPS" } },
    { stage: "governance", status: "complete", duration_ms: 52, timestamp: iso(47.96), metadata: { provider: "Bedrock Guardrails", action: "ALLOW", riskLevel: "LOW" } },
    { stage: "cache_lookup", status: "complete", duration_ms: 4, timestamp: iso(47.9), metadata: { provider: "Amazon ElastiCache for Valkey", cacheHit: true, tokensSaved: 3714, inputTokensSaved: 3428, outputTokensSaved: 286 } },
    { stage: "validation", status: "complete", duration_ms: 13, timestamp: iso(47.86), metadata: { validatorCount: 7, issueCount: 0, highestSeverity: "PASS", valid: true } },
    { stage: "response_delivered", status: "complete", duration_ms: 7, timestamp: iso(47.8), metadata: { source_count: 1, confidence: 0.94, provider: "cache", cacheHit: true, tokensSaved: 3714, inputTokens: 0, outputTokens: 0 } }
  ]
};

export const demoConfig: AdminConfig = {
  countries: [
    { code: "BE", name: "Belgium", languages: [{ code: "nl", name: "Dutch" }, { code: "fr", name: "French" }] },
    { code: "NL", name: "Netherlands", languages: [{ code: "nl", name: "Dutch" }] },
    { code: "US", name: "United States", languages: [{ code: "en", name: "English" }] },
    { code: "CA", name: "Canada", languages: [{ code: "en", name: "English" }, { code: "fr", name: "French" }] }
  ],
  documentTypes: ["policy", "product_information", "training", "marketing", "legal", "faq", "operations", "other"],
  accessScopes: ["country", "global"],
  maxUploadBytes: 26_214_400
};

export const demoJobs: IngestionJob[] = [
  { job_id: "a1", filename: "Benelux Product Guide 2026.pdf", country: "BE", language: "nl", document_type: "product_information", access_scope: "country", document_version: "2026.1", status: "ready", progress: 100, section_count: 84, source_uri: "s3://approved-knowledge/a1/guide.pdf", error_message: "", created_at: iso(7200), updated_at: iso(7050) },
  { job_id: "a2", filename: "Manager Training Handbook.pdf", country: "BE", language: "fr", document_type: "training", access_scope: "country", document_version: "2026.2", status: "indexing", progress: 72, section_count: 46, source_uri: "", error_message: "", created_at: iso(220), updated_at: iso(8) },
  { job_id: "a3", filename: "Global Product FAQ.docx", country: "US", language: "en", document_type: "faq", access_scope: "global", document_version: "2026.3", status: "ready", progress: 100, section_count: 31, source_uri: "s3://approved-knowledge/a3/faq.docx", error_message: "", created_at: iso(86400), updated_at: iso(86320) }
];

const daily = [32, 45, 41, 58, 62, 55, 76, 81, 74, 93, 88, 106, 114, 121];
export const demoOverview: AnalyticsOverview = {
  rangeDays: 30,
  totals: { questions: 1842, users: 618, inputTokens: 2_050_000, outputTokens: 410_810, tokens: 2_460_810, averageConfidence: 0.87, unanswered: 94, helpful: 486, notHelpful: 42, helpfulRate: 0.92 },
  topics: [
    { label: "Rank qualification", value: 412 }, { label: "Product information", value: 361 },
    { label: "Ordering & returns", value: 288 }, { label: "Bonuses & Case Credits", value: 274 },
    { label: "Sponsoring", value: 183 }, { label: "Compliance", value: 156 }
  ],
  countries: [{ label: "BE", value: 702 }, { label: "NL", value: 516 }, { label: "US", value: 361 }, { label: "CA", value: 263 }],
  languages: [{ label: "nl", value: 922 }, { label: "fr", value: 482 }, { label: "en", value: 438 }],
  trend: daily.map((questions, index) => {
    const date = new Date(now.getTime() - (daily.length - index - 1) * 86400000).toISOString().slice(0, 10);
    return { date, questions, users: Math.round(questions * 0.39), tokens: questions * 1320 };
  })
};

export const demoInteractions: Interaction[] = [
  { correlation_id: "n1", session_id: "s1", country: "BE", language: "nl", question: "Kan een Manager zich opnieuw kwalificeren als Manager?", answer: "De beschikbare documenten bevatten niet genoeg informatie om dit duidelijk te beantwoorden.", topic: "Manager requalification", confidence: 0.42, source_count: 0, tokens: 812, fallback: true, failure_layer: "evidence_gate", traffic_source: "widget", created_at: iso(1800), rating: -1, comment: "The policy has this rule but it was not found." },
  { correlation_id: "n2", session_id: "s2", country: "BE", language: "fr", question: "Que se passe-t-il si je suis inactif pendant plusieurs mois ?", answer: "Les documents approuvés ne fournissent pas de réponse claire.", topic: "Long-term inactivity", confidence: 0.38, source_count: 0, tokens: 694, fallback: true, failure_layer: "retrieval_miss", traffic_source: "evaluation", created_at: iso(7600), rating: -1, comment: "Expected an inactivity explanation." },
  { correlation_id: "n3", session_id: "s3", country: "NL", language: "nl", question: "Hoeveel Case Credits heb ik nodig voor Supervisor?", answer: "Voor Supervisor zijn 10 Open Group Case Credits nodig.", topic: "Rank qualification", confidence: 0.94, source_count: 1, tokens: 1042, fallback: false, failure_layer: "", traffic_source: "backend_test", created_at: iso(9000), rating: 1, comment: "Clear answer and source." }
];
