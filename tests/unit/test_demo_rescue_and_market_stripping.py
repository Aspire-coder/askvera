"""Demo W8: close Fable's three review findings on commit 655794d.

1. The cross-language strong-match rescue treated an English question as a
   translation: "Can my spouse also join as a distributor?" with the planner
   query "FBO licensed use Forever registered trademarks" scored 0.6625 against
   the English NL licence section and forced strong_local_match. The rescue now
   needs the question to carry none of the section language's common function
   words (a static, local list).
2. _without_market_names removed ordinary words that spell a market:
   "Can I ship a turkey to Mali?" lost "turkey".
3. A compound directory record kept a fragment: "What are the office hours in
   Kenya/East Africa?" became "What are the office hours /East Africa?".

Every test is offline. Sockets, AWS clients, embeddings, the OpenSearch client,
the selector model and session/cache writes are replaced and raise if used.
"""

from __future__ import annotations

import copy
import socket
from types import SimpleNamespace

import pytest

import services.aws_clients as aws_clients
import services.embeddings as embeddings
from app.evidence import approve_evidence
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.providers import RetrievalQueryPlan, _document_relevance
from app.retrieval.section_index import _confidence_from_documents
from config import settings

THRESHOLD = settings.OPENSEARCH_SELECTOR_STRONG_MATCH_THRESHOLD
FABLE_QUESTION = "Can my spouse also join as a distributor?"
FABLE_QUERY = "FBO licensed use Forever registered trademarks"
ENGLISH_PLANNER_QUERY = "license fee to use Forever trademark FBO"
DUTCH_QUESTION = "Hoeveel kost een licentie om het Forever-merk te gebruiken als FBO?"
FRENCH_QUESTION = "Quel est le prix d'une licence pour utiliser la marque Forever en tant que FBO ?"
GERMAN_QUESTION = "Wie viel kostet eine Lizenz, um die Marke Forever als FBO zu nutzen?"
TOP_SCORE = 1.203775

EN_19_02_B = (
    "Each FBO is hereby licensed by Forever to use Forever's registered trademarks in the manner "
    "described. The license granted herein shall be effective only as long as the FBO is in good standing."
)
EN_19_02 = "Limited License to Use Company Marks. The FBO may use Company marks only as permitted by this section."


def _live_call(*_: object, **__: object):
    raise AssertionError("W8 tests must never make an AWS, embedding, OpenSearch, network or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _live_call)
    monkeypatch.setattr(socket, "create_connection", _live_call)
    monkeypatch.setattr(aws_clients, "get_aws_clients", _live_call)
    monkeypatch.setattr(embeddings, "embed_text", _live_call)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "embed_text", _live_call)
    monkeypatch.setattr(opensearch_sections, "_client", _live_call)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", _live_call)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", _live_call)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", _live_call)


# --- 1. Cross-language rescue ------------------------------------------------------------


def _document(section_id: str, language: str, content: str, score: float = TOP_SCORE, *,
              country: str = "NL") -> RetrievedDocument:
    source_file = f"{country}-{language.upper()} Benelux Company Policy"
    title = "Limited License to Use Company Marks"
    return RetrievedDocument(
        id=f"{country.lower()}-{language}-{section_id}",
        title=f"{source_file} - Sec {section_id}: {title}",
        content=content,
        source=f"opensearch-section://{source_file}/{section_id}",
        excerpt=content[:300],
        country=country,
        language=language,
        score=score,
        metadata={"access_scope": "country", "document_type": "policy", "section_id": section_id,
                  "section_title": title, "parent_section_id": "19.02", "status": "active"},
    )


def _english_rows(country: str = "NL") -> list[RetrievedDocument]:
    return [_document("19.02-b", "en", EN_19_02_B, country=country),
            _document("19.02", "en", EN_19_02, TOP_SCORE - 0.042681, country=country)]


def _rows(documents: list[RetrievedDocument]) -> list[tuple[dict, float]]:
    return [({"section_title": d.metadata["section_title"], "content": d.content, "language": d.language}, d.score)
            for d in documents]


def _rescue(question: str, query: str, documents: list[RetrievedDocument], country: str = "NL") -> float:
    return opensearch_sections._translated_query_local_relevance(
        question, country, documents[0], [query], _rows(documents)
    )


def _gate(question: str, documents: list[RetrievedDocument], query: str):
    relevance = _document_relevance(question, documents[0])
    if relevance < THRESHOLD:
        relevance = max(relevance, _rescue(question, query, documents))
    result = RetrievalResult(
        documents=documents, citations=[d.to_source() for d in documents],
        confidence=_confidence_from_documents(documents),
        metadata={"evidence_selector_applied": True, "evidence_selector_confidence": None,
                  "max_local_relevance": relevance, "strong_local_match": relevance >= THRESHOLD},
    )
    return relevance, approve_evidence(question, result, "NL", "en")


class _Client:
    def __init__(self, hits: list[dict]) -> None:
        self.hits = hits

    def search(self, index, body):
        del index, body
        return {"hits": {"hits": copy.deepcopy(self.hits)}}


class _Runtime:
    def converse(self, **_kwargs):
        return {"output": {"message": {"content": [{
            "text": '{"selected_ranks":[1,2],"directly_answers_top_rank":false,"top_rank_confidence":0.6}'
        }]}}}


def _retrieve(monkeypatch, question: str, queries: list[str]):
    for name, value in {
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED": False, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED": True,
        "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED": False, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK": False,
        "RETRIEVAL_PARENT_DIVERSITY_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    hits = [
        {"_id": d.id, "_score": 30.0 - index, "_source": {
            "id": d.id, "section_id": d.metadata["section_id"], "section_title": d.metadata["section_title"],
            "content": d.content, "source_file": "NL-EN Benelux Company Policy", "country": d.country,
            "language": d.language, "document_type": "policy", "access_scope": "country", "status": "active",
            "parent_section_id": "19.02"}}
        for index, d in enumerate(_english_rows())
    ]
    client = _Client(hits)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0] * 4)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=_Runtime()))
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda message, *_: RetrievalQueryPlan([message, *queries]))
    return provider.retrieve(question, "NL", "en", "fbo", "cid-w8")


def test_fable_english_question_is_not_rescued(monkeypatch) -> None:
    documents = _english_rows()
    assert _document_relevance(FABLE_QUERY, documents[0]) >= THRESHOLD, "fixture must offer a rescuing query"
    assert _rescue(FABLE_QUESTION, FABLE_QUERY, documents) == 0.0

    result = _retrieve(monkeypatch, FABLE_QUESTION, [FABLE_QUERY])
    assert result.metadata["evidence_selector_applied"] is True
    assert result.metadata["max_local_relevance"] == pytest.approx(
        _document_relevance(FABLE_QUESTION, result.documents[0]), abs=1e-6
    )
    assert result.metadata["strong_local_match"] is False


@pytest.mark.parametrize(
    "question",
    [
        FABLE_QUESTION,
        "Could my partner sign up as a distributor too?",
        "How do I register my wife under my account?",
        "Why was my distributor application rejected?",
        "What happens to my account if I move abroad?",
        "Is my husband allowed to open a second account?",
    ],
)
def test_english_phrasings_are_not_rescued_against_english_sections(question) -> None:
    documents = _english_rows()
    relevance, decision = _gate(question, documents, FABLE_QUERY)
    assert _rescue(question, FABLE_QUERY, documents) == 0.0
    assert relevance == pytest.approx(_document_relevance(question, documents[0]))
    assert relevance < THRESHOLD
    assert decision.approved is False


@pytest.mark.parametrize("question", [DUTCH_QUESTION, FRENCH_QUESTION, GERMAN_QUESTION])
def test_translated_questions_against_the_english_own_market_section_are_still_rescued(question) -> None:
    documents = _english_rows()
    assert _document_relevance(question, documents[0]) < THRESHOLD, "fixture must reproduce the lexical miss"
    relevance, decision = _gate(question, documents, ENGLISH_PLANNER_QUERY)
    assert relevance == pytest.approx(_document_relevance(ENGLISH_PLANNER_QUERY, documents[0]))
    assert relevance >= THRESHOLD
    assert decision.approved is True


def test_live_dutch_question_still_sets_strong_local_match_through_retrieve(monkeypatch) -> None:
    result = _retrieve(monkeypatch, DUTCH_QUESTION, ["kosten licentie Forever merk FBO", ENGLISH_PLANNER_QUERY])
    assert result.metadata["strong_local_match"] is True


@pytest.mark.parametrize("question", [DUTCH_QUESTION, FRENCH_QUESTION, GERMAN_QUESTION])
def test_translated_questions_against_foreign_sections_are_never_rescued(question) -> None:
    assert _rescue(question, ENGLISH_PLANNER_QUERY, _english_rows(country="US")) == 0.0


def test_section_language_is_what_the_markers_are_read_for() -> None:
    in_language = opensearch_sections._question_in_section_language
    assert in_language(FABLE_QUESTION, "en") and in_language(FABLE_QUESTION, "EN-gb")
    assert not in_language(FABLE_QUESTION, "nl")
    assert in_language(DUTCH_QUESTION, "nl") and not in_language(DUTCH_QUESTION, "en")
    assert in_language(FRENCH_QUESTION, "fr") and not in_language(FRENCH_QUESTION, "en")
    assert in_language(GERMAN_QUESTION, "de") and not in_language(GERMAN_QUESTION, "en")
    assert in_language("Für wen gilt das?", "de"), "accents fold before matching"
    # A section language without a marker list cannot be told apart, so it gets no rescue.
    assert in_language(DUTCH_QUESTION, "es") and in_language(DUTCH_QUESTION, "")


def test_marker_lists_share_no_word() -> None:
    lists = opensearch_sections.SECTION_LANGUAGE_MARKERS
    for left in lists:
        for right in lists:
            if left < right:
                assert not lists[left] & lists[right], (left, right)


# --- 2 and 3. Market-name stripping ------------------------------------------------------


def _replace(anchor: str, message: str) -> str:
    return AIOrchestrator()._replace_directory_target(anchor, message)


def _history(*turns: str) -> str:
    return "\n".join(line for turn in turns for line in (f"user: {turn}", "vera: An earlier answer."))


@pytest.mark.parametrize(
    "anchor,message,expected",
    [
        ("Can I ship a turkey to Mali?", "What about Gambia?", "Can I ship a turkey?"),
        ("Can I ship a turkey to Mali?", "What about Mali?", "Can I ship a turkey to Mali?"),
        ("Can I ship a turkey to Turkey?", "What about Gambia?", "Can I ship a turkey?"),
        ("Can I order china plates for Mali?", "What about Gambia?", "Can I order china plates?"),
        ("Can I order china plates in Japan?", "What about China?", "Can I order china plates?"),
    ],
)
def test_common_nouns_that_spell_a_market_are_kept(anchor, message, expected) -> None:
    assert _replace(anchor, message) == expected


@pytest.mark.parametrize(
    "anchor,message,expected",
    [
        ("what is the delivery cost in mali?", "what about gambia?", "what is the delivery cost?"),
        ("what is mali's minimum order?", "what about gambia?", "what is minimum order?"),
        # Flipped for Fable W8b note 1 (option B): an anchor with no capital at all gives no
        # case signal, so every market-name span counts (clean-base behaviour) and "turkey"
        # goes too. Keeping a stale market is the harmful direction; this is the less-bad one.
        ("can i ship a turkey to mali?", "what about gambia?", "can i ship a?"),
    ],
)
def test_a_writer_without_capitals_still_gets_the_replacement(anchor, message, expected) -> None:
    assert _replace(anchor, message) == expected


def test_caseless_script_spans_count_as_written_names() -> None:
    orchestrator = AIOrchestrator()
    assert orchestrator._reads_as_market_reference("日本の配送料は?", 0, 2) is True
    assert orchestrator._reads_as_market_reference("Can I ship a turkey?", 13, 19) is False


@pytest.mark.parametrize(
    "anchor,message,expected",
    [
        ("What are the office hours in Kenya/East Africa?", "What about Uganda?", "What are the office hours?"),
        ("What are the office hours in Kenya / East Africa?", "What about Japan?", "What are the office hours?"),
        ("What are Kenya/East Africa's office hours?", "What about Uganda?", "What are office hours?"),
        ("What is the delivery cost in Mali/Senegal?", "What about Gambia?", "What is the delivery cost?"),
        ("What are the office hours in Kenya/East Africa?", "What about Kenya?",
         "What are the office hours in Kenya/East Africa?"),
    ],
)
def test_compound_market_references_are_removed_whole(anchor, message, expected) -> None:
    assert _replace(anchor, message) == expected


def test_kenya_east_africa_follow_up_resolves_to_uganda_only() -> None:
    orchestrator = AIOrchestrator()
    retrieval = orchestrator._build_retrieval_query(
        "What about Uganda?", _history("What are the office hours in Kenya/East Africa?"), "cid"
    )
    assert retrieval == "What are the office hours? What about Uganda?"
    assert "/" not in retrieval and "East Africa" not in retrieval
    assert opensearch_sections._directory_target_country_names(retrieval, "US") == {"Uganda"}


def test_w7_live_gambia_replacement_is_unchanged() -> None:
    orchestrator = AIOrchestrator()
    history = _history("What is the delivery cost in Mali?", "What's the minimum order amount?")
    retrieval = orchestrator._build_retrieval_query("What about delivery cost for Gambia?", history, "cid")
    assert retrieval == "What is the delivery cost? What about delivery cost for Gambia?"


# --- W8b. Lower-case market names after a connector (Fable W8 finding 1) -----------------
#
# W8 accepted a lower-case span only when the whole text had no capital and an
# English connector led into it, so "office hours in kenya" (capital "W") kept
# Kenya as a second directory target and nl/fr connectors never counted.


def _targets(anchor: str, message: str) -> set[str]:
    return opensearch_sections._directory_target_country_names(f"{_replace(anchor, message)} {message}", "US")


LOWERCASE_AFTER_CONNECTOR = [
    # anchor, capitalised twin, follow-up, expected stripped anchor, expected directory targets
    ("What are the office hours in kenya?", "What are the office hours in Kenya?", "And for Mali?",
     "What are the office hours?", {"Mali"}),
    ("What about the netherlands?", "What about the Netherlands?", "And for Belgium?",
     "What about the?", {"Belgium"}),
    ("Wat kost verzending naar duitsland?", "Wat kost verzending naar Duitsland?", "En voor België?",
     "Wat kost verzending?", {"Belgium"}),
    ("wat kost verzending naar duitsland?", "wat kost verzending naar Duitsland?", "En voor België?",
     "wat kost verzending?", {"Belgium"}),
    ("wat kost verzending naar duitsland?", "wat kost verzending naar Duitsland?", "en voor belgië?",
     "wat kost verzending?", {"Belgium"}),
    ("Quel est le coût de livraison au mali ?", "Quel est le coût de livraison au Mali ?", "Et pour la Gambie ?",
     "Quel est le coût de livraison?", {"Gambia"}),
    ("what are the office hours in kenya?", "what are the office hours in Kenya?", "and for mali?",
     "what are the office hours?", {"Mali"}),
]


@pytest.mark.parametrize("anchor,capitalised,message,expected,targets", LOWERCASE_AFTER_CONNECTOR)
def test_lower_case_market_after_a_connector_is_replaced(anchor, capitalised, message, expected, targets) -> None:
    assert _replace(anchor, message) == expected
    assert _replace(anchor, message) == _replace(capitalised, message)
    assert _targets(anchor, message) == targets


def test_lower_case_kenya_follow_up_resolves_to_mali_only() -> None:
    retrieval = AIOrchestrator()._build_retrieval_query(
        "And for Mali?", _history("What are the office hours in kenya?"), "cid"
    )
    assert "kenya" not in retrieval.casefold()
    assert opensearch_sections._directory_target_country_names(retrieval, "US") == {"Mali"}


@pytest.mark.parametrize(
    "anchor,message,expected",
    [
        ("Can I feed a guinea pig in Mali?", "What about Gambia?", "Can I feed a guinea pig?"),
        # Flipped for Fable W8b note 1 (option B): all lower-case anchor, no case signal, so
        # "guinea" is read as the market like the clean base did.
        ("can i feed a guinea pig in mali?", "what about gambia?", "can i feed a pig?"),
        # Flipped for Fable W8b note 1 (option B): all lower-case anchor, "china" is stripped.
        ("can i order china plates for mali?", "what about gambia?", "can i order plates?"),
        ("What about china plates?", "What about Japan?", "What about china plates?"),
        ("Can I ship a turkey to turkey?", "What about Gambia?", "Can I ship a turkey?"),
        # Flipped for Fable W8b note 1 (option B): all lower-case anchor, both "turkey" spans go.
        ("can i ship a turkey to turkey?", "what about gambia?", "can i ship a?"),
        ("Can I ship a turkey to Turkey?", "What about Gambia?", "Can I ship a turkey?"),
        ("Can georgia sponsor me in Mali?", "What about Gambia?", "Can georgia sponsor me?"),
        ("Does georgia need a licence?", "What about Gambia?", "Does georgia need a licence?"),
        ("Can I ship bread en masse to mali?", "What about Gambia?", "Can I ship bread en masse?"),
    ],
)
def test_ordinary_words_spelling_a_market_stay_without_a_connector(anchor, message, expected) -> None:
    assert _replace(anchor, message) == expected


def test_dutch_and_between_two_replaced_markets_goes_with_them() -> None:
    assert _replace("Wat kost verzending naar Mali en Senegal?", "En voor België?") == "Wat kost verzending?"


# Fable W8b note 1: the W8b row "delivery cost mali?" is fixed by option B (no capital in
# the anchor) and now asserted in test_lower_case_market_without_a_case_signal_or_with_a_new
# _connector_is_replaced. What remains is a lower-case market with no connector in a
# sentence that does carry capitals.
@pytest.mark.xfail(
    strict=True,
    reason="residual: a lower-case market with no connector in a capitalised sentence reads as an ordinary word",
)
@pytest.mark.parametrize(
    "anchor,message",
    [
        ("Is mali open on Saturdays?", "What about Gambia?"),
        ("What are mali office hours?", "And Gambia?"),
        ("Does mali deliver on weekends?", "And for Gambia?"),
        ("Delivery cost mali?", "What about Gambia?"),
    ],
)
def test_bare_lower_case_market_without_connector_is_a_documented_residual(anchor, message) -> None:
    assert _targets(anchor, message) == {"Gambia"}


# --- W8b. Rescue needs positive evidence of translation (Fable W8 finding 2) --------------

MARKERLESS_ENGLISH = [
    "Is a spouse allowed as distributor?",
    "Is spouse eligible as second account holder?",
    "spouse eligibility as distributor, yes or no",
]


@pytest.mark.parametrize("question", MARKERLESS_ENGLISH)
@pytest.mark.parametrize("query", [FABLE_QUERY, ENGLISH_PLANNER_QUERY])
def test_english_question_without_listed_markers_is_not_rescued(question, query) -> None:
    documents = _english_rows()
    assert _rescue(question, query, documents) == 0.0
    relevance, decision = _gate(question, documents, query)
    assert relevance == pytest.approx(_document_relevance(question, documents[0]))
    assert relevance < THRESHOLD
    assert decision.approved is False


@pytest.mark.parametrize("question", [DUTCH_QUESTION, FRENCH_QUESTION, GERMAN_QUESTION])
def test_demo_translations_keep_their_rescue_value(question) -> None:
    documents = _english_rows()
    assert _rescue(question, ENGLISH_PLANNER_QUERY, documents) == pytest.approx(
        _document_relevance(ENGLISH_PLANNER_QUERY, documents[0])
    )
    assert _rescue(question, ENGLISH_PLANNER_QUERY, documents) >= THRESHOLD


def test_translation_evidence_is_a_marker_of_another_listed_language() -> None:
    other = opensearch_sections._question_in_another_listed_language
    for question in MARKERLESS_ENGLISH:
        assert not other(question, "en")
    assert other(DUTCH_QUESTION, "en") and other(FRENCH_QUESTION, "en") and other(GERMAN_QUESTION, "en")
    assert other(FABLE_QUESTION, "nl"), "an English question against a Dutch section is a translation"
    assert not other(DUTCH_QUESTION, "nl")
    assert other("Für wen gilt das?", "en"), "accents fold before matching"


# --- W8c. Connectors van/von/de/à and anchors without capitals (Fable W8b note 1) ----------
#
# W8b kept a lower-case stale market unless in|for|of|... led into it, so
# "is mali open on saturdays?" + "what about gambia?" targeted Gambia and Mali while
# the clean base (655794d) targeted Gambia only. A kept stale market sends retrieval
# to the wrong market, the harmful direction.

LOWER_CASE_MARKET_W8C = [
    # anchor, follow-up, expected stripped anchor, expected directory targets
    # No capital anywhere in the anchor: every market-name span counts.
    ("is mali open on saturdays?", "what about gambia?", "is open on saturdays?", {"Gambia"}),
    ("what are mali office hours?", "and gambia?", "what are office hours?", {"Gambia"}),
    ("does mali deliver on weekends?", "and for gambia?", "does deliver on weekends?", {"Gambia"}),
    ("mali minimum order?", "what about gambia?", "minimum order?", {"Gambia"}),
    ("delivery cost mali?", "what about gambia?", "delivery cost?", {"Gambia"}),
    ("wat zijn de openingstijden van mali?", "en voor gambia?", "wat zijn de openingstijden?", {"Gambia"}),
    ("wat zijn de bezorgkosten van kenia?", "en voor gambia?", "wat zijn de bezorgkosten?", {"Gambia"}),
    ("quels sont les horaires de mali ?", "et pour la gambie ?", "quels sont les horaires?", {"Gambia"}),
    ("la livraison à mali ?", "et pour la gambie ?", "la livraison?", {"Gambia"}),
    # Capitals elsewhere: the new connector is what makes the name count, and it goes with it.
    ("Lieferkosten von mali?", "Und für Gambia?", "Lieferkosten?", {"Gambia"}),
    ("Livraison de la turquie au mali ?", "Et pour la Gambie ?", "Livraison?", {"Gambia"}),
    ("Wat zijn de openingstijden van mali?", "En voor Gambia?", "Wat zijn de openingstijden?", {"Gambia"}),
    ("Wat zijn de bezorgkosten van kenia?", "En voor Gambia?", "Wat zijn de bezorgkosten?", {"Gambia"}),
    ("Quels sont les horaires de mali ?", "Et pour la Gambie ?", "Quels sont les horaires?", {"Gambia"}),
    ("La livraison à mali ?", "Et pour la Gambie ?", "La livraison?", {"Gambia"}),
    ("Quels sont les horaires de l'italie ?", "Et pour le Mali ?", "Quels sont les horaires?", {"Mali"}),
    # A capitalised name was already stripped; its connector now goes with it.
    ("Wat zijn de openingstijden van Mali?", "En voor Gambia?", "Wat zijn de openingstijden?", {"Gambia"}),
    ("Quels sont les horaires de l'Italie ?", "Et pour le Mali ?", "Quels sont les horaires?", {"Mali"}),
]


@pytest.mark.parametrize("anchor,message,expected,targets", LOWER_CASE_MARKET_W8C)
def test_lower_case_market_without_a_case_signal_or_with_a_new_connector_is_replaced(
    anchor, message, expected, targets
) -> None:
    assert _replace(anchor, message) == expected
    assert _targets(anchor, message) == targets


@pytest.mark.parametrize(
    "anchor,message,targets",
    [
        ("wat zijn de openingstijden van mali?", "En voor Mali?", {"Mali"}),
        ("Wat zijn de openingstijden van mali?", "En voor Mali?", {"Mali"}),
        ("Lieferkosten von mali?", "Und für Mali?", {"Mali"}),
        ("la livraison à mali ?", "et pour le mali ?", {"Mali"}),
    ],
)
def test_same_market_anchor_behind_a_new_connector_is_untouched(anchor, message, targets) -> None:
    assert _replace(anchor, message) == anchor
    assert _targets(anchor, message) == targets


def test_lower_case_mali_follow_up_resolves_to_gambia_only() -> None:
    retrieval = AIOrchestrator()._build_retrieval_query(
        "what about gambia?", _history("is mali open on saturdays?"), "cid"
    )
    assert "mali" not in retrieval.casefold()
    assert opensearch_sections._directory_target_country_names(retrieval, "US") == {"Gambia"}


def test_case_signal_is_read_from_the_whole_anchor() -> None:
    orchestrator = AIOrchestrator()
    assert orchestrator._reads_as_market_reference("can i ship a turkey?", 13, 19) is True
    assert orchestrator._reads_as_market_reference("Can I ship a turkey?", 13, 19) is False


# --- W8c. English homographs and names are no evidence of translation (Fable W8b note 3) ---

HOMOGRAPH_OR_NAME_LEAKS = [
    "Is spouse Van de Berg allowed as distributor?",
    "Is a delivery van allowed as distributor vehicle?",
    "Is fur allowed as distributor product?",
    "Is spouse allowed as distributor? Bitte.",
    "Spouse allowed as distributor, sa?",
    "Is Het Pand allowed as distributor venue?",
    "Is mon allowed as distributor?",
    "Is mag allowed as distributor?",
]


@pytest.mark.parametrize("question", HOMOGRAPH_OR_NAME_LEAKS)
@pytest.mark.parametrize("query", [FABLE_QUERY, ENGLISH_PLANNER_QUERY])
def test_english_homographs_and_names_do_not_rescue(question, query) -> None:
    documents = _english_rows()
    assert not opensearch_sections._question_in_another_listed_language(question, "en")
    assert _rescue(question, query, documents) == 0.0
    relevance, decision = _gate(question, documents, query)
    assert relevance == pytest.approx(_document_relevance(question, documents[0]))
    assert relevance < THRESHOLD
    assert decision.approved is False


def test_genuine_markers_still_count_after_the_homograph_exclusion() -> None:
    other = opensearch_sections._question_in_another_listed_language
    assert other("Kan ik per van leveren?", "en"), "kan/ik still mark Dutch"
    assert other("Für wen gilt das Forever-Zeichen?", "en"), "für is not the English fur"
    documents = _english_rows()
    for question in (DUTCH_QUESTION, FRENCH_QUESTION, GERMAN_QUESTION):
        for query in (FABLE_QUERY, ENGLISH_PLANNER_QUERY):
            assert _rescue(question, query, documents) == pytest.approx(_document_relevance(query, documents[0]))
            assert _rescue(question, query, documents) >= THRESHOLD


def test_english_question_against_the_dutch_section_keeps_its_rescue() -> None:
    dutch = "Elke FBO krijgt hierbij van Forever een licentie om de geregistreerde handelsmerken van Forever te gebruiken."
    documents = [_document("19.02-b", "nl", dutch)]
    query = "FBO licentie handelsmerken Forever"
    assert _rescue(FABLE_QUESTION, query, documents) == pytest.approx(_document_relevance(query, documents[0]))
    assert _rescue(FABLE_QUESTION, query, documents) >= THRESHOLD
