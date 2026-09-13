"""Citations for the answer the reader receives, not for the text the model first wrote.

`ResponseBuilder.build` chooses citations from the model's text. The orchestrator
then appends directory contact lines, and numeric repair deletes sentences whose
figures the sources do not state. Citations chosen before those edits used to be
delivered unchanged. `ResponseBuilder.reconcile_citations` chooses them again.
"""

import pytest

from app.response import ResponseBuilder
from app.retrieval import RetrievedDocument, RetrievalResult
from app.validation.validators.numeric_grounding_validator import remove_unsupported_numeric_sentences


def _doc(doc_id, country, section, content, score, parent="", directory=False):
    metadata = {"section_id": section, "parent_section_id": parent}
    if directory:
        metadata.update({"directory_section": "sponsoring", "directory_kind": "international_sponsoring"})
    return RetrievedDocument(
        id=doc_id, title=f"{country} {section}", content=content, source=f"s3://kb/{doc_id}",
        country=country, language="en", score=score, metadata=metadata,
    )


_DIRECTORY = (
    "Welcome to Forever Denmark!\n+45 70 20 30 40\nDelivery Cost: under 2CC - €18 ex VAT per order.\n"
    "Business Hours Office 09.00 am - 16.00 pm (Mon - Fri)\nTelephone Office +45 70 20 30 40\nEmail service@example.dk"
)
_CONTACTS = "\nPhone: +45 70 20 30 40\nEmail: service@example.dk"
_TRIP_CLAUSE = "Section 6.02: c) Incentive trips must be taken within 24 months of qualifying."
_TRIP_SENTENCE = "Incentive trips must be taken within 24 months of qualifying."
# Figures no retrieved source states; numeric repair deletes this sentence.
_INVENTED = (
    "\nThe booking deposit is 450 EUR, the travel insurance premium is 35 EUR, the airport transfer costs 65 EUR, "
    "the hotel city tax is 12 EUR per night, the excursion package costs 180 EUR, the luggage allowance is 23 kg, "
    "and the guest supplement is 390 EUR for each accompanying adult traveller sharing the room."
)
# The cited policy claim and an invented deposit share one sentence, so repair deletes both.
_CLAIM_WITH_INVENTED_DEPOSIT = (
    "Incentive trips must be taken within 24 months of qualifying, with a travel deposit of 450 EUR." + _CONTACTS
)
_REFUSAL = "I'm sorry, the approved documents do not contain enough information to answer that."


def _policy(country="DK", section="6.02-c", content=_TRIP_CLAUSE, score=0.9):
    return _doc(f"{country}:{section}", country, section, content, score, parent=section.split("-")[0])


def _directory():
    return _doc("GLOBAL:sponsoring-dk", "GLOBAL", "sponsoring-dk", _DIRECTORY, 0.8, directory=True)


def _sections(citations):
    return [(citation.get("country"), citation.get("section")) for citation in citations]


def _repaired(answer, documents):
    return remove_unsupported_numeric_sentences(answer, documents)[0]


def _built_and_reconciled(built_answer, delivered_answer, documents, country, metadata=None):
    result = RetrievalResult(documents, [], 0.9, dict(metadata or {}))
    builder = ResponseBuilder()
    built = builder._supporting_citations(built_answer, result, session_country=country)
    reconciled = builder.reconcile_citations(
        built_answer=built_answer,
        delivered_answer=delivered_answer,
        citations=built,
        retrieval_result=result,
        session_country=country,
    )
    return built, reconciled


def test_citations_chosen_before_repair_name_a_claim_the_repair_deleted() -> None:
    """Reproduction: this is what the orchestrator delivered before reconciliation."""
    documents = [_policy(), _directory()]
    delivered = _repaired(_CLAIM_WITH_INVENTED_DEPOSIT, documents)
    built = ResponseBuilder()._supporting_citations(
        _CLAIM_WITH_INVENTED_DEPOSIT, RetrievalResult(documents, [], 0.9), session_country="DK"
    )

    assert "24 months" not in delivered
    assert ("DK", "6.02") in _sections(built)


def test_reconciled_citations_drop_the_passage_whose_claim_was_deleted() -> None:
    documents = [_policy(), _directory()]
    delivered = _repaired(_CLAIM_WITH_INVENTED_DEPOSIT, documents)
    _built, reconciled = _built_and_reconciled(_CLAIM_WITH_INVENTED_DEPOSIT, delivered, documents, "DK")
    assert _sections(reconciled) == [("GLOBAL", "sponsoring-dk")]


def test_reconciled_citations_add_the_support_left_once_invented_figures_are_deleted() -> None:
    """Invented figures diluted every passage below the gate; the delivered answer is grounded."""
    documents = [_policy(), _directory()]
    built_answer = _TRIP_SENTENCE + _INVENTED + _CONTACTS
    delivered = _repaired(built_answer, documents)
    built, reconciled = _built_and_reconciled(built_answer, delivered, documents, "DK")

    assert built == []
    assert _sections(reconciled) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]


def test_repair_that_removes_nothing_returns_the_same_citations() -> None:
    documents = [_policy(), _directory()]
    answer = _TRIP_SENTENCE + _CONTACTS
    delivered = _repaired(answer, documents)
    built, reconciled = _built_and_reconciled(answer, delivered, documents, "DK")

    assert delivered == answer
    assert reconciled == built and all(left is right for left, right in zip(reconciled, built))


def test_appended_directory_lines_leave_citations_unchanged() -> None:
    """Restored contact lines are copied from an approved record; they are not scored as model text."""
    documents = [_policy(), _directory()]
    answer = _TRIP_SENTENCE + _CONTACTS
    built, reconciled = _built_and_reconciled(
        answer, answer + "\n\nTelephone Office: +45 70 20 30 40", documents, "DK"
    )
    assert reconciled == built and all(left is right for left, right in zip(reconciled, built))


def test_inline_markers_and_source_lines_removed_for_display_are_not_a_deletion() -> None:
    documents = [_policy(), _directory()]
    answer = _TRIP_SENTENCE[:-1] + " [1].\nSources: [1]" + _CONTACTS
    delivered = _TRIP_SENTENCE + _CONTACTS
    built, reconciled = _built_and_reconciled(
        answer, delivered, documents, "DK", metadata={"evidence_decision": {"approved": True}}
    )
    assert _sections(built) == [("DK", "6.02")]
    assert reconciled == built


@pytest.mark.parametrize("country", ["", "GLOBAL", None])
def test_unknown_or_global_session_never_gains_a_citation(country) -> None:
    """Without a known reader market foreign policy cannot be told apart, so nothing is added."""
    documents = [_policy(), _directory()]
    built_answer = _TRIP_SENTENCE + _INVENTED + _CONTACTS
    built, reconciled = _built_and_reconciled(built_answer, _repaired(built_answer, documents), documents, country)
    assert built == [] and reconciled == []


@pytest.mark.parametrize("country", ["", "GLOBAL", None])
def test_unknown_or_global_session_still_loses_a_citation_whose_claim_was_deleted(country) -> None:
    documents = [_policy(), _directory()]
    delivered = _repaired(_CLAIM_WITH_INVENTED_DEPOSIT, documents)
    built, reconciled = _built_and_reconciled(_CLAIM_WITH_INVENTED_DEPOSIT, delivered, documents, country)
    assert ("DK", "6.02") in _sections(built)
    assert _sections(reconciled) == [("GLOBAL", "sponsoring-dk")]


def test_another_markets_policy_is_never_added() -> None:
    documents = [_policy(country="SE"), _directory()]
    built_answer = _TRIP_SENTENCE + _INVENTED + _CONTACTS
    _built, reconciled = _built_and_reconciled(built_answer, _repaired(built_answer, documents), documents, "DK")
    assert _sections(reconciled) == [("GLOBAL", "sponsoring-dk")]


def test_a_refusal_that_replaced_the_answer_carries_no_citation() -> None:
    documents = [_policy(), _directory()]
    built, reconciled = _built_and_reconciled(_CLAIM_WITH_INVENTED_DEPOSIT, _REFUSAL, documents, "DK")
    assert built and reconciled == []


def test_directory_citation_stays_only_while_the_answer_still_quotes_its_contact() -> None:
    documents = [_policy(), _directory()]
    built_answer = (
        _TRIP_SENTENCE + "\nCall Forever Denmark on +45 70 20 30 40 or email service@example.dk and quote "
        "booking code 7781 when you pay the 95 EUR fee."
    )
    repaired = _repaired(built_answer, documents)
    assert repaired == _TRIP_SENTENCE

    built, without_contact = _built_and_reconciled(built_answer, repaired, documents, "DK")
    _built, with_restored_contact = _built_and_reconciled(
        built_answer, repaired + "\n\nTelephone Office: +45 70 20 30 40", documents, "DK"
    )
    assert _sections(built) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]
    assert _sections(without_contact) == [("DK", "6.02")]
    assert _sections(with_restored_contact) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]


def test_first_citation_keeps_its_place_when_it_is_still_supported() -> None:
    documents = [_policy(), _directory()]
    built_answer = (
        _TRIP_SENTENCE + "\nThe travel deposit is 450 EUR, insurance is 35 EUR, the airport transfer is 65 EUR "
        "and hotel tax is 12 EUR per night, payable before 15 guests board." + _CONTACTS
    )
    built, reconciled = _built_and_reconciled(built_answer, _repaired(built_answer, documents), documents, "DK")
    assert _sections(built) == [("GLOBAL", "sponsoring-dk"), ("DK", "6.02")]
    assert _sections(reconciled) == _sections(built)


def test_no_more_than_two_citations_are_returned() -> None:
    documents = [
        _directory(),
        _policy(),
        _policy(section="6.03", content="Section 6.03: Incentive trips must be taken within 24 months of qualifying "
                                        "and guests must be 18.", score=0.88),
        _policy(section="6.04", content="Section 6.04: Incentive trips taken within 24 months of qualifying include "
                                        "2 guests.", score=0.86),
    ]
    built_answer = _TRIP_SENTENCE + _INVENTED + _CONTACTS
    _built, reconciled = _built_and_reconciled(built_answer, _repaired(built_answer, documents), documents, "DK")
    assert len(reconciled) == 2
    assert _sections(reconciled)[0] == ("GLOBAL", "sponsoring-dk")


def test_evidence_contract_citations_are_kept_when_their_text_survives() -> None:
    documents = [_policy(), _directory(), _policy(section="6.03", content="Section 6.03: Guests must be 18 or older.")]
    built_answer = "Incentive trips must be taken within 24 months, and a 450 EUR deposit applies." + _CONTACTS
    metadata = {"evidence_contract": {"status": "accepted", "evidence_ids": []}}
    built, reconciled = _built_and_reconciled(
        built_answer, _repaired(built_answer, documents), documents, "DK", metadata=metadata
    )
    assert len(built) == 3
    assert _sections(reconciled) == _sections(built)


# Another step (PII scrub, role-label or source-contradiction correction) can
# rewrite a sentence in place before repair runs. The rewritten sentence is not
# the model's text word for word, but the passage still supports it.
_REWRITTEN_BUILT = _TRIP_SENTENCE + "\nContact Forever Denmark on +45 70 20 30 40.\nThe deposit is 450 EUR."
_REWRITTEN_DELIVERED = (
    "Incentive trips have to be taken within 24 months of qualifying.\nContact Forever Denmark on +45 70 20 30 40."
)


def test_a_sentence_rewritten_by_an_earlier_step_keeps_its_supported_citation() -> None:
    documents = [_policy(), _directory()]
    built, reconciled = _built_and_reconciled(_REWRITTEN_BUILT, _REWRITTEN_DELIVERED, documents, "DK")
    assert _sections(built) == [("DK", "6.02"), ("GLOBAL", "sponsoring-dk")]
    assert _sections(reconciled) == [("DK", "6.02"), ("GLOBAL", "sponsoring-dk")]


def test_a_deleted_claim_is_not_kept_because_a_neighbouring_line_was_rewritten() -> None:
    documents = [_policy(), _directory()]
    built_answer = (
        "Incentive trips must be taken within 24 months of qualifying, with a travel deposit of 450 EUR.\n"
        "Contact Forever Denmark on +45 70 20 30 40."
    )
    built, reconciled = _built_and_reconciled(
        built_answer, "You can contact Forever Denmark on +45 70 20 30 40.", documents, "DK"
    )
    assert ("DK", "6.02") in _sections(built)
    assert _sections(reconciled) == [("GLOBAL", "sponsoring-dk")]


def test_text_used_to_keep_a_citation_excludes_lines_appended_after_the_models_text() -> None:
    """A rewritten line followed by model text stays; trailing lines the model never wrote do not."""
    builder = ResponseBuilder()
    built_answer = "Incentive trips must be taken within 24 months of qualifying.\nPlease contact the office."
    delivered = (
        "Incentive trips have to be taken within 24 months of qualifying.\nPlease contact the office.\n\n"
        "Telephone Office: +45 70 20 30 40\nTelephone for Orders: +45 70 20 30 41"
    )
    assert builder._delivered_model_text(built_answer, delivered, []) == (
        "Incentive trips have to be taken within 24 months of qualifying.\nPlease contact the office."
    )
    assert builder._delivered_model_text(built_answer, "Telephone Office: +45 70 20 30 40", []) == ""


def test_a_rewritten_sentence_never_keeps_another_markets_policy() -> None:
    documents = [_policy(country="SE"), _directory()]
    result = RetrievalResult(documents, [], 0.9)
    builder = ResponseBuilder()
    # Without a known market the foreign passage was cited; a Danish reader must not keep it.
    built = builder._supporting_citations(_REWRITTEN_BUILT, result, session_country="")
    assert ("SE", "6.02") in _sections(built)
    reconciled = builder.reconcile_citations(
        built_answer=_REWRITTEN_BUILT, delivered_answer=_REWRITTEN_DELIVERED, citations=built,
        retrieval_result=result, session_country="DK",
    )
    assert "SE" not in {country for country, _section in _sections(reconciled)}


def test_a_rewritten_answer_replaced_by_a_refusal_carries_no_citation() -> None:
    documents = [_policy(), _directory()]
    built, reconciled = _built_and_reconciled(_REWRITTEN_BUILT, _REFUSAL, documents, "DK")
    assert built and reconciled == []
