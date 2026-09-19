"""R05/N6: directory protection requires genuine compatible runtime intent.

Mocked dependency behaviour. Reproduces (offline) the Norway former-FBO/
downline miss found by ``docs/conversation-quality/phase2/R06_DIAGNOSIS.md``:
a country named in a question is not, by itself, evidence that the question
wants directory/sponsoring content. The raw capture
(``output/evidence-first-v2/retrieval-capture-20260918-r3.json``, case
``ho-slp-16-norway-former-fbo-reapplication-and-downline-no``) shows current
production ranking ``GLOBAL sponsoring-081-norway`` first (score 10.097727)
ahead of the correct policy clause ``NO:17.08-c`` (1.403168) for a question
that only names the country ("Forever Norge") while asking about a former
FBO's reapplication and downline - an ordinary company-policy question.

Root cause: ``_directory_record_country_score`` (app/retrieval/opensearch_sections.py)
unconditionally awards a >= 6.0 target-country-match bonus to a global
directory record whenever a country is named in ``target_country_names``,
regardless of what the question is actually asking for. That bonus feeds
both ``_merge_hits`` (the raw merge score) and, through it,
``_dominant_directory_row``/``_restore_dominant_directory_record`` (the
post-selector dominance guard) - so a country mention alone can bury every
competing policy clause with no genuine directory signal at all.

Fix: the >= 6.0 branches of ``_directory_record_country_score`` now also
require a directory-compatible runtime scope intent (deterministic,
provenance "runtime") whenever one was computed for the request -
``_runtime_scope_intent`` in app/retrieval/providers.py, the existing
classifier V2 already relies on for ``_authorized_policy_market``. "policy"
and "ambiguous" are the two intents that mean a country mention is not a
genuine directory signal; every other intent value ("directory",
"international_sponsoring", and "unknown" - the planner-disabled/
planner-unavailable fallback) keeps the prior, permissive scoring, and a
caller that never computed an intent (``None``, the default) also keeps the
prior behaviour unconditionally - this is an additive gate, not a new
classifier, and it never touches retrieval inclusion (the row can still be
searched for and returned; only its score-driven ranking/protection changes).

``_runtime_scope_intent`` itself gains one new deterministic input,
``directory_topic_route`` in ``_planned_retrieval_plan``, reusing the
existing ``_directory_guard_topic_match`` regex gate verbatim (already used
by the post-selector dominance guard to distinguish "wants directory/
contact/logistics/bonus detail" from "a general policy/rules question that
happens to name a country"). This recovers cross-market sponsoring/bonus
questions that name no operational-field keyword and no literal "sponsor"
root word (e.g. the Ghana bonus-threshold control below), which would
otherwise fall through to "ambiguous" and lose protection right alongside
the genuine Norway regression.

Intent values that count as directory-compatible: "directory",
"international_sponsoring", and "unknown" (the deliberately permissive
planner-off/planner-unavailable fallback). "policy" and "ambiguous" do not.

Language coverage: every regex this intent computation reads
(``SPONSORING_QUESTION_RE``, ``DIRECTORY_OPERATIONAL_QUESTION_RE``,
``DIRECTORY_POLICY_WORDING_RE``, ``_directory_guard_topic_match``'s
components) matches English vocabulary only, so a question can only be
*recognized* as genuinely directory-intentioned in English today. The
*suppression* side is not language-limited, though: it is the default when
nothing matches, so a policy question naming a market in French or Finnish
(or any other language) falls through to "ambiguous" exactly like the
English case, and directory protection is correctly withheld either way -
see the French/Finnish controls below.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_record_country_score,
    _directory_target_country_names,
    _restore_dominant_directory_record,
)
from app.retrieval.providers import RetrievalQueryPlan, _planned_retrieval_plan
from config import settings

NORWAY_QUESTION_EN = (
    "I cancelled my Forever Norge distributorship. When can I reapply to become an FBO "
    "again, and do I keep my old downline?"
)
NORWAY_QUESTION_NO = (
    "Jeg sa opp forhandlerskapet mitt i Forever Norge. Naar kan jeg soke om aa bli FBO "
    "igjen, og faar jeg beholde den gamle downline-en min?"
)
HK_QUESTION = "What is the delivery fee in Hong Kong, and what is the free-delivery threshold?"
GHANA_QUESTION = (
    "I'm an FBO living outside Ghana. How much do I need to earn before Forever Ghana "
    "pays my bonus, and who covers the bank transfer charges?"
)
MEXICO_SPONSORING_QUESTION = "How does international sponsoring work if I sponsor someone in Mexico?"
KENYA_QUESTION = "What are Kenya's business hours?"


def _stub_planner(monkeypatch, scopes: str = "[]", intent: str = "knowledge") -> None:
    """Mock the Bedrock query planner. No network, AWS, or model call happens."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": (
                            '{"queries":[],"document_scopes":' + scopes + ',"intent":"' + intent + '",'
                            '"intent_confidence":0.99}'
                        )
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))


def _plan(monkeypatch, message: str, country: str = "NO", language: str = "en") -> RetrievalQueryPlan:
    _stub_planner(monkeypatch)
    return _planned_retrieval_plan(message, country, language, "cid")


# --- confirmed cause (fail-before, at the scoring-function level) ----------


def test_directory_record_country_score_ignores_intent_when_none_is_supplied() -> None:
    """Legacy/offline callers that never computed a runtime intent (``None``,
    the default) keep the prior, unconditional behaviour - this is the exact
    shape that produced the Norway 8.0 bonus before this fix, preserved on
    purpose for callers (including every pre-existing test in
    ``test_opensearch_sections.py`` and the Kenya/Uganda directory gate
    suite) that construct rows/plans directly without a runtime intent."""
    row = {"document_type": "office_directory", "metadata": {"record_country": "Norway"}}

    assert _directory_record_country_score(NORWAY_QUESTION_EN, row, {"Norway"}) == 8.0
    assert _directory_record_country_score(NORWAY_QUESTION_EN, row, {"Norway"}, None) == 8.0


@pytest.mark.parametrize("intent", ["policy", "ambiguous"])
def test_directory_record_country_score_suppresses_the_bonus_for_incompatible_intent(intent) -> None:
    """A genuine runtime intent of "policy" or "ambiguous" means the country
    mention is not a directory/sponsoring signal - the >= 6.0 bonuses must
    collapse to 0.0 so the row cannot dominate the merge, while retrieval
    inclusion (the row still exists as a candidate) is untouched."""
    exact_match_row = {"document_type": "office_directory", "metadata": {"record_country": "Norway"}}
    substring_match_row = {"document_type": "office_directory", "metadata": {"record_country": "Gambia"}}
    runtime_scope_intent = {"provenance": "runtime", "intent": intent, "decision_source": "test"}

    assert _directory_record_country_score(NORWAY_QUESTION_EN, exact_match_row, {"Norway"}, runtime_scope_intent) == 0.0
    assert (
        _directory_record_country_score(
            "What is Gambia's telephone number, given the policy?", substring_match_row, {"United States"}, runtime_scope_intent
        )
        == 0.0
    )


@pytest.mark.parametrize("intent", ["directory", "international_sponsoring", "unknown"])
def test_directory_record_country_score_keeps_the_bonus_for_compatible_intent(intent) -> None:
    """Directory, sponsoring, and the deliberately permissive "unknown"
    fallback (planner disabled/unavailable) all keep the full bonus - these
    are exactly the intents V2-09's own named controls (Hong Kong, Ghana,
    Kenya, Uganda, Mexico) resolve to."""
    row = {"document_type": "office_directory", "metadata": {"record_country": "Norway"}}
    runtime_scope_intent = {"provenance": "runtime", "intent": intent, "decision_source": "test"}

    assert _directory_record_country_score(NORWAY_QUESTION_EN, row, {"Norway"}, runtime_scope_intent) == 8.0


def test_wrong_country_penalty_is_unaffected_by_intent() -> None:
    """The -4.0 wrong-country penalty is not a boost - it demotes a
    mismatched record so it cannot compete, which never causes the Norway
    shape of bug. It must stay unconditional."""
    row = {"document_type": "office_directory", "metadata": {"record_country": "Sweden"}}
    suppressed = {"provenance": "runtime", "intent": "ambiguous", "decision_source": "test"}

    assert _directory_record_country_score(NORWAY_QUESTION_EN, row, {"Norway"}) == -4.0
    assert _directory_record_country_score(NORWAY_QUESTION_EN, row, {"Norway"}, suppressed) == -4.0


# --- the runtime scope intent computation (English classifier) -------------


def test_norway_shaped_policy_question_is_ambiguous_not_directory(monkeypatch) -> None:
    """The exact failure shape: a company-policy question that only names a
    country. Confirmed cause of the raw capture's 10.097727 vs 1.403168 gap."""
    plan = _plan(monkeypatch, NORWAY_QUESTION_EN)

    assert plan.runtime_scope_intent["intent"] == "ambiguous"
    assert plan.include_global_documents is True  # inclusion is untouched - only ranking/protection changes


@pytest.mark.parametrize("question", [NORWAY_QUESTION_NO], ids=["norwegian"])
def test_norway_question_in_its_own_language_is_also_ambiguous(monkeypatch, question) -> None:
    """The Norwegian original behaves like the English translation: none of
    the English-only classifier regexes match Norwegian text, so this falls
    through to the same safe default ("ambiguous") rather than accidentally
    matching something and being protected anyway."""
    plan = _plan(monkeypatch, question)

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


@pytest.mark.parametrize(
    "question",
    [
        "Quelle est la politique de Forever Norge sur la reinscription apres demission?",
        "Mika on Forever Norjan kaytanto entisen FBO:n uudelleenhakemuksesta?",
    ],
    ids=["french", "finnish"],
)
def test_policy_question_naming_a_market_in_french_or_finnish_is_also_ambiguous(monkeypatch, question) -> None:
    """Suppression is not language-limited: it is the default outcome when
    no English keyword regex matches, so a French or Finnish policy question
    naming a market behaves exactly like the English Norway case and stays
    ambiguous (never falsely promoted to "directory"). Genuine directory
    *recognition* (the classifier's compatible branches - SPONSORING_QUESTION_RE,
    DIRECTORY_OPERATIONAL_QUESTION_RE, _directory_guard_topic_match) is
    English-only today; this is what makes the safe/deny side generalize
    while the allow side does not yet."""
    plan = _plan(monkeypatch, question, country="FR")

    # Whether the result lands on "ambiguous" or "policy" depends only on
    # whether any market name is recognized in the untranslated text (e.g.
    # "Norge" is a configured alias; its Finnish inflection "Norjan" is
    # not) - but both values suppress directory protection identically,
    # which is the actual invariant under test here.
    assert plan.runtime_scope_intent["intent"] in {"ambiguous", "policy"}


def test_hong_kong_delivery_fee_question_is_directory(monkeypatch) -> None:
    """V2-09 regression control: must keep the global record protected."""
    plan = _plan(monkeypatch, HK_QUESTION, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_ghana_cross_market_bonus_question_is_directory(monkeypatch) -> None:
    """V2-09 regression control (the exact fixture wording,
    ``ho-slp-12-gb-session-foreign-fbo-ghana-bonus-threshold-and-charges-en``):
    no operational-field keyword and no literal "sponsor" root word appear,
    so this depends on the new ``directory_topic_route`` signal (the "bonus"
    branch of the reused ``_directory_guard_topic_match`` gate)."""
    plan = _plan(monkeypatch, GHANA_QUESTION, country="GB")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_kenya_business_hours_question_is_still_directory(monkeypatch) -> None:
    """Kenya/Uganda directory gate control: unchanged."""
    plan = _plan(monkeypatch, KENYA_QUESTION, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_us_session_mexico_sponsoring_question_is_international_sponsoring(monkeypatch) -> None:
    """Control: a literal "sponsor" root word routes through the pre-existing
    SPONSORING_QUESTION_RE branch, unaffected by this change."""
    plan = _plan(monkeypatch, MEXICO_SPONSORING_QUESTION, country="US")

    assert plan.runtime_scope_intent["intent"] == "international_sponsoring"


# --- integration: the merge order and the dominance guard -------------------


def _directory_hit(record_id: str, record_country: str, score: float = 1.0) -> dict:
    # Deliberately generic office-directory content (business hours, address,
    # minimum order) - like the real International Sponsoring Directory
    # record - and not lexically similar to the Norway question's actual
    # topic (former-FBO reapplication and downline retention). This is what
    # makes the Norway bug a *scoring* defect rather than a genuine lexical
    # win: the record only leads because of the unconditional country bonus.
    return {
        "_id": record_id,
        "_score": score,
        "_source": {
            "id": record_id,
            "section_id": record_id,
            # Deliberately avoids the literal phrase "Forever <country>" used
            # in the question text - a title/content collision with the
            # question's own wording is a separate, generic lexical-overlap
            # effect (`_source_score`'s title-character-overlap bonus) that
            # is not what this fix addresses, and would otherwise swamp the
            # signal this test isolates.
            "section_title": f"{record_country} Sponsoring Record",
            "source_file": "International Sponsoring Directory",
            "content": (
                "Business Hours Monday - Friday 8:00 - 17:00\n"
                "Telephone Office +000 000 000\n"
                "Address 1 Example Road"
            ),
            "search_text": f"{record_country} business hours telephone address",
            "country": "GLOBAL",
            "language": "en",
            "status": "active",
            "access_scope": "global",
            "document_type": "international_sponsoring_directory",
            "metadata": {
                "directory_kind": "international_sponsoring",
                "directory_section": "sponsoring",
                "record_country": record_country,
            },
        },
    }


def _policy_hit(country: str, section_id: str, score: float = 1.0) -> dict:
    return {
        "_id": f"{country}:{section_id}",
        "_score": score,
        "_source": {
            "id": f"{country}:{section_id}",
            "section_id": section_id,
            "section_title": "Former FBO reapplication and downline retention",
            "content": (
                "A former FBO who reapplies within the configured window retains their prior "
                "downline under company policy."
            ),
            "search_text": "former fbo reapplication downline retention policy",
            "country": country,
            "language": "no",
            "status": "active",
            "access_scope": "country",
            "document_type": "policy",
        },
    }


def test_norway_merge_order_directory_dominates_without_a_runtime_intent() -> None:
    """Fail-before, reproduced at the merge level: with no runtime intent
    (the legacy/offline shape), the directory record's country-match bonus
    still lets it outrank the correct policy clause."""
    provider = OpenSearchSectionProvider()
    directory_hit = _directory_hit("sponsoring-081-norway", "Norway")
    policy_hit = _policy_hit("NO", "17.08-c")

    rows = provider._merge_hits(
        [directory_hit, policy_hit], [], NORWAY_QUESTION_EN, target_country_names={"Norway"}
    )

    assert rows[0][0]["id"] == "sponsoring-081-norway"


def test_norway_merge_order_policy_clause_wins_once_intent_is_ambiguous() -> None:
    """The fix: once the actual computed runtime intent ("ambiguous") is
    threaded through, the directory record's bonus collapses to 0.0 and the
    policy clause - which has ordinary lexical/vector relevance to the
    question - outranks it."""
    provider = OpenSearchSectionProvider()
    directory_hit = _directory_hit("sponsoring-081-norway", "Norway")
    policy_hit = _policy_hit("NO", "17.08-c")
    runtime_scope_intent = {"provenance": "runtime", "intent": "ambiguous", "decision_source": "test"}

    rows = provider._merge_hits(
        [directory_hit, policy_hit],
        [],
        NORWAY_QUESTION_EN,
        target_country_names={"Norway"},
        runtime_scope_intent=runtime_scope_intent,
    )

    assert rows[0][0]["id"] == "NO:17.08-c"


def test_dominance_guard_does_not_restore_norway_when_intent_is_ambiguous() -> None:
    """The post-selector dominance guard must not resurrect the directory
    record either, once the runtime intent rules out protection - even when
    its raw score would otherwise clear the dominance thresholds."""
    directory_row = {
        "id": "sponsoring-081-norway",
        "document_type": "international_sponsoring_directory",
        "metadata": {"record_country": "Norway"},
    }
    policy_row = {"id": "NO:17.08-c", "document_type": "policy"}
    raw_rows = [(directory_row, 10.097727), (policy_row, 1.403168)]
    selector_rows = [(policy_row, 1.403168), (directory_row, 10.097727)]
    runtime_scope_intent = {"provenance": "runtime", "intent": "ambiguous", "decision_source": "test"}

    restored = _restore_dominant_directory_record(
        NORWAY_QUESTION_EN, raw_rows, selector_rows, {"Norway"}, runtime_scope_intent
    )

    assert restored == selector_rows


def test_dominance_guard_still_restores_a_genuine_directory_question() -> None:
    """Control mirroring the Kyrgyzstan production fixture pinned in
    ``test_opensearch_sections.py``: when the runtime intent is
    "international_sponsoring" (a genuine "bonus" question), the guard still
    restores the dominant, country-matched directory record."""
    directory_row = {
        "id": "kyrgyzstan-bonus-payment",
        "document_type": "office_directory",
        "metadata": {"record_country": "Kyrgyzstan"},
    }
    policy_row = {"id": "us-policy-4-04-f", "document_type": "policy"}
    raw_rows = [(directory_row, 9.444), (policy_row, 1.066)]
    selector_rows = [(policy_row, 1.066), (directory_row, 9.444)]
    runtime_scope_intent = {
        "provenance": "runtime",
        "intent": "international_sponsoring",
        "decision_source": "test",
    }

    restored = _restore_dominant_directory_record(
        "How are foreign FBOs paid their bonus in Kyrgyzstan?", raw_rows, selector_rows, {"Kyrgyzstan"}, runtime_scope_intent
    )

    assert restored[0][0]["id"] == "kyrgyzstan-bonus-payment"


# --- full retrieve() pipeline controls (V2-09 named regressions) -----------


class _Client:
    """Locale searches return a policy row; global searches return the directory row(s)."""

    def __init__(self, global_hits: list[dict], local_hits: list[dict] | None = None) -> None:
        self.global_hits = global_hits
        self.local_hits = local_hits if local_hits is not None else []

    def search(self, index: str, body: dict) -> dict:
        del index
        is_global = "'access_scope': 'global'" in repr(body)
        return {"hits": {"hits": list(self.global_hits if is_global else self.local_hits)}}


@pytest.fixture
def _offline_retrieval(monkeypatch):
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda *_a, **_k: [0.0])
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "RETRIEVAL_PARENT_DIVERSITY_ENABLED", False)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)


def _retrieve_with_real_planner(monkeypatch, message: str, country: str, client) -> "opensearch_sections.RetrievalResult":
    _stub_planner(monkeypatch)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=MagicMock()))
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    provider = OpenSearchSectionProvider()
    return provider.retrieve(message, country, "en", "fbo", "cid")


def test_norway_retrieve_ranks_policy_evidence_at_or_above_the_directory_record(monkeypatch, _offline_retrieval) -> None:
    client = _Client(
        [_directory_hit("sponsoring-081-norway", "Norway")],
        [_policy_hit("NO", "17.08-c")],
    )
    result = _retrieve_with_real_planner(monkeypatch, NORWAY_QUESTION_EN, "NO", client)

    assert result.documents, "the policy clause must still be returned"
    assert result.documents[0].id == "NO:17.08-c"


def test_hong_kong_retrieve_keeps_the_global_record_at_rank_one(monkeypatch, _offline_retrieval) -> None:
    client = _Client([_directory_hit("sponsoring-030-hong-kong", "Hong Kong")])
    result = _retrieve_with_real_planner(monkeypatch, HK_QUESTION, "US", client)

    assert result.documents[0].id == "sponsoring-030-hong-kong"


def test_ghana_retrieve_keeps_the_global_record_at_rank_one(monkeypatch, _offline_retrieval) -> None:
    client = _Client(
        [_directory_hit("sponsoring-010-ghana", "Ghana")],
        [_policy_hit("GB", "9.01")],
    )
    result = _retrieve_with_real_planner(monkeypatch, GHANA_QUESTION, "GB", client)

    assert result.documents[0].id == "sponsoring-010-ghana"


def test_mexico_retrieve_keeps_the_global_record_at_rank_one(monkeypatch, _offline_retrieval) -> None:
    client = _Client([_directory_hit("sponsoring-mexico", "Mexico")])
    result = _retrieve_with_real_planner(monkeypatch, MEXICO_SPONSORING_QUESTION, "US", client)

    assert result.documents[0].id == "sponsoring-mexico"


def test_kenya_retrieve_directory_gate_target_resolution_is_unchanged() -> None:
    """The Kenya/Uganda gate tests do not construct a runtime intent at all
    (they monkeypatch ``_build_search_plan`` directly), so this only checks
    the shared, untouched target-resolution helper - the gate tests
    themselves (``test_demo_kenya_directory_gate.py``) are not modified."""
    assert _directory_target_country_names(KENYA_QUESTION, "US") == {"Kenya"}


# --- R05/N6 follow-up (2026-09-18): multilingual directory-intent RECOGNITION
#
# An independent review of the fix above found that RECOGNITION (not
# suppression) was English-only: SPONSORING_QUESTION_RE,
# DIRECTORY_OPERATIONAL_QUESTION_RE, and _DIRECTORY_GUARD_TOPIC_RE all match
# English vocabulary only, so a genuine directory question phrased in
# Spanish, French, or German fell through to "ambiguous" and lost the
# country bonus entirely (8.0 -> 0.0), alongside two English shapes that
# name no field literally ("reach", "credit cards"). Every case below is
# taken verbatim from the reviewer's repro set: US session, a Ghana
# `international_sponsoring_directory` row, targets={'Ghana'}.

GHANA_PHONE_QUESTION_ES = "¿Cuál es el número de teléfono de Forever Ghana?"
GHANA_PHONE_QUESTION_FR = "Quel est le numéro de téléphone de Forever Ghana ?"
GHANA_ADDRESS_QUESTION_DE = "Wie lautet die Adresse von Forever Ghana?"
GHANA_REACH_QUESTION_EN = "How do I reach Forever Ghana?"
GHANA_LOCATED_QUESTION_EN = "Where is Forever Ghana located?"
GHANA_CREDIT_CARDS_QUESTION_EN = "Does Forever Ghana accept credit cards?"
GHANA_ADDRESS_QUESTION_EN = "What is the Ghana office address?"
GHANA_COUNTRY_MANAGER_QUESTION_EN = "Who is the country manager for Forever Ghana?"


@pytest.mark.parametrize(
    "question,language",
    [
        (GHANA_PHONE_QUESTION_ES, "es"),
        (GHANA_PHONE_QUESTION_FR, "fr"),
        (GHANA_ADDRESS_QUESTION_DE, "de"),
    ],
    ids=["spanish-phone", "french-phone", "german-address"],
)
def test_reviewer_repro_non_english_directory_field_question_is_directory(monkeypatch, question, language) -> None:
    """Fail-before: each question literally names a directory field
    (teléfono/téléphone/Adresse) in its own request language, using terms
    already reviewed in ``config/directory_field_vocabulary.py``'s
    ``LANGUAGE_FIELD_TERMS`` for 13 languages - this needed no new
    vocabulary, only wiring ``utils.directory_fields.directory_field_intent_present``
    into ``_runtime_scope_intent``."""
    plan = _plan(monkeypatch, question, country="US", language=language)

    assert plan.runtime_scope_intent["intent"] == "directory"


@pytest.mark.parametrize(
    "question",
    [GHANA_REACH_QUESTION_EN, GHANA_LOCATED_QUESTION_EN, GHANA_CREDIT_CARDS_QUESTION_EN],
    ids=["reach", "located", "credit-cards"],
)
def test_reviewer_repro_english_contact_or_payment_synonym_is_directory(monkeypatch, question) -> None:
    """Fail-before: "located" already matched English's own
    ``_FIELD_REQUEST_PATTERNS["address"]`` before this task (it was simply
    never consulted from ``providers.py``); "reach" and "credit cards" name
    no existing field term at all and needed the new, small, closed
    ``DIRECTORY_INTENT_SYNONYM_TERMS["en"]`` addition."""
    plan = _plan(monkeypatch, question, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_ghana_office_address_control_still_directory(monkeypatch) -> None:
    """Control from the reviewer's own repro set: this English phrasing
    already worked before this follow-up (via ``_DIRECTORY_DETAIL_RE``/
    ``_directory_guard_topic_match``) and must keep working."""
    plan = _plan(monkeypatch, GHANA_ADDRESS_QUESTION_EN, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_ghana_country_manager_question_names_no_field_and_stays_ambiguous(monkeypatch) -> None:
    """"Country manager" names no canonical directory field (phone, email,
    website, address, business hours, payment methods, delivery cost/time,
    fax) in any vocabulary this fix reads, and matches none of the existing
    English deterministic routes either (no operational keyword, no
    "sponsor" root word, no ``_DIRECTORY_DETAIL_RE`` wording). It therefore
    stays "ambiguous" and loses the country-match bonus, exactly like
    before this follow-up - a genuine, documented gap (see
    ``directory_field_intent_present``'s docstring), not a regression this
    task introduces."""
    plan = _plan(monkeypatch, GHANA_COUNTRY_MANAGER_QUESTION_EN, country="US")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


def test_norway_english_still_suppressed_after_multilingual_recognition(monkeypatch) -> None:
    """Regression guard: the new multilingual field check must never flip
    the Norway former-FBO/downline question (which names no directory
    field in any language) from "ambiguous" to "directory"."""
    plan = _plan(monkeypatch, NORWAY_QUESTION_EN, country="NO")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


def test_norway_norwegian_still_suppressed_after_multilingual_recognition(monkeypatch) -> None:
    """Same control in Norwegian, the request's own language - "no" is one
    of the 13 languages ``directory_field_intent_present`` reads, but the
    Norwegian text names no directory field either, so this must also stay
    "ambiguous", not be newly (and wrongly) promoted by this follow-up."""
    plan = _plan(monkeypatch, NORWAY_QUESTION_NO, country="NO", language="no")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


def test_unrecognized_language_falls_back_to_english_only_recognition(monkeypatch) -> None:
    """A request language this module has no vocabulary for (e.g. "xx", not
    one of the 13 configured languages nor a real BCP-47 tag) must fall back
    to exactly the English-only recognition that existed before this
    follow-up - no better and no worse. The Ghana phone question written in
    Spanish, but declared under an unrecognized language tag, therefore
    stays "ambiguous": ``directory_field_intent_present`` returns ``False``
    for an unrecognized language (see its docstring), and the message text
    itself matches none of the English-only deterministic routes either
    (no "sponsor" root word, no ``DIRECTORY_OPERATIONAL_QUESTION_RE``/
    ``_DIRECTORY_DETAIL_RE`` wording - "teléfono" is not an English word).
    This is identical to the pre-N6 (``5b1d33f``) shape for the same
    reason: an unconditional country bonus never depended on language
    either, and this fix does not change what happens for a language it
    does not recognize."""
    plan = _plan(monkeypatch, GHANA_PHONE_QUESTION_ES, country="US", language="xx")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


# --- R05/N6 follow-up NOTE 6: "bonus" alone must not imply directory intent


def test_norway_own_market_bonus_mention_stays_ambiguous(monkeypatch) -> None:
    """Independent review NOTE 6: ``_DIRECTORY_GUARD_TOPIC_RE`` (reused
    verbatim by ``directory_topic_route``) includes a bare "bonus" branch,
    so a Norway-shaped, own-market policy question that happens to also
    mention "bonus" must not be promoted to "directory" on that word alone
    - that is exactly the class of bug this task exists to close. The
    distinguishing signal already exists and needed no new vocabulary: the
    session's own market (``country="NO"``) is the ONLY market named in the
    message, so this is not a genuinely cross-market question."""
    norway_with_bonus = (
        "I cancelled my Forever Norge distributorship. When can I reapply to become an FBO "
        "again, and do I keep my old downline and their bonus?"
    )
    plan = _plan(monkeypatch, norway_with_bonus, country="NO")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


def test_ghana_cross_market_bonus_question_still_directory_after_note_6_gate(monkeypatch) -> None:
    """The pre-existing Ghana cross-market bonus control
    (``test_ghana_cross_market_bonus_question_is_directory`` above) must
    still resolve to "directory" once the NOTE 6 gate is added: the message
    names Ghana while the session's own market is GB, so
    ``named_markets - {own_market_code}`` is non-empty and the "bonus"-only
    match is trusted."""
    plan = _plan(monkeypatch, GHANA_QUESTION, country="GB")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_kyrgyzstan_foreign_fbo_bonus_question_still_directory_after_note_6_gate(monkeypatch) -> None:
    """Real 2026-09-14 production-failure shape control: a US session asking
    about foreign FBOs' bonus payment in Kyrgyzstan is genuinely
    cross-market (Kyrgyzstan named, session market is US) and must stay
    "directory" after the NOTE 6 gate."""
    plan = _plan(monkeypatch, "How are foreign FBOs paid their bonus in Kyrgyzstan?", country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_bonus_with_other_directory_wording_is_unaffected_by_note_6_gate(monkeypatch) -> None:
    """The NOTE 6 gate only narrows the case where "bonus" is the SOLE
    reason ``_directory_guard_topic_match`` fired. A question that also
    carries independent directory/operational wording (here, "business
    hours") alongside "bonus" must still resolve to "directory" even for an
    own-market question, because that other wording is its own signal,
    untouched by this gate."""
    plan = _plan(
        monkeypatch,
        "What are Forever Norge's business hours, and how is my bonus calculated?",
        country="NO",
    )

    assert plan.runtime_scope_intent["intent"] == "directory"


# --- full retrieve() pipeline control: a non-English multilingual repro ----


def test_ghana_spanish_phone_retrieve_keeps_the_global_record_at_rank_one(monkeypatch, _offline_retrieval) -> None:
    """End-to-end control mirroring ``test_ghana_retrieve_keeps_the_global_record_at_rank_one``
    but in Spanish, the request language, exercising the full
    ``retrieve()`` pipeline (merge + dominance guard) rather than only the
    classifier."""
    client = _Client(
        [_directory_hit("sponsoring-010-ghana", "Ghana")],
        [_policy_hit("GB", "9.01")],
    )
    _stub_planner(monkeypatch)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=MagicMock()))
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    provider = OpenSearchSectionProvider()
    result = provider.retrieve(GHANA_PHONE_QUESTION_ES, "GB", "es", "fbo", "cid")

    assert result.documents[0].id == "sponsoring-010-ghana"


# --- R05/N6 second follow-up (2026-09-18): Fable re-review findings F1/F2 --
#
# F1: the multilingual field-intent disjunct added above is 13-language, but
# the policy-wording suppression it is checked alongside
# (DIRECTORY_POLICY_WORDING_RE = policy|rules, is_policy_safety_question) was
# still English-only, so a NON-English POLICY question naming a field was
# wrongly promoted to "directory" instead of staying "policy" - reopening
# the N6 class of bug. Every repro below is taken verbatim from the
# reviewer's stubbed-planner (scopes=[]) Norway/Ghana repro set.

NORWAY_POLICY_PAYMENT_QUESTION_ES = (
    "¿Cuál es la política de Forever Norway sobre los métodos de pago?"
)
NORWAY_POLICY_ADDRESS_QUESTION_FR = (
    "Quelles sont les règles de Forever Norge sur l'adresse de livraison ?"
)
NORWAY_POLICY_EMAIL_QUESTION_DE = (
    "Welche Regeln gelten bei Forever Norge für die Rückgabe per E-Mail?"
)
GHANA_POLICY_DELIVERY_QUESTION_FR = (
    "Quelle est la politique de Forever Ghana sur les frais de livraison ?"
)


@pytest.mark.parametrize(
    "question,country,language",
    [
        (NORWAY_POLICY_PAYMENT_QUESTION_ES, "NO", "es"),
        (NORWAY_POLICY_ADDRESS_QUESTION_FR, "NO", "fr"),
        (NORWAY_POLICY_EMAIL_QUESTION_DE, "NO", "de"),
        (GHANA_POLICY_DELIVERY_QUESTION_FR, "GB", "fr"),
    ],
    ids=["spanish-payment", "french-address", "german-email", "french-ghana-delivery"],
)
def test_f1_reviewer_repro_non_english_policy_question_naming_a_field_stays_policy(
    monkeypatch, question, country, language
) -> None:
    """Fail-before (F1): each question uses localized policy/rules wording
    (politica/politique/Regeln) AND names a directory field in the same
    language (metodos de pago/adresse de livraison/E-Mail/frais de
    livraison) - before this fix, the field disjunct fired and there was no
    non-English policy-wording check to stop it, so these resolved to
    "directory" with the full 8.0 bonus. The English equivalent
    ("What is the policy of Forever Norway on payment methods?") already
    correctly resolves to "policy"/0.0."""
    plan = _plan(monkeypatch, question, country=country, language=language)

    assert plan.runtime_scope_intent["intent"] == "policy"


@pytest.mark.parametrize(
    "question,language",
    [
        (GHANA_PHONE_QUESTION_ES, "es"),
        (GHANA_PHONE_QUESTION_FR, "fr"),
        (GHANA_ADDRESS_QUESTION_DE, "de"),
    ],
    ids=["spanish-phone", "french-phone", "german-address"],
)
def test_f1_earlier_non_english_directory_repros_stay_directory(monkeypatch, question, language) -> None:
    """Regression guard: the F1 policy-wording fix must not suppress the
    earlier (non-policy) non-English directory repros - none of these use
    any localized policy/rules wording, so they must keep resolving to
    "directory"/8.0."""
    plan = _plan(monkeypatch, question, country="US", language=language)

    assert plan.runtime_scope_intent["intent"] == "directory"


@pytest.mark.parametrize(
    "question",
    [GHANA_REACH_QUESTION_EN, GHANA_LOCATED_QUESTION_EN, GHANA_CREDIT_CARDS_QUESTION_EN],
    ids=["reach", "located", "credit-cards"],
)
def test_f1_earlier_english_synonym_repros_stay_directory(monkeypatch, question) -> None:
    """Regression guard: the F1/F2 changes must not disturb the earlier
    English contact/payment-synonym repros."""
    plan = _plan(monkeypatch, question, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


# F2: the "reach" synonym in DIRECTORY_INTENT_SYNONYM_TERMS["en"] compiled
# with a leading word-start boundary only, so it also matched inflected
# forms like "reaches" - a bare contact verb false-positive unrelated to
# the intended "How do I reach Forever Ghana?" shape.

GHANA_DOWNLINE_REACHES_MANAGER_QUESTION = (
    "What happens to my downline in Ghana when it reaches Manager level?"
)


def test_f2_reviewer_repro_reaches_inflection_does_not_trigger_directory_synonym(monkeypatch) -> None:
    """Fail-before (F2): "reaches" (an inflected verb form describing a
    downline reaching a rank, not a contact request) must not match the
    "reach" synonym and must not be promoted to "directory" by it. This
    question names no directory field and no other directory/operational
    wording, so it must land on "ambiguous"."""
    plan = _plan(monkeypatch, GHANA_DOWNLINE_REACHES_MANAGER_QUESTION, country="US")

    assert plan.runtime_scope_intent["intent"] == "ambiguous"


def test_f2_bare_reach_synonym_still_matches_as_a_whole_word(monkeypatch) -> None:
    """Control: the literal word "reach" itself must still match after the
    trailing boundary was added - only its inflected forms are excluded."""
    plan = _plan(monkeypatch, GHANA_REACH_QUESTION_EN, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_f2_contact_question_still_routes_to_directory_without_the_synonym(monkeypatch) -> None:
    """"contact" was removed from DIRECTORY_INTENT_SYNONYM_TERMS as
    redundant with opensearch_sections._DIRECTORY_DETAIL_RE (already
    matches "contact" and feeds deterministic_directory_route independently
    of this synonym set) - this question must still resolve to "directory"
    through that route."""
    plan = _plan(monkeypatch, "How do I contact Forever Ghana?", country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


# --- R05/N6 third follow-up (2026-09-18): coordinator review of 88da3cc ----
#
# The F1 policy-wording set only spelled its accented forms ("política"),
# so a question that omits accents entirely - which users routinely do -
# did not match it, while LANGUAGE_FIELD_TERMS's own field patterns
# (e.g. Spanish "m[eé]todos?\s+de\s+pago") already tolerate the missing
# accent. That asymmetry let an accentless non-English policy question
# fall through to the (accent-tolerant) field disjunct and be wrongly
# promoted to "directory" - the exact F1 bug, reopened for accentless
# input. Fixed by accent-folding (NFKD, strip combining marks, casefold)
# both POLICY_WORDING_TERMS and the question before matching.

NORWAY_POLICY_PAYMENT_QUESTION_ES_NO_ACCENT = (
    "Cual es la politica de Forever Norway sobre los metodos de pago?"
)
NORWAY_POLICY_ADDRESS_QUESTION_FR_NO_ACCENT = (
    "Quelles sont les regles de Forever Norge sur l'adresse de livraison ?"
)
GHANA_POLICY_PAYMENT_QUESTION_PT_ACCENTED = (
    "Qual é a política de Forever Ghana sobre as formas de pagamento?"
)
GHANA_POLICY_PAYMENT_QUESTION_PT_NO_ACCENT = (
    "Qual e a politica de Forever Ghana sobre as formas de pagamento?"
)
NORWAY_POLICY_EMAIL_QUESTION_DE_CONTROL = NORWAY_POLICY_EMAIL_QUESTION_DE  # "Regeln" already has no accent


@pytest.mark.parametrize(
    "question,country,language",
    [
        (NORWAY_POLICY_PAYMENT_QUESTION_ES_NO_ACCENT, "NO", "es"),
        (NORWAY_POLICY_ADDRESS_QUESTION_FR_NO_ACCENT, "NO", "fr"),
        (GHANA_POLICY_PAYMENT_QUESTION_PT_NO_ACCENT, "GB", "pt"),
        (NORWAY_POLICY_EMAIL_QUESTION_DE_CONTROL, "NO", "de"),
    ],
    ids=["spanish-accentless", "french-accentless", "portuguese-accentless", "german-control-no-accent-to-begin-with"],
)
def test_f1_accentless_non_english_policy_question_stays_policy(monkeypatch, question, country, language) -> None:
    """Fail-before (coordinator review of 88da3cc): the accentless Spanish/
    French/Portuguese spellings of the F1 repros must resolve to "policy"
    exactly like their accented originals - users routinely omit accents.
    German is included as a same-shape control: "Regeln" already carries no
    accent, so this proves the fix is additive and does not regress the
    case that already worked."""
    plan = _plan(monkeypatch, question, country=country, language=language)

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_f1_accented_and_accentless_spanish_policy_question_agree(monkeypatch) -> None:
    """Direct before/after pairing: the accented and accentless spellings of
    the same Spanish question must resolve identically."""
    accented = _plan(monkeypatch, NORWAY_POLICY_PAYMENT_QUESTION_ES, country="NO", language="es")
    accentless = _plan(monkeypatch, NORWAY_POLICY_PAYMENT_QUESTION_ES_NO_ACCENT, country="NO", language="es")

    assert accented.runtime_scope_intent["intent"] == "policy"
    assert accentless.runtime_scope_intent["intent"] == "policy"


def test_f1_portuguese_accented_policy_question_stays_policy(monkeypatch) -> None:
    """Control: the accented Portuguese original must also resolve to
    "policy" (Portuguese was not in the original F1 repro set)."""
    plan = _plan(monkeypatch, GHANA_POLICY_PAYMENT_QUESTION_PT_ACCENTED, country="GB", language="pt")

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_f1_nfd_decomposed_accented_policy_question_stays_policy(monkeypatch) -> None:
    """A question can arrive with its accents already NFD-decomposed (a
    base letter followed by a separate combining-mark codepoint, rather
    than one precomposed character) - a different Unicode encoding of the
    identical accented text, not different content. This must resolve to
    "policy" exactly like the NFC (precomposed) spelling."""
    import unicodedata

    nfd_question = unicodedata.normalize("NFD", NORWAY_POLICY_PAYMENT_QUESTION_ES)
    assert nfd_question != NORWAY_POLICY_PAYMENT_QUESTION_ES  # sanity: actually decomposed
    assert unicodedata.normalize("NFC", nfd_question) == NORWAY_POLICY_PAYMENT_QUESTION_ES

    plan = _plan(monkeypatch, nfd_question, country="NO", language="es")

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_f1_localized_policy_wording_present_unit_accent_variants() -> None:
    """Unit-level control directly on ``localized_policy_wording_present``,
    isolating the accent-folding fix from the full retrieval-plan pipeline:
    accented, accentless, and NFD-decomposed Spanish/French/Portuguese
    policy wording must all be recognized, and Cyrillic (ru/sr) entries -
    unaffected by NFKD folding, since they have no decomposable diacritic -
    must be unchanged."""
    import unicodedata

    from utils.directory_fields import localized_policy_wording_present

    assert localized_policy_wording_present("Cual es la politica?", language="es") is True
    assert localized_policy_wording_present("¿Cuál es la política?", language="es") is True
    assert localized_policy_wording_present(
        unicodedata.normalize("NFD", "¿Cuál es la política?"), language="es"
    ) is True
    assert localized_policy_wording_present("Quelles sont les regles?", language="fr") is True
    assert localized_policy_wording_present("Qual e a politica?", language="pt") is True
    assert localized_policy_wording_present("Какова политика?", language="ru") is True
    assert localized_policy_wording_present("Kakva je politika?", language="sr") is True
    assert localized_policy_wording_present("What is the delivery cost?", language="es") is False


# --- R05/N6 fourth follow-up (2026-09-18): coordinator review finding S1 ---
#
# Fable review of 88da3cc/0b1f0e3 found POLICY_WORDING_TERMS's docstring
# claimed "policy/rules/regulations/terms" coverage that did not actually
# exist - only "policy"/"rules" nominative/plural forms were present, and
# DIRECTORY_POLICY_WORDING_RE (English) was still "policy|rules" only. Every
# repro below is taken verbatim from the reviewer's stubbed-planner
# (scopes=[]) Norway directory-row repro set and must resolve to "policy",
# not "directory".

GHANA_PHONE_METHODS_QUESTION_EN = "What payment methods does Forever Norway accept?"


@pytest.mark.parametrize(
    "question,language",
    [
        ("¿Cuál es el reglamento de Forever Norway sobre la dirección de entrega?", "es"),
        ("Согласно политике Forever Norway, какой адрес доставки?", "ru"),
    ],
    ids=["spanish-reglamento", "russian-dative-politike"],
)
def test_s1_reviewer_repro_regulation_condition_guideline_wording_stays_policy(
    monkeypatch, question, language
) -> None:
    """Fail-before (S1): each question uses a regulation-family policy
    synonym POLICY_WORDING_TERMS did not cover before this follow-up
    (reglamento, the Russian dative "политике") AND names a directory field
    (dirección/адрес) in the same language - before this fix these resolved
    to "directory"/8.0; the English equivalent already correctly stays
    "policy". Both "reglamento" and the ru oblique cases remain part of the
    sixth follow-up's kept vocabulary (see
    ``config/directory_field_vocabulary.py``'s ``POLICY_WORDING_TERMS``),
    so this assertion is unchanged by that later follow-up."""
    plan = _plan(monkeypatch, question, country="NO", language=language)

    assert plan.runtime_scope_intent["intent"] == "policy"


# R05/N6 sixth follow-up (2026-09-18, coordinator review of 99ec438): the
# three repros below (spanish-condiciones, french-conditions,
# italian-condizioni) used to be parametrized alongside the two above,
# asserting "policy". A later, independent Fable review found that bare
# "condiciones"/"conditions"/"condizioni" (plural, no country/field
# specificity) are themselves dominated in ordinary usage by an idiomatic,
# non-policy sense ("la oficina esta en buenas condiciones" = "the office
# is in good condition") - see the 27-probe false-suppression finding
# documented in ``config/directory_field_vocabulary.py``'s
# ``POLICY_WORDING_TERMS`` comment. The coordinator's explicit decision was
# to drop every bare condition-family form, keeping only the compound
# "terms and conditions" phrase - so these three repros now correctly
# resolve to "directory" again (the country-bonus PROTECTION reopens for
# this shape, exactly as it was before the fourth follow-up). This
# assertion is CHANGED, not deleted, per the coordinator's explicit
# instruction to document every such change rather than silently drop the
# test.
@pytest.mark.parametrize(
    "question,language",
    [
        ("¿Cuáles son las condiciones de Forever Norway sobre la dirección de entrega?", "es"),
        ("Quelles sont les conditions de Forever Norge sur l'adresse de livraison ?", "fr"),
        ("Quali sono le condizioni di Forever Norway sull'indirizzo di consegna?", "it"),
    ],
    ids=["spanish-condiciones", "french-conditions", "italian-condizioni"],
)
def test_s1_bare_condition_repros_now_resolve_directory_after_sixth_follow_up(
    monkeypatch, question, language
) -> None:
    """CHANGED assertion (sixth follow-up, coordinator review of 99ec438):
    was "policy" under the fourth follow-up; bare plural "condiciones"/
    "conditions"/"condizioni" is now dropped from POLICY_WORDING_TERMS
    (its dominant sense is idiomatic/circumstantial, not a policy document
    - see the module's own comment), so these now correctly resolve to
    "directory"/8.0 again."""
    plan = _plan(monkeypatch, question, country="NO", language=language)

    assert plan.runtime_scope_intent["intent"] == "directory"


@pytest.mark.parametrize(
    "question",
    [
        "What are the regulations of Forever Norway on the delivery address?",
        "What are the terms and conditions of Forever Norway on the delivery address?",
    ],
    ids=["english-regulations", "english-terms-and-conditions"],
)
def test_s1_reviewer_repro_english_regulation_condition_guideline_wording_stays_policy(
    monkeypatch, question
) -> None:
    """Fail-before (S1): the same hole existed in English -
    DIRECTORY_POLICY_WORDING_RE only matched "policy"/"rules", so
    "regulations"/"terms and conditions" fell through to
    deterministic_directory_route (via "address" matching
    _DIRECTORY_DETAIL_RE) and were wrongly promoted to "directory". Both
    "regulations" and "terms and conditions" remain kept after the sixth
    follow-up, so this assertion is unchanged by that later follow-up
    (unlike the "english-guidelines" case, moved below)."""
    plan = _plan(monkeypatch, question, country="NO")

    assert plan.runtime_scope_intent["intent"] == "policy"


# R05/N6 sixth follow-up (2026-09-18): "english-guidelines" used to be
# parametrized alongside the two cases above, asserting "policy". Bare
# "guidelines" is dropped from DIRECTORY_POLICY_WORDING_RE by this
# follow-up (its dominant sense is someone's personal/professional
# guidance - "guidelines from my doctor" - not a Forever policy document),
# so this now correctly resolves to "directory" again. CHANGED, not
# deleted, per the coordinator's explicit instruction.
def test_s1_bare_guidelines_repro_now_resolves_directory_after_sixth_follow_up(monkeypatch) -> None:
    """CHANGED assertion (sixth follow-up, coordinator review of 99ec438):
    was "policy" under the fourth follow-up; bare "guidelines" is now
    dropped from ``DIRECTORY_POLICY_WORDING_RE``
    (``app/retrieval/providers.py``), so this now correctly resolves to
    "directory"/8.0 again."""
    plan = _plan(
        monkeypatch,
        "What are the guidelines of Forever Norway on the delivery address?",
        country="NO",
    )

    assert plan.runtime_scope_intent["intent"] == "directory"


@pytest.mark.parametrize(
    "question",
    [GHANA_REACH_QUESTION_EN, "How do I contact Forever Ghana?"],
    ids=["reach", "contact"],
)
def test_s1_directory_controls_unaffected_reach_and_contact(monkeypatch, question) -> None:
    """False-suppression guard: neither "condition(s)" nor any other S1
    addition appears in these questions, so they must keep resolving to
    "directory" exactly as before this follow-up."""
    assert "condition" not in question.lower()
    plan = _plan(monkeypatch, question, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


@pytest.mark.parametrize(
    "question,language",
    [
        (GHANA_PHONE_QUESTION_ES, "es"),
        (GHANA_PHONE_QUESTION_FR, "fr"),
        (GHANA_ADDRESS_QUESTION_DE, "de"),
    ],
    ids=["spanish-phone", "french-phone", "german-address"],
)
def test_s1_directory_controls_unaffected_non_english_phone_and_address(monkeypatch, question, language) -> None:
    """False-suppression guard: the es/fr/de phone and address repros carry
    none of the new regulation/condition/guideline vocabulary and must keep
    resolving to "directory"."""
    plan = _plan(monkeypatch, question, country="US", language=language)

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s1_directory_control_payment_methods_unaffected(monkeypatch) -> None:
    """False-suppression guard: a plain payment-methods directory question
    naming no policy-family word at all must keep resolving to "directory"."""
    plan = _plan(monkeypatch, GHANA_PHONE_METHODS_QUESTION_EN, country="US")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s1_condition_word_absent_from_directory_control_questions() -> None:
    """Explicit proof (per the coordinator's instruction) that "condition"/
    "conditions" does not appear in any of the standing directory control
    questions this suite relies on - so the S1 additions cannot be silently
    suppressing them."""
    controls = [
        GHANA_REACH_QUESTION_EN,
        GHANA_LOCATED_QUESTION_EN,
        GHANA_CREDIT_CARDS_QUESTION_EN,
        GHANA_ADDRESS_QUESTION_EN,
        GHANA_PHONE_QUESTION_ES,
        GHANA_PHONE_QUESTION_FR,
        GHANA_ADDRESS_QUESTION_DE,
        GHANA_PHONE_METHODS_QUESTION_EN,
        "How do I contact Forever Ghana?",
    ]
    for question in controls:
        assert "condition" not in question.lower()


def test_s1_localized_policy_wording_present_unit_new_terms() -> None:
    """Unit-level control directly on ``localized_policy_wording_present``
    for every S1 addition, isolated from the full retrieval-plan pipeline.

    R05/N6 sixth follow-up (2026-09-18, coordinator review of 99ec438):
    most of this test's assertions are CHANGED (True -> False), not
    deleted, per the coordinator's explicit instruction to document every
    such change. Only the words whose dominant sense is a policy document
    survive: the original F1 policy/rules set, the regulation(s)
    equivalents, and the ru oblique cases of политика/правила - see
    ``config/directory_field_vocabulary.py``'s ``POLICY_WORDING_TERMS``
    comment for the full rationale and the 27-probe false-suppression
    finding that drove this change. Every bare condition-family and
    guideline-family form below is now False; each line says which."""
    from utils.directory_fields import localized_policy_wording_present as p

    assert p("Cual es el reglamento?", language="es") is True  # regulation(s) equivalent: kept
    assert p("Cuales son las condiciones?", language="es") is False  # CHANGED: bare condition-family, dropped
    assert p("Cual es la directriz?", language="es") is False  # CHANGED: bare guideline-family, dropped
    assert p("Quel est le reglement?", language="fr") is True  # regulation(s) equivalent (original F1): kept
    assert p("Quelles sont les conditions?", language="fr") is False  # CHANGED: bare condition-family, dropped
    assert p("Quelle est la directive?", language="fr") is False  # CHANGED: bare guideline-family, dropped
    assert p("Was ist die Vorschrift?", language="de") is True  # regulation(s) equivalent: kept
    assert p("Was ist die Bestimmung?", language="de") is False  # CHANGED: dominant sense is "destination", dropped
    assert p("Was ist die Bedingung?", language="de") is False  # CHANGED: bare condition-family, dropped
    assert p("Wat zijn de voorwaarden?", language="nl") is False  # CHANGED: bare condition-family, dropped
    assert p("Wat is de richtlijn?", language="nl") is False  # CHANGED: bare guideline-family, dropped (was never actually in the original F1 set despite the fourth follow-up's docstring claim)
    assert p("Qual e il regolamento?", language="it") is True  # regulation(s) equivalent: kept
    assert p("Quali sono le condizioni?", language="it") is False  # CHANGED: bare condition-family, dropped
    assert p("Qual e la linea guida?", language="it") is False  # CHANGED: bare guideline-family, dropped
    assert p("Qual e o regulamento?", language="pt") is True  # regulation(s) equivalent: kept
    assert p("Quais sao as condicoes?", language="pt") is False  # CHANGED: bare condition-family, dropped
    assert p("Qual e a diretriz?", language="pt") is False  # CHANGED: bare guideline-family, dropped
    assert p("Mitkä ovat ehdot?", language="fi") is False  # CHANGED: bare condition-family, dropped
    assert p("Mikä on määräys?", language="fi") is False  # CHANGED: singular dropped - only plural "maaraykset" is kept, per the coordinator's exact wording
    assert p("Mikä on ohje?", language="fi") is False  # CHANGED: bare guideline-family, dropped
    assert p("Hva er vilkår for retur?", language="no") is False  # CHANGED: bare condition-family, dropped
    assert p("Hva er reglene?", language="no") is True  # CHANGED AGAIN (seventh follow-up): rules-family definite plural, restored - see test_s7_* below
    assert p("Hvad er vilkår for retur?", language="da") is False  # CHANGED: bare condition-family, dropped
    assert p("Hvad er reglerne?", language="da") is True  # CHANGED AGAIN (seventh follow-up): rules-family definite plural, restored - see test_s7_* below
    assert p("Vad är villkor för retur?", language="sv") is False  # CHANGED: bare condition-family, dropped
    assert p("Vad är reglerna?", language="sv") is True  # CHANGED AGAIN (seventh follow-up): rules-family definite plural, restored - see test_s7_* below
    assert p("Согласно политике", language="ru") is True  # oblique case of политика: explicitly kept by the coordinator
    assert p("по политику", language="ru") is True  # oblique case of политика: explicitly kept
    assert p("политикой", language="ru") is True  # oblique case of политика: explicitly kept
    assert p("правилам", language="ru") is True  # oblique case of правила: explicitly kept
    assert p("правилами", language="ru") is True  # oblique case of правила: explicitly kept
    assert p("в правилах", language="ru") is True  # oblique case of правила: explicitly kept
    assert p("условия", language="ru") is False  # CHANGED: bare condition-family, dropped
    assert p("условиях", language="ru") is False  # CHANGED: bare condition-family, dropped
    assert p("politici", language="sr") is False  # CHANGED: sr oblique forms were not explicitly named in the coordinator's KEEP list (only ru's were), so sr reverts to its original F1 set
    assert p("politikom", language="sr") is False  # CHANGED: same reasoning as "politici" above
    assert p("pravilima", language="sr") is True  # CHANGED AGAIN (seventh follow-up): rules-family oblique plural, restored - see test_s7_* below
    assert p("uslovi", language="sr") is False  # CHANGED: bare condition-family, dropped
    assert p("условима", language="sr") is False  # CHANGED: bare condition-family, dropped
    # Not a false positive: an unrelated question in a covered language.
    assert p("Cual es el telefono?", language="es") is False


def test_s6_compound_terms_and_conditions_phrases_present_across_languages() -> None:
    """New (sixth follow-up, coordinator review of 99ec438): the compound
    "terms and conditions" phrase, added per language as the sole surviving
    way to recognize the condition/guideline-adjacent sense, since it
    cannot fire on a bare word appearing alone elsewhere in a question."""
    from utils.directory_fields import localized_policy_wording_present as p

    assert p("Cuales son los terminos y condiciones?", language="es") is True
    assert p("Quelles sont les conditions generales ?", language="fr") is True
    assert p("Was sind die Geschaftsbedingungen?", language="de") is True
    assert p("Wo finde ich die AGB?", language="de") is True
    assert p("Was sind die Nutzungsbedingungen?", language="de") is True
    assert p("Wat zijn de algemene voorwaarden?", language="nl") is True
    assert p("Quali sono i termini e condizioni?", language="it") is True
    assert p("Quais sao os termos e condicoes?", language="pt") is True
    assert p("Hva er vilkar og betingelser?", language="no") is True
    assert p("Hvad er salgsbetingelser?", language="da") is True
    assert p("Las vara allmanna villkor innan du bestaller.", language="sv") is True
    assert p("Mitka ovat kayttoehdot?", language="fi") is True
    assert p("Mitka ovat toimitusehdot?", language="fi") is True
    assert p("Kakovy usloviya ispolzovaniya", language="ru") is False  # transliterated (not Cyrillic) - proves the phrase match is script-specific, not a false positive from partial matching
    assert p("Каковы условия использования?", language="ru") is True
    assert p("Каковы условия продажи?", language="ru") is True


def test_s6_richtlinie_kept_with_justification(monkeypatch) -> None:
    """German "Richtlinie"/"Richtlinien" is the sole guideline-family word
    kept, because it was part of the original, second-follow-up F1 set
    (already reviewed then), not a new addition - see the justification
    comment directly above ``POLICY_WORDING_TERMS`` in
    ``config/directory_field_vocabulary.py``. Full pipeline control: a
    German question combining "Richtlinie" with a directory field name
    must resolve to "policy", not "directory"."""
    plan = _plan(
        monkeypatch,
        "Was ist die Richtlinie von Forever Norge zur Lieferadresse?",
        country="NO",
        language="de",
    )

    assert plan.runtime_scope_intent["intent"] == "policy"


# --- R05/N6 fifth follow-up (2026-09-18): coordinator review of d77c13f ----
#
# Two English false-suppression leaks in the fourth follow-up's own
# DIRECTORY_POLICY_WORDING_RE widening: (1) "terms of" matched *inside* the
# unrelated "in terms of X" idiom, not just the intended "terms of
# service"/"terms of payment" phrasing; (2) singular "condition" matched a
# genuine physical-condition question with no policy-document sense at all.

OFFICE_HOURS_IN_TERMS_OF_WEEKENDS_QUESTION = (
    "What are the office hours of Forever Norway in terms of weekends?"
)
PHONE_AND_GOOD_CONDITION_QUESTION = (
    "What is the phone number of Forever Norway? Is the office in good condition?"
)
TERMS_OF_PAYMENT_QUESTION = "What are the terms of payment at Forever Norway?"


def test_s2_reviewer_repro_in_terms_of_idiom_stays_directory(monkeypatch) -> None:
    """Fail-before (S2a): "in terms of weekends" is the exact "in terms of
    X" idiom the fourth follow-up's "terms of" addition was supposed to
    exclude, but did not - it wrongly suppressed a genuine office-hours
    directory question to "policy". Must stay "directory"/8.0."""
    plan = _plan(monkeypatch, OFFICE_HOURS_IN_TERMS_OF_WEEKENDS_QUESTION, country="NO")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s2_reviewer_repro_singular_condition_stays_directory(monkeypatch) -> None:
    """Fail-before (S2b): "in good condition" is a genuine physical-condition
    question (about the office itself, not a policy document) that the
    fourth follow-up's singular "condition" wrongly suppressed. Must stay
    "directory"/8.0 - the phone-number mention alone already establishes
    directory intent."""
    plan = _plan(monkeypatch, PHONE_AND_GOOD_CONDITION_QUESTION, country="NO")

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s2_terms_of_payment_still_stays_policy(monkeypatch) -> None:
    """Control: the genuine "terms of X" policy-document phrasing (not
    preceded by "in") must still resolve to "policy" after the lookbehind
    fix - only the "in terms of X" idiom is excluded, not "terms of"
    generally."""
    plan = _plan(monkeypatch, TERMS_OF_PAYMENT_QUESTION, country="NO")

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_s2_directory_policy_wording_regex_unit_controls() -> None:
    """Unit-level control directly on DIRECTORY_POLICY_WORDING_RE, isolated
    from the full retrieval-plan pipeline."""
    from app.retrieval.providers import DIRECTORY_POLICY_WORDING_RE as policy_re

    assert policy_re.search(OFFICE_HOURS_IN_TERMS_OF_WEEKENDS_QUESTION) is None
    assert policy_re.search(PHONE_AND_GOOD_CONDITION_QUESTION) is None
    assert policy_re.search(TERMS_OF_PAYMENT_QUESTION) is not None
    assert policy_re.search("What are the terms and conditions of Forever Norway?") is not None
    assert policy_re.search("certain terms of service apply") is not None
    assert policy_re.search("What is the return policy?") is not None


# R05/N6 sixth follow-up (2026-09-18, coordinator review of 99ec438): the
# "-plural-policy" cases below (es/fr/it/pt) used to assert True. The
# fifth follow-up's own reasoning - "the plural is not idiomatic that way
# in any of the four [Romance languages]" - was factually wrong: a later,
# independent Fable review found "buenas condiciones"/"conditions de
# vente" (unqualified)/"buone condizioni"/"boas condicoes" ARE the standard
# plural idiom for a physical/circumstantial sense too ("La oficina esta
# en buenas condiciones?" = "Is the office in good condition?", exactly as
# ambiguous as the singular). The coordinator's decision drops the bare
# plural for these four languages as well, keeping only the compound
# "terminos y condiciones"/"conditions generales"/"termini e condizioni"/
# "termos e condicoes" phrase (see
# ``test_s6_compound_terms_and_conditions_phrases_present_across_languages``
# above). Every "-plural-policy" id below is CHANGED (True -> False), not
# deleted, per the coordinator's explicit instruction; the singular cases
# were already False and are unaffected.
@pytest.mark.parametrize(
    "text,language,expected",
    [
        ("¿Está el teléfono en buena condición?", "es", False),
        ("¿Cuáles son las condiciones de venta?", "es", False),  # CHANGED: was True; bare plural is itself the idiom, dropped
        ("Le téléphone est en bonne condition ?", "fr", False),
        ("Quelles sont les conditions de vente ?", "fr", False),  # CHANGED: was True; bare plural is itself the idiom, dropped
        ("Il telefono è in buona condizione?", "it", False),
        ("Quali sono le condizioni di vendita?", "it", False),  # CHANGED: was True; bare plural is itself the idiom, dropped
        ("O telefone está em boa condição?", "pt", False),
        ("Quais são as condições de venda?", "pt", False),  # CHANGED: was True; bare plural is itself the idiom, dropped
    ],
    ids=[
        "es-singular-physical-not-policy", "es-plural-also-not-policy",
        "fr-singular-physical-not-policy", "fr-plural-also-not-policy",
        "it-singular-physical-not-policy", "it-plural-also-not-policy",
        "pt-singular-physical-not-policy", "pt-plural-also-not-policy",
    ],
)
def test_s2_romance_language_bare_condition_forms_dropped_entirely(text, language, expected) -> None:
    """Neither the singular NOR the bare plural condition-family form
    triggers policy wording in these four Romance languages any more - see
    the sixth follow-up note above this test. Only the compound "terms and
    conditions" phrase (tested separately) still does."""
    from utils.directory_fields import localized_policy_wording_present as p

    assert p(text, language=language) is expected


# R05/N6 sixth follow-up (2026-09-18): every id below used to assert True
# ("...kept"). A later, independent Fable review found that German "unter
# der Bedingung" ("under the condition that"), Dutch "onder voorwaarde
# dat", Finnish, Russian "в условиях пандемии" ("under pandemic
# conditions"), and Serbian all have the same circumstance/conjunction
# sense the Romance languages do, dominant enough in ordinary usage that
# the coordinator's decision drops every bare condition-family form
# regardless of language, keeping only each language's compound "terms and
# conditions" phrase. CHANGED (True -> False), not deleted, per the
# coordinator's explicit instruction.
@pytest.mark.parametrize(
    "text,language",
    [
        ("Welche Bedingung gilt hier?", "de"),
        ("Wat is de voorwaarde?", "nl"),
        ("Mikä on ehto?", "fi"),
        ("Какое условие?", "ru"),
        ("Koji je uslov?", "sr"),
    ],
    ids=["german-singular-dropped", "dutch-singular-dropped", "finnish-singular-dropped", "russian-singular-dropped", "serbian-singular-dropped"],
)
def test_s2_non_romance_bare_condition_forms_also_dropped_after_sixth_follow_up(text, language) -> None:
    """CHANGED (sixth follow-up, coordinator review of 99ec438): these
    bare condition-family forms are no longer recognized in any language -
    only each language's compound "terms and conditions" phrase is."""
    from utils.directory_fields import localized_policy_wording_present as p

    assert p(text, language=language) is False


# --- R05/N6 sixth follow-up (2026-09-18): every reviewer idiom repro, ------
# --- as a full-pipeline "directory" control -------------------------------
#
# Per the coordinator's explicit instruction: the 16 distinct example
# shapes the coordinator's message quoted from the review (of the 35
# probes the review ran, 27 of which were false suppressions) are
# exercised here as a full ``_planned_retrieval_plan`` control, each
# embedded in a question that also names a genuine directory field
# (address/phone) so the assertion proves not merely "not policy" but the
# full, correct "directory"/8.0 protection outcome.
@pytest.mark.parametrize(
    "question,country,language",
    [
        (
            "¿Cuál es la dirección de Forever Ghana? ¿La oficina está en buenas condiciones?",
            "US", "es",
        ),
        (
            "Qual è l'indirizzo di Forever Ghana? L'ufficio è in buone condizioni?",
            "US", "it",
        ),
        (
            "Qual é o endereço de Forever Ghana? O escritório está em boas condições?",
            "US", "pt",
        ),
        (
            "What are the road conditions near Forever Ghana's office address?",
            "US", "en",
        ),
        (
            "What is Forever Ghana's phone number? What are the weather conditions?",
            "US", "en",
        ),
        (
            "Какой адрес Forever Norway? В условиях пандемии офис работает как обычно?",
            "NO", "ru",
        ),
        (
            "Hva er telefonnummeret til Forever Norge? Uansett vilkår, er kontoret åpent?",
            "NO", "no",
        ),
        (
            "Hvad er telefonnummeret på Forever Norge? Under alle vilkår er kontoret åbent.",
            "NO", "da",
        ),
        (
            "Vad är telefonnumret till Forever Norge? Under alla villkor är kontoret öppet?",
            "NO", "sv",
        ),
        (
            "Wat is het telefoonnummer van Forever Ghana? Onder voorwaarde dat, is het kantoor open?",
            "US", "nl",
        ),
        (
            "Wie lautet die Telefonnummer von Forever Norge? Nur unter der Bedingung, dass das Büro geöffnet ist?",
            "NO", "de",
        ),
        (
            "Wie lautet die Telefonnummer von Forever Norge? Was ist die Bestimmung meiner Sendung?",
            "NO", "de",
        ),
        (
            "Quelle est l'adresse de Forever Ghana ? Dans ces conditions, le bureau est-il ouvert ?",
            "US", "fr",
        ),
        (
            "Quel est le numéro de téléphone de Forever Ghana ? Je suis les directives de mon médecin.",
            "US", "fr",
        ),
        (
            "Qual è l'indirizzo di Forever Ghana? Seguo le linee guida del mio medico.",
            "US", "it",
        ),
        (
            "¿Cuál es el número de teléfono de Forever Ghana? Sigo las directrices de mi médico.",
            "US", "es",
        ),
    ],
    ids=[
        "es-buenas-condiciones", "it-buone-condizioni", "pt-boas-condicoes",
        "en-road-conditions", "en-weather-conditions", "ru-usloviyakh-pandemii",
        "no-uansett-vilkar", "da-under-alle-vilkar", "sv-under-alla-villkor",
        "nl-onder-voorwaarde-dat", "de-unter-der-bedingung", "de-bestimmung-destination",
        "fr-dans-ces-conditions", "fr-directives-du-medecin",
        "it-linee-guida-del-medico", "es-directrices",
    ],
)
def test_s6_reviewer_idiom_repros_stay_directory(monkeypatch, question, country, language) -> None:
    """Fail-before (sixth follow-up, coordinator review of 99ec438): every
    one of these idiom/subordinate-clause shapes was wrongly suppressed to
    "policy"/0.0 by the fourth/fifth follow-ups' bare condition/guideline
    vocabulary. Each also names a genuine directory field (address or
    phone) in the same sentence, so a correct outcome is "directory"/8.0,
    not merely "not policy"."""
    plan = _plan(monkeypatch, question, country=country, language=language)

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s6_whitespace_collapse_prevents_in_terms_of_leak(monkeypatch) -> None:
    """New (sixth follow-up): irregular/doubled whitespace inside "in terms
    of" must not defeat the fixed-width negative lookbehind in
    DIRECTORY_POLICY_WORDING_RE. Before the whitespace-collapse fix in
    _runtime_scope_intent, "in  terms  of" (double-spaced) would not match
    the lookbehind (exactly one space) and would leak through as if it were the
    accepted "terms of X" phrasing, wrongly suppressing this genuine
    office-hours directory question to "policy"."""
    plan = _plan(
        monkeypatch,
        "What are the  office  hours of Forever Norway in  terms  of weekends?",
        country="NO",
    )

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s6_whitespace_collapse_unit_control() -> None:
    """Unit-level control directly on the whitespace-collapse behaviour,
    isolated from the full retrieval-plan pipeline."""
    from app.retrieval.providers import _runtime_scope_intent

    result = _runtime_scope_intent(
        "What are the office hours of Forever Norway in  terms  of weekends?",
        include_global_documents=True,
        named_markets={"Norway"},
        shared_office_markets=set(),
        deterministic_directory_route=True,
        language="en",
    )

    assert result["intent"] == "directory"


# --- R05/N6 seventh follow-up (2026-09-18): coordinator review of 52cee7b -
#
# The sixth follow-up over-corrected: "reglene"/"reglerne"/"reglerna" (the
# definite PLURAL of no/da/sv "regel" = "rule") are rules-family, squarely
# inside the KEEP list's "policy/RULES family" - not guideline-family, and
# not condition-family - but were swept up and dropped alongside the
# (correctly dropped) retningslinjene/riktlinjerna guideline-family
# definite forms because neither was "explicitly named" in the sixth
# follow-up's KEEP list. Restored, narrowly: only the definite plural of
# "regel" itself for no/da/sv, and "pravilima"/"правилима" (the
# dative/instrumental plural of Serbian "pravila" = rules) for sr.


@pytest.mark.parametrize(
    "question,language",
    [
        ("Hva er reglene til Forever Norge for leveringsadressen?", "no"),
        ("Hvad er reglerne for Forever Norge for leveringsadressen?", "da"),
        ("Vad är reglerna för Forever Norge för leveransadressen?", "sv"),
    ],
    ids=["norwegian-reglene", "danish-reglerne", "swedish-reglerna"],
)
def test_s7_reviewer_repro_scandinavian_rules_definite_plural_stays_policy(monkeypatch, question, language) -> None:
    """Fail-before (S7, sixth follow-up over-correction): "the rules of
    Forever Norge for the delivery address" is the ordinary way to phrase
    a rules-family policy question in Norwegian/Danish/Swedish using the
    definite plural of "regel". Must resolve to "policy"/0.0, exactly like
    its English equivalent ("What are the rules of Forever Norge for the
    delivery address?")."""
    plan = _plan(monkeypatch, question, country="NO", language=language)

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_s7_reviewer_repro_serbian_pravilima_stays_policy(monkeypatch) -> None:
    """Fail-before (S7): "pravilima" (dative/instrumental plural of
    "pravila" = rules) is rules-family, restored alongside the
    Scandinavian definite plurals above. Must resolve to "policy"/0.0."""
    plan = _plan(
        monkeypatch,
        "Koja su pravilima Forever Norge za adresu isporuke?",
        country="NO",
        language="sr",
    )

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_s7_retningslinjene_and_riktlinjerna_stay_dropped(monkeypatch) -> None:
    """Regression guard: the guideline-family definite plurals
    (retningslinjene, riktlinjerna) must stay dropped - only the
    rules-family "reglene"/"reglerna" were restored, not the entire
    "definite plural" shape regardless of which word it inflects."""
    no_plan = _plan(
        monkeypatch,
        "Hva er retningslinjene til Forever Norge for telefonnummeret?",
        country="NO",
        language="no",
    )
    sv_plan = _plan(
        monkeypatch,
        "Vad är riktlinjerna för Forever Norge för telefonnumret?",
        country="NO",
        language="sv",
    )

    assert no_plan.runtime_scope_intent["intent"] == "directory"
    assert sv_plan.runtime_scope_intent["intent"] == "directory"


def test_s7_serbian_politika_oblique_and_uslov_family_stay_dropped(monkeypatch) -> None:
    """Regression guard: only "pravilima"/"правилима" (rules-family) was
    restored for Serbian - politika's own oblique forms (politici,
    politiku, politikom) and the entire uslov/услов condition-family stay
    dropped, exactly as the sixth follow-up left them."""
    politici_plan = _plan(
        monkeypatch,
        "Koja je politici Forever Norge za adresu isporuke?",
        country="NO",
        language="sr",
    )
    uslovi_plan = _plan(
        monkeypatch,
        "Koji su uslovi Forever Norge za adresu isporuke?",
        country="NO",
        language="sr",
    )

    assert politici_plan.runtime_scope_intent["intent"] == "directory"
    assert uslovi_plan.runtime_scope_intent["intent"] == "directory"


def test_s7_som_regel_idiom_control_unchanged(monkeypatch) -> None:
    """"som regel" ("as a rule") control, documented in N1: restoring
    "reglene" does not change the pre-existing, already-accepted "som
    regel" idiom trade-off (that idiom is matched by bare "regel", which
    was never dropped) - a genuinely directory-intentioned Norwegian
    question using the idiom is still suppressed to "policy", exactly as
    before this follow-up. Not fixed here; this control proves the
    restoration did not touch that pre-existing, documented trade-off
    either way."""
    plan = _plan(
        monkeypatch,
        "Vi gjør dette som regel hver dag. Hva er telefonnummeret til Forever Norge?",
        country="NO",
        language="no",
    )

    assert plan.runtime_scope_intent["intent"] == "policy"


def test_s7_localized_policy_wording_present_unit_control() -> None:
    """Unit-level control directly on ``localized_policy_wording_present``
    for every S7 restoration and its regression guards, isolated from the
    full retrieval-plan pipeline."""
    from utils.directory_fields import localized_policy_wording_present as p

    assert p("Hva er reglene?", language="no") is True
    assert p("Hvad er reglerne?", language="da") is True
    assert p("Vad är reglerna?", language="sv") is True
    assert p("pravilima", language="sr") is True
    assert p("правилима", language="sr") is True
    assert p("Hva er retningslinjene?", language="no") is False
    assert p("Vad är riktlinjerna?", language="sv") is False
    assert p("politici", language="sr") is False
    assert p("uslovi", language="sr") is False


# --- R05/N6 eighth follow-up (2026-09-18): coordinator review of a53dcae --
# --- (three LOW findings) --------------------------------------------------
#
# Finding 1: whitespace collapse previously happened only in
# _runtime_scope_intent, so "in  terms  of" (double-spaced) could still
# leak through three other call sites that searched
# DIRECTORY_POLICY_WORDING_RE against the raw message directly:
# own_market_directory_route (app/retrieval/providers.py),
# _directory_guard_topic_match and own_market_field
# (app/retrieval/opensearch_sections.py). Also, "within terms of X" (the
# "in" is not its own word inside "within", so the existing
# "(?<!\bin\s)" lookbehind never excluded it) was wrongly treated as the
# accepted "terms of X" policy-document phrasing. Fixed with a single
# helper, ``directory_policy_wording_present`` (app/retrieval/providers.py),
# which collapses whitespace and adds a second lookbehind excluding
# "within terms of" too - used at all four sites, one source of truth.


def test_s8_directory_policy_wording_present_unit_control() -> None:
    """Unit-level control directly on the new helper, isolated from any
    call site."""
    from app.retrieval.providers import directory_policy_wording_present as p

    assert p("within terms of the delivery cost") is False
    assert p("in terms of the delivery cost") is False
    assert p("the terms of service") is True
    assert p("certain terms of service apply") is True
    assert p("office hours in  terms  of weekends") is False  # double-spaced
    assert p("office hours within  terms  of weekends") is False  # double-spaced


def test_s8_runtime_scope_intent_gate_within_terms_of(monkeypatch) -> None:
    """Gate 1: _runtime_scope_intent (via the full pipeline). "within terms
    of" must not suppress a genuine directory question."""
    plan = _plan(
        monkeypatch,
        "What are the office hours of Forever Norway within  terms  of weekends?",
        country="NO",
    )

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s8_own_market_directory_route_gate_within_terms_of(monkeypatch) -> None:
    """Gate 2: own_market_directory_route (app/retrieval/providers.py). A
    no-country-named delivery-cost question using "within terms of" must
    still resolve to "directory", exercised through the full pipeline
    against a market with a configured own-market directory record."""
    plan = _plan(
        monkeypatch,
        "What is Forever NL's delivery cost within  terms  of shipping speed?",
        country="NL",
    )

    assert plan.runtime_scope_intent["intent"] == "directory"


def test_s8_directory_guard_topic_match_gate_within_terms_of() -> None:
    """Gate 3: _directory_guard_topic_match (app/retrieval/opensearch_sections.py),
    tested directly. "within terms of" must not be treated as policy
    wording, so the topic gate still fires on the address wording present
    in the same question."""
    from app.retrieval.opensearch_sections import _directory_guard_topic_match

    assert _directory_guard_topic_match(
        "What is the office address within  terms  of the delivery schedule?"
    ) is True
    # Control: genuine policy wording still suppresses the gate.
    assert _directory_guard_topic_match(
        "What are the regulations for the office address?"
    ) is False


def test_s8_own_market_field_gate_within_terms_of() -> None:
    """Gate 4: own_market_field, inside _directory_target_country_names
    (app/retrieval/opensearch_sections.py), tested directly against a
    market configured with its own directory record (NL). "within terms
    of" must not block the own-market fallback."""
    within_result = _directory_target_country_names(
        "What is the delivery cost within  terms  of shipping speed?", "NL"
    )
    policy_result = _directory_target_country_names(
        "What are the regulations on the delivery cost?", "NL"
    )

    assert within_result  # non-empty: own-market fallback still applies
    assert not policy_result  # empty: genuine policy wording still suppresses it
