from app.orchestrator.chat_orchestrator import AIOrchestrator


def _history(question: str) -> str:
    return f"user: {question}\nvera: An earlier answer."


def test_noisy_known_directory_field_followups_keep_context() -> None:
    orchestrator = AIOrchestrator()
    for message in ("Und die Lieferkotsen?", "Et les frais de livraision ?"):
        assert orchestrator._is_directory_field_follow_up(message)
        assert orchestrator._needs_history_context(message, _history("What is the delivery cost in Kenya?"))


def test_noisy_unknown_place_followup_stays_standalone() -> None:
    orchestrator = AIOrchestrator()
    message = "Und die Lieferkotsen in Berlin?"
    assert not orchestrator._localized_follow_up_shape(message)
    assert not orchestrator._needs_history_context(message, _history("What is the delivery cost in Kenya?"))
