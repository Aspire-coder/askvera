"""Regression tests for document-driven section scoring."""

import pytest

from app.retrieval import section_index
from app.retrieval.models import RetrievedDocument
from app.retrieval.section_index import (
    _confidence_from_documents,
    _purchase_channel_score,
    _return_policy_score,
    _source_score,
)
from config import settings


def _row(section_id: str, title: str, content: str) -> dict[str, object]:
    return {
        "rank": 0.5,
        "section_id": section_id,
        "section_title": title,
        "content": content,
        "search_text": f"{title}\n{content}",
    }


def test_exact_rank_phrase_beats_adjacent_rank_section() -> None:
    """A literal rank name should prefer its governing section, not a nearby mention."""
    recognized = _row(
        "5.01",
        "Recognized Manager",
        "5.01 Recognized Manager requirements and recognition.",
    )
    nearby = _row(
        "8.04",
        "Gem Manager",
        "A Recognized Manager may later qualify for a Gem Manager award.",
    )

    question = "What is a Recognized Manager?"
    assert _source_score(recognized, question) > _source_score(nearby, question)


def test_distinctive_program_name_beats_generic_policy_text() -> None:
    """A document's own branded program name receives an exact-match preference."""
    program = _row(
        "10.01",
        "Earned Incentive Program / Forever2Drive",
        "Forever2Drive is part of the Earned Incentive Program.",
    )
    generic = _row(
        "9.01",
        "Leadership Bonus",
        "Managers can qualify for leadership bonuses.",
    )

    question = "What is Forever2Drive?"
    assert _source_score(program, question) > _source_score(generic, question)


def test_document_title_match_is_unicode_safe() -> None:
    """Scoring must use the document language rather than an English term list."""
    governing = _row(
        "7.03",
        "Conditions pour devenir Manager",
        "Les conditions pour devenir Manager sont decrites dans cette section.",
    )
    nearby = _row(
        "7.04",
        "Programme de reconnaissance",
        "Un Manager peut recevoir une reconnaissance ulterieure.",
    )

    question = "Quelles sont les conditions pour devenir Manager?"
    assert _source_score(governing, question) > _source_score(nearby, question)


def _document(score: float) -> RetrievedDocument:
    return RetrievedDocument(
        id=str(score),
        title="Approved section",
        content="Approved evidence",
        source="s3://approved/policy.pdf",
        score=score,
    )


def test_confidence_uses_capped_corroboration_after_selector_reordering() -> None:
    confidence = _confidence_from_documents(
        [_document(2.31), _document(4.62), _document(1.37), _document(2.0)]
    )

    assert confidence >= 0.35


def test_corroboration_cannot_rescue_a_weak_evidence_set() -> None:
    confidence = _confidence_from_documents(
        [_document(0.5), _document(1.0), _document(0.4)]
    )

    assert confidence < 0.35


def test_single_document_gets_no_margin_bonus() -> None:
    """A lone, uncorroborated document must not be scored as though it beat
    a competitor - a missing runner-up is the absence of competition, not a
    win. Before this fix, a missing runner-up defaulted to 0.0, which made
    margin equal top_score and silently doubled the top-score term, letting
    a single mediocre match (~2.05) clear BEDROCK_MIN_CONFIDENCE (0.47) on
    its own.
    """
    confidence = _confidence_from_documents([_document(2.05)])

    # top_score/10 + margin(=0)/10 + avg_score/30 + corroboration(=0)
    expected = round((2.05 / 10.0) + 0.0 + (2.05 / 30.0) + 0.0, 3)
    assert confidence == expected
    assert confidence < 0.35


def test_single_strong_document_still_reaches_high_confidence() -> None:
    """The fix must not cap a single, genuinely strong match too low."""
    confidence = _confidence_from_documents([_document(9.5)])

    assert confidence >= 0.47


def test_score_sorted_confidence_is_unchanged_by_corroboration() -> None:
    documents = [_document(4.0), _document(2.0), _document(1.0)]
    expected = round((4.0 / 10.0) + (2.0 / 10.0) + ((7.0 / 3.0) / 30.0), 3)

    assert _confidence_from_documents(documents) == expected


def test_margin_ignores_a_demoted_candidate_the_selector_rejected() -> None:
    """A row the evidence selector passed over can still outscore the section
    it did choose, and lands right behind it once demoted to "remaining"
    evidence. That demoted row must not stand in as the margin's runner-up -
    otherwise a confidently selected, correct answer gets zero margin credit
    just because a topically-adjacent but wrong section scored higher on raw
    lexical overlap.
    """
    documents = [_document(1.396), _document(3.31), _document(1.386), _document(1.381), _document(1.354)]

    top_score, real_runner_up = 1.396, 1.386
    margin = top_score - real_runner_up
    avg_score = sum(document.score for document in documents) / len(documents)
    corroboration = min((3.31 - top_score) / 40.0, 0.1)
    expected = round((top_score / 10.0) + (margin / 10.0) + (avg_score / 30.0) + corroboration, 3)

    assert _confidence_from_documents(documents) == expected
    # The demoted 3.31 leader must not zero out the margin term.
    assert margin > 0


@pytest.fixture
def _hardening_enabled(monkeypatch):
    """Enable the flag these two scorers are gated behind, using the real
    config/retrieval_scoring_rules.json (their reviewed data source)."""
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)
    section_index._load_scoring_rules.cache_clear()
    yield
    section_index._load_scoring_rules.cache_clear()


def test_purchase_channel_score_rewards_a_named_direct_channel(_hardening_enabled) -> None:
    score = _purchase_channel_score(
        "Can I buy products online?",
        "Selling",
        "You may engage in Selling Products Online via the approved FBO website.",
    )
    assert score > 0


def test_purchase_channel_score_ignores_unrelated_evidence(_hardening_enabled) -> None:
    assert _purchase_channel_score("Can I buy products online?", "Other", "Unrelated content here.") == 0.0


def test_purchase_channel_score_requires_purchase_intent(_hardening_enabled) -> None:
    assert _purchase_channel_score("What is the weather", "Other", "Selling Products Online") == 0.0


def test_purchase_channel_score_fires_on_where_to_order_combo(_hardening_enabled) -> None:
    score = _purchase_channel_score(
        "Where do I order from?", "Other", "You may use your personal Forever web shop."
    )
    assert score > 0


def test_return_policy_score_prefers_buyback_clause_for_unopened_product(_hardening_enabled) -> None:
    score = _return_policy_score(
        "Can I return an unopened product and within what window",
        "Returns",
        "FLP shall buy back any unsold, salable product.",
    )
    assert score > 0


def test_return_policy_score_does_not_fall_back_to_general_satisfaction_phrase(_hardening_enabled) -> None:
    """Regression guard for the 2026-09-01 live-index canary failure: a
    buy-back-window question must not be answered by the general
    satisfaction-guarantee clause just because that clause happens to
    contain a phrase like "100 product satisfaction" - see the comment on
    _return_policy_score and OPENSEARCH_RETRIEVAL_HARDENING_ENABLED.
    """
    score = _return_policy_score(
        "Can I return an unopened product and within what window",
        "Returns",
        "This is covered by our 100 product satisfaction guarantee.",
    )
    assert score == 0.0


def test_return_policy_score_uses_general_clause_without_buyback_intent(_hardening_enabled) -> None:
    score = _return_policy_score(
        "What is your return policy",
        "Returns",
        "This is covered by our 100 product satisfaction guarantee.",
    )
    assert score > 0


def test_return_policy_score_still_credits_a_buyback_clause_with_different_wording(_hardening_enabled) -> None:
    """A question that doesn't use a buy-back trigger word (e.g. no
    "unopened"/"window"/"unsold") must not zero out a candidate that is
    substantively the buy-back clause just because of that wording gap -
    the branch selection is driven by the message, but the candidate's own
    content should still get credit. This does not touch or weaken the
    2026-09-01 regression guard above: that guard fires only when the
    message DOES contain a buy-back trigger word, and stays unchanged.
    """
    score = _return_policy_score(
        "I never used it, can I get a refund?",
        "Returns",
        "FLP shall buy back any unsold, salable product.",
    )
    assert score > 0


def test_return_policy_score_requires_return_intent(_hardening_enabled) -> None:
    assert _return_policy_score("What is the weather", "Returns", "buy back unsold") == 0.0


def test_scoring_rules_are_disabled_when_hardening_flag_is_off() -> None:
    """These scorers must stay inert by default - OPENSEARCH_RETRIEVAL_HARDENING_ENABLED is False in production."""
    assert not settings.OPENSEARCH_RETRIEVAL_HARDENING_ENABLED
    score = _purchase_channel_score(
        "Can I buy products online?", "Selling", "Selling Products Online via the approved FBO website."
    )
    assert score == 0.0


def test_scoring_rules_fail_open_on_a_missing_config_file(monkeypatch, tmp_path, _hardening_enabled) -> None:
    """A missing or malformed rules file must not break retrieval - it should
    just leave these optional scorers inert, the same fail-open behavior the
    glossary loader uses for missing config."""
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_SCORING_RULES_PATH", str(tmp_path / "missing.json"))
    section_index._load_scoring_rules.cache_clear()

    score = _purchase_channel_score(
        "Can I buy products online?", "Selling", "Selling Products Online via the approved FBO website."
    )

    assert score == 0.0


def test_scoring_rules_fail_open_on_malformed_json(monkeypatch, tmp_path, _hardening_enabled) -> None:
    bad_path = tmp_path / "bad_rules.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_SCORING_RULES_PATH", str(bad_path))
    section_index._load_scoring_rules.cache_clear()

    score = _return_policy_score("What is your return policy", "Returns", "100 product satisfaction")

    assert score == 0.0


def test_scoring_rules_file_matches_the_previously_hardcoded_values(_hardening_enabled) -> None:
    """Pin the reviewed data file's content so a future edit is a deliberate,
    visible change rather than a silent drift from what shipped before this
    was externalized from section_index.py."""
    rules = section_index._load_scoring_rules(settings.OPENSEARCH_RETRIEVAL_SCORING_RULES_PATH)

    assert set(rules["purchase_channel"]["evidence"]) == {
        "selling products online",
        "personal forever web shop",
        "approved fbo website",
        "online shop",
        "purchase products online",
    }
    assert set(rules["return_policy"]["buyback_window"]["evidence"]) == {
        "buy back",
        "unsold",
        "salable",
        "saleable",
    }
    assert set(rules["return_policy"]["general"]["evidence"]) == {
        "product return",
        "return of the product",
        "timely return",
        "100 product satisfaction",
        "proof of purchase",
    }
