"""CX phase 3, Lane 2: FieldCoverage and the partial-answer gap note.

docs/conversation-quality/phase3/CX_DESIGN.md,
docs/conversation-quality/phase3/CX_LANES.md,
docs/conversation-quality/phase3/CX_LANE2_PARTIAL_AND_QUALITY.md.
"""

from __future__ import annotations

from app.response.outcome import OutcomeKind
from app.response.partial_answer import (
    FieldCoverage,
    assess_field_coverage,
    partial_answer_note,
)
from app.retrieval.models import RetrievedDocument


def _directory_document(
    content: str,
    *,
    country: str = "Kenya",
    directory_fields: dict[str, str] | None = None,
) -> RetrievedDocument:
    metadata: dict[str, object] = {
        "directory_kind": "international_sponsoring",
        "record_country": country,
    }
    if directory_fields is not None:
        metadata["directory_fields"] = directory_fields
    return RetrievedDocument(
        id=f"directory-{country.lower()}",
        title=f"{country} directory",
        content=content,
        source=f"s3://approved/directory/{country.lower()}.pdf",
        country="GLOBAL",
        language="en",
        metadata=metadata,
    )


def _policy_document(content: str, *, country: str = "KE") -> RetrievedDocument:
    """A non-directory-shaped approved document (plain policy/prose) --
    carries none of directory_kind/directory_section/directory_fields, so
    app.response.outcome._is_directory_shaped is False for it."""
    return RetrievedDocument(
        id=f"policy-{country.lower()}",
        title=f"{country} policy",
        content=content,
        source=f"s3://approved/{country.lower()}/policy.pdf",
        country=country,
        language="en",
        metadata={},
    )


def _fake_render(key: str, language: str, **placeholders: object) -> str:
    """A minimal stand-in for the not-yet-written app/response/cx_render.py
    (Lane 4). Returns a deterministic, inspectable string rather than real
    localized copy -- exactly what this lane's tests must not invent."""
    parts = ", ".join(f"{name}={value!r}" for name, value in sorted(placeholders.items()))
    return f"{key}[{language}]({parts})"


# --- assess_field_coverage --------------------------------------------------


def test_no_field_requested_is_empty_coverage() -> None:
    document = _directory_document("Kenya Office\nTelephone Office: +254 20 2026869")
    coverage = assess_field_coverage(
        question="What is the minimum order policy?",
        language="en",
        answer_text="The minimum order is 50 CV.",
        evidence_documents=[document],
    )
    assert coverage == FieldCoverage(frozenset(), frozenset(), frozenset(), frozenset())


def test_answered_field_when_value_survives_to_the_answer() -> None:
    document = _directory_document(
        "Kenya Office\nTelephone Office: +254 20 2026869\nEmail: info@kenya.example"
    )
    coverage = assess_field_coverage(
        question="What is the phone number?",
        language="en",
        answer_text="You can reach the Kenya office at +254 20 2026869.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"phone"})
    assert coverage.answered == frozenset({"phone"})
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset()


def test_unsupported_field_when_no_evidence_carries_it() -> None:
    document = _directory_document("Kenya Office\nTelephone Office: +254 20 2026869")
    coverage = assess_field_coverage(
        question="What is the phone number and email?",
        language="en",
        answer_text="You can reach the Kenya office at +254 20 2026869.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"phone", "email"})
    assert coverage.answered == frozenset({"phone"})
    assert coverage.unsupported == frozenset({"email"})
    assert coverage.omitted == frozenset()


def test_omitted_field_when_evidence_has_it_but_answer_dropped_it() -> None:
    document = _directory_document(
        "Kenya Office\nTelephone Office: +254 20 2026869\nEmail: info@kenya.example"
    )
    coverage = assess_field_coverage(
        question="What is the phone number and email?",
        language="en",
        answer_text="You can reach the Kenya office at +254 20 2026869.",
        evidence_documents=[document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"email"})
    assert coverage.answered == frozenset({"phone"})


def test_structured_directory_fields_metadata_is_reused_not_reparsed() -> None:
    # Field values from metadata["directory_fields"] (already extracted by
    # retrieval) must be read exactly like a parsed record -- no second
    # extraction path.
    document = _directory_document(
        "Kenya Office",
        directory_fields={"Telephone Office": "+254 20 2026869"},
    )
    coverage = assess_field_coverage(
        question="What is the phone number?",
        language="en",
        answer_text="Call +254 20 2026869.",
        evidence_documents=[document],
    )
    assert coverage.answered == frozenset({"phone"})


def test_evidence_from_a_non_matching_record_is_still_read_as_passed_in() -> None:
    # assess_field_coverage trusts its evidence_documents argument to already
    # be the approved evidence for this turn -- it does no country matching
    # of its own (that decision belongs to app/evidence.py and the
    # orchestrator's own directory-record resolution).
    document = _directory_document(
        "South Africa Office\nTelephone Office: +27 11 555 0000", country="South Africa"
    )
    coverage = assess_field_coverage(
        question="What is the phone number?",
        language="en",
        answer_text="The Kenya office number is not listed here.",
        evidence_documents=[document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"phone"})


# --- assess_field_coverage: non-English questions ---------------------------


def test_spanish_question_requests_phone_and_email() -> None:
    document = _directory_document(
        "Oficina de Espana\nTelephone Office: +34 900 000 000\nEmail: info@es.example"
    )
    coverage = assess_field_coverage(
        question="Cual es el telefono y el correo electronico?",
        language="es",
        answer_text="El telefono es +34 900 000 000.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"phone", "email"})
    assert coverage.answered == frozenset({"phone"})
    assert coverage.omitted == frozenset({"email"})


def test_french_question_requests_website() -> None:
    document = _directory_document("Bureau de France\nWebsite: www.france.example")
    coverage = assess_field_coverage(
        question="Quel est le site web?",
        language="fr",
        answer_text="Notre site web est www.france.example.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"website"})
    assert coverage.answered == frozenset({"website"})


def test_german_question_requests_address_only() -> None:
    document = _directory_document(
        "Buro Deutschland\nOffice & Product Centre Address: Musterstrasse 1, Berlin"
    )
    coverage = assess_field_coverage(
        question="Wie lautet die Adresse?",
        language="de",
        answer_text="Die Adresse ist unbekannt.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"address"})
    assert coverage.omitted == frozenset({"address"})


def test_finnish_question_requests_phone() -> None:
    document = _directory_document("Suomen toimisto\nTelephone Office: +358 9 000 0000")
    coverage = assess_field_coverage(
        question="Mika on puhelinnumero?",
        language="fi",
        answer_text="Numero on +358 9 000 0000.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"phone"})
    assert coverage.answered == frozenset({"phone"})


def test_unrecognised_language_requests_nothing() -> None:
    document = _directory_document("Office\nTelephone Office: +1 555 0000")
    coverage = assess_field_coverage(
        question="Care este numarul de telefon?",
        language="ro",
        answer_text="Nu stim.",
        evidence_documents=[document],
    )
    assert coverage == FieldCoverage(frozenset(), frozenset(), frozenset(), frozenset())


# --- assess_field_coverage: bulleted fact lines (coordinator BLOCKER fix, --
# --- 2026-09-19) -------------------------------------------------------------

# The real Kenya directory record shape: bulleted facts
# (minimum order/delivery cost/payment methods), THEN a contact block --
# parse_directory_fields only ever saw the contact block; the bullets above
# it were silently dropped, which is exactly what made a real, stated
# payment-methods answer come back "unsupported".
_KENYA_RECORD_CONTENT = (
    "Forever Living Kenya\n"
    "• Minimum order size FBO: 50 CV\n"
    "• Delivery Cost: 500 KES\n"
    "• Payment methods accepted: Bank deposit, Credit Card, "
    "Mobile Money Transfer (Mpesa).\n"
    "Telephone Office: +254 20 2026869\n"
    "Email: info@kenya.example\n"
)


def test_kenya_record_payment_methods_bullet_is_answered() -> None:
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="What payment methods are accepted?",
        language="en",
        answer_text="They accept Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"payment_methods"})
    assert coverage.answered == frozenset({"payment_methods"})
    assert coverage.unsupported == frozenset()


def test_kenya_record_delivery_cost_bullet_is_answered() -> None:
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="What is the delivery cost?",
        language="en",
        answer_text="The delivery cost is 500 KES.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"delivery_cost"})
    assert coverage.answered == frozenset({"delivery_cost"})
    assert coverage.unsupported == frozenset()


def test_kenya_record_payment_methods_bullet_never_unsupported_even_if_dropped_from_answer() -> None:
    # The record states it, but the generated answer never used the value --
    # omitted (a real gap to consider filling), never the stronger, wrong
    # claim "unsupported" (no evidence for it at all).
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="What payment methods are accepted?",
        language="en",
        answer_text="Please contact the office for more details.",
        evidence_documents=[document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"payment_methods"})


def test_kenya_record_missing_field_is_genuinely_unsupported() -> None:
    # The record has no delivery-time bullet at all (only minimum order,
    # delivery cost, payment methods, then contacts) -- this is the one case
    # that SHOULD still be unsupported.
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="What is the delivery time?",
        language="en",
        answer_text="This is not stated in our records.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"delivery_time"})
    assert coverage.unsupported == frozenset({"delivery_time"})


def test_policy_prose_evidence_is_never_unsupported() -> None:
    # Prose can state a fact without ever using the field's own label line --
    # this module has no free-text extraction for that shape (only the
    # labeled-line vocabulary), so it lands as "omitted" (no value
    # collected), never the stronger, wrong claim "unsupported".
    document = _policy_document(
        "Members may pay for their orders by card, bank transfer or mobile money."
    )
    coverage = assess_field_coverage(
        question="What payment methods are accepted?",
        language="en",
        answer_text="You can pay by card, bank transfer or mobile money.",
        evidence_documents=[document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"payment_methods"})


def test_policy_prose_evidence_with_no_stated_value_is_omitted_not_unsupported() -> None:
    document = _policy_document("Orders are processed within two business days.")
    coverage = assess_field_coverage(
        question="What payment methods are accepted?",
        language="en",
        answer_text="This is not covered in the policy.",
        evidence_documents=[document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"payment_methods"})


def test_mixed_directory_and_policy_evidence_is_never_unsupported() -> None:
    # A directory record that lacks delivery_time entirely, alongside a
    # policy document -- mixed evidence must never report unsupported, even
    # for the field the directory record itself does not have.
    directory_document = _directory_document(_KENYA_RECORD_CONTENT)
    policy_document = _policy_document("Standard shipping applies across East Africa.")
    coverage = assess_field_coverage(
        question="What is the delivery time and the payment methods?",
        language="en",
        answer_text="They accept Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).",
        evidence_documents=[directory_document, policy_document],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.answered == frozenset({"payment_methods"})
    assert coverage.omitted == frozenset({"delivery_time"})


def test_no_evidence_at_all_is_never_unsupported() -> None:
    coverage = assess_field_coverage(
        question="What is the delivery time?",
        language="en",
        answer_text="We do not have this information.",
        evidence_documents=[],
    )
    assert coverage.unsupported == frozenset()
    assert coverage.omitted == frozenset({"delivery_time"})


def test_spanish_question_for_bulleted_payment_methods_is_answered() -> None:
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="Cuales son los metodos de pago aceptados?",
        language="es",
        answer_text="Aceptan Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"payment_methods"})
    assert coverage.answered == frozenset({"payment_methods"})
    assert coverage.unsupported == frozenset()


def test_french_question_for_bulleted_delivery_cost_is_answered() -> None:
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="Quel est le cout de livraison?",
        language="fr",
        answer_text="Le cout de livraison est de 500 KES.",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"delivery_cost"})
    assert coverage.answered == frozenset({"delivery_cost"})
    assert coverage.unsupported == frozenset()


def test_german_question_for_bulleted_payment_methods_is_answered() -> None:
    document = _directory_document(_KENYA_RECORD_CONTENT)
    coverage = assess_field_coverage(
        question="Welche Zahlungsmethoden werden akzeptiert?",
        language="de",
        answer_text="Akzeptiert werden Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).",
        evidence_documents=[document],
    )
    assert coverage.requested == frozenset({"payment_methods"})
    assert coverage.answered == frozenset({"payment_methods"})
    assert coverage.unsupported == frozenset()


# --- partial_answer_note ----------------------------------------------------


def test_note_is_none_when_nothing_unsupported() -> None:
    coverage = FieldCoverage(
        requested=frozenset({"phone"}),
        answered=frozenset({"phone"}),
        unsupported=frozenset(),
        omitted=frozenset(),
    )
    assert partial_answer_note(coverage, "en", render=_fake_render) is None


def test_note_renders_the_partial_answer_gap_key_with_sorted_field_ids() -> None:
    coverage = FieldCoverage(
        requested=frozenset({"phone", "email", "website"}),
        answered=frozenset({"phone"}),
        unsupported=frozenset({"website", "email"}),
        omitted=frozenset(),
    )
    note = partial_answer_note(coverage, "es", render=_fake_render)
    assert note == "partial_answer_gap[es](fields=['email', 'website'])"


def test_note_is_none_for_a_non_answer_outcome_kind() -> None:
    coverage = FieldCoverage(
        requested=frozenset({"email"}),
        answered=frozenset(),
        unsupported=frozenset({"email"}),
        omitted=frozenset(),
    )
    assert (
        partial_answer_note(
            coverage, "en", render=_fake_render, outcome_kind=OutcomeKind.EVIDENCE_MISSING
        )
        is None
    )


def test_note_fires_for_partial_answer_outcome_kind() -> None:
    coverage = FieldCoverage(
        requested=frozenset({"email"}),
        answered=frozenset(),
        unsupported=frozenset({"email"}),
        omitted=frozenset(),
    )
    note = partial_answer_note(
        coverage, "de", render=_fake_render, outcome_kind=OutcomeKind.PARTIAL_ANSWER
    )
    assert note == "partial_answer_gap[de](fields=['email'])"


def test_note_is_deterministic() -> None:
    coverage = FieldCoverage(
        requested=frozenset({"phone", "email"}),
        answered=frozenset(),
        unsupported=frozenset({"phone", "email"}),
        omitted=frozenset(),
    )
    first = partial_answer_note(coverage, "fr", render=_fake_render)
    second = partial_answer_note(coverage, "fr", render=_fake_render)
    assert first == second
