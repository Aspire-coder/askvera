"""AI chat orchestration for ASK Vera."""

from typing import Any

from app.models import ModelRouter, model_router
from app.prompts import PromptBuilder
from app.retrieval import RetrievalService, retrieval_service
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
    ) -> None:
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retriever = retriever or retrieval_service
        self.model_router = router or model_router

    def handle_chat(self, body: ChatRequest, correlation_id: str) -> dict[str, Any]:
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
            return {**cached, "correlationId": correlation_id}

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
            result = self.model_router.generate(prompt_package, retrieval_result, correlation_id).to_chat_result()
        except LowConfidenceError as exc:
            return {"response": exc.message, "sources": [], "confidence": 0.0, "correlationId": correlation_id}

        result["response"] = scrub_pii(result["response"], correlation_id, body.language)
        check_text(result["response"], correlation_id)
        append_session_turn(body.sessionId, scrubbed_input, result["response"], correlation_id)
        write_audit_event(
            {
                "type": "chat",
                "country": body.country,
                "language": body.language,
                "confidence": result["confidence"],
            },
            correlation_id,
        )
        set_cache_value(cache_key, result, correlation_id)
        return {**result, "correlationId": correlation_id}


ai_orchestrator = AIOrchestrator()
