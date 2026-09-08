"""AI chat orchestration for AskVera."""

import re
from dataclasses import replace
from time import perf_counter

from botocore.exceptions import BotoCoreError, ClientError

from app.metrics.health import record_validation_outcome
from app.metrics.responses import record_delivered_response, record_numeric_repair
from app.models.responses import ModelResponse
from app.orchestrator.compound_requests import separate_question_and_command
from app.operations import pipeline_trace_store
from app.models.router import ModelRouter, model_router
from app.evidence import (
    EvidenceDecision,
    assistant_meta_response,
    approve_evidence,
    classify_intent,
    is_planner_trusted_low_risk_subtype,
    localized_conversation_response,
    mentions_out_of_corpus_topic,
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
from app.retrieval import RetrievalService, confidence_from_sources, retrieval_service
from app.retrieval.models import RetrievalResult
from app.retrieval.cache_evidence import restore_evidence, serialize_evidence
from app.governance import GovernanceDecision, GovernanceEngine, governance_engine
from app.validation import OutputValidator, ValidationContext, ValidationResult, output_validator, validation_summary
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences
from config import settings
from config.vera_persona import FALLBACK_RESPONSES
from services.audit import write_audit_event
from services.aws_clients import get_aws_clients
from services.candidate_control import CandidateFlags, get_candidate_flags
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
from services.guardrails import is_policy_safety_question
from services.market_config import find_market_mentions, find_probable_market_typo
from services.pii import contains_sensitive_pii_placeholder, remove_unresolved_pii_placeholders, scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
from utils.exceptions import SessionExpiredError
from utils.exceptions import LowConfidenceError, LowConfidenceThresholdError, RetrievalMissError
from utils.inline_citations import separate_verified_citations
from utils.directory_fields import (
    parse_directory_fields,
    preserve_directory_role_labels,
    correct_directory_source_contradictions,
    remove_unrequested_directory_fields,
    restore_missing_directory_contacts,
    restore_missing_requested_directory_fields,
    restore_missing_requested_order_size,
)
from utils.logging import get_logger
from utils.validators import ChatRequest

LOGGER = get_logger("app.orchestrator")
# Reference follow-ups point back at the prior answer with no new subject of
# their own ("elaborate", "what else") - retrieval should reuse the prior
# self-contained question as-is.
FOLLOW_UP_REFERENCE_MARKERS = (
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
# Topic-shift follow-ups carry a new subject alongside an implicit reference
# to the prior question's frame ("what about Kenya?", "and in Kenya?").
# Retrieval needs both the prior topic and the new subject, so these are
# merged with the anchor question instead of replacing it.
FOLLOW_UP_TOPIC_SHIFT_MARKERS = (
    "what about",
    "how about",
    "what if",
)
FOLLOW_UP_CONTEXT_MARKERS = FOLLOW_UP_REFERENCE_MARKERS + FOLLOW_UP_TOPIC_SHIFT_MARKERS
# A follow-up that opens like a question and asks for no new content is judged on
# its own words rather than on the question it inherits for retrieval. Both lists
# are deliberately narrow: anything unmatched keeps the inherited context, which
# is the safer direction. See AIOrchestrator._governance_text.
QUESTION_OPENERS = re.compile(
    r"^(?:what|how|when|where|which|who|why|whose|whom|is|are|was|were|do|does|did|can|could|"
    r"should|would|will|may|might|has|have|had)\b",
    re.IGNORECASE,
)
# "Do it anyway" opens with an auxiliary verb but continues an instruction rather
# than asking anything. Those cues keep the inherited context.
CONTINUATION_TERMS = re.compile(
    r"\b(?:anyway|anyhow|regardless|nonetheless|go\s+ahead|do\s+it|just\s+do|carry\s+on|"
    r"continue|proceed)\b",
    re.IGNORECASE,
)
# A message that opens with an instruction to produce something, and asks nothing,
# is a command rather than a question. Leading position matters: "Belgium, write
# the number down" is not what this targets, and a question containing any of
# these verbs keeps its question mark and is not matched.
LEADING_INSTRUCTION = re.compile(
    r"^(?:then\s+|now\s+|ok(?:ay)?[,\s]+|so\s+|just\s+|please\s+|and\s+)*"
    r"(?:just\s+|please\s+)*"
    r"(?:write|create|draft|generate|make|compose|post|publish|send|give\s+me|show\s+me)\b",
    re.IGNORECASE,
)
CONTENT_REQUEST_TERMS = re.compile(
    r"\b(?:write|writing|create|creating|make|making|draft|drafting|compose|composing|generate|"
    r"generating|produce|producing|post|posting|publish|publishing|send|sending|word|phrase|"
    r"caption|captions|script|slogan|tagline|testimonial|advert\w*|ad\s+copy|claim|claims|"
    r"promise|promises|guarantee|guarantees|guaranteed)\b",
    re.IGNORECASE,
)
DIRECTORY_DETAIL_TERMS = re.compile(
    r"\b(address|office|business\s+hours?|office\s+hours?|telephone|phone|email|website|contact|sponsor)\b",
    re.IGNORECASE,
)
# Maps a directory clarification card's id to the wording that names that
# specific field unambiguously. "office"/"contact" are deliberately absent -
# both are too generic to pin down a single field on their own, so a message
# containing only those still counts as ambiguous. Used to detect when the
# user already named exactly one field, so _directory_clarification_response
# doesn't ask them to choose again from a card that duplicates what they
# already said (TRB-19189-follow-up, reported after deploy).
DIRECTORY_FIELD_TERMS: dict[str, re.Pattern[str]] = {
    "directory-telephone": re.compile(r"\b(telephone|phone)\b", re.IGNORECASE),
    "directory-hours": re.compile(r"\b(business\s+hours?|office\s+hours?|hours)\b", re.IGNORECASE),
    "directory-email": re.compile(r"\bemail\b", re.IGNORECASE),
    # Excludes "address" inside "email address" (e.g. "what's the email
    # address for the UK office?") - without this, that phrase matches both
    # directory-email and directory-address, so len(named_fields) != 1 and
    # the field is (wrongly) never treated as already specified, producing
    # an unresolvable loop: the generic "which detail?" clarification fires
    # again even after the user names or clicks "Email address".
    "directory-address": re.compile(r"(?<!email\s)\baddress\b", re.IGNORECASE),
    "directory-website": re.compile(r"\bwebsite\b", re.IGNORECASE),
    "directory-sponsoring": re.compile(r"\bsponsor\w*\b", re.IGNORECASE),
}
# Deliberately directory-shaped so the retrieval planner's existing global-
# directory intent classification picks it up; carries no country name so it
# falls back to the request's own selected country.
OFFICE_CONTACT_LOOKUP_QUERY = "What is the office phone number, email address, and website for this country?"
OFFICE_CONTACT_FIELD_RE = re.compile(r"phone|telephone|email|e-mail", re.IGNORECASE)


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

        # Admin-portal "current vs experimental" toggle (services/candidate_control.py) -
        # read once per request and threaded down explicitly, rather than each
        # hook point calling get_candidate_flags() itself, so every function
        # below stays a pure, DB-free call when exercised directly (as most
        # unit tests do) and only this one entry point pays the lookup cost.
        candidate_flags = get_candidate_flags()
        scrubbed_input = scrub_pii(
            body.message,
            correlation_id,
            body.language,
            preserve_location_names=True,
            preserve_person_names=True,
        )
        response = self._mixed_request_response(body, scrubbed_input, correlation_id, candidate_flags)
        if response is None:
            response = self._handle_scrubbed_chat(body, scrubbed_input, correlation_id, candidate_flags)
        # Persist the original request and the actual delivered response exactly
        # once, including refusals, cache hits and partial mixed-intent answers.
        append_session_turn(body.sessionId, scrubbed_input, response.answer, correlation_id)
        # Counted at the same single choke point, and for the same reason: this
        # is the one place every return path has converged, so the fallback rate
        # measures what was actually delivered rather than what one branch
        # intended. Sessions that raise above (expired, consent) are not
        # deliveries and are correctly absent.
        record_delivered_response(response.metadata)
        return response

    def _mixed_request_response(
        self, body: ChatRequest, scrubbed_input: str, correlation_id: str, candidate_flags: CandidateFlags,
    ) -> ChatResponse | None:
        parts = separate_question_and_command(scrubbed_input)
        if parts is None:
            return None
        question, command = parts
        question_decision = self._evaluate_governance(question, body, correlation_id)
        command_decision = self._evaluate_governance(command, body, correlation_id)
        metadata = command_decision.metadata or {}
        issue_codes = {str(issue.get("code", "")) for issue in metadata.get("risk", {}).get("issues", [])}
        explicit_refusal = metadata.get("topic") in {"income_claim", "medical_claim", "off_topic"} or bool(
            issue_codes & {"INCOME_CLAIM_RISK", "MEDICAL_CLAIM_RISK"})
        if (not question_decision.allowed or command_decision.allowed or not explicit_refusal
                or metadata.get("providerError")):
            return None
        # Preserve every scope/session field. The unsafe command never enters
        # retrieval, the model prompt, or the safe-question cache key.
        safe_body = body.model_copy(update={"message": question})
        response = self._handle_scrubbed_chat(safe_body, question, correlation_id, candidate_flags)
        decline = self._governance_user_message(
            command_decision, body.language, body.country, command, correlation_id,
        )
        return self._replace_answer(response, f"{response.answer}\n\n{decline}", {
            "mixed_intent": True, "refused_part_count": 1,
        })

    def _handle_scrubbed_chat(
        self, body: ChatRequest, scrubbed_input: str, correlation_id: str, candidate_flags: CandidateFlags,
    ) -> ChatResponse:
        """Run the normal checked pipeline; the entry point owns turn persistence."""
        chat_response = self._early_conversation_response(
            scrubbed_input, body, correlation_id, candidate_flags
        )
        if chat_response:
            return chat_response
        history = get_session_history(body.sessionId, correlation_id)
        retrieval_query = self._build_retrieval_query(scrubbed_input, history, correlation_id)
        request_query = self._build_request_query(scrubbed_input, retrieval_query, history)
        governance_decision = self._evaluate_governance(
            self._governance_text(scrubbed_input, request_query), body, correlation_id
        )
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message, candidate_flags
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
            candidate_flags,
            history,
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
            if candidate_flags.narrowing_fallback:
                narrowing_response = self._candidate_narrowing_response(body, correlation_id, history)
                if narrowing_response:
                    return self._validate_response(
                        narrowing_response,
                        body,
                        correlation_id,
                        retrieval_result=retrieval_result,
                    )
            return self._validate_response(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language, body.message),
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
                    self._insufficient_evidence_message(body.language, body.message),
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
        governance_decision = self._evaluate_governance(
            chat_response.answer,
            body,
            correlation_id,
            allow_claim_topics=self._answer_explains_reviewed_policy(body, chat_response),
        )
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message, candidate_flags
            )
        self._record_semantic_shadow_result(
            semantic_candidate,
            chat_response,
            body,
            correlation_id,
            semantic_lookup_ms,
        )
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
        citation_cleaned = separate_verified_citations(chat_response.answer, retrieval_result.documents)
        if citation_cleaned != chat_response.answer:
            chat_response = self._replace_answer(chat_response, citation_cleaned, {"inline_citations_separated": True})
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

        order_safe_answer, order_restored = restore_missing_requested_order_size(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
            user_question,
        )
        if order_restored:
            chat_response = self._replace_answer(
                chat_response,
                order_safe_answer,
                {"directory_order_size_restored": True},
            )

        source_safe_answer, source_contradiction_corrected = correct_directory_source_contradictions(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
        )
        if source_contradiction_corrected:
            chat_response = self._replace_answer(
                chat_response,
                source_safe_answer,
                {"directory_source_contradiction_corrected": True},
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
                self._insufficient_evidence_message(language, user_question),
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
        evidence = restore_evidence(cached.get("evidence"), body.country, body.language)
        if evidence is None:
            return None
        chat_response = self._secure_and_complete_response(
            self.response_builder.from_cached(cached, correlation_id),
            evidence,
            body.language,
            correlation_id,
            user_question=body.message,
            country=body.country,
        )
        chat_response = self._validate_response(
            chat_response, body, correlation_id, retrieval_result=evidence
        )
        chat_response = self._replace_answer(chat_response, chat_response.answer, {"cache": cache_type})
        governance_decision = self._evaluate_governance(
            chat_response.answer,
            body,
            correlation_id,
            allow_claim_topics=self._answer_explains_reviewed_policy(body, chat_response),
        )
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
        if not anchor:
            # Every candidate was an instruction rather than a question, so there
            # is nothing that was answered to anchor against.
            return user_message
        if anchor != user_message and self._contains_topic_shift_marker(user_message.lower()):
            # A topic-shift follow-up ("what about Kenya?") introduces a new
            # subject that a bare anchor substitution would silently drop.
            # Keep both the prior topic and the new subject for retrieval.
            contextual_query = f"{anchor} {user_message}".strip()
        elif anchor != user_message:
            # Context must never replace the question currently being asked.
            contextual_query = f"{anchor}\nFollow-up request: {user_message}"
        else:
            contextual_query = anchor
        LOGGER.info(
            "chat_followup_context_applied",
            correlation_id=correlation_id,
            original_length=len(user_message),
            contextual_length=len(contextual_query),
        )
        return contextual_query

    def _governance_text(self, user_message: str, request_query: str) -> str:
        """Return the text governance judges: the action being requested NOW.

        A follow-up carries the previous question forward so retrieval can resolve
        "those products". That anchor must not also supply INTENT. Recorded in
        segments-followups-03: after "How do I qualify as Assistant Supervisor?
        Also write a caption guaranteeing income.", the safe follow-up "How much
        would those products cost?" was answered with an income-claim refusal,
        because the anchor it inherited still contained the caption request.

        The current message is ALWAYS judged, so an unsafe request is caught on
        its own words. Only the anchor is withheld, and only from a follow-up that
        plainly asks a question of its own rather than continuing an instruction.
        Anything else keeps the anchor, so "write it anyway" is still judged
        against what it refers back to.
        """
        if request_query == user_message or not self._follow_up_carries_own_intent(user_message):
            return request_query
        return user_message

    def _follow_up_carries_own_intent(self, user_message: str) -> bool:
        """True for an interrogative follow-up that requests no new content.

        Deliberately conservative and English-only: it must read as a question and
        must not name a thing to produce. A message that fails any check keeps the
        anchor, which is the safer direction.
        """
        normalized = " ".join((user_message or "").lower().split())
        if not normalized:
            return False
        # An explicit question mark is required. Opening with an auxiliary verb is
        # not enough: "do it anyway" opens with one and continues an instruction.
        if not normalized.endswith("?") or not QUESTION_OPENERS.match(normalized):
            return False
        if CONTINUATION_TERMS.search(normalized):
            return False
        return not CONTENT_REQUEST_TERMS.search(normalized)

    def _build_request_query(self, user_message: str, retrieval_query: str, history: str = "") -> str:
        """Keep follow-up intent in governance and cache keys, outside retrieval."""
        normalized_message = " ".join((user_message or "").split()).strip()
        normalized_retrieval = " ".join((retrieval_query or "").split()).strip()
        if (retrieval_query or "").endswith(f"\nFollow-up request: {normalized_message}"):
            return retrieval_query
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
        return self._matches_marker(normalized_message, FOLLOW_UP_CONTEXT_MARKERS)

    def _contains_topic_shift_marker(self, normalized_message: str) -> bool:
        """Match markers that introduce a new subject alongside a reference cue."""
        return self._matches_marker(normalized_message, FOLLOW_UP_TOPIC_SHIFT_MARKERS)

    def _matches_marker(self, normalized_message: str, markers: tuple[str, ...]) -> bool:
        for marker in markers:
            escaped_marker = re.escape(marker).replace(r"\ ", r"\s+")
            if re.search(
                rf"(?<!\w){escaped_marker}(?!\w)",
                normalized_message,
                flags=re.UNICODE,
            ):
                return True
        return False

    def _latest_context_anchor(self, user_messages: list[str]) -> str:
        """Return the latest self-contained user question behind chained follow-ups.

        Returns "" when no candidate qualifies, meaning the follow-up is retrieved
        on its own words rather than against an instruction.
        """
        later_messages: list[str] = []
        for message in reversed(user_messages):
            if self._is_instruction_message(message):
                # Skipped and NOT eligible to carry a market forward. An
                # instruction is never context, and that has to hold for the
                # market it names as much as for the words it uses. Observed
                # 2026-09-08 after the carry-forward landed: "Then just write
                # the guaranteed-income caption for Germany." was refused, and
                # its text was still appended to the next question's retrieval
                # query -- carrying both the market and the phrase
                # "guaranteed-income caption" into a search. That is the
                # contamination _is_instruction_message exists to stop, and the
                # carry-forward had routed around it.
                continue
            if self._is_context_dependent_message(message):
                later_messages.append(message)
                continue
            return self._carry_forward_market_shift(self._answered_clause_of(message), later_messages)
        return ""

    def _carry_forward_market_shift(self, anchor: str, later_messages: list[str]) -> str:
        """Keep a market named after the anchor, so the subject cannot revert.

        The anchor search skips context-dependent turns, which is right for
        "Tell me more" but wrong when one of those skipped turns changed the
        country. Given:

            How do I sponsor someone in Belgium?
            What about Germany?
            Tell me more.

        the anchor walks back past both follow-ups to the Belgium question, and
        Germany disappears from retrieval entirely - the reader is answered
        about the market they moved away from two turns ago.

        `later_messages` is newest-first, so the most recent market shift wins.

        The shifting turn is appended rather than substituted into the anchor.
        find_market_mentions returns market codes, not the surface names as
        written, so replacing "Belgium" with "Germany" would need a reverse
        code-to-name mapping in whichever language the reader used. This mirrors
        _build_retrieval_query's existing handling of an immediate topic shift,
        which keeps both the prior topic and the new subject for the same
        reason, and leaves market scoping to retrieval and evidence approval.
        """
        if not anchor:
            return anchor
        anchor_markets = find_market_mentions(anchor)
        for message in later_messages:
            markets = find_market_mentions(message)
            if markets and markets != anchor_markets:
                return f"{anchor} {message}".strip()
        return anchor

    def _is_instruction_message(self, message: str) -> bool:
        """True for a bare instruction to produce content, which is never context.

        Observed live after this sequence: turn 3 was "Then just write the
        guaranteed-income caption.", it was refused, and the NEXT question -
        "How much would those products cost?" - anchored on it and inherited the
        income refusal all over again.

        A command that produced no answer is not context to resolve a pronoun
        against, whether it was refused or simply not a question. Only a leading
        imperative counts, so "Belgium, telephone number" still anchors normally.
        """
        normalized = " ".join((message or "").lower().split())
        if not normalized or "?" in normalized:
            return False
        return bool(LEADING_INSTRUCTION.match(normalized))

    def _answered_clause_of(self, message: str) -> str:
        """Anchor a follow-up on the question that was answered, not the refusal.

        A split request keeps both clauses in history, so anchoring on the whole
        message carries the declined command into the next turn. Confirmed on the
        deployed build: after "How do I qualify as Assistant Supervisor? Also
        write a caption guaranteeing income.", the follow-up "How much would those
        products cost?" reached the query planner still carrying the caption
        request, was classified income_claim at 0.85, skipped retrieval entirely
        and returned the income refusal.

        Carrying a refused clause forward is wrong regardless of what it triggers:
        it was never answered, so it is not context. Splitting is the same
        conservative syntax check used to answer the turn, and a message that does
        not split is anchored unchanged.
        """
        parts = separate_question_and_command(message)
        return parts[0] if parts else message

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

    def _evaluate_governance(
        self,
        text: str,
        body: ChatRequest,
        correlation_id: str,
        *,
        allow_claim_topics: bool = False,
    ) -> GovernanceDecision:
        """Run unified governance checks for input or output text."""
        return self.governance_engine.evaluate(
            text=text,
            country=body.country,
            language=body.language,
            role=body.role,
            correlation_id=correlation_id,
            allow_claim_topics=allow_claim_topics,
        )

    def _answer_explains_reviewed_policy(self, body: ChatRequest, chat_response: ChatResponse) -> bool:
        """True when the answer is the explanation a policy-safety question asked for.

        Verified live 2026-09-07: the pipeline retrieved the governing sections
        (16.02-j Making Product Claims, 16.02-k Making Earnings Claims), generated
        a correct grounded answer, passed all eight validators, and then blocked
        that answer at output governance - because an explanation of a prohibition
        necessarily contains the prohibited vocabulary.

        Deliberately narrow: the question must be one of the reviewed exact
        phrasings, and the answer must cite approved sources. An ungrounded answer
        gets no exemption, and off_topic is never skipped.
        """
        return bool(is_policy_safety_question(body.message) and chat_response.citations)

    def _governance_fallback(
        self,
        decision: GovernanceDecision,
        correlation_id: str,
        language: str = "en",
        country: str = "",
        message: str = "",
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse:
        """Return a safe fallback when governance blocks the request or response."""
        user_message = self._governance_user_message(
            decision, language, country, message, correlation_id, candidate_flags
        )
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
        correlation_id: str = "",
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> str:
        """Convert internal governance reasons into user-friendly copy."""
        risk_issues = (decision.metadata or {}).get("risk", {}).get("issues", [])
        issue_codes = {str(issue.get("code", "")).lower() for issue in risk_issues}
        guardrail_topic = str((decision.metadata or {}).get("topic", "")).lower()

        is_income = guardrail_topic == "income_claim" or any("income" in code for code in issue_codes)
        is_medical = guardrail_topic == "medical_claim" or any(
            "medical" in code or "health" in code for code in issue_codes
        )
        is_off_topic = guardrail_topic == "off_topic"
        if (is_income or is_medical or is_off_topic) and candidate_flags.in_voice_guardrail:
            candidate_topic = "income_claim" if is_income else "medical_claim" if is_medical else "off_topic"
            candidate = self._candidate_guardrail_phrasing(candidate_topic, language, country, correlation_id)
            if candidate:
                return candidate

        if is_income:
            return localized_conversation_response("income_claim", language) or FALLBACK_RESPONSES["income_claim"]
        if is_medical:
            claim_response, _ = localized_claim_response(message, "medical_claim", country, language)
            if claim_response:
                return claim_response
            return localized_conversation_response("medical_claim", language) or FALLBACK_RESPONSES["medical_claim"]
        if is_off_topic:
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
                "Forever Living company policies and information from the international sponsoring directory."
            )
        )

    def _insufficient_evidence_message(self, language: str = "en", user_message: str = "") -> str:
        """Use the approved fallback while remaining compatible with older config.

        A question about prices, the catalogue, stock or order status gets a
        different answer, because "the documents do not contain enough
        information, please rephrase" is not true and not useful: no rephrasing
        will help, since the corpus has never held that content. Observed live
        on 2026-09-07, where "How much does Forever Aloe Vera Gel cost?"
        returned the generic message and the reader was invited to try again.

        The prompt already carries this rule, but evidence approval rejects
        first on these questions, so generation never runs and the rule never
        fires. This is the same statement made on the path that actually
        executes.

        This only ever replaces one fallback with a better one. It is reached
        only after the pipeline has already failed to answer, so a false match
        cannot displace a real answer.
        """
        # A question naming a market keeps the ordinary fallback. The corpus
        # boundary is a statement about the whole corpus -- "those aren't part
        # of the approved documents I work from" -- and that is only safe for
        # subjects the documents never carry for anyone.
        #
        # The sponsoring directory holds per-market commercial detail: minimum
        # order sizes are in it, and delivery terms plausibly are. Observed
        # 2026-09-08, "What is the delivery cost for orders in New Zealand?"
        # received the boundary answer, asserting the documents do not cover it
        # when the directory may well cover it and retrieval simply failed. An
        # unhelpful "I could not find that" is honest; a confident wrong denial
        # is not, and it stops the reader asking again.
        if (
            user_message
            and not find_market_mentions(user_message)
            and mentions_out_of_corpus_topic("catalogue", user_message, language)
        ):
            boundary = localized_conversation_response("catalogue_scope", language)
            if boundary:
                return boundary
        return localized_conversation_response("insufficient_evidence", language) or FALLBACK_RESPONSES.get(
            "insufficient_evidence",
            FALLBACK_RESPONSES.get(
                "low_confidence",
                "I couldn't find a clear answer in the approved information available to me.",
            ),
        )

    def _candidate_narrowing_response(
        self,
        body: ChatRequest,
        correlation_id: str,
        history: str = "",
    ) -> ChatResponse | None:
        """Experimental: ask a narrowing question instead of a flat refusal.

        Gated behind chat_candidate_control.narrowing_fallback_enabled (admin
        portal toggle, services/candidate_control.py). Best-effort only, same
        contract as _office_contact_addendum above: any failure here silently
        returns None so the caller falls through to today's
        _insufficient_evidence_message - this can only ever add helpfulness,
        never break the base fallback path.

        history is passed so the model can see it already asked a clarifying
        question on a prior turn - without it, each turn only sees the
        latest message in isolation and re-asks a similarly generic
        question forever instead of ever converging (observed live: asking
        about a product's price looped through "which product?" ->
        "which detail?" -> "which product?" without ever answering or
        admitting the detail isn't available).
        """
        try:
            system_prompt = (
                "You are AskVera, a company-policy assistant. The user's question "
                "could not be answered from the approved documents available to you. "
                "If the conversation so far shows you already asked a clarifying "
                "question about this same topic (even if worded differently), do "
                "NOT ask another clarifying question - instead say plainly that you "
                "don't have that specific detail in the approved documents, and "
                "suggest contacting Forever Living support or their upline for an "
                "official answer. Otherwise, ask ONE short, specific clarifying "
                "question that would help narrow down what they actually need. Do "
                "not answer the question, do not invent facts, and do not mention "
                "documents, search, or retrieval. Reply in the same language as the "
                "user's question. Return only your response and nothing else."
            )
            user_prompt = f"Conversation so far:\n{history}\n\nLatest message: {body.message}" if history else body.message
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": settings.BEDROCK_CANDIDATE_NARROWING_MAX_OUTPUT_TOKENS},
            )
            text_out = response["output"]["message"]["content"][0].get("text", "").strip()
            if not text_out:
                return None
            return self.response_builder.fallback(
                text_out,
                correlation_id,
                metadata={
                    "failure_layer": "candidate_narrowing_fallback",
                    "response_source": "candidate_narrowing_fallback",
                    "fallback": False,
                },
            )
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError):
            LOGGER.exception("candidate_narrowing_fallback_failed", correlation_id=correlation_id)
            return None

    def _candidate_guardrail_phrasing(
        self,
        topic: str,
        language: str,
        country: str,
        correlation_id: str,
    ) -> str | None:
        """Experimental: phrase a guardrail decline in the model's own words.

        EXPERIMENTAL PLACEHOLDER WORDING - not reviewed by Legal. Only
        reachable via chat_candidate_control.in_voice_guardrail_enabled
        (admin portal toggle), which must stay off anywhere real users could
        see it until Legal's final medical/income-claim wording lands (a
        separate, already-in-flight task). The decision to decline stays
        fully deterministic - the governance/risk-policy layer that reached
        this point is unchanged; only the phrasing below is generated.
        """
        mandatory_elements = {
            "medical_claim": (
                "You must not make or imply any claim that a product can treat, cure, "
                "or prevent a disease or medical condition. You must tell the user to "
                "speak with a qualified healthcare professional for medical questions."
            ),
            "income_claim": (
                "You must not guarantee, predict, or imply any specific earnings or "
                "income outcome. You must make clear individual results vary and "
                "there is no guaranteed income."
            ),
            "off_topic": (
                "You must make clear you can only help with approved Forever Living "
                "company policy and international sponsoring directory information."
            ),
        }.get(topic)
        if mandatory_elements is None:
            return None
        try:
            system_prompt = (
                "You are AskVera, a company-policy assistant. You must decline the "
                "user's request. Write ONE short, natural paragraph declining, in "
                f"the requested language ({language}). {mandatory_elements} Do not "
                "soften, hedge around, or omit these requirements. Do not answer the "
                "underlying question. Return only the decline paragraph and nothing "
                "else."
            )
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": f"Country: {country}. Topic: {topic}."}]}],
                inferenceConfig={"maxTokens": settings.BEDROCK_CANDIDATE_GUARDRAIL_MAX_OUTPUT_TOKENS},
            )
            text_out = response["output"]["message"]["content"][0].get("text", "").strip()
            return text_out or None
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError):
            LOGGER.exception(
                "candidate_guardrail_phrasing_failed", correlation_id=correlation_id, topic=topic
            )
            return None

    def _office_contact_addendum(self, body: ChatRequest, correlation_id: str) -> str | None:
        """Offer a country's directory contact details instead of a bare refusal.

        This is a best-effort, data-driven lookup against the global
        sponsoring/office directory - never a hardcoded per-country table. Any
        failure or empty result silently falls back to today's plain
        insufficient-evidence message; it can only add information, never
        remove or change it.
        """
        if not settings.FALLBACK_OFFICE_CONTACT_ENABLED:
            return None
        try:
            directory_result = self.retriever.retrieve(
                OFFICE_CONTACT_LOOKUP_QUERY,
                body.country,
                body.language,
                body.role,
                correlation_id,
            )
        except Exception:  # noqa: BLE001 - best-effort addition, must never break the fallback path
            LOGGER.exception("office_contact_lookup_failed", correlation_id=correlation_id)
            return None

        record = next(
            (
                document
                for document in directory_result.documents
                if str(document.metadata.get("access_scope") or "").lower() == "global"
            ),
            None,
        )
        if record is None:
            return None

        fields = record.metadata.get("directory_fields")
        if not isinstance(fields, dict) or not fields:
            fields = parse_directory_fields(record.content)
        contact_lines = [
            f"{label}: {value}"
            for label, value in fields.items()
            if OFFICE_CONTACT_FIELD_RE.search(str(label)) and str(value).strip()
        ]
        if not contact_lines:
            return None

        lead_in = localized_conversation_response("office_contact_lead_in", body.language) or (
            "In the meantime, here is a direct way to reach that office:"
        )
        return f"{lead_in}\n" + "\n".join(contact_lines)

    def _static_assistant_response(
        self,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse:
        """Return controlled non-policy responses without retrieval."""
        answer = assistant_meta_response(
            body.message, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
        )
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
        candidate_flags: CandidateFlags = CandidateFlags(),
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
        intent = classify_intent(
            scrubbed_input, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
        )
        if intent == "assistant_meta":
            return self._static_assistant_response(body, correlation_id, candidate_flags)
        if intent == "policy_fact" and not find_market_mentions(scrubbed_input):
            # A named market takes the normal retrieval path; this only fires
            # when no market was recognized at all, so a likely typo (e.g.
            # "Nigar" for "Niger", TRB-19189) doesn't fall straight through to
            # a generic "not enough information" refusal.
            probable_country = find_probable_market_typo(scrubbed_input)
            if probable_country:
                return self._market_typo_confirmation_response(probable_country, body, correlation_id)
        return None

    def _market_typo_confirmation_response(
        self,
        probable_country: str,
        body: ChatRequest,
        correlation_id: str,
    ) -> ChatResponse:
        """Ask the user to confirm a likely misspelled market name (TRB-19189).

        Never silently substitutes the corrected country - answering directly
        risks confidently using the wrong market's policies with no visible
        signal to the user, so this always asks rather than assumes.
        """
        template = localized_conversation_response("country_typo_confirmation", body.language) or (
            'Did you mean "{country}"? Please confirm, or rephrase your question with the country name.'
        )
        answer = template.replace("{country}", probable_country)
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "fallback": False,
                "response_source": "market_typo_confirmation",
                "probable_country": probable_country,
            },
        )

    def _conversation_route_response(
        self,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
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

        # The planner is advisory here, exactly as it is for assistant_meta below.
        # Asking what the rules prohibit is not a request to make the prohibited
        # claim, so a reviewed policy-safety question must never be short-circuited
        # into claim-refusal copy. Declining the shortcut removes no protection:
        # the deterministic guardrails already exempted this same question at input
        # governance, and retrieval, the evidence gate, output governance and the
        # validators all still run. The matcher is a strict whole-message match, so
        # an appended instruction or compound request does not qualify.
        if intent in {"medical_claim", "income_claim"} and is_policy_safety_question(body.message):
            return None

        response_key = ""
        if intent == "assistant_meta":
            # The planner is advisory. Reviewed exact phrases always produce
            # assistant identity/capability copy; a "thanks" classification is
            # additionally trusted on its own once it clears every guard in
            # is_planner_trusted_low_risk_subtype - see that function for why
            # only "thanks" is safe to trust without an exact phrase match.
            intent_confidence = float(metadata.get("intent_confidence") or 0.0)
            if classify_intent(
                body.message, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
            ) == "assistant_meta" or is_planner_trusted_low_risk_subtype(
                body.message, intent, subtype, intent_confidence
            ):
                response_key = (
                    subtype
                    if subtype in {"greeting", "capability", "thanks", "wellbeing", "casual"}
                    else "capability"
                )
            else:
                intent = "off_topic"
                response_key = "off_topic"
        elif intent == "medical_claim":
            if candidate_flags.in_voice_guardrail:
                candidate = self._candidate_guardrail_phrasing(
                    "medical_claim", body.language, body.country, correlation_id
                )
                if candidate:
                    return self.response_builder.fallback(
                        candidate,
                        correlation_id,
                        metadata={
                            "intent": "medical_claim",
                            "fallback": False,
                            "response_source": "candidate_guardrail_phrasing",
                        },
                    )
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
            if candidate_flags.in_voice_guardrail:
                candidate = self._candidate_guardrail_phrasing(intent, body.language, body.country, correlation_id)
                if candidate:
                    return self.response_builder.fallback(
                        candidate,
                        correlation_id,
                        metadata={
                            "intent": intent,
                            "fallback": False,
                            "response_source": "candidate_guardrail_phrasing",
                        },
                    )
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
        candidate_flags: CandidateFlags = CandidateFlags(),
        history: str = "",
    ) -> tuple[ChatResponse | None, RetrievalResult, EvidenceDecision | None]:
        """Resolve semantic routes or enforce the evidence gate for knowledge requests."""
        routed_response = self._conversation_route_response(retrieval_result, body, correlation_id, candidate_flags)
        if routed_response:
            return routed_response, retrieval_result, None

        evidence_decision = approve_evidence(retrieval_query, retrieval_result, body.country, body.language)
        scope_query = self._scope_query(scrubbed_input, retrieval_query, history)
        if evidence_decision.approved and self._is_cross_market_local_evidence(scope_query, retrieval_result, body):
            # Incidental local candidates must not veto a valid global answer.
            # Reapprove global evidence alone; never let the local policy stand
            # in for the foreign country's rules, even in comparison requests.
            globals_only = [doc for doc in evidence_decision.evidence if doc.metadata.get("access_scope") == "global"]
            sources = [doc.to_source() for doc in globals_only]
            scoped_result = replace(
                retrieval_result, documents=globals_only, citations=sources,
                confidence=min(retrieval_result.confidence, confidence_from_sources(sources)),
                metadata={**retrieval_result.metadata, "strong_local_match": False},
            )
            evidence_decision = approve_evidence(retrieval_query, scoped_result, body.country, body.language)
            if not evidence_decision.approved:
                evidence_decision = replace(evidence_decision, reason="cross_market_local_evidence")
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
        if candidate_flags.narrowing_fallback:
            narrowing_response = self._candidate_narrowing_response(body, correlation_id, history)
            if narrowing_response:
                return narrowing_response, approved_result, evidence_decision
        fallback_message = self._insufficient_evidence_message(body.language, body.message)
        office_contact_addendum = self._office_contact_addendum(body, correlation_id)
        if office_contact_addendum:
            fallback_message = f"{fallback_message}\n\n{office_contact_addendum}"
        fallback = self._validate_response(
            self.response_builder.fallback(
                fallback_message,
                correlation_id,
                metadata={
                    "failure_layer": "evidence_gate",
                    "evidence_decision": evidence_decision.to_metadata(),
                    "office_contact_offered": bool(office_contact_addendum),
                },
            ),
            body,
            correlation_id,
            retrieval_result=approved_result,
        )
        return fallback, approved_result, evidence_decision

    def _scope_query(self, current: str, contextual: str, history: str) -> str:
        """Inherit a target only for dependent turns without an explicit new market."""
        if not find_market_mentions(current) and self._needs_history_context(current, history):
            return contextual
        return current

    def _is_cross_market_local_evidence(
        self,
        scrubbed_input: str,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
    ) -> bool:
        """Return true when the message asks about a market this session's own evidence cannot cover.

        Only the raw current-turn message is checked, not the history-expanded
        retrieval query - a topic-shift follow-up query merges in the prior
        question's own market (e.g. "delivery cost for Belgium? What about
        Canada?"), which would make this session's own market look mentioned
        too and mask the mismatch.
        """
        mentioned_markets = {code.upper() for code in find_market_mentions(scrubbed_input)}
        if not (mentioned_markets - {body.country.upper()}):
            return False
        if not retrieval_result.documents:
            return False
        return any(document.metadata.get("access_scope") != "global" for document in retrieval_result.documents)

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
        named_fields = {
            field_id for field_id, pattern in DIRECTORY_FIELD_TERMS.items() if pattern.search(body.message or "")
        }
        if len(named_fields) == 1:
            # The user already said which single field they want (e.g. "do you
            # have a telephone number?") - asking them to choose it again from
            # a list that includes what they just said isn't a real
            # clarification. Fall through to the normal insufficient-evidence
            # path instead.
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
        # Recorded before any repair attempt, so ValidationHealth reflects what
        # the model produced rather than what repair rescued.
        record_validation_outcome(has_critical=result.has_critical())
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
                        # Sections are logged alongside the removed figures so a
                        # reviewer can check the removal against the evidence
                        # the answer was actually built from. Without them, a
                        # log line saying a number was deleted gives no way to
                        # tell a correct repair from the false positive this
                        # validator produced on 2026-09-07.
                        LOGGER.warning(
                            "output_validator_numeric_claims_repaired",
                            correlation_id=correlation_id,
                            removed_numeric_claims=removed_numbers,
                            removed_claim_count=len(removed_numbers),
                            evidence_sections=[
                                str((document.metadata or {}).get("section_id") or "")
                                for document in retrieval_result.documents[:5]
                            ],
                        )
                        record_numeric_repair(len(removed_numbers))
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
                    self._insufficient_evidence_message(body.language, body.message),
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
        cache_value["evidence"] = serialize_evidence(retrieval_result)
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
