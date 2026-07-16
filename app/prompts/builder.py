"""Prompt assembly for ASK Vera."""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING, Any

from app.metrics import STAGE_PROMPT_BUILD
from app.metrics.pipeline import record_pipeline_metric
from config import settings
from config.vera_persona import role_scope_for
from utils.logging import get_logger

from .models import PromptPackage
from .templates import COMPLIANCE_PROMPT, EVIDENCE_CONTRACT_PROMPT, FOLLOWUP_PROMPT, RAG_PROMPT, SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.retrieval.models import RetrievalResult

LOGGER = get_logger("app.prompts")


class PromptBuilder:
    """Build prompt packages without depending on AWS services."""

    def build(
        self,
        *,
        user_question: str,
        conversation: str,
        country: str,
        language: str,
        role: str,
        retrieval_result: RetrievalResult | None = None,
        retrieved_documents: str | None = None,
        persona: str = SYSTEM_PROMPT,
        compliance_rules: str = COMPLIANCE_PROMPT,
        prompt_version: str = "v1",
        metadata: dict[str, Any] | None = None,
    ) -> PromptPackage:
        """Assemble a complete prompt package."""
        started = perf_counter()
        success = False
        correlation_id = (metadata or {}).get("correlation_id", "")
        try:
            retrieved_context = retrieved_documents if retrieved_documents is not None else self._format_retrieval_context(retrieval_result)
            rendered_system = (
                persona.replace("{{user_language}}", language)
                .replace("{{user_country}}", country)
                .replace("{{user_role}}", role)
                .replace("{{role_content_scope}}", role_scope_for(role))
                .replace("{{retrieved_chunks}}", retrieved_context)
                .replace("{{session_history}}", conversation)
            ).strip()
            prompt_parts = [rendered_system, compliance_rules.strip(), FOLLOWUP_PROMPT.strip()]
            if settings.EVIDENCE_GATED_OUTPUT_ENABLED:
                prompt_parts.append(EVIDENCE_CONTRACT_PROMPT.strip())
            system_prompt = "\n\n".join(prompt_parts)
            package = PromptPackage(
                system_prompt=system_prompt,
                user_prompt=RAG_PROMPT.replace("$query$", user_question),
                retrieved_context=retrieved_context,
                country=country,
                language=language,
                role=role,
                prompt_version=prompt_version,
                metadata={
                    "user_question": user_question,
                    "has_conversation": bool(conversation.strip()),
                    "retrieval_confidence": retrieval_result.confidence if retrieval_result else None,
                    "retrieval_source_count": len(retrieval_result.documents) if retrieval_result else 0,
                    "evidence_contract": settings.EVIDENCE_GATED_OUTPUT_ENABLED,
                    **(metadata or {}),
                },
            )
            LOGGER.info(
                "prompt_builder_prompt_built",
                correlation_id=package.metadata.get("correlation_id", ""),
                country=country,
                language=language,
                role=role,
                prompt_version=prompt_version,
                source_count=package.metadata["retrieval_source_count"],
                has_conversation=package.metadata["has_conversation"],
            )
            success = True
            return package
        finally:
            record_pipeline_metric(
                stage=STAGE_PROMPT_BUILD,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                success=success,
                correlation_id=correlation_id,
                metadata={"country": country, "language": language, "role": role, "promptVersion": prompt_version},
            )

    def _format_retrieval_context(self, retrieval_result: RetrievalResult | None) -> str:
        """Render retrieved documents into model-ready context."""
        if retrieval_result is None or not retrieval_result.documents:
            return ""
        chunks: list[str] = []
        for index, document in enumerate(retrieval_result.documents, start=1):
            section = str(
                document.metadata.get("parent_section_id")
                or document.metadata.get("section_id")
                or ""
            ).strip()
            chunks.append(
                "\n".join(
                    [
                        f"[Source {index}] {document.title}",
                        f"Source ID: {document.id}",
                        f"Policy section: {section or 'not supplied'}",
                        f"Page: {document.page or 'not supplied'}",
                        f"URI: {document.source}",
                        f"Country: {document.country}",
                        f"Language: {document.language}",
                        f"Content: {document.content or document.excerpt}",
                    ]
                )
            )
        return "\n\n".join(chunks)
