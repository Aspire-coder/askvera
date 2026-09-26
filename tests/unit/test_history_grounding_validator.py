"""Tests for the history-is-not-evidence groundedness check.

Regression for the live failure (correlation ids
35aec7ae-7d03-4dba-9755-22b7b04e4d85 and 4cb3d453-9629-492d-81bd-5c1be4ddbf31):
a US session's third turn asked "Is this the whole contract or are there other
documents?", retrieval returned exactly one global sponsoring-directory
record, and the model answered from policy facts stated in an earlier turn's
history instead - quoting section 18.01(c) and listing sections 19, 20 and 21,
none of which this turn's evidence contains.

Canary fix (2026-09-25, chained-followup-market-continuity): the validator
now also requires ``conversation_history`` to actually cover a flagged
sentence, and never requires history to exist at all before that check can
even run - see ``history_grounding_validator``'s module docstring for the two
false-positive classes this closes. Every ``_context(...)`` call below that
exercises a genuine history-sourced-claim reproduction now also passes
``history=...``; the ones that must stay valid either pass no history at all
(turn 0) or history that does not itself state the sentence in question.
"""

from app.response.models import ChatResponse
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.validation.models import ValidationContext, ValidationResult
from app.validation.validators.history_grounding_validator import HistoryGroundingValidator

_DIRECTORY_RECORD = (
    "Sponsoring Directory - North America\n"
    "Country: United States\n"
    "Order Desk: 1-888-440-2563\n"
    "Minimum order size FBO: 50 USD"
)

_HISTORY_POLICY_FACTS = (
    "Section 18.01(c) states that this agreement, together with the attached "
    "exhibits, constitutes the entire contract between the parties. Sections "
    "19, 20 and 21 govern termination, assignment and dispute resolution."
)

# The earlier-turn assistant answer the reproduced failure actually copied
# prose from - "user:"/"assistant:" line prefixes, mirroring how
# ``app.orchestrator.chat_orchestrator`` reads session history text.
_HISTORY_WITH_POLICY_FACTS = (
    "user: Is this the whole contract or are there other documents?\n"
    f"assistant: {_HISTORY_POLICY_FACTS}"
)


def _directory_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="sponsoring-098-north-america",
        title="Global Sponsoring Directory",
        content=_DIRECTORY_RECORD,
        source="s3://directory/global-sponsoring.pdf",
        country="GLOBAL",
        metadata={"document_type": "international_sponsoring_directory", "access_scope": "global"},
    )


def _policy_document(content: str = _HISTORY_POLICY_FACTS) -> RetrievedDocument:
    return RetrievedDocument(
        id="us-policy-18",
        title="US-EN-Company-Policy.pdf",
        content=content,
        source="s3://policy/US-EN-Company-Policy.pdf",
        country="US",
        metadata={"document_type": "policy"},
    )


def _context(
    answer: str, documents: list[RetrievedDocument], history: str = ""
) -> ValidationContext:
    return ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="test-correlation",
        ),
        correlation_id="test-correlation",
        country="US",
        language="en",
        role="fbo",
        retrieval_result=RetrievalResult(documents=documents, citations=[], confidence=0.6),
        conversation_history=history,
    )


def test_blocks_policy_facts_carried_over_from_history_when_only_a_directory_record_was_retrieved() -> None:
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=_HISTORY_WITH_POLICY_FACTS), result
    )

    assert result.has_critical()
    codes = {issue.code for issue in result.issues}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in codes


def test_same_reproduction_without_history_is_not_flagged() -> None:
    """Turn 0 of a conversation: the identical uncovered sentences must not be
    flagged with no history present at all to have copied them from - the
    first of the two false-positive classes this fix closes."""
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_never_produces_a_half_emptied_list_it_only_flags_for_fallback() -> None:
    """The validator never rewrites the answer; a caller that discards it on
    CRITICAL gets a clean fallback, never a partially stripped numbered list
    like the one that shipped live (items 2, 3 and 4 empty)."""
    answer = (
        "This is the entire agreement, and it fully covers every requirement "
        "without needing any additional referenced material, and it includes:\n"
        "1. The main agreement\n"
        "2. Section 19 on termination\n"
        "3. Section 20 on assignment\n"
        "4. Section 21 on dispute resolution"
    )
    original_answer = answer
    history = (
        "user: Is this the whole contract or are there other documents?\n"
        "assistant: This is the entire agreement, and it fully covers every "
        "requirement without needing any additional referenced material, and "
        "it includes the main agreement, section 19 on termination, section "
        "20 on assignment and section 21 on dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.has_critical()
    # The validator only ever reports issues; it must never mutate the answer
    # under review into a half-emptied version of itself.
    assert original_answer == answer


def test_positive_control_full_answer_preserved_when_policy_evidence_is_present() -> None:
    """The same question, this time with the real policy section retrieved:
    nothing should be stripped or flagged."""
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document(), _policy_document()]), result
    )

    assert result.valid
    assert not result.issues


def test_followup_turn_still_answers_from_evidence_with_history_present() -> None:
    """"Tell me more" must keep resolving against evidence retrieved this turn."""
    answer = "Sections 19, 20 and 21 govern termination, assignment and dispute resolution."
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_policy_document(), _directory_document()]), result
    )

    assert result.valid


def test_directory_only_answer_to_a_directory_question_is_untouched() -> None:
    """A directory-only turn answering a directory question is legitimately
    grounded in the directory record's own fields and must not be flagged."""
    answer = "The order desk number is 1-888-440-2563, and the minimum FBO order is 50 USD."
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid


def test_generic_service_boilerplate_beside_a_directory_supplement_is_not_flagged() -> None:
    """A short, generic customer-care referral is not a factual claim about
    anything the directory record states or omits, and must not be confused
    for one merely because it shares little vocabulary with the record.

    Reproduces the false positive found in tests/unit/test_demo_support_contact_wiring.py:
    a "please contact customer care" style answer, with a directory-sourced
    phone number appended, must survive untouched.
    """
    answer = (
        "You are welcome to place an order directly. Please contact customer "
        "care for further help. Telephone Office: 1-888-440-2563."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context(answer, [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_non_policy_turn_without_retrieval_is_untouched() -> None:
    """A greeting or capability answer with no retrieval result must not be
    dragged through the groundedness check."""
    answer = "Hi! I can help with questions about your Forever Living business."
    result = ValidationResult()

    context = ValidationContext(
        chat_response=ChatResponse(
            answer=answer,
            citations=[],
            suggestions=[],
            cards=[],
            confidence=0.9,
            metadata={},
            correlation_id="test-correlation",
        ),
        correlation_id="test-correlation",
        country="US",
        language="en",
        role="fbo",
        retrieval_result=None,
    )

    HistoryGroundingValidator().validate(context, result)

    assert result.valid
    assert not result.issues


def test_empty_answer_is_untouched() -> None:
    result = ValidationResult()

    HistoryGroundingValidator().validate(_context("", [_directory_document()]), result)

    assert result.valid
    assert not result.issues


def test_followup_offer_and_question_not_covered_by_history_are_not_flagged() -> None:
    """Reproduces the "Tell me more" turn of the live failure: a clarifying
    question and a forward-looking offer, neither of which history itself
    states, must not be flagged even though history is present and neither
    sentence is covered by this turn's thin directory-only evidence."""
    answer = (
        "What specific information would you like to know more about? "
        "Please let me know what would be most helpful, and I will provide "
        "the details from our approved resources."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=_HISTORY_WITH_POLICY_FACTS), result
    )

    assert result.valid
    assert not result.issues


def test_question_sentence_covered_by_history_is_still_not_flagged() -> None:
    """A question asserts no fact, so it is never flagged even when its own
    vocabulary happens to be covered by conversation history."""
    history = (
        "user: How do I sponsor someone in Belgium?\n"
        "assistant: Would you like to know more about qualification "
        "requirements or the application process for Belgium sponsoring?"
    )
    answer = (
        "Would you like to know more about qualification requirements or the "
        "application process for Belgium sponsoring?"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.valid
    assert not result.issues


def test_spanish_question_sentence_covered_by_history_is_not_flagged() -> None:
    """The interrogative skip is language-agnostic: a Spanish "¿...?" sentence
    covered by history is still not flagged."""
    history = (
        "user: ¿Cómo puedo patrocinar a alguien en Bélgica?\n"
        "assistant: ¿Le gustaría conocer los requisitos de "
        "calificación o el proceso de solicitud para Bélgica?"
    )
    answer = (
        "¿Le gustaría conocer los requisitos de calificación o "
        "el proceso de solicitud para Bélgica?"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.valid
    assert not result.issues


def test_non_english_history_sourced_claim_is_flagged() -> None:
    """The history-sourced-claim check is language-agnostic: a Spanish factual
    sentence copied from an earlier assistant turn is flagged the same way
    the English reproduction is."""
    history_facts = (
        "La sección 18.01(c) establece que este acuerdo, junto con los "
        "anexos adjuntos, constituye el contrato completo entre las partes. "
        "Las secciones 19, 20 y 21 rigen la terminación, la cesión "
        "y la resolución de disputas."
    )
    history = (
        "user: ¿Es este todo el contrato o hay otros documentos?\n"
        f"assistant: {history_facts}"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(history_facts, [_directory_document()], history=history), result
    )

    assert result.has_critical()
    codes = {issue.code for issue in result.issues}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in codes


def test_answer_restating_the_users_own_earlier_question_is_not_flagged() -> None:
    """Review round 1 fix: this validator's purpose is catching prose copied
    from an earlier ASSISTANT answer, not the user's own words reflected back.
    The user's long earlier question shares plenty of vocabulary with an
    answer that legitimately restates it - if history were compared as a
    whole (including the user's own turns) this would be wrongly flagged -
    but the actual earlier assistant reply shares little of that vocabulary,
    so comparing against assistant-only text correctly leaves it alone.
    """
    history = (
        "user: How do I sponsor someone in Belgium and what documents are "
        "required for that application process?\n"
        "vera: You can find the Belgium sponsoring office contact details below."
    )
    answer = (
        "To sponsor someone in Belgium you need to provide the required "
        "application documents for that process."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.valid
    assert not result.issues


def test_fact_on_a_multiline_assistant_answers_continuation_line_is_flagged() -> None:
    """A stored assistant answer can itself span multiple lines (a
    multi-paragraph reply); a continuation line with no "user:"/"vera:"
    prefix still belongs to that assistant turn, not to a new, unlabeled
    turn - so a fact stated only on that continuation line and copied into
    this turn's answer is still caught as history-sourced.
    """
    history = (
        "user: What are the terms for sponsoring in Norway?\n"
        "vera: You can sponsor someone in Norway by completing an application.\n"
        "The minimum monthly volume requirement is 200 PV per associate."
    )
    answer = (
        "The minimum monthly volume requirement is 200 PV per associate for "
        "Norway sponsoring purposes."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.has_critical()
    codes = {issue.code for issue in result.issues}
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in codes


# ---------------------------------------------------------------------------
# Third mode (2026-09-26, production rollback of main 65dbb74): a generic
# menu/option line repeated from the model's own earlier turn carries no
# specific fact and must not cost the reader the whole answer - see the
# validator's module docstring. The exemption is confined to list items;
# prose keeps the previous treatment.
# ---------------------------------------------------------------------------

_GERMANY_DIRECTORY_RECORD = (
    "Sponsoring Directory - Europe\n"
    "Country: Germany\n"
    "Welcome to Forever Germany!\n"
    "Telephone for Orders: +49 6131 8999 0\n"
    "Email: service@example.de\n"
    "Minimum order size FBO: 50,00 in products.\n"
    "Delivery Cost: 5,00 per order. Orders above 12 cases ship free.\n"
    "Opening hours: Mon-Fri 09.00-17.00"
)

# The exact line the live log quoted as the one flagged sentence.
_MENU_LINE = "**Getting started** – how the business opportunity works, or sponsoring someone"

_BELGIUM_ANSWER_WITH_MENU = (
    "You can sponsor someone in Belgium through the Forever Belgium office.\n"
    "Here is what I can help you with next:\n"
    f"- {_MENU_LINE}\n"
    "- **Qualifications** – what a new applicant needs before being sponsored\n"
    "- **Next steps** – how to get in touch with the local office"
)

_GERMANY_ANSWER_WITH_MENU = (
    "You can sponsor someone in Germany through the Forever Germany office.\n"
    "Here is what I can help you with next:\n"
    f"- {_MENU_LINE}\n"
    "- **Qualifications** – what a new applicant needs before being sponsored\n"
    "- **Next steps** – how to get in touch with the local office"
)

_LIVE_CANARY_HISTORY = (
    "user: How do I sponsor someone in Belgium?\n"
    f"vera: {_BELGIUM_ANSWER_WITH_MENU}\n"
    "user: What about Germany?\n"
    f"vera: {_GERMANY_ANSWER_WITH_MENU}"
)


def _germany_directory_document() -> RetrievedDocument:
    return RetrievedDocument(
        id="sponsoring-042-germany",
        title="Forever Germany",
        content=_GERMANY_DIRECTORY_RECORD,
        source="s3://directory/global-sponsoring.pdf",
        country="GLOBAL",
        metadata={"document_type": "international_sponsoring_directory", "access_scope": "global"},
    )


def _germany_turn_result(answer: str, history_fact: str) -> ValidationResult:
    """Validate ``answer`` on the Germany turn with ``history_fact`` as the
    earlier Belgium-turn assistant answer (services/session.py's shape)."""
    history = (
        "user: How do I sponsor someone in Belgium?\n"
        f"vera: {history_fact}\n"
        "user: What about Germany?"
    )
    result = ValidationResult()
    HistoryGroundingValidator().validate(
        _context(answer, [_germany_directory_document()], history=history), result
    )
    return result


def test_live_canary_menu_line_repeated_from_own_earlier_turn_is_not_flagged() -> None:
    """The 2026-09-26 production rollback: on the "Tell me more." turn of the
    Belgium/Germany canary, retrieval returned the Forever Germany record and
    the model answered with its details plus a generic menu line it had
    already used in its own previous turn. That line is uncovered by the
    directory record and covered by assistant history, but asserts no market
    fact, so the answer (and the Germany details in it) must be delivered."""
    answer = (
        "Forever Germany can be reached on +49 6131 8999 0 or at service@example.de. "
        "The minimum order size for an FBO is 50,00 in products and delivery costs "
        "5,00 per order; orders above 12 cases ship free. Opening hours are Mon-Fri 09.00-17.00.\n"
        "I can also tell you more about:\n"
        f"- {_MENU_LINE}\n"
        "- **Qualifications** – what a new applicant needs before being sponsored"
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_germany_directory_document()], history=_LIVE_CANARY_HISTORY), result
    )

    assert result.valid
    assert not result.issues
    assert not result.has_critical()


def test_menu_line_is_exempt_only_with_its_bullet() -> None:
    """The menu line as a bullet (the live shape) is a generic option line:
    no digit, currency, contact marker or market name. The same text as a
    bare bold-label line is not a menu line and keeps the previous
    treatment (review 2026-09-26: "**Note**: ..." lines carry inverted
    directory notes)."""
    result = ValidationResult()
    HistoryGroundingValidator().validate(
        _context(f"- {_MENU_LINE}", [_germany_directory_document()], history=_LIVE_CANARY_HISTORY), result
    )
    assert result.valid
    assert not result.issues

    result = ValidationResult()
    HistoryGroundingValidator().validate(
        _context(_MENU_LINE, [_germany_directory_document()], history=_LIVE_CANARY_HISTORY), result
    )
    assert result.has_critical()


def test_inverted_directory_note_as_plain_bullet_or_bold_note_is_still_flagged() -> None:
    """Review 2026-09-26: the REJ1 inverted note reaches the reader as a plain
    bullet or a "**Note**:" line far more often than as prose, so neither
    shape is exempt - only a bullet that opens with a bold label and a dash
    or colon is."""
    for item in (
        "- This office accepts new sponsoring applications from any interested prospect right now",
        "- Please be aware that it currently is not taking on any fresh applicants for sponsorship.",
        "**Note**: the office is currently accepting fresh applicants for sponsorship from every prospect",
        "1) This office accepts new sponsoring applications from any interested prospect right now",
        "- Bonuses are always paid out monthly by bank transfer to your local account",
    ):
        result = _germany_turn_result(item, item)

        assert result.has_critical(), item
        assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in {issue.code for issue in result.issues}


def test_thousands_of_menu_lines_validate_in_linear_time() -> None:
    """Review 2026-09-26: the market-name lookup used to rebuild its table
    on every call (about 4 ms), so a 6,000-line answer took 23 s."""
    import time

    lines = "\n".join(
        f"- **Option {index}** – how the business opportunity works, or sponsoring someone" for index in range(6000)
    )
    lines = lines.replace("Option 0", "Getting started")
    history = f"user: How do I sponsor someone in Belgium?\nvera: {lines}\nuser: What about Germany?"
    started = time.perf_counter()
    result = ValidationResult()
    HistoryGroundingValidator().validate(_context(lines, [_germany_directory_document()], history=history), result)
    assert time.perf_counter() - started < 3.0


def test_original_reproduction_with_section_numbers_is_still_flagged() -> None:
    """The section-number reproduction is prose (and carries digits), so the
    third-mode filter leaves it exactly as flagged as before."""
    answer = (
        "This is the whole contract. Section 18.01(c) states that this agreement, "
        "together with the attached exhibits, constitutes the entire contract "
        "between the parties. Sections 19, 20 and 21 govern termination, "
        "assignment and dispute resolution."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=_HISTORY_WITH_POLICY_FACTS), result
    )

    assert result.has_critical()
    assert {issue.code for issue in result.issues} == {"HISTORY_SOURCED_CLAIM_UNGROUNDED"}


def test_copied_prose_sentence_without_any_marker_is_still_flagged() -> None:
    """Prose keeps the previous treatment: a marker-free sentence copied
    from an earlier assistant turn that inverts a directory note (the REJ1
    shape in tests/unit/test_directory_contact_route.py) is still caught."""
    fact = "Please be aware that the office currently is not taking on any fresh applicants for sponsorship."

    result = _germany_turn_result(fact, fact)

    assert result.has_critical()
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in {issue.code for issue in result.issues}


def _assert_copied_list_item_is_flagged(item: str) -> None:
    result = _germany_turn_result(f"- {item}", f"- {item}")

    assert result.has_critical(), item
    assert "HISTORY_SOURCED_CLAIM_UNGROUNDED" in {issue.code for issue in result.issues}


def test_copied_market_fact_list_item_without_digits_is_still_flagged_en() -> None:
    """A Belgium payment fact repeated on the Germany turn misleads about the
    market even as a bullet with no digit: the market name is the marker."""
    _assert_copied_list_item_is_flagged(
        "In Belgium, bonuses are paid by bank transfer to a Belgian account every month."
    )


def test_copied_market_fact_list_item_without_digits_is_still_flagged_de() -> None:
    """German capitalises every noun, so the market marker must not depend on
    capitalisation; "Belgien" resolves through the shared alias table."""
    _assert_copied_list_item_is_flagged(
        "In Belgien werden Boni jeden Monat per Banküberweisung auf ein belgisches Konto gezahlt."
    )


def test_copied_market_fact_list_item_without_digits_is_still_flagged_fr() -> None:
    _assert_copied_list_item_is_flagged(
        "En Belgique, les bonus sont versés chaque mois par virement bancaire sur un compte belge."
    )


def test_copied_market_fact_list_item_without_digits_is_still_flagged_ru() -> None:
    """Cyrillic script: the alias table carries the Russian market name, so a
    copied Belgium fact is flagged without any Latin-script assumption."""
    _assert_copied_list_item_is_flagged(
        "Бельгия выплачивает бонусы каждый месяц банковским переводом на бельгийский счёт."
    )


def test_copied_list_item_with_email_is_still_flagged() -> None:
    _assert_copied_list_item_is_flagged(
        "**Applications** – reach the sponsoring desk by email at sponsoring@example.be for new applications"
    )


def test_copied_list_item_with_url_is_still_flagged() -> None:
    _assert_copied_list_item_is_flagged(
        "**Forms** – the application form is available online at www.example.com/sponsoring for download"
    )


def test_copied_list_item_with_currency_symbol_or_iso_code_is_still_flagged() -> None:
    for item in (
        "**Starter kit** – costs about fifty € and is paid when the application is submitted",
        "**Bonuses** – always paid out in EUR by bank transfer after the qualification period ends",
    ):
        _assert_copied_list_item_is_flagged(item)


def test_copied_list_item_with_digits_is_still_flagged() -> None:
    _assert_copied_list_item_is_flagged(
        "**Contract** – section 18.01(c) states that this agreement constitutes the entire contract"
    )


def test_generic_copied_list_item_without_markers_is_not_flagged_en_de_fr() -> None:
    """A copied menu line carrying none of the markers - no digit, currency,
    contact marker or market name - is generic and is left alone in every
    language and under every list-marker shape."""
    for item in (
        "- **Getting started** – how the business opportunity works, or sponsoring someone",
        "* **Qualifications** – what a new applicant needs before being sponsored by you",
        "1. **Erste Schritte** – wie die Geschäftsmöglichkeit funktioniert oder wie man jemanden sponsert",
        "• **Premiers pas** – comment fonctionne l'opportunité commerciale, ou comment parrainer quelqu'un",
        "(2) **Nächste Schritte** – wie Sie mit dem örtlichen Büro in Kontakt treten können",
    ):
        result = _germany_turn_result(item, item)

        assert result.valid, item
        assert not result.issues, item


def test_lowercase_currency_code_lookalike_word_is_not_a_marker() -> None:
    """A currency ISO code counts only as an upper-case whole token: the
    French pronoun "ils" (ILS) never turns a generic menu line into a
    "specific fact"."""
    item = "- **Contact** – ils peuvent vous expliquer le processus de parrainage et répondre à vos questions"

    result = _germany_turn_result(item, item)

    assert result.valid
    assert not result.issues


def test_copied_list_lead_in_prose_is_still_flagged() -> None:
    """The P014 half-emptied-list shape: the lead-in is prose, so it keeps
    the previous treatment even though it carries no digit itself (and the
    validator still never rewrites the answer)."""
    answer = (
        "This is the entire agreement, and it fully covers every requirement "
        "without needing any additional referenced material, and it includes:\n"
        "1. The main agreement\n"
        "2. Section 19 on termination\n"
        "3. Section 20 on assignment"
    )
    history = (
        "user: Is this the whole contract or are there other documents?\n"
        "assistant: This is the entire agreement, and it fully covers every "
        "requirement without needing any additional referenced material, and "
        "it includes the main agreement, section 19 on termination and section "
        "20 on assignment."
    )
    result = ValidationResult()

    HistoryGroundingValidator().validate(
        _context(answer, [_directory_document()], history=history), result
    )

    assert result.has_critical()
