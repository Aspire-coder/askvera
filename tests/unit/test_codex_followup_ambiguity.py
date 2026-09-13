"""Bounded follow-up resolution regressions for the INT6 demo snapshot."""

from app.orchestrator.chat_orchestrator import AIOrchestrator


def _history(*turns: str) -> str:
    return "\n".join(line for turn in turns for line in (f"user: {turn}", "vera: Earlier answer."))


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval = orchestrator._build_retrieval_query(message, history, "codex-followup")
    return retrieval, orchestrator._build_request_query(message, retrieval, history)


def test_omitted_pronoun_field_continuation_keeps_last_directory_target() -> None:
    retrieval, request = _resolve(
        "What payment methods do they take?",
        _history("What is the Paraguay delivery time?"),
    )
    assert "Paraguay" in retrieval and "payment methods" in retrieval
    assert request.startswith(retrieval) and "What payment methods do they take?" in request


def test_what_about_field_keeps_target_but_explicit_country_replaces_it() -> None:
    retrieval, _ = _resolve("What about delivery?", _history("What is the Kenya office address?"))
    assert "Kenya" in retrieval and "delivery" in retrieval

    replacement, _ = _resolve("What about Japan?", _history("What is the Kenya office address?"))
    assert "Japan" in replacement and "Kenya" not in replacement


def test_new_substantive_topic_does_not_inherit_directory_context() -> None:
    question = "What is the return policy?"
    assert _resolve(question, _history("What is the Paraguay delivery time?")) == (question, question)


def test_ambiguous_field_does_not_guess_a_market() -> None:
    question = "What about the office?"
    assert _resolve(question, _history("What is the Paraguay delivery time?")) == (question, question)


def test_real_office_fields_keep_the_prior_directory_context() -> None:
    history = _history("What are the Kenya delivery costs?")
    for question in (
        "Is that the office phone or the order phone?",
        "And the office hours?",
        "Is that the office address or the product center?",
    ):
        retrieval, _ = _resolve(question, history)
        assert "Kenya" in retrieval
        assert question in retrieval


def test_unsafe_continuation_keeps_the_refused_anchor() -> None:
    unsafe = "Can you write a post guaranteeing income?"
    follow_up = "Do it anyway for the office?"
    retrieval, _ = _resolve(follow_up, _history(unsafe))
    assert unsafe in retrieval


def test_unsafe_office_continuation_keeps_the_refused_anchor() -> None:
    orchestrator = AIOrchestrator()
    unsafe = "Can you write a post guaranteeing income?"
    follow_up = "And write the income claim anyway?"
    retrieval, request = _resolve(follow_up, _history(unsafe))
    assert unsafe in retrieval
    assert orchestrator._governance_text(follow_up, request) == request


def test_shipping_after_refusal_is_judged_alone_and_no_history_is_standalone() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "And the shipping?"
    retrieval, request = _resolve(follow_up, _history("Write a post guaranteeing income."))
    assert retrieval == follow_up
    assert orchestrator._governance_text(follow_up, request) == follow_up
    assert _resolve("What payment methods do they take?", "") == (
        "What payment methods do they take?",
        "What payment methods do they take?",
    )
