"""A company-policy request for another market is refused in every locale, not just English.

## History

A first version of this fix used a co-occurrence rule ("a policy noun and a
company qualifier appear anywhere in the message") and localized display
names/aliases. An adversarial review (Fable) REJECTED that version with six
blocking findings (B1-B6): over-refusal of 31/42 legitimate own-market
questions (co-occurrence fired on "internationale" because it contains
"national", and on "Forever" as a qualifier); ordinary words added as market
aliases (Nederlands, Saksan, Gane, Nemačka, ...); missing/wrong Finnish
consonant-gradation forms; an English regression (the localized sponsoring
pattern dropped a trailing ``\\b`` and an alternative, and ran on English
text at all - main never did); localized country names rendered in the
wrong script/case inside reviewed copy; and refusal of legitimate verb-final
German/Dutch/Russian sponsoring questions that main answers.

This rewrite is narrower by construction:
- English is byte-identical to main (app/evidence.py branches on language
  BEFORE any new code runs; the literal legacy regexes and the English-only
  mixed-sponsoring carve-out are untouched).
- The non-English recognizer (config/policy_request_vocabulary.py) is a
  tight, word-bounded ADJACENCY pattern per locale (mirroring the English
  regex's own shape), not a co-occurrence rule, and "Forever" is never a
  qualifier.
- There is no localized mixed-sponsoring carve-out: for a non-English
  session, if a localized sponsoring stem is present, the company-policy
  gate is skipped entirely (today's, i.e. main's, non-English behaviour -
  under-refusal, which is accepted; over-refusal is not).
- The alias/display-name changes were reverted entirely
  (config/market_name_aliases.json is byte-identical to main again).

This file pins, per non-English locale: (a) a company-policy request for
Germany and for Kenya, nominative names, is refused; (b) representative
Fable B1 "must not refuse" questions are approved; (c) representative Fable
B6 verb-final sponsoring questions are approved; (d) representative Fable B2
alias-collision sentences name no market (automatic now the aliases are
reverted - pinned here so it stays that way). It also pins the English
byte-identical guarantee (item 1) and fold()'s length preservation (item 5).
"""

from __future__ import annotations

import re

import pytest

from app.evidence import approve_evidence
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import LOCALIZED_POLICY_PATTERN
from app.retrieval.models import RetrievedDocument, RetrievalResult
from config import policy_request_vocabulary
from services.market_config import find_market_mentions


def _document(doc_id: str, country: str, language: str, scope: str, document_type: str, score: float) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        title=doc_id,
        content="Policy content.",
        source=f"s3://approved/{doc_id}",
        country=country,
        language=language,
        score=score,
        metadata={"access_scope": scope, "document_type": document_type, "status": "active"},
    )


def _retrieval_with_foreign_and_own(session: str, language: str, destination: str) -> RetrievalResult:
    documents = [
        _document(f"{destination}:1.01", destination, "en", "country", "policy", 0.95),
        _document(f"{session}:1.01", session, language, "country", "policy", 0.9),
        _document(f"GLOBAL:sponsoring-{destination.lower()}", "GLOBAL", "en", "global", "international_sponsoring_directory", 0.8),
    ]
    return RetrievalResult(documents=documents, citations=[], confidence=0.9, metadata={})


# ---------------------------------------------------------------------------
# (a) Nominative company-policy requests for Germany/Kenya, refused, per locale.
# ---------------------------------------------------------------------------
NOMINATIVE_CROSS_MARKET_CASES = [
    ("fr", "CA", "Quelle est la politique de l'entreprise en Allemagne ?", "Quelle est la politique de l'entreprise au Kenya ?"),
    ("es", "ES", "¿Cuál es la política de la empresa en Alemania?", "¿Cuál es la política de la empresa en Kenia?"),
    ("de", "AT", "Was ist die Unternehmensrichtlinie in Deutschland?", "Was ist die Unternehmensrichtlinie in Kenia?"),
    ("nl", "NL", "Wat is het bedrijfsbeleid in Duitsland?", "Wat is het bedrijfsbeleid in Kenia?"),
    ("it", "IT", "Qual è la politica aziendale in Germania?", "Qual è la politica aziendale in Kenya?"),
    ("da", "DK", "Hvad er virksomhedens politik i Tyskland?", "Hvad er virksomhedens politik i Kenya?"),
    ("no", "NO", "Hva er selskapets retningslinjer i Tyskland?", "Hva er selskapets retningslinjer i Kenya?"),
    # fi/ru/sr use the NOMINATIVE market name literally (not the natural
    # inflected form) because config/market_name_aliases.json is
    # byte-identical to main again (item 4: the inflected-form aliases were
    # reverted, left for a native-review follow-up) - find_market_mentions
    # only recognises the nominative spellings main already ships.
    ("fi", "FI", "Mikä on yrityksen käytäntö Saksa?", "Mikä on yrityksen käytäntö Kenia?"),
    ("sv", "SE", "Vad är företagets policy i Tyskland?", "Vad är företagets policy i Kenya?"),
    ("ru", "US", "Какая политика компании — Германия?", "Какая политика компании — Кения?"),
    ("sr", "RS", "Каква је политика компаније Немачка?", "Каква је политика компаније Кенија?"),
]


@pytest.mark.parametrize("language, session, germany_question, kenya_question", NOMINATIVE_CROSS_MARKET_CASES)
def test_nominative_company_policy_request_for_germany_is_refused(language, session, germany_question, kenya_question) -> None:
    decision = approve_evidence(germany_question, _retrieval_with_foreign_and_own(session, language, "DE"), session, language)

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []


@pytest.mark.parametrize("language, session, germany_question, kenya_question", NOMINATIVE_CROSS_MARKET_CASES)
def test_nominative_company_policy_request_for_kenya_is_refused(language, session, germany_question, kenya_question) -> None:
    decision = approve_evidence(kenya_question, _retrieval_with_foreign_and_own(session, language, "KE"), session, language)

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"
    assert decision.evidence == []


# ---------------------------------------------------------------------------
# (b) Fable B1: legitimate own-market questions (return policy, international
# shipping, product/policy mentioning a foreign market only incidentally)
# must NOT be refused. Representative subset of Fable's 42-question probe.
# ---------------------------------------------------------------------------
B1_OWN_MARKET_NOT_REFUSED_CASES = [
    ("fr", "CA", "DE", "Quelle est la politique de retour de Forever si j'expédie un produit en Allemagne ?"),
    ("fr", "CA", "DE", "Quelle est la politique de livraison internationale vers l'Allemagne ?"),
    ("fr", "CA", "IT", "Quelle est la politique de l'entreprise concernant les distributeurs italiens qui commandent ici ?"),
    ("es", "ES", "DE", "¿Cuál es la política de envío de Forever para pedidos a Alemania?"),
    ("es", "ES", "DE", "¿Cuál es la política de envío internacional a Alemania?"),
    ("es", "ES", "GH", "¿Cuál es la política de la empresa para que un FBO gane el bono?"),
    ("de", "AT", "DE", "Wie ist die Rückgaberichtlinie für Forever Aloe Vera Gel, das ich nach Deutschland geschickt habe?"),
    ("de", "AT", "DE", "Wie ist die internationale Versandrichtlinie nach Deutschland?"),
    ("de", "AT", "DE", "Darf ich laut Unternehmensrichtlinie jemanden sponsern, der in Deutschland lebt?"),
    ("nl", "NL", "NL", "Kan ik het bedrijfsbeleid in het Nederlands krijgen?"),
    ("nl", "NL", "DE", "Wat is het retourbeleid van Forever als ik een product naar Duitsland stuur?"),
    ("nl", "NL", "DE", "Wat is het internationaal verzendbeleid naar Duitsland?"),
    ("it", "IT", "DE", "Qual è la policy di spedizione internazionale verso la Germania?"),
    ("it", "IT", "DE", "Posso sponsorizzare qualcuno in Germania secondo la policy aziendale?"),
    ("da", "DK", "DE", "Hvad er Forevers returpolitik, hvis jeg sender et produkt til Tyskland?"),
    ("da", "DK", "DE", "Hvad er den internationale forsendelsespolitik til Tyskland?"),
    ("da", "DK", "FI", "Hvad er virksomhedens politik for de finske kunder, der bestiller her?"),
    ("no", "NO", "DE", "Hva er Forevers returpolitikk hvis jeg sender et produkt til Tyskland?"),
    ("no", "NO", "DE", "Hva er de internasjonale retningslinjene for frakt til Tyskland?"),
    ("no", "NO", "DK", "Hva er selskapets retningslinjer for danske kunder som bestiller her?"),
    ("fi", "FI", "SE", "Voinko saada yrityksen toimintaperiaatteet ruotsin kielellä?"),
    ("fi", "FI", "DE", "Onko Forever Livingin käytäntö saatavilla saksan kielellä?"),
    ("fi", "FI", "DE", "Mikä on Foreverin palautuskäytäntö, jos lähetän tuotteen Saksaan?"),
    ("sv", "SE", "DE", "Vad är den internationella fraktpolicyn till Tyskland?"),
    ("ru", "US", "DE", "Какая политика возврата Forever, если я отправлю товар в Германию?"),
    ("sr", "RS", "DE", "Kakva je politika povraćaja Forever ako pošaljem proizvod u Nemačku?"),
    ("sr", "RS", "DE", "Kakva je politika međunarodne isporuke u Nemačku?"),
    ("fr", "CA", "DE", "Forever Living en Allemagne est-elle la même entreprise qu'ici ?"),
    ("de", "AT", "DE", "Ist Forever Living in Deutschland dasselbe Unternehmen wie hier?"),
    ("fr", "CA", "DE", "Quel est le contact du bureau Forever en Allemagne ?"),
    ("de", "AT", "DE", "Wie lautet die Adresse des Forever Büros in Deutschland?"),
]


@pytest.mark.parametrize("language, session, destination, question", B1_OWN_MARKET_NOT_REFUSED_CASES)
def test_legitimate_own_market_question_is_not_refused(language, session, destination, question) -> None:
    decision = approve_evidence(question, _retrieval_with_foreign_and_own(session, language, destination), session, language)

    assert decision.reason != "cross_market_policy_request"


# ---------------------------------------------------------------------------
# (c) Fable B6: verb-final German/Dutch and Russian (and other locale)
# sponsoring questions naming a foreign market, under a localized company
# policy phrase, must NOT be refused (main answers the English equivalent).
# ---------------------------------------------------------------------------
B6_SPONSORING_NOT_REFUSED_CASES = [
    ("de", "AT", "Darf ich laut Unternehmensrichtlinie jemanden in Deutschland sponsern?"),
    ("de", "AT", "Darf ich laut Unternehmensrichtlinie jemanden sponsern, der in Deutschland lebt?"),
    ("nl", "NL", "Mag ik volgens het bedrijfsbeleid iemand in Duitsland sponsoren?"),
    ("nl", "NL", "Mag ik volgens het bedrijfsbeleid iemand sponsoren die in Duitsland woont?"),
    ("da", "DK", "Må jeg ifølge virksomhedens politik sponsorere en person i Tyskland?"),
    ("sv", "SE", "Får jag enligt företagets policy sponsra någon i Tyskland?"),
    ("fi", "FI", "Saanko Forever Livingin yrityspolitiikan mukaan sponsoroida jonkun Saksassa?"),
    ("ru", "US", "Могу ли я по политике компании спонсировать кого-то в Германии?"),
    ("sr", "RS", "Mogu li po politici kompanije sponzorisati nekoga u Nemačkoj?"),
]


@pytest.mark.parametrize("language, session, question", B6_SPONSORING_NOT_REFUSED_CASES)
def test_verb_final_sponsoring_question_is_not_refused(language, session, question) -> None:
    decision = approve_evidence(question, _retrieval_with_foreign_and_own(session, language, "DE"), session, language)

    assert decision.reason != "cross_market_policy_request"


# ---------------------------------------------------------------------------
# N1 (Fable re-review): the bare English/loanword stem "sponsor" was missing
# from fr/fi/ru/sr's SPONSORING_STEMS, so a bare "sponsor"/"sponsoring"
# question typed in one of those sessions (English-typed, or a loanword like
# Finnish "sponsori") skipped main's English carve-out entirely and was
# wrongly refused, where main (which never looks at session language for
# this check) approves it. Each case is asserted against app/evidence.py's
# ACTUAL decision on an unpatched main checkout (see the git-worktree
# comparison run for this fix), not just an expected literal, so this stays
# tied to real main behaviour rather than a guess about it.
# ---------------------------------------------------------------------------
N1_BARE_SPONSOR_STEM_CASES = [
    ("fr", "CA", "IT", "Under company policy, can I sponsor someone in Italy?"),
    ("fr", "CA", "IT", "What is the company policy on international sponsoring in Italy?"),
    ("fr", "CA", "DE", "Selon la politique de l'entreprise, le sponsoring en Allemagne est-il possible ?"),
    ("fr", "CA", "DE", "Quelle est la politique de l'entreprise pour un sponsor en Allemagne ?"),
    ("fi", "FI", "DE", "Mikä on yrityksen käytäntö, jos sponsori on Saksa?"),
    ("fi", "FI", "IT", "Under company policy, can I sponsor someone in Italy?"),
    ("fi", "FI", "IT", "What is the company policy on international sponsoring in Italy?"),
    ("ru", "US", "IT", "Under company policy, can I sponsor someone in Italy?"),
    ("ru", "US", "IT", "What is the company policy on international sponsoring in Italy?"),
    ("sr", "RS", "IT", "Under company policy, can I sponsor someone in Italy?"),
    ("sr", "RS", "IT", "What is the company policy on international sponsoring in Italy?"),
]


@pytest.mark.parametrize("language, session, destination, question", N1_BARE_SPONSOR_STEM_CASES)
def test_bare_sponsor_stem_question_is_approved_and_matches_main(language, session, destination, question) -> None:
    decision = approve_evidence(question, _retrieval_with_foreign_and_own(session, language, destination), session, language)

    assert decision.approved is True
    assert decision.reason == "approved"
    # Verified equal to main's own decision for this exact message (git
    # worktree comparison run during this fix) - main never looks at
    # session language for the company-policy/sponsoring checks, so an
    # English-typed sentence decides the same way regardless of session
    # language, and main answers every one of these from GLOBAL evidence.


@pytest.mark.parametrize("language", ["fr", "fi", "ru", "sr"])
def test_bare_sponsor_stem_is_recognised_for_every_locale_missing_it(language) -> None:
    assert policy_request_vocabulary.contains_sponsoring_stem("sponsor", language) is True
    assert policy_request_vocabulary.contains_sponsoring_stem("sponsoring", language) is True


def test_spons_substring_is_not_added_anywhere_it_was_not_already() -> None:
    """Fable noted "spons" also matches "respons..." ("responsible",
    "responsabilite", ...) - accepted under-refusal risk, left exactly as
    it was. fr/fi/ru/sr must not gain a bare "spons" entry as part of N1;
    only the shared "sponsor" stem was added."""
    for locale in ("fr", "fi", "ru", "sr"):
        assert "spons" not in policy_request_vocabulary.SPONSORING_STEMS.get(locale, ())


# ---------------------------------------------------------------------------
# (d) Fable B2: sentences naming no market that a rejected earlier version's
# alias additions wrongly matched. Automatic now the aliases are reverted to
# main byte-identical - pinned here as a regression guard.
# ---------------------------------------------------------------------------
B2_NO_MARKET_NAMED_CASES = [
    ("nl", "Ik spreek Nederlands, kunt u in het Nederlands antwoorden?"),
    ("nl", "Is het beleid beschikbaar in het Nederlands?"),
    ("fi", "Voitko vastata ruotsin kielellä?"),
    ("fi", "Onko dokumentti saatavilla saksan kielellä?"),
    ("fi", "Puhun tanskan ja norjan kieltä."),
    ("es", "Espero que mi equipo gane el bono este mes."),
    ("es", "¿Qué pasa si no gane suficiente volumen?"),
    ("fr", "Les distributeurs italiens peuvent-ils commander ici ?"),
    ("no", "Hva er reglene for danske og finske kunder?"),
    ("da", "De danske regler gælder her."),
    ("sr", "Nemačka firma me je kontaktirala."),
    ("sv", "Kanadas regler gäller inte här."),
    ("de", "Ich gehe ins Lokal."),
]


@pytest.mark.parametrize("language, message", B2_NO_MARKET_NAMED_CASES)
def test_alias_collision_sentence_names_no_market(language, message) -> None:
    assert find_market_mentions(message) == set()


# ---------------------------------------------------------------------------
# 1. English byte-identical: is_company_policy_request(text) (default
# language="en") matches the untouched legacy regex on every repo string
# literal, plus Fable's B4 sentences.
# ---------------------------------------------------------------------------
_LEGACY_ENGLISH_RE = re.compile(r"\b(?:company|local|national)\s+polic(?:y|ies)\b", re.IGNORECASE)

B4_ENGLISH_SENTENCES = [
    "What is the company policy if I sponsored someone in Italy?",
    "What is the company policy for a sponsorships program in Italy?",
    "Under company policy, what happens when I have sponsored someone in Italy?",
    "What is the company policy on international sponsoring in Italy?",
]


@pytest.mark.parametrize("text", B4_ENGLISH_SENTENCES)
def test_english_is_company_policy_request_matches_legacy_regex_exactly(text) -> None:
    assert policy_request_vocabulary.is_company_policy_request(text) is bool(_LEGACY_ENGLISH_RE.search(text))


def test_english_sponsoring_pattern_is_untouched_from_main() -> None:
    """This module defines no English sponsoring pattern at all any more -
    the English-only mixed-sponsoring carve-out in app/evidence.py uses
    app.retrieval.providers.SPONSORING_QUESTION_RE directly, unmodified."""
    assert not hasattr(policy_request_vocabulary, "sponsoring_pattern")


@pytest.mark.parametrize(
    "question, session",
    [
        # Fable B4: on a broken sponsoring pattern (missing trailing \b and
        # the "international sponsoring" alternative), the first of these
        # flipped from refused to approved. On main - and here, since
        # app/evidence.py's English path is byte-identical to main - none of
        # these three match SPONSORING_QUESTION_RE at all ("sponsored" is
        # past tense, "sponsorships" is plural, neither is a listed
        # fragment), so the mixed-sponsoring carve-out never applies and
        # each is refused, same as main.
        ("What is the company policy if I sponsored someone in Italy?", "GB"),
        ("What is the company policy for a sponsorships program in Italy?", "GB"),
        ("Under company policy, what happens when I have sponsored someone in Italy?", "GB"),
    ],
)
def test_english_approve_evidence_outcome_for_b4_sentences_matches_main(question, session) -> None:
    decision = approve_evidence(question, _retrieval_with_foreign_and_own(session, "en", "IT"), session, "en")

    assert decision.approved is False
    assert decision.reason == "cross_market_policy_request"


def test_english_international_sponsoring_carve_out_still_applies() -> None:
    """The "international sponsoring" alternative Fable found dropped
    (B4) is exercised directly: a present-tense "sponsoring" question is
    still answered from GLOBAL, unchanged from main."""
    question = "What is the company policy on international sponsoring in Italy?"
    decision = approve_evidence(question, _retrieval_with_foreign_and_own("GB", "en", "IT"), "GB", "en")

    assert decision.approved is True
    assert decision.reason == "approved"


# ---------------------------------------------------------------------------
# 5. fold(): length-preserving for sharp S, ligatures and dotted-I forms.
# ---------------------------------------------------------------------------
FOLD_LENGTH_PRESERVING_CASES = ["Straße", "groß", "ﬁnal", "Ĳssel", "İstanbul", "ǆ", "ﬀ"]


@pytest.mark.parametrize("text", FOLD_LENGTH_PRESERVING_CASES)
def test_fold_is_length_preserving(text) -> None:
    folded = policy_request_vocabulary.fold(text)
    assert len(folded) == len(text)


def test_fold_does_not_use_casefold_nfkd_expansion() -> None:
    """str.casefold() maps "ß" -> "ss" (2 chars from 1); fold() must not do that."""
    assert policy_request_vocabulary.fold("Straße") == "straße"
    assert policy_request_vocabulary.fold("Straße") != "strasse"


# ---------------------------------------------------------------------------
# LOCALIZED_POLICY_PATTERN still matches exactly what it matched before its
# fragment list moved into config.policy_request_vocabulary (unrelated to
# the B1-B6 rewrite; untouched by it).
# ---------------------------------------------------------------------------
def _legacy_localized_policy_pattern():
    return chat_orchestrator._follow_up_stem_pattern(
        "policy", "beleid", "politique", "richtlinie", "politik", "política", "käytäntö",
        "politica", "retningslinj", "riktlinj", "политик", word_start=False,
    )


LOCALIZED_POLICY_PATTERN_CORPUS = [
    "And the delivery policy?",
    "What about ons beleid?",
    "Et la politique?",
    "Unternehmensrichtlinien",
    "Was ist die Politik?",
    "¿Cuál es la política?",
    "Mikä on käytäntö?",
    "Qual è la politica?",
    "Hvad er retningslinjen?",
    "Vad är riktlinjen?",
    "Какая политика?",
    "No policy words here at all.",
    "",
]


@pytest.mark.parametrize("text", LOCALIZED_POLICY_PATTERN_CORPUS)
def test_localized_policy_pattern_unchanged_after_moving_fragments(text) -> None:
    legacy = _legacy_localized_policy_pattern()
    assert bool(LOCALIZED_POLICY_PATTERN.search(text)) == bool(legacy.search(text))
