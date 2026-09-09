"""Catalogue-based country-name expansion: does it match more without reaching further?

The defect: `content` is indexed as plain text with no analyser settings, so
"Reunion" and "Réunion" are different terms and a reader who omits the accent
does not match the document that carries it. Expansion adds the document's
spelling as an extra query.

The risk that comes with it: a changed query can change what the planner asks
for and which scopes are selected, so "the filter code is unchanged" is not
proof that eligibility is unchanged. The access tests below therefore run the
expanded queries through `approve_evidence` and compare the decision, rather
than reasoning about the filters.

These are deterministic decision tests. They say nothing about whether a
delivered answer improves; that needs the bounded end-to-end run, which cannot
be executed locally.
"""

from __future__ import annotations

import pytest

from app.evidence import approve_evidence
from app.retrieval.country_names import country_name_queries
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.retrieval.providers import _planned_retrieval_plan


# --- accented names --------------------------------------------------------


def test_the_accented_spelling_is_added_for_an_unaccented_question() -> None:
    """The reported defect, in one assertion."""
    queries = country_name_queries("What is the delivery cost in Reunion?")

    assert "What is the delivery cost in Réunion?" in queries


def test_the_unaccented_spelling_is_added_for_an_accented_question() -> None:
    """The same gap in the other direction - documents are not all accented."""
    queries = country_name_queries("What is the delivery cost in Réunion?")

    assert "What is the delivery cost in Reunion?" in queries


def test_every_added_spelling_is_an_approved_name_for_that_market() -> None:
    """Réunion has two accented spellings and both are approved names for RE.

    Neither is preferred, because the generated catalogue does not record which
    language produced a name. What matters is that nothing outside RE's own
    approved names can reach the search.
    """
    from app.retrieval.country_names import _catalogue

    approved = {name.casefold() for name in _catalogue()["RE"][1]}
    queries = country_name_queries("What is the delivery cost in Reunion?")

    assert queries
    for query in queries:
        substituted = _substituted_name(
            "What is the delivery cost in Reunion?", query
        )
        assert substituted.casefold() in approved


def _substituted_name(question: str, query: str) -> str:
    """The words the expansion put in place of the country name.

    Compared word by word, not character by character: "Reunion" and "Reunión"
    share the prefix "Reuni" and the suffix "n", and a character-level diff
    reports the single accented letter rather than the name. Trimming whole
    words also proves the query is the question with one contiguous run of
    words replaced.
    """
    original = question.split()
    expanded = query.split()
    head = 0
    while head < min(len(original), len(expanded)) and original[head] == expanded[head]:
        head += 1
    tail = 0
    while (
        tail < min(len(original), len(expanded)) - head
        and original[len(original) - 1 - tail] == expanded[len(expanded) - 1 - tail]
    ):
        tail += 1
    return " ".join(expanded[head : len(expanded) - tail]).strip(" ,.?!;:")


# --- abbreviations ---------------------------------------------------------


def test_an_abbreviation_gains_the_configured_name() -> None:
    """"DRC" is what a reader writes; it is not what a document says."""
    queries = country_name_queries("What is the minimum order in DRC?")

    assert queries == ["What is the minimum order in Democratic Republic of Congo?"]


def test_a_question_already_using_the_configured_name_gains_nothing() -> None:
    """Adding a spelling the question already has buys another search for nothing."""
    assert country_name_queries("What is the minimum order in Belgium?") == []


# --- overlapping country names ---------------------------------------------


def test_the_longer_name_wins_over_the_country_inside_it() -> None:
    """"Equatorial Guinea" contains "Guinea" and is a different market.

    The span located must be the whole name, so nothing can substitute over the
    "Guinea" inside it and turn a question about GQ into one about GN.
    """
    from app.retrieval.country_names import _written_span

    question = "What are the office hours in Equatorial Guinea?"

    assert _written_span(question, "GQ")[0] == "Equatorial Guinea"
    assert country_name_queries(question) == []


def test_the_shorter_name_does_not_pull_in_the_longer_market() -> None:
    queries = country_name_queries("What are the office hours in Guinea?")

    assert not any("Equatorial" in query for query in queries)


def test_a_mention_the_matcher_refuses_to_resolve_is_not_expanded() -> None:
    """"Upper Congo" is suppressed rather than resolved, and stays that way.

    Expanding it would pick one of the two Congos, which is the wrong-country
    answer the suppression exists to prevent.
    """
    assert country_name_queries("What is the delivery cost in Upper Congo?") == []


# --- realistic sentences ---------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Hi, I have a customer in Reunion who wants to order - what does delivery cost?",
        "Could you tell me the minimum order size for a new FBO in DRC, please?",
        "my customer in reunion asked about delivery",
    ],
)
def test_the_question_survives_into_the_added_query(question: str) -> None:
    """Only the country name changes.

    A bare country name would rank the market's documents and lose what was
    being asked about them, so the sentence has to come through intact. Proved
    by putting the reader's own name back and getting the question back.
    """
    queries = country_name_queries(question)

    assert queries
    for query in queries:
        assert query != question
        added = _substituted_name(question, query)
        original = _substituted_name(query, question)
        assert query.replace(added, original, 1) == question


def test_two_named_markets_are_both_expanded() -> None:
    queries = country_name_queries("How do I sponsor someone in Reunion and DRC?")

    assert any("Réunion" in query for query in queries)
    assert any("Democratic Republic of Congo" in query for query in queries)


# --- negative controls: nothing unrelated arrives --------------------------


@pytest.mark.parametrize(
    "question",
    [
        "How do I sponsor someone?",
        "What is the minimum order size?",
        "",
        "   ",
    ],
)
def test_a_question_naming_no_market_is_not_expanded(question: str) -> None:
    assert country_name_queries(question) == []


def test_no_unrelated_country_is_introduced() -> None:
    """Expansion for one market must not name another.

    The negative control for ranking: an added query that mentioned France
    would give France's passages a query of their own to rank against.
    """
    from services.market_config import find_market_mentions

    question = "What is the delivery cost in Reunion?"
    for query in country_name_queries(question):
        assert find_market_mentions(query) == {"RE"}


def test_the_expansion_is_bounded() -> None:
    """A question naming many markets must not multiply the searches without limit."""
    question = "Compare Reunion, DRC, Belgium, France and Guinea for me"
    queries = country_name_queries(question)

    assert len(queries) <= 4


def test_expansion_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.retrieval.country_names.settings.OPENSEARCH_COUNTRY_NAME_EXPANSION_ENABLED",
        False,
    )

    assert country_name_queries("What is the delivery cost in Reunion?") == []


# --- the original question keeps its place ---------------------------------


def test_the_plan_keeps_the_original_question_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider weights the first query 1.0 and every later one 0.88.

    Appending is what keeps the reader's own wording authoritative; this
    asserts the position rather than trusting the comment that says so.
    """
    monkeypatch.setattr(
        "app.retrieval.providers.settings.BEDROCK_QUERY_PLANNER_ENABLED", False
    )
    question = "What is the delivery cost in Reunion?"

    plan = _planned_retrieval_plan(question, "RE", "en", "cid")

    assert plan.queries[0] == question
    assert "What is the delivery cost in Réunion?" in plan.queries


def test_the_plan_without_a_named_market_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """A question naming no market must produce the plan it produced before."""
    monkeypatch.setattr(
        "app.retrieval.providers.settings.BEDROCK_QUERY_PLANNER_ENABLED", False
    )
    question = "What is the minimum order size?"

    plan = _planned_retrieval_plan(question, "US", "en", "cid")

    assert country_name_queries(question) == []
    assert plan.queries[0] == question


# --- access is not widened -------------------------------------------------
#
# Asserted against approve_evidence for every expanded query, because a query
# change can move planning and scope selection even when no filter changed.


def _document(country: str, access_scope: str) -> RetrievedDocument:
    return RetrievedDocument(
        id="section-1",
        title="Company Policy",
        content="Delivery costs 6EUR and the FBO support fee is 3 EUR per month.",
        source="s3://bucket/doc.pdf",
        country=country,
        language="en",
        score=0.9,
        metadata={"access_scope": access_scope, "section_id": "section-1"},
    )


def _result(*documents: RetrievedDocument) -> RetrievalResult:
    return RetrievalResult(documents=list(documents), citations=[], confidence=0.9)


def test_expansion_cannot_open_a_foreign_local_policy() -> None:
    """A US session asking Belgium's company policy stays refused.

    Belgium gains no expansion of its own - the question already says
    "Belgium" - so this also covers the case where expansion is a no-op and the
    restriction has to hold on the original.
    """
    question = "What is the company policy in Belgium?"

    for query in [question, *country_name_queries(question)]:
        decision = approve_evidence(query, _result(_document("BE", "country")), "US", "en")
        assert decision.approved is False
        assert decision.reason == "cross_market_policy_request"


def test_expansion_of_an_abbreviated_market_cannot_open_its_local_policy() -> None:
    """The case where expansion does fire: "DRC" becomes the configured name.

    Substituting the fuller name must not make the request look like anything
    other than a foreign local-policy question.
    """
    question = "What is the company policy in DRC?"
    expanded = country_name_queries(question)

    assert expanded, "this case is only meaningful while expansion actually fires"
    for query in [question, *expanded]:
        decision = approve_evidence(query, _result(_document("CD", "country")), "US", "en")
        assert decision.approved is False
        assert decision.reason == "cross_market_policy_request"


def test_approved_global_sponsoring_stays_eligible_through_expansion() -> None:
    """The permission that must not be lost while tightening nothing."""
    question = "How do I sponsor someone in Belgium?"

    for query in [question, *country_name_queries(question)]:
        assert approve_evidence(query, _result(_document("GLOBAL", "global")), "US", "en").approved


def test_the_eligible_document_set_is_the_same_for_every_expanded_query() -> None:
    """The control the reviewer asked for, stated as documents rather than code.

    Not "the filter is unchanged" but "the same documents are approved". Run
    over a mixed result so a change in either direction - a document gained or
    a document lost - shows up.
    """
    question = "What is the delivery cost in Reunion?"
    documents = _result(
        _document("RE", "country"),
        _document("BE", "country"),
        _document("GLOBAL", "global"),
    )

    baseline = approve_evidence(question, documents, "RE", "en")
    for query in country_name_queries(question):
        decision = approve_evidence(query, documents, "RE", "en")
        assert decision.approved == baseline.approved
        assert decision.reason == baseline.reason


def test_global_directory_targeting_reads_the_message_not_the_expansion() -> None:
    """Directory scope is derived before expansion and must stay that way.

    If it ever consumed the expanded queries, a market named only by an added
    spelling could pull in that market's directory record.
    """
    import inspect
    import re

    from app.retrieval import opensearch_sections

    source = inspect.getsource(opensearch_sections.OpenSearchSectionProvider.retrieve)
    source = re.sub(r"#.*", "", source)

    assert "_directory_target_country_names(message, country)" in source
    assert "_directory_target_country_names(search_plan" not in source
    assert "_directory_target_country_names(search_message" not in source


def test_a_reader_who_used_the_configured_name_gains_no_spelling_variants() -> None:
    """The rule that keeps CLDR out of the search.

    "France" is FR's configured name. Without this rule the folded match also
    admitted "Francë" - Albanian, approved, and not a spelling any approved
    document uses. The reader already wrote the name the system uses.
    """
    assert country_name_queries("What is the policy in France?") == []
    assert country_name_queries("delivery in Reunion Islands") == []


def test_markets_are_expanded_in_the_order_they_appear() -> None:
    """Ordering by country code spent the budget before reaching Réunion.

    "Compare Reunion, DRC, Belgium, France and Guinea" resolves five markets
    and only three are expanded. The first named must be among them.
    """
    queries = country_name_queries("Compare Reunion, DRC, Belgium, France and Guinea for me")

    assert any("Réunion" in query for query in queries)


def test_an_ordinary_question_still_uses_the_selected_market() -> None:
    """The control for everything above.

    A question that names no country must be unaffected: no expansion, and the
    session's own market answers it exactly as before.
    """
    question = "What is the minimum order size?"

    assert country_name_queries(question) == []
    assert approve_evidence(question, _result(_document("US", "country")), "US", "en").approved
