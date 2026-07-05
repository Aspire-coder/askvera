"""Metrics package."""

from .collector import MetricsCollector, metrics_collector
from .models import PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot
from .publisher import MetricsPublisher, metrics_publisher

STAGE_GOVERNANCE = "governance"
STAGE_MODEL_GENERATE = "model_generate"
STAGE_PROMPT_BUILD = "prompt_build"
STAGE_RESPONSE_BUILD = "response_build"
STAGE_RETRIEVAL = "retrieval"
STAGE_VALIDATION = "validation"

__all__ = [
    "MetricsCollector",
    "MetricsPublisher",
    "PipelineMetric",
    "PipelineStageSnapshot",
    "RequestMetric",
    "RequestMetricSnapshot",
    "STAGE_GOVERNANCE",
    "STAGE_MODEL_GENERATE",
    "STAGE_PROMPT_BUILD",
    "STAGE_RESPONSE_BUILD",
    "STAGE_RETRIEVAL",
    "STAGE_VALIDATION",
    "metrics_collector",
    "metrics_publisher",
]
