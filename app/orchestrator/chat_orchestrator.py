"""AI chat orchestration for ASK Vera."""

from app.models.responses import ModelResponse
from app.models.router import ModelRouter, model_router
from app.evidence import approve_evidence, classify_intent, with_approved_evidence
from app.evidence_contract import parse_evidence_contract
from app.prompts import PromptBuilder
from app.response import ChatResponse, ResponseBuilder, response_builder
from app.retrieval import RetrievalService, retrieval_service
from app.retrieval.models import RetrievalResult
from app.governance import GovernanceDecision, GovernanceEngine, governance_engine
from app.validation import OutputValidator, ValidationContext, ValidationResult, output_validator, validation_summary
from config.vera_persona import FALLBACK_RESPONSES
from services.audit import write_audit_event
from services.cache import build_cache_key, get_cache_value, set_cache_value
from services.consent_service import has_valid_consent
from services.pii import scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
from utils.exceptions import LowConfidenceError, LowConfidenceThresholdError, RetrievalMissError
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
    "explain more",
    "tell me more",
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
        validate_and_touch_session(body.sessionId, correlation_id)
        if not has_valid_consent(body.sessionId, correlation_id):
            raise ConsentRequiredError()

        scrubbed_input = scrub_pii(body.message, correlation_id, body.language)
        history = get_session_history(body.sessionId, correlation_id)
        retrieval_query = self._build_retrieval_query(scrubbed_input, history, correlation_id)
        governance_decision = self._evaluate_governance(retrieval_query, body, correlation_id)
        if not governance_decision.allowed:
            return self._governance_fallback(governance_decision, correlation_id)

        intent = classify_intent(scrubbed_input)
        if intent == "assistant_meta":
            chat_response = self._static_assistant_response(body, correlation_id)
            append_session_turn(body.sessionId, scrubbed_input, chat_response.answer, correlation_id)
            return chat_response

        cache_key = build_cache_key(retrieval_query, body.country, body.language, body.role)
        cached = get_cache_value(cache_key, correlation_id)
        if cached:
            chat_response = self._validate_response(
                self.response_builder.from_cached(cached, correlation_id),
                body,
                correlation_id,
            )
            governance_decision = self._evaluate_governance(chat_response.answer, body, correlation_id)
            if not governance_decision.allowed:
                LOGGER.warning(
                    "cached_response_governance_blocked",
                    correlation_id=correlation_id,
                    country=body.country,
                    language=body.language,
                    role=body.role,
                )
                return self._governance_fallback(governance_decision, correlation_id)
            return chat_response

        retrieval_result = self.retriever.retrieve(retrieval_query, body.country, body.language, body.role, correlation_id)
        evidence_decision = approve_evidence(retrieval_query, retrieval_result, body.country, body.language)
        retrieval_result = with_approved_evidence(retrieval_result, evidence_decision)
        if not evidence_decision.approved:
            LOGGER.warning(
                "evidence_decision_rejected",
                correlation_id=correlation_id,
                country=body.country,
                language=body.language,
                role=body.role,
                **evidence_decision.to_metadata(),
            )
            return self._validate_response(
                self.response_builder.fallback(
                    FALLBACK_RESPONSES["insufficient_evidence"],
                    correlation_id,
                    metadata={
                        "failure_layer": "evidence_gate",
                        "evidence_decision": evidence_decision.to_metadata(),
                    },
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )
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
                    exc.message,
                    correlation_id,
                    metadata={"failure_layer": failure_layer},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )

        contracted_response = self._apply_evidence_contract(model_response, retrieval_result, correlation_id)
        if contracted_response is None:
            return self._validate_response(
                self.response_builder.fallback(
                    FALLBACK_RESPONSES["insufficient_evidence"],
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
        safe_answer = scrub_pii(chat_response.answer, correlation_id, body.language)
        if safe_answer != chat_response.answer:
            chat_response = ChatResponse(
                answer=safe_answer,
                citations=chat_response.citations,
                suggestions=chat_response.suggestions,
                cards=chat_response.cards,
                confidence=chat_response.confidence,
                metadata={**chat_response.metadata, "response_pii_scrubbed": True},
                correlation_id=chat_response.correlation_id,
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
            return self._governance_fallback(governance_decision, correlation_id)
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
        if self._should_cache_response(chat_response):
            set_cache_value(cache_key, chat_response.to_cache_value(), correlation_id)
        else:
            LOGGER.info(
                "cache_write_skipped",
                correlation_id=correlation_id,
                reason="fallback_or_critical_validation",
            )
        return chat_response

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
        """Expand vague follow-up questions with recent user-message context."""
        if not self._needs_history_context(user_message, history):
            return user_message

        user_messages = self._user_messages_from_history(history)
        if not user_messages:
            return user_message

        anchor = user_messages[0] if "first question" in user_message.lower() else user_messages[-1]
        query = f"{anchor}\nFollow-up request: {user_message}"
        LOGGER.info(
            "chat_followup_context_applied",
            correlation_id=correlation_id,
            original_length=len(user_message),
            contextual_length=len(query),
        )
        return query

    def _needs_history_context(self, user_message: str, history: str) -> bool:
        """Return true when a user message likely depends on earlier chat turns."""
        if not history:
            return False
        normalized = " ".join(user_message.lower().split())
        if not normalized:
            return False
        word_count = len(normalized.split())
        return word_count <= 14 and any(marker in normalized for marker in FOLLOW_UP_CONTEXT_MARKERS)

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

    def _governance_fallback(self, decision: GovernanceDecision, correlation_id: str) -> ChatResponse:
        """Return a safe fallback when governance blocks the request or response."""
        user_message = self._governance_user_message(decision)
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

    def _governance_user_message(self, decision: GovernanceDecision) -> str:
        """Convert internal governance reasons into user-friendly copy."""
        risk_issues = (decision.metadata or {}).get("risk", {}).get("issues", [])
        issue_codes = {str(issue.get("code", "")).lower() for issue in risk_issues}

        if any("income" in code for code in issue_codes):
            return FALLBACK_RESPONSES["income_claim"]
        if any("medical" in code or "health" in code for code in issue_codes):
            return FALLBACK_RESPONSES["medical_claim"]
        if decision.reason == "Governance provider failed.":
            return FALLBACK_RESPONSES["bedrock_error"]
        if decision.reason in {
            "Request blocked by high-risk policy.",
            "Request blocked by risk policy.",
        }:
            return FALLBACK_RESPONSES["off_topic"]
        return (
            decision.reason
            or "I can't help with that request, but I'm happy to help with Forever Living products, policies, ordering, or business support."
        )

    def _static_assistant_response(self, body: ChatRequest, correlation_id: str) -> ChatResponse:
        """Return controlled non-policy responses without retrieval."""
        message = (body.message or "").strip().lower()
        if "who are you" in message:
            answer = (
                "I'm ASK Vera, Forever Living's approved-document assistant. I can help with product, policy, "
                "ordering, and business-support questions using the approved information available to me."
            )
        elif "what can you help" in message or message == "help":
            answer = (
                "I can help find approved answers about Forever Living products, company policies, business-plan "
                "basics, discounts, bonuses, rank qualifications, ordering, and support topics."
            )
        elif "thank" in message:
            answer = "You're welcome. I'm here whenever you want help finding an approved Forever Living answer."
        else:
            answer = "Hi, I'm ASK Vera. What Forever Living product, policy, or business-support question can I help with?"
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={"intent": "assistant_meta", "fallback": False, "response_source": "template"},
        )

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
                    FALLBACK_RESPONSES["insufficient_evidence"],
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

        validation = metadata.get("validation")
        if isinstance(validation, dict) and str(validation.get("highestSeverity", "")).upper() == "CRITICAL":
            return False

        return bool((chat_response.answer or "").strip())


ai_orchestrator = AIOrchestrator()
