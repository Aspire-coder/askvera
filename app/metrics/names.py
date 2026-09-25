"""Stable metric names used by metrics providers."""

REQUEST_COUNT = "RequestCount"
REQUEST_DURATION = "RequestDuration"
TOTAL_REQUESTS = "TotalRequests"
SUCCESSFUL_REQUESTS = "SuccessfulRequests"
FAILED_REQUESTS = "FailedRequests"
AVERAGE_REQUEST_DURATION = "AverageRequestDuration"
GOVERNANCE_LATENCY = "GovernanceLatency"
RETRIEVAL_LATENCY = "RetrievalLatency"
PROMPT_BUILD_LATENCY = "PromptBuildLatency"
MODEL_LATENCY = "ModelLatency"
VALIDATION_LATENCY = "ValidationLatency"
RESPONSE_BUILD_LATENCY = "ResponseBuildLatency"
CACHE_HIT_RATIO = "CacheHitRatio"
AUDIT_QUEUE_DEPTH = "AuditQueueDepth"
RETRIEVAL_HEALTH = "RetrievalHealth"
GOVERNANCE_HEALTH = "GovernanceHealth"
VALIDATION_HEALTH = "ValidationHealth"
# Suffixed, unlike the metric names above, to stay distinct from
# config.vera_persona.FALLBACK_RESPONSES -- the canned fallback *texts*, which
# chat_orchestrator.py already imports under that exact name. The CloudWatch
# metric strings are unaffected.
DELIVERED_RESPONSES_METRIC = "DeliveredResponses"
FALLBACK_RESPONSES_METRIC = "FallbackResponses"
FALLBACK_BY_LAYER_METRIC = "FallbackResponsesByLayer"
NUMERIC_REPAIRS_METRIC = "NumericClaimRepairs"

PIPELINE_STAGE_METRIC_NAMES = {
    "governance": GOVERNANCE_LATENCY,
    "retrieval": RETRIEVAL_LATENCY,
    "prompt_build": PROMPT_BUILD_LATENCY,
    "model_generate": MODEL_LATENCY,
    "validation": VALIDATION_LATENCY,
    "response_build": RESPONSE_BUILD_LATENCY,
}

SYSTEM_METRIC_NAMES = {
    "cache_hit_ratio": CACHE_HIT_RATIO,
    "audit_queue_depth": AUDIT_QUEUE_DEPTH,
    "retrieval_health": RETRIEVAL_HEALTH,
    "governance_health": GOVERNANCE_HEALTH,
    "validation_health": VALIDATION_HEALTH,
    "delivered_responses": DELIVERED_RESPONSES_METRIC,
    "fallback_responses": FALLBACK_RESPONSES_METRIC,
    "fallback_by_layer": FALLBACK_BY_LAYER_METRIC,
    "numeric_claim_repairs": NUMERIC_REPAIRS_METRIC,
}

# System metrics that carry one extra CloudWatch dimension, taken from the
# metric's own metadata: {metric name: (metadata key, dimension name)}.
#
# Cardinality is the reason this is an explicit allowlist rather than "promote
# every metadata key". CloudWatch bills per distinct dimension combination, so
# only bounded, enumerable values belong here. `failure_layer` is drawn from a
# fixed set defined in the orchestrator, not from user input.
SYSTEM_METRIC_DIMENSIONS = {
    "fallback_by_layer": ("failure_layer", "FailureLayer"),
}

# Substituted when a dimension's metadata value is missing or blank.
# CloudWatch rejects empty dimension values outright.
UNKNOWN_DIMENSION_VALUE = "unknown"
