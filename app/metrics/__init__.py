"""Metrics package."""

from .collector import MetricsCollector, metrics_collector
from .models import HealthSummary, MetricsSnapshot, PipelineMetric, PipelineStageSnapshot, RequestMetric, RequestMetricSnapshot, SystemMetric
from .provider import MetricsProvider
from .publisher import MetricsPublisher, metrics_publisher
from .registry import MetricsRegistry, metrics_registry

STAGE_GOVERNANCE = "governance"
STAGE_MODEL_GENERATE = "model_generate"
STAGE_PROMPT_BUILD = "prompt_build"
STAGE_RESPONSE_BUILD = "response_build"
STAGE_RETRIEVAL = "retrieval"
STAGE_VALIDATION = "validation"

__all__ = [
    "MetricsCollector",
    "MetricsProvider",
    "MetricsPublisher",
    "MetricsRegistry",
    "HealthSummary",
    "MetricsSnapshot",
    "PipelineMetric",
    "PipelineStageSnapshot",
    "RequestMetric",
    "RequestMetricSnapshot",
    "SystemMetric",
    "STAGE_GOVERNANCE",
    "STAGE_MODEL_GENERATE",
    "STAGE_PROMPT_BUILD",
    "STAGE_RESPONSE_BUILD",
    "STAGE_RETRIEVAL",
    "STAGE_VALIDATION",
    "metrics_collector",
    "metrics_publisher",
    "metrics_registry",
]
