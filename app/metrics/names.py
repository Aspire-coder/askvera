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
}
