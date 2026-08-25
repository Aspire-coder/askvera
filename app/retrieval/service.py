"""Retrieval pipeline service."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from app.metrics import STAGE_RETRIEVAL
from app.metrics.pipeline import record_pipeline_metric
from config import settings
from services.analytics import record_retrieval_shadow_comparison
from services.retrieval_runtime import get_retrieval_runtime_control
from utils.logging import get_logger

from .models import RetrievedDocument, RetrievalResult
from .providers import BedrockRetrievalProvider, RetrievalProvider
from .section_index import SectionSearchProvider

LOGGER = get_logger("app.retrieval.shadow")
_SHADOW_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="retrieval-shadow")


def _submit_shadow_task(task) -> None:
    """Submit a best-effort comparison that cannot change the live response."""
    _SHADOW_EXECUTOR.submit(task)


class RetrievalService:
    """Coordinate retrieval pipeline stages."""

    def __init__(
        self,
        provider: RetrievalProvider | None = None,
        shadow_provider: RetrievalProvider | None = None,
    ) -> None:
        self._fixed_provider = provider is not None
        self._provider_name = settings.RETRIEVAL_PROVIDER
        self.provider = provider or self._default_provider()
        self._fixed_shadow_provider = shadow_provider

    def _default_provider(self) -> RetrievalProvider:
        """Select the configured retrieval backend."""
        return self._provider_for_name(settings.RETRIEVAL_PROVIDER)

    @staticmethod
    def _provider_for_name(
        provider_name: str,
        *,
        index_name: str | None = None,
        enable_bedrock_rerank: bool = False,
        enable_rrf: bool = False,
        enable_parent_diversity: bool = False,
        enable_evidence_selector: bool | None = None,
        enable_retrieval_hardening: bool | None = None,
        profile_name: str = "current",
    ) -> RetrievalProvider:
        """Build a provider without changing the established live selection."""
        if provider_name == "section":
            return SectionSearchProvider()
        if provider_name == "opensearch_section":
            from .opensearch_sections import OpenSearchSectionProvider

            return OpenSearchSectionProvider(
                index_name=index_name,
                enable_bedrock_rerank=enable_bedrock_rerank,
                enable_rrf=enable_rrf,
                enable_parent_diversity=enable_parent_diversity,
                enable_evidence_selector=enable_evidence_selector,
                enable_retrieval_hardening=enable_retrieval_hardening,
                profile_name=profile_name,
            )
        return BedrockRetrievalProvider()

    def _current_provider(self) -> RetrievalProvider:
        """Return a provider that matches the latest loaded configuration."""
        if not self._fixed_provider and self._provider_name != settings.RETRIEVAL_PROVIDER:
            self.provider = self._default_provider()
            self._provider_name = settings.RETRIEVAL_PROVIDER
        return self.provider

    def retrieve(self, message: str, country: str, language: str, role: str, correlation_id: str) -> RetrievalResult:
        """Return approved documents for a chat request."""
        started = perf_counter()
        success = False
        result: RetrievalResult | None = None
        provider = self._current_provider()
        try:
            result = provider.retrieve(message, country, language, role, correlation_id)
            success = True
            try:
                self._submit_shadow_comparison(
                    message=message,
                    country=country,
                    language=language,
                    role=role,
                    correlation_id=correlation_id,
                    primary_result=result,
                )
            except Exception:  # noqa: BLE001 - shadow work cannot affect the primary path.
                LOGGER.exception(
                    "retrieval_shadow_orchestration_failed",
                    correlation_id=correlation_id,
                )
            return result
        finally:
            record_pipeline_metric(
                stage=STAGE_RETRIEVAL,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={
                    "country": country,
                    "language": language,
                    "role": role,
                    "provider": type(provider).__name__,
                    "sourceCount": len(result.documents) if result else 0,
                    "confidence": round(float(result.confidence), 3) if result else 0.0,
                },
            )

    def _submit_shadow_comparison(
        self,
        *,
        message: str,
        country: str,
        language: str,
        role: str,
        correlation_id: str,
        primary_result: RetrievalResult,
    ) -> None:
        """Launch an isolated comparison while preserving the primary result."""
        control = get_retrieval_runtime_control()
        if control.mode != "shadow" or not self._sampled_for_shadow(correlation_id, control.sample_rate):
            return
        if (
            settings.RETRIEVAL_VNEXT_PROVIDER != "opensearch_section"
            or not settings.OPENSEARCH_VNEXT_INDEX
            or settings.OPENSEARCH_VNEXT_INDEX == settings.OPENSEARCH_INDEX
        ):
            LOGGER.warning(
                "retrieval_shadow_skipped_unsafe_configuration",
                correlation_id=correlation_id,
                provider=settings.RETRIEVAL_VNEXT_PROVIDER,
                has_vnext_index=bool(settings.OPENSEARCH_VNEXT_INDEX),
                index_is_isolated=settings.OPENSEARCH_VNEXT_INDEX != settings.OPENSEARCH_INDEX,
            )
            return

        shadow_provider = self._fixed_shadow_provider or self._provider_for_name(
            settings.RETRIEVAL_VNEXT_PROVIDER,
            index_name=settings.OPENSEARCH_VNEXT_INDEX,
            enable_bedrock_rerank=settings.RETRIEVAL_VNEXT_RERANK_ENABLED,
            enable_rrf=settings.RETRIEVAL_VNEXT_RRF_ENABLED,
            enable_parent_diversity=settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED,
            enable_evidence_selector=settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED,
            enable_retrieval_hardening=settings.RETRIEVAL_VNEXT_HARDENING_ENABLED,
            profile_name="vnext",
        )

        def compare() -> None:
            self._run_shadow_comparison(
                shadow_provider=shadow_provider,
                message=message,
                country=country,
                language=language,
                role=role,
                correlation_id=correlation_id,
                primary_result=primary_result,
            )

        try:
            _submit_shadow_task(compare)
        except RuntimeError:
            LOGGER.exception("retrieval_shadow_submit_failed", correlation_id=correlation_id)

    @staticmethod
    def _sampled_for_shadow(correlation_id: str, sample_rate: float | None = None) -> bool:
        """Select a stable request sample without storing or inspecting its text."""
        sample_rate = max(
            0.0,
            min(float(settings.RETRIEVAL_SHADOW_SAMPLE_RATE if sample_rate is None else sample_rate), 1.0),
        )
        if sample_rate <= 0.0:
            return False
        if sample_rate >= 1.0:
            return True
        digest = hashlib.sha256(correlation_id.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
        return bucket < sample_rate

    def _run_shadow_comparison(
        self,
        *,
        shadow_provider: RetrievalProvider,
        message: str,
        country: str,
        language: str,
        role: str,
        correlation_id: str,
        primary_result: RetrievalResult,
    ) -> None:
        """Evaluate vNext and emit metadata only; never return its result."""
        started = perf_counter()
        try:
            shadow_result = shadow_provider.retrieve(
                message,
                country,
                language,
                role,
                f"{correlation_id}-shadow",
            )
        except Exception:  # noqa: BLE001 - shadow work must never affect UAT
            LOGGER.exception(
                "retrieval_shadow_failed",
                correlation_id=correlation_id,
                vnext_index=settings.OPENSEARCH_VNEXT_INDEX,
                vnext_pipeline_version=settings.RETRIEVAL_VNEXT_PIPELINE_VERSION,
            )
            return

        primary_keys = {_document_key(document) for document in primary_result.documents}
        shadow_keys = {_document_key(document) for document in shadow_result.documents}
        shared_keys = primary_keys & shadow_keys
        union_keys = primary_keys | shadow_keys
        comparison = {
            "correlation_id": correlation_id,
            "country": country,
            "language": language,
            "primary_provider": primary_result.metadata.get("provider", settings.RETRIEVAL_PROVIDER),
            "primary_index": settings.OPENSEARCH_INDEX,
            "primary_pipeline_version": settings.RETRIEVAL_PIPELINE_VERSION,
            "primary_count": len(primary_result.documents),
            "primary_confidence": round(float(primary_result.confidence), 4),
            "primary_top_id": _top_document_key(primary_result),
            "vnext_provider": shadow_result.metadata.get("provider", settings.RETRIEVAL_VNEXT_PROVIDER),
            "vnext_index": settings.OPENSEARCH_VNEXT_INDEX,
            "vnext_pipeline_version": settings.RETRIEVAL_VNEXT_PIPELINE_VERSION,
            "vnext_count": len(shadow_result.documents),
            "vnext_confidence": round(float(shadow_result.confidence), 4),
            "vnext_top_id": _top_document_key(shadow_result),
            "vnext_fusion_strategy": shadow_result.metadata.get("fusion_strategy", ""),
            "vnext_candidate_count": int(shadow_result.metadata.get("candidate_count") or 0),
            "vnext_selected_candidate_count": int(
                shadow_result.metadata.get("selected_candidate_count") or 0
            ),
            "vnext_threshold_eligible_count": int(
                shadow_result.metadata.get("threshold_eligible_count") or 0
            ),
            "vnext_selector_rejected": bool(
                shadow_result.metadata.get("evidence_selector_rejected")
            ),
            "top_result_matches": _top_document_key(primary_result) == _top_document_key(shadow_result),
            "shared_result_count": len(shared_keys),
            "result_overlap": round(len(shared_keys) / len(union_keys), 4) if union_keys else 1.0,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        }
        LOGGER.info("retrieval_shadow_comparison", **comparison)
        try:
            record_retrieval_shadow_comparison(comparison)
        except Exception:  # noqa: BLE001 - telemetry must never affect retrieval
            LOGGER.exception("retrieval_shadow_analytics_failed", correlation_id=correlation_id)


def _document_key(document: RetrievedDocument) -> str:
    """Return a content-free identifier suitable for comparison telemetry."""
    if document.id:
        return document.id
    section_id = document.metadata.get("parent_section_id") or document.metadata.get("section_id") or ""
    return f"{document.source}|{section_id}|{document.page}"


def _top_document_key(result: RetrievalResult) -> str:
    return _document_key(result.documents[0]) if result.documents else ""


retrieval_service = RetrievalService()
