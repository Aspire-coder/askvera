"""AI chat orchestration for AskVera."""

import re
from time import perf_counter

from app.models.responses import ModelResponse
from app.operations import pipeline_trace_store
from app.models.router import ModelRouter, model_router
from app.evidence import (
    EvidenceDecision,
    assistant_meta_response,
    approve_evidence,
    classify_intent,
    localized_conversation_response,
    with_approved_evidence,
)
from app.evidence_contract import parse_evidence_contract
from app.prompts import PromptBuilder
from app.response import ChatResponse, ResponseBuilder, response_builder
from app.response.quality import (
    contact_for_country,
    format_period_not_covered,
    remove_or_replace_contact_placeholders,
    unsupported_requested_years,
)
from app.retrieval import RetrievalService, retrieval_service
from app.retrieval.models import RetrievalResult
from app.governance import GovernanceDecision, GovernanceEngine, governance_engine
from app.validation import OutputValidator, ValidationContext, ValidationResult, output_validator, validation_summary
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences
from config import settings
from config.vera_persona import FALLBACK_RESPONSES
from services.audit import write_audit_event
from services.cache import (
    build_cache_key,
    get_cache_value,
    set_cache_value,
)
from services.semantic_cache import (
    SemanticCacheHit,
    get_semantic_cache_value,
    semantic_cache_active,
    set_semantic_cache_value,
)
from services.consent_service import has_valid_consent
from services.claim_safety import localized_claim_response
from services.pii import contains_sensitive_pii_placeholder, remove_unresolved_pii_placeholders, scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
from utils.exceptions import SessionExpiredError
from utils.exceptions import LowConfidenceError, LowConfidenceThresholdError, RetrievalMissError
from utils.directory_fields import (
    parse_directory_fields,
    preserve_directory_role_labels,
    remove_unrequested_directory_fields,
    restore_missing_directory_contacts,
    restore_missing_requested_directory_fields,
)
from utils.logging import get_logger
from utils.validators import ChatRequest

LOGGER = get_logger("app.orchestrator")
FOLLOW_UP_CONTEXT_MARKERS = (
    "that",
    "this",
    "it",
    "them",
    "those",
    "previous",
    "earlier",
    "above",
    "first question",
    "last question",
    "more about",
    "more detail",
    "more details",
    "more information",
    "explain more",
    "tell me more",
    "elaborate",
    "expand on",
    "go deeper",
    "what else",
    "continue",
    "how so",
    "why is that",
)
DIRECTORY_DETAIL_TERMS = re.compile(
    r"\b(address|office|business\s+hours?|office\s+hours?|telephone|phone|email|website|contact|sponsor)\b",
    re.IGNORECASE,
)


class ConsentRequiredError(Exception):
    """Raised when a chat request has not accepted the current legal terms."""


class AIOrchestrator:
    """Coordinate the existing ASK Vera chat request lifecycle."""

    def __init__(
        self,
        prompt_builder: PromptBuilder | None = None,
        retriever: RetrievalService | None = None,
        router: ModelRouter | None = None,
        builder: ResponseBuilder | None = None,
        validator: OutputValidator | None = None,
        governance: GovernanceEngine | None = None,
    ) -> None:
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retriever = retriever or retrieval_service
        self.model_router = router or model_router
        self.response_builder = builder or response_builder
        self.output_validator = validator or output_validator
        self.governance_engine = governance or governance_engine

    def handle_chat(self, body: ChatRequest, correlation_id: str) -> ChatResponse:
        """Run the existing chat flow and return response data."""
        LOGGER.info(
            "ai_orchestrator_request_started",
            correlation_id=correlation_id,
            country=body.country,
            language=body.language,
            role=body.role,
            session_id=body.sessionId,
        )
        if validate_and_touch_session(body.sessionId, correlation_id) is False:
            raise SessionExpiredError()
        if not has_valid_consent(body.sessionId, correlation_id):
            raise ConsentRequiredError()

        scrubbed_input = scrub_pii(
            body.message,
            correlation_id,
            body.language,
            preserve_location_names=True,
            preserve_person_names=True,
        )
        chat_response = self._early_conversation_response(scrubbed_input, body, correlation_id)
        if chat_response:
            append_session_turn(body.sessionId, scrubbed_input, chat_response.answer, correlation_id)
            return chat_response
        history = get_session_history(body.sessionId, correlation_id)
        retrieval_query = self._build_retrieval_query(scrubbed_input, history, correlation_id)
        request_query = self._build_request_query(scrubbed_input, retrieval_query, history)
        governance_decision = self._evaluate_governance(request_query, body, correlation_id)
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message
            )

        cache_key = build_cache_key(request_query, body.country, body.language, body.role)
        cached_response = self._cached_response(cache_key, body, correlation_id, scrubbed_input)
        if cached_response:
            return cached_response

        retrieval_result = self.retriever.retrieve(retrieval_query, body.country, body.language, body.role, correlation_id)
        chat_response, retrieval_result, evidence_decision = self._route_or_approve_evidence(
            retrieval_query,
            retrieval_result,
            scrubbed_input,
            body,
            correlation_id,
        )
        if chat_response:
            return chat_response
        assert evidence_decision is not None
        cached_response, semantic_candidate, semantic_lookup_ms = self._semantic_cached_response(
            request_query, retrieval_result, body, correlation_id, scrubbed_input
        )
        if cached_response:
            return cached_response
        prompt_package = self.prompt_builder.build(
            user_question=scrubbed_input,
            conversation=history,
            country=body.country,
            language=body.language,
            role=body.role,
            retrieval_result=retrieval_result,
            metadata={"correlation_id": correlation_id},
        )
        try:
            model_response = self.model_router.generate(prompt_package, retrieval_result, correlation_id)
        except LowConfidenceError as exc:
            failure_layer = self._low_confidence_failure_layer(exc)
            return self._validate_response(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language),
                    correlation_id,
                    metadata={"failure_layer": failure_layer},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )

        if model_response.finish_reason == "guardrail_intervened":
            return self.response_builder.fallback(
                localized_conversation_response("guardrail_blocked", body.language)
                or (
                    "I couldn't provide that response because it did not pass AskVera's safety checks. "
                    "Please rephrase the question without private information or unsafe claims."
                ),
                correlation_id,
                metadata={
                    "failure_layer": "aws_guardrail",
                    "response_source": "guardrail",
                },
            )

        contracted_response = self._apply_evidence_contract(model_response, retrieval_result, correlation_id)
        if contracted_response is None:
            return self._validate_response(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language),
                    correlation_id,
                    metadata={"failure_layer": "evidence_contract"},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )
        model_response, retrieval_result = contracted_response

        chat_response = self.response_builder.build(
            model_response=model_response,
            retrieval_result=retrieval_result,
            correlation_id=correlation_id,
            session_metadata={
                "session_id": body.sessionId,
                "country": body.country,
                "language": body.language,
                "role": body.role,
                "cache": "miss",
                "evidence_decision": evidence_decision.to_metadata(),
            },
        )
        chat_response = self._secure_and_complete_response(
            chat_response,
            retrieval_result,
            body.language,
            correlation_id,
            user_question=body.message,
            country=body.country,
        )
        chat_response = self._validate_response(
            chat_response,
            body,
            correlation_id,
            model_response=model_response,
            retrieval_result=retrieval_result,
        )
        governance_decision = self._evaluate_governance(chat_response.answer, body, correlation_id)
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message
            )
        self._record_semantic_shadow_result(
            semantic_candidate,
            chat_response,
            body,
            correlation_id,
            semantic_lookup_ms,
        )
        append_session_turn(body.sessionId, scrubbed_input, chat_response.answer, correlation_id)
        write_audit_event(
            {
                "type": "chat",
                "country": body.country,
                "language": body.language,
                "confidence": chat_response.confidence,
                "validation": chat_response.metadata.get("validation"),
                "failure_layer": chat_response.metadata.get("failure_layer"),
                "finish_reason": chat_response.metadata.get("finish_reason"),
            },
            correlation_id,
        )
        self._cache_response(
            cache_key,
            request_query,
            retrieval_result,
            chat_response,
            body,
            correlation_id,
        )
        return chat_response

    def _secure_and_complete_response(
        self,
        chat_response: ChatResponse,
        retrieval_result: RetrievalResult,
        language: str,
        correlation_id: str,
        *,
        user_question: str,
        country: str = "",
    ) -> ChatResponse:
        """Restore approved directory fields, then enforce outbound PII safety."""
        completed_answer, restored_fields = chat_response.answer, []
        if chat_response.citations:
            directory_field_sets = [
                fields
                for document in retrieval_result.documents
                for fields in [
                    document.metadata.get("directory_fields", {})
                    if isinstance(document.metadata.get("directory_fields"), dict)
                    else parse_directory_fields(document.content)
                    if document.metadata.get("directory_kind")
                    or document.metadata.get("directory_section")
                    else {}
                ]
                if fields
            ]
            completed_answer, restored_requested_fields = restore_missing_requested_directory_fields(
                completed_answer,
                directory_field_sets,
                user_question,
            )
            completed_answer, restored_fields = restore_missing_directory_contacts(
                completed_answer,
                directory_field_sets,
            )
            restored_fields = [*restored_requested_fields, *restored_fields]
        if restored_fields:
            chat_response = self._replace_answer(
                chat_response,
                completed_answer,
                {"directory_contacts_restored": restored_fields},
            )

        role_safe_answer, role_label_corrected = preserve_directory_role_labels(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
        )
        if role_label_corrected:
            chat_response = self._replace_answer(
                chat_response,
                role_safe_answer,
                {"directory_role_label_corrected": True},
            )

        focused_answer, extra_fields_removed = remove_unrequested_directory_fields(
            chat_response.answer,
            user_question,
        )
        if extra_fields_removed:
            chat_response = self._replace_answer(
                chat_response,
                focused_answer,
                {"unrequested_directory_fields_removed": True},
            )

        safe_answer = scrub_pii(
            chat_response.answer,
            correlation_id,
            language,
            allowed_texts=[
                *settings.PII_APPROVED_PUBLIC_TERMS,
                *contact_for_country(country).values(),
                *(document.content for document in retrieval_result.documents),
            ],
            allowed_name_texts=[user_question],
        )
        if safe_answer != chat_response.answer:
            chat_response = self._replace_answer(chat_response, safe_answer, {"response_pii_scrubbed": True})

        contact_safe_answer, contact_changes = remove_or_replace_contact_placeholders(
            chat_response.answer,
            country,
        )
        if contact_changes:
            chat_response = self._replace_answer(
                chat_response,
                contact_safe_answer,
                {"contact_placeholder_actions": contact_changes},
            )

        cleaned_answer = remove_unresolved_pii_placeholders(chat_response.answer)
        if cleaned_answer != chat_response.answer:
            chat_response = self._replace_answer(
                chat_response,
                cleaned_answer,
                {"unresolved_pii_placeholders_removed": True},
            )
        if not chat_response.answer.strip():
            chat_response = self._replace_answer(
                chat_response,
                self._insufficient_evidence_message(language),
                {"empty_after_output_cleanup": True, "fallback": True},
            )
        return chat_response

    @staticmethod
    def _replace_answer(
        chat_response: ChatResponse,
        answer: str,
        metadata: dict[str, object],
    ) -> ChatResponse:
        """Return a response with updated answer text and metadata."""
        return ChatResponse(
            answer=answer,
            citations=chat_response.citations,
            suggestions=chat_response.suggestions,
            cards=chat_response.cards,
            confidence=chat_response.confidence,
            metadata={**chat_response.metadata, **metadata},
            correlation_id=chat_response.correlation_id,
        )

    def _cached_response(
        self,
        cache_key: str,
        body: ChatRequest,
        correlation_id: str,
        session_input: str = "",
    ) -> ChatResponse | None:
        """Read and revalidate a cached response before returning it."""
        cache_started = perf_counter()
        cached = get_cache_value(cache_key, correlation_id)
        cached_usage = dict(cached.get("token_usage") or {}) if cached else {}
        saved_input_tokens = int(cached_usage.get("inputTokens", cached_usage.get("input_tokens", 0)) or 0)
        saved_output_tokens = int(cached_usage.get("outputTokens", cached_usage.get("output_tokens", 0)) or 0)
        pipeline_trace_store.record(
            correlation_id,
            "cache_lookup",
            success=True,
            duration_ms=round((perf_counter() - cache_started) * 1000, 2),
            metadata={
                "service": "Amazon ElastiCache for Valkey",
                "cacheHit": bool(cached),
                "tokensSaved": saved_input_tokens + saved_output_tokens,
                "inputTokensSaved": saved_input_tokens,
                "outputTokensSaved": saved_output_tokens,
            },
        )
        response = self._cached_response_value(cached, body, correlation_id, cache_type="exact")
        if response and response.metadata.get("cache") == "exact":
            append_session_turn(body.sessionId, session_input or body.message, response.answer, correlation_id)
        return response

    def _cached_response_value(
        self,
        cached: dict | None,
        body: ChatRequest,
        correlation_id: str,
        *,
        cache_type: str,
    ) -> ChatResponse | None:
        if not cached:
            return None
        chat_response = self._secure_and_complete_response(
            self.response_builder.from_cached(cached, correlation_id),
            RetrievalResult(documents=[], citations=[], confidence=0.0),
            body.language,
            correlation_id,
            user_question=body.message,
            country=body.country,
        )
        chat_response = self._validate_response(
            chat_response, body, correlation_id
        )
        chat_response = self._replace_answer(chat_response, chat_response.answer, {"cache": cache_type})
        governance_decision = self._evaluate_governance(chat_response.answer, body, correlation_id)
        if not governance_decision.allowed:
            LOGGER.warning(
                "cached_response_governance_blocked",
                correlation_id=correlation_id,
                country=body.country,
                language=body.language,
                role=body.role,
                cache_type=cache_type,
            )
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message
            )
        return chat_response

    def _semantic_cached_response(
        self,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        session_input: str = "",
    ) -> tuple[ChatResponse | None, SemanticCacheHit | None, float]:
        """Read semantic cache only after current evidence has been approved."""
        if not semantic_cache_active():
            return None, None, 0.0
        started = perf_counter()
        cached = get_semantic_cache_value(
            retrieval_query,
            body.country,
            body.language,
            body.role,
            retrieval_result,
            correlation_id,
        )
        duration_ms = round((perf_counter() - started) * 1000, 2)
        live_mode = bool(settings.SEMANTIC_CACHE_ENABLED)
        pipeline_trace_store.record(
            correlation_id,
            "semantic_cache_lookup",
            success=True,
            duration_ms=duration_ms,
            metadata={
                "service": "Amazon ElastiCache for Valkey",
                "mode": "live" if live_mode else "shadow",
                "cacheHit": bool(cached and live_mode),
                "wouldHit": bool(cached),
                "served": bool(cached and live_mode),
                "similarity": round(cached.similarity, 4) if cached else 0.0,
                "candidatesChecked": cached.candidates_checked if cached else 0,
            },
        )
        if not cached or not live_mode:
            return None, cached, duration_ms
        response = self._cached_response_value(
            cached.response,
            body,
            correlation_id,
            cache_type="semantic",
        )
        if not response or response.metadata.get("cache") != "semantic":
            return response, cached, duration_ms
        response = self._replace_answer(
            response,
            response.answer,
            {
                "semantic_cache_similarity": round(cached.similarity, 4),
                "semantic_cache_candidates_checked": cached.candidates_checked,
            },
        )
        append_session_turn(body.sessionId, session_input or body.message, response.answer, correlation_id)
        return response, cached, duration_ms

    def _record_semantic_shadow_result(
        self,
        candidate: SemanticCacheHit | None,
        fresh_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
        lookup_duration_ms: float,
    ) -> None:
        """Compare a shadow candidate with the delivered fresh answer without logging either text."""
        if not settings.SEMANTIC_CACHE_SHADOW_ENABLED or settings.SEMANTIC_CACHE_ENABLED:
            return
        fresh_usage = dict((fresh_response.metadata or {}).get("token_usage") or {})
        input_tokens = int(fresh_usage.get("inputTokens", fresh_usage.get("input_tokens", 0)) or 0)
        output_tokens = int(fresh_usage.get("outputTokens", fresh_usage.get("output_tokens", 0)) or 0)
        answer_agreement = (
            self._text_agreement(str(candidate.response.get("response") or ""), fresh_response.answer)
            if candidate
            else 0.0
        )
        citation_agreement = (
            self._citation_agreement(candidate.response.get("sources"), fresh_response.citations)
            if candidate
            else 0.0
        )
        needs_review = bool(
            candidate and answer_agreement < settings.SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT
        )
        metadata = {
            "service": "Amazon ElastiCache for Valkey",
            "mode": "shadow",
            "cacheHit": False,
            "wouldHit": bool(candidate),
            "served": False,
            "freshGenerated": True,
            "similarity": round(candidate.similarity, 4) if candidate else 0.0,
            "candidatesChecked": candidate.candidates_checked if candidate else 0,
            "answerAgreement": answer_agreement,
            "citationAgreement": citation_agreement,
            "reviewRecommended": needs_review,
            "decision": "review" if needs_review else "agree" if candidate else "miss",
            "estimatedInputTokensSaved": input_tokens if candidate else 0,
            "estimatedOutputTokensSaved": output_tokens if candidate else 0,
            "estimatedTokensSaved": input_tokens + output_tokens if candidate else 0,
        }
        pipeline_trace_store.record(
            correlation_id,
            "semantic_cache_lookup",
            success=True,
            duration_ms=lookup_duration_ms,
            metadata=metadata,
        )
        write_audit_event(
            {
                "type": "semantic_cache_shadow",
                "country": body.country,
                "language": body.language,
                **{key: value for key, value in metadata.items() if key != "service"},
            },
            correlation_id,
        )

    @staticmethod
    def _text_agreement(left: str, right: str) -> float:
        """Return privacy-safe lexical agreement for two generated answers."""
        left_tokens = set(re.findall(r"[^\W_]+", left.casefold(), flags=re.UNICODE))
        right_tokens = set(re.findall(r"[^\W_]+", right.casefold(), flags=re.UNICODE))
        if not left_tokens or not right_tokens:
            return 0.0
        return round(len(left_tokens & right_tokens) / len(left_tokens | right_tokens), 4)

    @staticmethod
    def _citation_agreement(cached_sources: object, fresh_sources: object) -> float:
        """Compare source identities without storing source excerpts."""
        def identities(value: object) -> set[str]:
            if not isinstance(value, list):
                return set()
            return {
                str(item.get("uri") or item.get("title") or "").strip()
                for item in value
                if isinstance(item, dict) and (item.get("uri") or item.get("title"))
            }

        cached = identities(cached_sources)
        fresh = identities(fresh_sources)
        if not cached or not fresh:
            return 0.0
        return round(len(cached & fresh) / len(cached | fresh), 4)

    def _apply_evidence_contract(
        self,
        model_response: ModelResponse,
        retrieval_result: RetrievalResult,
        correlation_id: str,
    ) -> tuple[ModelResponse, RetrievalResult] | None:
        """Release only structured answers whose claims cite approved section IDs."""
        from config import settings

        if not settings.EVIDENCE_GATED_OUTPUT_ENABLED:
            return model_response, retrieval_result

        contract = parse_evidence_contract(model_response.text, retrieval_result.documents)
        if not contract.valid:
            LOGGER.warning(
                "evidence_contract_rejected",
                correlation_id=correlation_id,
                reason=contract.reason,
            )
            return None

        supported_documents = [
            document for document in retrieval_result.documents if document.id in set(contract.evidence_ids)
        ]
        contracted_retrieval_result = RetrievalResult(
            documents=supported_documents,
            citations=[document.to_source() for document in supported_documents],
            confidence=retrieval_result.confidence,
            metadata={
                **(retrieval_result.metadata or {}),
                "evidence_contract": {"status": "accepted", "evidence_ids": list(contract.evidence_ids)},
            },
        )
        LOGGER.info(
            "evidence_contract_accepted",
            correlation_id=correlation_id,
            evidence_count=len(supported_documents),
        )
        return (
            ModelResponse(
                text=contract.answer,
                citations=[document.to_source() for document in supported_documents],
                confidence=model_response.confidence,
                provider=model_response.provider,
                model_name=model_response.model_name,
                latency_ms=model_response.latency_ms,
                token_usage=model_response.token_usage,
                finish_reason=model_response.finish_reason,
                metadata={**(model_response.metadata or {}), "evidence_contract": "accepted"},
            ),
            contracted_retrieval_result,
        )

    def _build_retrieval_query(self, user_message: str, history: str, correlation_id: str) -> str:
        """Return the substantive question used to retrieve follow-up evidence."""
        user_message = self._normalize_malformed_spacing(user_message, correlation_id)
        if not self._needs_history_context(user_message, history):
            return user_message

        user_messages = self._user_messages_from_history(history)
        if not user_messages:
            return user_message

        anchor = user_messages[0] if "first question" in user_message.lower() else self._latest_context_anchor(user_messages)
        LOGGER.info(
            "chat_followup_context_applied",
            correlation_id=correlation_id,
            original_length=len(user_message),
            contextual_length=len(anchor),
        )
        return anchor

    def _build_request_query(self, user_message: str, retrieval_query: str, history: str = "") -> str:
        """Keep follow-up intent in governance and cache keys, outside retrieval."""
        normalized_message = " ".join((user_message or "").split()).strip()
        normalized_retrieval = " ".join((retrieval_query or "").split()).strip()
        if (
            not self._needs_history_context(normalized_message, history)
            or not normalized_retrieval
            or normalized_retrieval == normalized_message
        ):
            return normalized_retrieval or normalized_message
        return f"{normalized_retrieval}\nFollow-up request: {normalized_message}"

    def _normalize_malformed_spacing(self, message: str, correlation_id: str) -> str:
        """Repair character-spaced input without using a language vocabulary."""
        tokens = re.findall(r"[^\W_]", message, flags=re.UNICODE)
        word_tokens = re.findall(r"[^\W_]+", message, flags=re.UNICODE)
        if len(tokens) < 8 or not word_tokens:
            return message
        single_ratio = sum(len(token) == 1 for token in word_tokens) / len(word_tokens)
        if single_ratio < 0.65:
            return message

        groups = re.split(r"\s{2,}", message.strip())
        repaired: list[str] = []
        for group in groups:
            group_tokens = group.split()
            if len(group_tokens) >= 2 and all(len(token) == 1 for token in group_tokens):
                repaired.append("".join(group_tokens))
            else:
                repaired.append(group)
        normalized = " ".join(part for part in repaired if part).strip()
        if normalized and normalized != message.strip():
            LOGGER.info(
                "chat_character_spacing_repaired",
                correlation_id=correlation_id,
                original_length=len(message),
                normalized_length=len(normalized),
            )
            return normalized
        return message

    def _needs_history_context(self, user_message: str, history: str) -> bool:
        """Return true when a user message likely depends on earlier chat turns."""
        if not history:
            return False
        normalized = " ".join(user_message.lower().split())
        if not normalized:
            return False
        word_count = len(normalized.split())
        return word_count <= 14 and self._contains_follow_up_marker(normalized)

    def _contains_follow_up_marker(self, normalized_message: str) -> bool:
        """Match follow-up words as complete phrases, never inside policy terms."""
        for marker in FOLLOW_UP_CONTEXT_MARKERS:
            escaped_marker = re.escape(marker).replace(r"\ ", r"\s+")
            if re.search(
                rf"(?<!\w){escaped_marker}(?!\w)",
                normalized_message,
                flags=re.UNICODE,
            ):
                return True
        return False

    def _latest_context_anchor(self, user_messages: list[str]) -> str:
        """Return the latest self-contained user question behind chained follow-ups."""
        for message in reversed(user_messages):
            if not self._is_context_dependent_message(message):
                return message
        return user_messages[-1]

    def _is_context_dependent_message(self, user_message: str) -> bool:
        """Identify short references that cannot be retrieved safely on their own."""
        normalized = " ".join(user_message.lower().split())
        if not normalized:
            return False
        return len(normalized.split()) <= 14 and self._contains_follow_up_marker(normalized)

    def _user_messages_from_history(self, history: str) -> list[str]:
        """Extract prior user messages from compact session history."""
        messages: list[str] = []
        for line in history.splitlines():
            role, separator, content = line.partition(":")
            if separator and role.strip().lower() == "user":
                cleaned = content.strip()
                if cleaned:
                    messages.append(cleaned)
        return messages

    def _evaluate_governance(self, text: str, body: ChatRequest, correlation_id: str) -> GovernanceDecision:
        """Run unified governance checks for input or output text."""
        return self.governance_engine.evaluate(
            text=text,
            country=body.country,
            language=body.language,
            role=body.role,
            correlation_id=correlation_id,
        )

    def _governance_fallback(
        self,
        decision: GovernanceDecision,
        correlation_id: str,
        language: str = "en",
        country: str = "",
        message: str = "",
    ) -> ChatResponse:
        """Return a safe fallback when governance blocks the request or response."""
        user_message = self._governance_user_message(decision, language, country, message)
        failure_layer = self._governance_failure_layer(decision)
        LOGGER.warning(
            "governance_fallback_response",
            correlation_id=correlation_id,
            provider=decision.provider,
            risk=decision.risk_level.value,
            risk_action=decision.risk_action.value,
            guardrail_action=decision.guardrail_action.value,
            internal_reason=decision.reason,
            failure_layer=failure_layer,
        )
        return self.response_builder.fallback(
            user_message,
            correlation_id,
            metadata={
                "failure_layer": failure_layer,
                "governance_provider": decision.provider,
                "governance_reason": decision.reason,
            },
        )

    def _governance_failure_layer(self, decision: GovernanceDecision) -> str:
        """Classify governance failures for diagnostics."""
        if decision.provider == "bedrock_guardrails":
            return "local_guardrail"
        if decision.guardrail_action.value.lower() == "block":
            return "local_guardrail"
        return "risk_policy"

    def _low_confidence_failure_layer(self, exc: LowConfidenceError) -> str:
        """Classify retrieval/model confidence failures for diagnostics."""
        if isinstance(exc, RetrievalMissError):
            return "retrieval_miss"
        if isinstance(exc, LowConfidenceThresholdError):
            return "low_confidence"
        return "low_confidence"

    def _governance_user_message(
        self,
        decision: GovernanceDecision,
        language: str = "en",
        country: str = "",
        message: str = "",
    ) -> str:
        """Convert internal governance reasons into user-friendly copy."""
        risk_issues = (decision.metadata or {}).get("risk", {}).get("issues", [])
        issue_codes = {str(issue.get("code", "")).lower() for issue in risk_issues}
        guardrail_topic = str((decision.metadata or {}).get("topic", "")).lower()

        if guardrail_topic == "income_claim" or any("income" in code for code in issue_codes):
            return localized_conversation_response("income_claim", language) or FALLBACK_RESPONSES["income_claim"]
        if guardrail_topic == "medical_claim" or any("medical" in code or "health" in code for code in issue_codes):
            claim_response, _ = localized_claim_response(message, "medical_claim", country, language)
            if claim_response:
                return claim_response
            return localized_conversation_response("medical_claim", language) or FALLBACK_RESPONSES["medical_claim"]
        if guardrail_topic == "off_topic":
            return localized_conversation_response("off_topic", language) or FALLBACK_RESPONSES["off_topic"]
        if decision.reason == "Governance provider failed.":
            return localized_conversation_response("bedrock_error", language) or FALLBACK_RESPONSES["bedrock_error"]
        if decision.reason in {
            "Request blocked by high-risk policy.",
            "Request blocked by risk policy.",
        }:
            return localized_conversation_response("off_topic", language) or FALLBACK_RESPONSES["off_topic"]
        return (
            decision.reason
            or (
                "I'm sorry, but I can't help with that question. AskVera can help with approved "
                "Forever Living company policies and information from the global office directory."
            )
        )

    def _insufficient_evidence_message(self, language: str = "en") -> str:
        """Use the approved fallback while remaining compatible with older config."""
        return localized_conversation_response("insufficient_evidence", language) or FALLBACK_RESPONSES.get(
            "insufficient_evidence",
            FALLBACK_RESPONSES.get(
                "low_confidence",
                "I couldn't find a clear answer in the approved information available to me.",
            ),
        )

    def _static_assistant_response(self, body: ChatRequest, correlation_id: str) -> ChatResponse:
        """Return controlled non-policy responses without retrieval."""
        answer = assistant_meta_response(body.message, body.language)
        if not answer:
            answer = localized_conversation_response("greeting", body.language) or "Hello, I'm AskVera. How can I help?"
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={"intent": "assistant_meta", "fallback": False, "response_source": "template"},
        )

    def _early_conversation_response(
        self,
        scrubbed_input: str,
        body: ChatRequest,
        correlation_id: str,
    ) -> ChatResponse | None:
        """Handle privacy and exact zero-token conversation routes before retrieval."""
        if contains_sensitive_pii_placeholder(scrubbed_input):
            return self.response_builder.fallback(
                localized_conversation_response("sensitive_pii", body.language)
                or (
                    "For your privacy, I removed sensitive personal information from your message. "
                    "AskVera does not use or save government IDs, payment details, passwords, or other "
                    "sensitive identifiers. Please ask again without personal details."
                ),
                correlation_id,
                metadata={
                    "fallback": False,
                    "failure_layer": "sensitive_pii_input",
                    "response_source": "privacy",
                    "input_pii_scrubbed": True,
                },
            )
        if classify_intent(scrubbed_input, body.language) == "assistant_meta":
            return self._static_assistant_response(body, correlation_id)
        return None

    def _conversation_route_response(
        self,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
    ) -> ChatResponse | None:
        """Convert a high-confidence semantic route into controlled response copy."""
        metadata = retrieval_result.metadata or {}
        client_action = str(metadata.get("client_action") or "")
        intent = str(metadata.get("conversation_intent") or "knowledge")
        subtype = str(metadata.get("conversation_subtype") or "")

        if client_action == "open_support_form":
            return self.response_builder.fallback(
                localized_conversation_response("support_request", body.language)
                or "Opening the support request form.",
                correlation_id,
                metadata={
                    "fallback": False,
                    "response_source": "client_action",
                    "client_action": client_action,
                    "intent": "support_request",
                },
            )

        response_key = ""
        if intent == "assistant_meta":
            # The planner is advisory. Only reviewed exact phrases may produce
            # assistant identity/capability copy.
            if classify_intent(body.message, body.language) == "assistant_meta":
                response_key = (
                    subtype
                    if subtype in {"greeting", "capability", "thanks", "wellbeing", "casual"}
                    else "capability"
                )
            else:
                intent = "off_topic"
                response_key = "off_topic"
        elif intent == "medical_claim":
            answer, claim_scope = localized_claim_response(body.message, intent, body.country, body.language)
            if answer:
                return self.response_builder.fallback(
                    answer,
                    correlation_id,
                    metadata={
                        "intent": claim_scope,
                        "fallback": False,
                        "response_source": "reviewed_claim_copy",
                    },
                )
            response_key = intent
        elif intent in {"income_claim", "off_topic"}:
            response_key = intent
        if not response_key:
            return None

        answer = localized_conversation_response(response_key, body.language)
        if not answer:
            return None
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "intent": intent,
                "fallback": False,
                "response_source": "semantic_route",
            },
        )

    def _route_or_approve_evidence(
        self,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        scrubbed_input: str,
        body: ChatRequest,
        correlation_id: str,
    ) -> tuple[ChatResponse | None, RetrievalResult, EvidenceDecision | None]:
        """Resolve semantic routes or enforce the evidence gate for knowledge requests."""
        routed_response = self._conversation_route_response(retrieval_result, body, correlation_id)
        if routed_response:
            append_session_turn(body.sessionId, scrubbed_input, routed_response.answer, correlation_id)
            return routed_response, retrieval_result, None

        evidence_decision = approve_evidence(retrieval_query, retrieval_result, body.country, body.language)
        approved_result = with_approved_evidence(retrieval_result, evidence_decision)
        if evidence_decision.approved:
            unsupported_years = unsupported_requested_years(body.message, approved_result.documents)
            if unsupported_years:
                template = localized_conversation_response("period_not_covered", body.language) or (
                    "The approved documents available to me do not contain information for {period}. "
                    "I cannot speculate about policy changes outside the documented period."
                )
                answer = format_period_not_covered(template, unsupported_years)
                fallback = self._validate_response(
                    self.response_builder.fallback(
                        answer,
                        correlation_id,
                        metadata={
                            "fallback": False,
                            "failure_layer": "document_period_not_covered",
                            "response_source": "period_scope_guard",
                            "requested_periods": unsupported_years,
                        },
                    ),
                    body,
                    correlation_id,
                )
                append_session_turn(body.sessionId, scrubbed_input, fallback.answer, correlation_id)
                return fallback, approved_result, evidence_decision
            return None, approved_result, evidence_decision

        LOGGER.warning(
            "evidence_decision_rejected",
            correlation_id=correlation_id,
            country=body.country,
            language=body.language,
            role=body.role,
            **evidence_decision.to_metadata(),
        )
        clarification = self._directory_clarification_response(
            retrieval_result,
            body,
            correlation_id,
            scrubbed_input,
        )
        if clarification:
            return clarification, approved_result, evidence_decision
        fallback = self._validate_response(
            self.response_builder.fallback(
                self._insufficient_evidence_message(body.language),
                correlation_id,
                metadata={
                    "failure_layer": "evidence_gate",
                    "evidence_decision": evidence_decision.to_metadata(),
                },
            ),
            body,
            correlation_id,
            retrieval_result=approved_result,
        )
        return fallback, approved_result, evidence_decision

    def _directory_clarification_response(
        self,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        scrubbed_input: str,
    ) -> ChatResponse | None:
        """Ask for the missing directory detail when approved evidence is ambiguous.

        This is deliberately narrow: governance has already run, and the response
        is used only when the planner searched global directory content but could
        not approve a sufficiently clear answer. It never weakens guardrails or
        invents a country, office, phone number, or other contact value.
        """
        metadata = retrieval_result.metadata or {}
        if not metadata.get("global_documents_searched"):
            return None
        if not metadata.get("candidate_count") or not DIRECTORY_DETAIL_TERMS.search(body.message or ""):
            return None
        answer = (
            "I found approved directory information, but I need one more detail to answer accurately. "
            "Are you asking for the telephone number, business hours, email address, office address, "
            "website, or sponsoring information?"
        )
        response = self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "failure_layer": "directory_clarification",
                "response_source": "directory_clarification",
                "fallback": False,
            },
            cards=[
                {"id": "directory-telephone", "label": "Telephone number", "prompt": "What is the telephone number for that country?"},
                {"id": "directory-hours", "label": "Business hours", "prompt": "What are the business hours for that country?"},
                {"id": "directory-email", "label": "Email address", "prompt": "What is the email address for that country?"},
                {"id": "directory-address", "label": "Office address", "prompt": "What is the office address for that country?"},
                {"id": "directory-website", "label": "Website", "prompt": "What is the website for that country?"},
                {"id": "directory-sponsoring", "label": "Sponsoring information", "prompt": "What sponsoring information is available for that country?"},
            ],
        )
        append_session_turn(body.sessionId, scrubbed_input, response.answer, correlation_id)
        return response

    def _validate_response(
        self,
        chat_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
        model_response: ModelResponse | None = None,
        retrieval_result: RetrievalResult | None = None,
    ) -> ChatResponse:
        """Validate a chat response and return a safe fallback for critical failures."""
        result = self.output_validator.validate(
            ValidationContext(
                chat_response=chat_response,
                model_response=model_response,
                retrieval_result=retrieval_result,
                country=body.country,
                language=body.language,
                role=body.role,
                correlation_id=correlation_id,
            )
        )
        if result.issues:
            LOGGER.warning(
                "output_validator_issues_detected",
                correlation_id=correlation_id,
                issue_count=len(result.issues),
                highest_severity=result.highest_severity.value,
                issues=[
                    {
                        "code": issue.code,
                        "severity": issue.severity.value,
                        "field": issue.field,
                        "message": issue.message[:500],
                    }
                    for issue in result.issues
                ],
            )
        if result.has_critical():
            critical_codes = {
                str(issue.code).upper()
                for issue in result.issues
                if issue.severity.value.upper() == "CRITICAL"
            }
            if (
                critical_codes
                and all(code == "NUMERIC_CLAIM_UNGROUNDED" for code in critical_codes)
                and retrieval_result is not None
                and retrieval_result.documents
            ):
                repaired_answer, removed_numbers = remove_unsupported_numeric_sentences(
                    chat_response.answer,
                    retrieval_result.documents,
                )
                if repaired_answer and repaired_answer != chat_response.answer:
                    repaired_response = ChatResponse(
                        answer=repaired_answer,
                        citations=chat_response.citations,
                        suggestions=chat_response.suggestions,
                        cards=chat_response.cards,
                        confidence=chat_response.confidence,
                        metadata={
                            **(chat_response.metadata or {}),
                            "numeric_claim_repair": True,
                            "removed_numeric_claims": removed_numbers,
                        },
                        correlation_id=chat_response.correlation_id,
                    )
                    repaired_result = self.output_validator.validate(
                        ValidationContext(
                            chat_response=repaired_response,
                            model_response=model_response,
                            retrieval_result=retrieval_result,
                            country=body.country,
                            language=body.language,
                            role=body.role,
                            correlation_id=correlation_id,
                        )
                    )
                    if not repaired_result.has_critical():
                        LOGGER.warning(
                            "output_validator_numeric_claims_repaired",
                            correlation_id=correlation_id,
                            removed_numeric_claims=removed_numbers,
                        )
                        return self._with_validation_metadata(repaired_response, repaired_result)
            failure_layer = self._validation_failure_layer(result)
            LOGGER.warning(
                "output_validator_critical_fallback",
                correlation_id=correlation_id,
                issue_count=len(result.issues),
                highest_severity=result.highest_severity.value,
                failure_layer=failure_layer,
                critical_issue_codes=[
                    issue.code
                    for issue in result.issues
                    if issue.severity.value.upper() == "CRITICAL"
                ],
            )
            return self._with_validation_metadata(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language),
                    correlation_id,
                    metadata={"failure_layer": failure_layer},
                ),
                result,
            )
        return self._with_validation_metadata(chat_response, result)

    def _validation_failure_layer(self, result: ValidationResult) -> str:
        """Classify critical validation failures for diagnostics."""
        critical_codes = {
            str(issue.code).lower()
            for issue in result.issues
            if issue.severity.value.upper() == "CRITICAL"
        }
        if any("numeric" in code or "ground" in code for code in critical_codes):
            return "numeric_validator"
        if any("citation" in code for code in critical_codes):
            return "citation_validator"
        return "output_validator"

    def _with_validation_metadata(self, chat_response: ChatResponse, result: ValidationResult) -> ChatResponse:
        """Attach validation summary metadata without changing the public API response."""
        return ChatResponse(
            answer=chat_response.answer,
            citations=chat_response.citations,
            suggestions=chat_response.suggestions,
            cards=chat_response.cards,
            confidence=chat_response.confidence,
            metadata={
                **(chat_response.metadata or {}),
                "validation": validation_summary(result),
            },
            correlation_id=chat_response.correlation_id,
        )

    def _should_cache_response(self, chat_response: ChatResponse) -> bool:
        """Return true only for complete model answers that are safe to reuse."""
        metadata = chat_response.metadata or {}
        if metadata.get("fallback"):
            return False

        # Guardrail safety copy should be generated fresh and must never be
        # replayed as though it were a document-grounded policy response.
        if metadata.get("failure_layer") or metadata.get("response_source") in {"guardrail", "client_action"}:
            return False

        validation = metadata.get("validation")
        if isinstance(validation, dict) and str(validation.get("highestSeverity", "")).upper() == "CRITICAL":
            return False

        if float(chat_response.confidence or 0.0) < settings.BEDROCK_MIN_CONFIDENCE:
            return False

        return bool((chat_response.answer or "").strip())

    def _should_semantic_cache_response(self, chat_response: ChatResponse) -> bool:
        """Require strong, cited evidence before an answer can be reused semantically."""
        return (
            self._should_cache_response(chat_response)
            and bool(chat_response.citations)
            and float(chat_response.confidence or 0.0) >= settings.SEMANTIC_CACHE_MIN_CONFIDENCE
        )

    def _cache_response(
        self,
        cache_key: str,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        chat_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
    ) -> None:
        """Write exact cache and the more restrictive semantic cache."""
        if not self._should_cache_response(chat_response):
            LOGGER.info(
                "cache_write_skipped",
                correlation_id=correlation_id,
                reason="unsafe_or_low_confidence_response",
            )
            return
        cache_value = chat_response.to_cache_value()
        set_cache_value(cache_key, cache_value, correlation_id)
        if self._should_semantic_cache_response(chat_response):
            set_semantic_cache_value(
                retrieval_query,
                body.country,
                body.language,
                body.role,
                retrieval_result,
                cache_value,
                correlation_id,
            )


ai_orchestrator = AIOrchestrator()
