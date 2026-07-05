"""AI chat orchestration for ASK Vera."""

from app.models.responses import ModelResponse
from app.models.router import ModelRouter, model_router
from app.prompts import PromptBuilder
from app.response import ChatResponse, ResponseBuilder, response_builder
from app.retrieval import RetrievalService, retrieval_service
from app.retrieval.models import RetrievalResult
from app.validation import OutputValidator, ValidationContext, output_validator
from services.audit import write_audit_event
from services.cache import build_cache_key, get_cache_value, set_cache_value
from services.consent_service import has_valid_consent
from services.guardrails import check_text
from services.pii import scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
from utils.exceptions import LowConfidenceError
from utils.logging import get_logger
from utils.validators import ChatRequest

LOGGER = get_logger("app.orchestrator")


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
    ) -> None:
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retriever = retriever or retrieval_service
        self.model_router = router or model_router
        self.response_builder = builder or response_builder
        self.output_validator = validator or output_validator

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

        check_text(body.message, correlation_id)
        scrubbed_input = scrub_pii(body.message, correlation_id, body.language)
        cache_key = build_cache_key(scrubbed_input, body.country, body.language, body.role)
        cached = get_cache_value(cache_key, correlation_id)
        if cached:
            return self._validate_response(
                self.response_builder.from_cached(cached, correlation_id),
                body,
                correlation_id,
            )

        history = get_session_history(body.sessionId, correlation_id)
        retrieval_result = self.retriever.retrieve(scrubbed_input, body.country, body.language, body.role, correlation_id)
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
            return self._validate_response(
                self.response_builder.fallback(exc.message, correlation_id),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )

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
        check_text(chat_response.answer, correlation_id)
        append_session_turn(body.sessionId, scrubbed_input, chat_response.answer, correlation_id)
        write_audit_event(
            {
                "type": "chat",
                "country": body.country,
                "language": body.language,
                "confidence": chat_response.confidence,
            },
            correlation_id,
        )
        set_cache_value(cache_key, chat_response.to_cache_value(), correlation_id)
        return chat_response

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
                    }
                    for issue in result.issues
                ],
            )
        if result.has_critical():
            LOGGER.warning(
                "output_validator_critical_fallback",
                correlation_id=correlation_id,
                issue_count=len(result.issues),
                highest_severity=result.highest_severity.value,
            )
            return self.response_builder.fallback(
                "I could not generate a complete approved response. Please try again or contact Forever Living support.",
                correlation_id,
            )
        return chat_response


ai_orchestrator = AIOrchestrator()
