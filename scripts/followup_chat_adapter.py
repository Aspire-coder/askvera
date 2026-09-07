"""Process-local experimental wiring; never changes the selected policy market."""

from unittest.mock import patch

from scripts.followup_context_candidate import resolve_context
from services.market_config import find_market_mentions


def install(stack, orchestrator):
    from app.retrieval import opensearch_sections

    original_targets = opensearch_sections._directory_target_country_names
    original_scope = orchestrator._scope_query
    state = {}

    def build(current, history, correlation_id):
        state.clear()  # No target inheritance across independent requests/sessions.
        current = orchestrator._normalize_malformed_spacing(current, correlation_id)
        prior = orchestrator._user_messages_from_history(history)
        if "first question" in current.lower() and prior:
            prior = prior[:1]
        context = resolve_context(current, prior, is_dependent=orchestrator._is_context_dependent_message)
        query = "\n".join((*context.prior_questions, f"Follow-up request: {current}")) if context.prior_questions else current
        target_question = next((q for q in reversed((*context.prior_questions, current))
                                if find_market_mentions(q)), "")
        state.update(query=query, target_question=target_question)
        return query

    def targets(message, selected_country):
        # Restrict only the global directory's record target. Locale filters
        # continue receiving the actual session country, not this target.
        if message == state.get("query") and state.get("target_question"):
            return original_targets(state["target_question"], selected_country)
        return original_targets(message, selected_country)

    def scope(current, contextual, history):
        if contextual == state.get("query") and state.get("target_question"):
            return state["target_question"]
        return original_scope(current, contextual, history)

    stack.enter_context(patch.object(orchestrator, "_build_retrieval_query", build))
    stack.enter_context(patch.object(orchestrator, "_scope_query", scope))
    stack.enter_context(patch.object(opensearch_sections, "_directory_target_country_names", targets))
