"""Fable CX review finding S5 (2026-09-19).

``config/conversation_routes.json`` carried reviewed ``insufficient_evidence``
copy for only 5 of the 12 route locales (en fr es de nl). For the other 7
(it da fi no sr sv ru), ``app/response/cx_render.py``'s ``render()`` floored
to English for that key while the base orchestrator path
(``app.evidence.localized_conversation_response``) translated it at runtime
via Bedrock. Two consequences, both now fixed by adding the missing
``insufficient_evidence`` entries:

(a) a bilingual answer whenever the runtime translation failed (localized
    base text with an appended English CX sentence), and
(b) ``app/response/cx_compose.py``'s generic-copy recognition
    (``_starts_with_generic_missing``) never matching for these locales, so
    ``evidence_missing_detail`` (and, transitively, the personal-account
    note on the evidence-missing path) never applied.

These tests drive the real ``AIOrchestrator.handle_chat`` offline (the same
harness shape as ``tests/unit/test_cx_outcome_wiring.py``), for each of the
7 locales, with ``localize_reviewed_copy`` monkeypatched to raise if it is
ever called -- proving the fix does not depend on (or silently fall back to)
a runtime translation.
"""

from __future__ import annotations

import pytest

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response import cx_render
from app.retrieval.models import RetrievalResult
from app.validation.models import ValidationResult
from config import settings
from utils.validators import ChatRequest

# One field question per locale, worded so utils.directory_fields's own
# per-language field vocabulary (config/directory_field_vocabulary.py)
# confidently names "phone" -- verified directly against
# _requested_directory_field_set(question, language=locale) for each row
# below. The English snippets a leaked/untranslated fallback would carry are
# also pinned here, once, as NOT_EXPECTED, so every locale's assertion stays
# in sync with the exact English wording in config/conversation_routes.json.
NOT_EXPECTED = (
    "do not contain enough information",
    "approved policy documents currently available",
)

LOCALE_CASES = {
    "it": ("Qual è il numero di telefono?", "telefono"),
    "da": ("Hvad er telefonnummeret?", "telefon"),
    "fi": ("Mikä on puhelinnumero?", "puhelin"),
    "no": ("Hva er telefonnummeret?", "telefon"),
    "ru": ("Какой номер телефона?", "телефон"),
    "sr": ("Koji je broj telefona?", "telefon"),
    "sv": ("Vad är telefonnumret?", "telefon"),
}


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _Validator:
    def validate(self, *_: object, **__: object) -> ValidationResult:
        return ValidationResult()


class _Router:
    def generate(self, *_: object, **__: object) -> ModelResponse:
        # Never reached: with no retrieved evidence, evidence approval
        # declines before generation runs.
        raise AssertionError("the model must not be called for an evidence-missing turn")


class _EmptyRetriever:
    def retrieve(self, *_: object, **__: object) -> RetrievalResult:
        return RetrievalResult(documents=[], citations=[], confidence=0.0)


@pytest.fixture
def translation_forbidden(monkeypatch):
    """Fail loudly if any code path asks for a live translation.

    Same three patch points tests/unit/test_benchmark_capture.py's own
    ``translation_forbidden`` fixture uses, plus ``app.response.cx_render``'s
    own imported reference (this task's own new caller of
    ``localize_reviewed_copy``).
    """
    import app.evidence as evidence
    import services.controlled_copy as controlled_copy

    calls: list[tuple] = []

    def forbidden(*args, **_kwargs):
        calls.append(args)
        raise AssertionError(f"localize_reviewed_copy called: {args!r}")

    def no_clients(*_args, **_kwargs):
        calls.append(("get_aws_clients",))
        raise AssertionError("an AWS client was requested")

    monkeypatch.setattr(evidence, "localize_reviewed_copy", forbidden)
    monkeypatch.setattr(cx_render, "localize_reviewed_copy", forbidden)
    monkeypatch.setattr(controlled_copy, "localize_reviewed_copy", forbidden)
    monkeypatch.setattr(controlled_copy, "get_aws_clients", no_clients)
    return calls


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_MEMORY_BACKEND", "memory")
    for name, value in {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text,
        "get_session_history": lambda *_: "",
        "get_cache_value": lambda *_: None,
        "set_cache_value": lambda *_: None,
        "semantic_cache_active": lambda: False,
        "append_session_turn": lambda *_: None,
        "write_audit_event": lambda *_: None,
    }.items():
        monkeypatch.setattr(chat_orchestrator, name, value)

    def _run(message, *, country="US", language="en"):
        orchestrator = AIOrchestrator(
            retriever=_EmptyRetriever(), router=_Router(), validator=_Validator(), governance=_Governance()
        )
        body = ChatRequest(message=message, sessionId="s", country=country, language=language)
        return orchestrator.handle_chat(body, "cid")

    return _run


@pytest.mark.parametrize("language", sorted(LOCALE_CASES))
def test_evidence_missing_field_question_is_single_language_and_detailed(run, translation_forbidden, language):
    question, expected_word = LOCALE_CASES[language]

    response = run(question, language=language)

    assert response.metadata["outcome"]["kind"] == "evidence_missing"
    assert "evidence_missing_detail" in response.metadata["cx_applied"]
    assert "dropped:evidence_missing_detail" not in response.metadata["cx_applied"]

    answer_lower = response.answer.lower()
    assert expected_word in answer_lower

    for leaked_english in NOT_EXPECTED:
        assert leaked_english not in response.answer, (language, response.answer)

    assert translation_forbidden == []


@pytest.mark.parametrize("language", sorted(LOCALE_CASES))
def test_generic_copy_recognition_now_matches_between_base_and_cx_paths(language):
    """The bug's root cause, checked directly: cx_render's floor-to-English
    behaviour for an unreviewed key vs. the base path's runtime translation.
    With a reviewed entry now present for every locale, cx_render.render and
    app.evidence.localized_conversation_response resolve to the identical
    first paragraph -- no translation call needed for either."""
    from app.evidence import localized_conversation_response

    base_first_paragraph = (localized_conversation_response("insufficient_evidence", language) or "").split(
        "\n\n", 1
    )[0]
    cx_first_paragraph = cx_render.render("insufficient_evidence", language).split("\n\n", 1)[0]

    assert base_first_paragraph == cx_first_paragraph
    assert base_first_paragraph.strip()
