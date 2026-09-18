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


def _plan(monkeypatch, message: str, country: str = "NO") -> RetrievalQueryPlan:
    _stub_planner(monkeypatch)
    return _planned_retrieval_plan(message, country, "en", "cid")


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
