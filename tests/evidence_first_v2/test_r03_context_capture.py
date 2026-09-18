"""R03 controls for truthful follow-up retrieval capture, entirely offline."""

from __future__ import annotations

import json
import random
import re
import sys
import unicodedata

import pytest

from app.orchestrator.chat_orchestrator import AIOrchestrator
from scripts.evidence_first_v2 import capture_read_only_retrieval as capture


def _history(question: str) -> str:
    return f"user: {question}\nvera: A source-bound answer."


def test_retrieval_only_capture_rejects_any_case_that_needs_stored_turns() -> None:
    pack = {
        "cases": [
            {"id": "first-turn", "question": "What is the office number?", "conversation": []},
            {
                "id": "follow-up-in-any-language",
                "question": "Entä jos hän on johtaja?",
                "conversation": [{"question": "Mitä Suomessa tapahtuu FBO:lle?"}],
            },
        ]
    }

    with pytest.raises(ValueError, match="follow-up-in-any-language"):
        capture._require_runtime_context_capture(pack)


def test_history_anchors_directory_scope_without_replacing_an_unresolved_place() -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"
    follow_up = "And what about FBOs who live there?"
    history = _history(prior)

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-session-a",
    )

    assert "Tanzania" in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"
    assert provenance["prior_user_turn_id"].startswith("history-user-1-")
    assert orchestrator._scope_query(follow_up, query, history) == query
    assert orchestrator._scope_query(follow_up, query, "") == follow_up

    unresolved = "What about the office in Atlantis?"
    isolated_query, isolated_provenance = orchestrator._build_retrieval_query_with_provenance(
        unresolved, history, "r03", session_id="r03-session-b",
    )
    assert isolated_query == unresolved
    assert isolated_provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_configured_language_follow_up_uses_only_its_own_stored_turn() -> None:
    orchestrator = AIOrchestrator()
    prior = "Mitä Suomessa tapahtuu FBO:lle, joka ei ole ostanut mitään 36 kuukauteen?"
    follow_up = (
        "Entä jos hän on Sponsored Recognized Manager ja hänen tiimissään on "
        "ensimmäisen sukupolven Recognized Managereita?"
    )
    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-session",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"
    standalone, standalone_provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, "", "r03", session_id="r03-finnish-new-session",
    )
    assert standalone == follow_up
    assert standalone_provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize("follow_up", ["Entä jos hän on Atlantisissa?", "Entä jos hän on Berliinissä?"])
def test_finnish_anaphoric_follow_up_with_an_unresolved_place_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-unresolved-place",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_finnish_inflected_configured_market_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on Ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-configured-place",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize("follow_up", ["Entä jos hän asuu atlantisissa?", "Entä jos hän asuu berliinissä?"])
def test_lowercase_finnish_anaphoric_unknown_place_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-unknown-place",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_lowercase_finnish_inflected_configured_market_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-configured-place",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_lowercase_configured_finnish_market_after_on_replaces_the_prior_market() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-lowercase-configured-after-on",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu nyt ugandassa?",
        "Entä jos hän on nyt ugandassa?",
        "Entä jos hän työskentelee ugandassa?",
        "Entä jos hän asuu, nyt Ugandassa?",
        "Entä jos hän asuu nyt pysyvästi ugandassa?",
        "Entä jos hän asuu edelleen ugandassa?",
        "Entä jos hän asuu ugandassa ja työskentelee siellä?",
        "ENTÄ JOS HÄN ASUU UGANDASSA?",
    ],
)
def test_bounded_finnish_location_phrase_replaces_the_prior_market(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-location-phrase",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän asuu nyt berliinissä?", "Entä jos hän asuu tiimissä?"],
)
def test_unknown_lowercase_finnish_residence_complement_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-location-unknown",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_finnish_configured_market_matching_uses_exact_tokens_not_substrings() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu pseudougandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-substring-control",
    )

    assert query == follow_up
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu ugandassa tai Atlantisissa?",
        "Entä jos hän asuu Atlantisissa tai ugandassa?",
        "Entä jos hän on Kenya mutta asuu ugandassa?",
        "Entä jos hän asuu ugandassa tai kenyassa?",
    ],
)
def test_finnish_competing_market_or_unknown_signal_stays_standalone(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-finnish-competing-signals",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän työskentelee nyt pysyvästi atlantisissa?",
    ],
)
def test_unsupported_finnish_place_shape_keeps_context_but_is_unresolved(follow_up: str) -> None:
    """A WEAK location verb ("työskentelee") governing an unknown place keeps

    context but is never trusted (R03 correction 9 B2 - Fable's reference
    check on correction 9: this must stay ``unresolved`` with no id, since it
    IS a residence/location-verb complement, just not the strong "asuu" one).
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-unsupported-shape",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän työskentelee atlantisissa?",
        "Entä jos hän työskentelee nyt atlantisissa?",
        "Entä jos hän työskentelee tiimissä?",
        "Entä jos hän työskentelee johdossa?",
        "Entä jos hän työskentelee verkostossa?",
    ],
)
def test_ambiguous_lowercase_finnish_complement_keeps_context(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-ambiguous-complement",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän on atlantisissa?",
        "Entä jos hän on nyt atlantisissa?",
        "Entä jos hän on nyt pysyvästi tiimissä?",
        "Entä jos hän on nyt tiimissä?",
        "Entä jos hän on nyt johdossa?",
        "Entä jos hän on nyt verkostossa?",
        "Entä jos hän on tiimissä?",
        "Entä jos hän on johdossa?",
        "Entä jos hän on verkostossa?",
    ],
)
def test_bounded_finnish_location_phrase_does_not_scan_ordinary_nouns(follow_up: str) -> None:
    """R03 correction 9 SHOULD-FIX (over-fire): an ordinary case-marked noun

    that is neither a configured-market stem nor the complement of a
    residence/location verb ("on", the copula, is not in that closed set) is
    not a place candidate at all, so it no longer blocks trust. This was
    correction 8's own defect: it made the trusted path unreachable for
    realistic follow-ups like this one.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-location-noun",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_bounded_finnish_location_phrase_without_history_stays_standalone() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu nyt ugandassa?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, "", "r03", session_id="r03-finnish-location-no-history",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_lowercase_finnish_anaphoric_role_follow_up_without_a_place_keeps_context() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on johtaja?"
    prior = "Mitä Suomessa tapahtuu FBO:lle, joka ei ole ostanut mitään 36 kuukauteen?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-lowercase-role",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän on United States mutta asuu ugandassa?",
        "Entä jos hän asuu ugandassa mutta työskentelee South Africa?",
        "Entä jos hän asuu ugandassa mutta työskentelee United Kingdom?",
    ],
)
def test_multiword_direct_market_mention_is_collected_over_the_whole_message(follow_up: str) -> None:
    """R03 correction 8 - Fable BLOCKER on correction 7.

    A multi-word configured market name ("United States", "South Africa",
    "United Kingdom") competing with a configured Finnish inessive form used
    to be invisible, because the prior code called ``find_market_mentions``
    once per token instead of over the whole message. Both markets must now
    be collected, so the turn goes standalone rather than trusting Uganda.
    """
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c8-multiword-conflict",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän muuttaa ugandaan?", "Entä jos hän on kotoisin ugandasta?"],
)
def test_noninessive_finnish_case_forms_of_a_configured_market_are_not_trusted(follow_up: str) -> None:
    """R03 correction 8 - Fable SHOULD-FIX on correction 7.

    An illative ("ugandaan") or elative ("ugandasta") form of a configured
    market is not the supported inessive form, so it must not silently keep
    the prior Tanzania target with trusted provenance. The closed
    locative/directional case-ending set now flags it as place-shaped
    residue, so the turn keeps the anchor but is recorded as ``unresolved``
    rather than a trusted resolved follow-up.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c8-noninessive-form",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_negated_finnish_residence_verb_is_never_trusted() -> None:
    """R03 correction 8 - Fable NOTE on correction 7.

    "Entä jos hän ei asu ugandassa?" ("what if he does NOT live in Uganda")
    used to resolve trusted to Uganda even though negation inverts the claim.
    The closed negation set now blocks trust whenever it scopes the
    residence verb, so this fails closed as standalone rather than
    asserting either Tanzania or Uganda.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän ei asu ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c8-negated-residence",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_dead_accented_configured_key_now_matches() -> None:
    """R03 correction 8 - Fable NOTE #4 on correction 7 (dead accented keys).

    The configured inessive map used to normalize its keys without stripping
    accents, while tokens are always accent-stripped, so an accented
    single-word market alias such as "Argentína" could never match its own
    "-ssa" form. Keys are now normalized exactly like the tokens they are
    matched against, so this previously dead key resolves and its exact
    accented span is replaced in the retrieval query.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on Argentínassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c8-dead-accented-key",
    )

    assert "Argentina" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_finnish_configured_market_matching_normalizes_accents_on_both_sides() -> None:
    """A capitalized accented configured form ("Ugandassa" with stray accents

    normalized away) still resolves the same as the plain-ASCII form, proving
    the fix generalizes rather than special-casing one market's alias.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on Ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c8-accent-normalization-control",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_finnish_anaphoric_follow_up_asking_about_finland_is_reported_standalone() -> None:
    """"Entä jos hän asuu Suomessa?" ("what if he lives in Finland").

    "Suomessa" is not a configured single-word inessive alias for Finland
    (the configured name is "Finland"), so it is an unrecognised capitalized
    place. Per the earned-trust rule this fails closed exactly like any other
    capitalized unknown place: standalone, dropping the Tanzania anchor
    rather than guessing at a market. This is the R03 correction 8 answer to
    the acceptance criterion asking to state Finland's outcome explicitly.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu Suomessa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c8-finland-capitalized",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_finnish_possessive_inessive_token_is_not_mistaken_for_illative_residue() -> None:
    """"tiimissään" ("in their team") ends in a doubled vowel plus "n" just

    like a short illative place form, but it is an inessive-possessive
    ending, not a place. The case-ending heuristic excludes an immediately
    preceding "ss" for exactly this reason, so this configured-language role
    follow-up (with no place at all) keeps its trusted dependent status
    instead of being downgraded by a false-positive residue match.
    """
    orchestrator = AIOrchestrator()
    follow_up = (
        "Entä jos hän on Sponsored Recognized Manager ja hänen tiimissään on "
        "ensimmäisen sukupolven Recognized Managereita?"
    )
    prior = "Mitä Suomessa tapahtuu FBO:lle, joka ei ole ostanut mitään 36 kuukauteen?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c8-possessive-inessive",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_direct_market_mention_alone_keeps_context_without_trusted_market_swap() -> None:
    """A bare nominative market mention with no configured inessive support

    ("Entä jos hän on Kenya?") is a name mention, not a residence claim by
    itself, so the earned-trust rule records this Finnish follow-up as
    ``unresolved`` rather than a trusted resolved dependent follow-up, even
    though the unrelated, pre-existing ``_replace_directory_target`` step
    still swaps the anchor's named market the same way it would for any
    other language's direct market mention.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on Kenya?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c8-direct-mention-alone",
    )

    assert "Kenya" in query
    assert "Tanzania" not in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_nfd_input_does_not_corrupt_the_substitution_span() -> None:
    """R03 correction 9 BLOCKER (Fable on correction 8).

    `_follow_up_raw_tokens` and `_follow_up_tokens` were tokenized
    independently and assumed to stay index-aligned. NFD input broke that:
    a combining accent is not a word character, so "hän" (NFD: h, a,
    COMBINING DIAERESIS, n) split into "ha" and "n" in the raw array while
    the folded array still saw one token "han" - every later index built
    from one array and read from the other pointed at the wrong word. The
    reproduced symptom was a wrong, TRUSTED substitution: the retrieval
    query gained a stray "Uganda" token instead of replacing "ugandassa".
    Tokenizing once, with spans, makes this structurally impossible.
    """
    orchestrator = AIOrchestrator()
    follow_up = unicodedata.normalize("NFD", "Entä jos hän asuu ugandassa?")
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-nfd-input",
    )

    assert "Uganda" in query
    assert "ugandassa" not in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_nfkd_expanding_character_does_not_crash_or_misalign() -> None:
    """R03 correction 9 BLOCKER (Fable on correction 8).

    "½" NFKD-decomposes into three characters ("1", a fraction slash, "2"),
    two of which are word characters - so the (now-removed) accent-stripped
    array grew by one token relative to the raw array, and every later
    index read past the end of the shorter one. The reproduced symptom was
    an IndexError raised out of `_resolve_finnish_anaphoric`, reachable from
    `handle_chat` with no handling on that path. It must neither crash nor
    silently corrupt the query.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on ½ vuotta ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-nfkd-expanding-character",
    )

    assert "Uganda" in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


@pytest.mark.parametrize(
    "follow_up",
    [
        # A ligature ("ﬁ") NFKD-decomposes to two ASCII letters.
        "Entä jos hän asuu ugandassa ja ﬁrmassa?",
        # Fullwidth letters (a CJK input-method compatibility form) NFKD-decompose
        # to their ASCII equivalents.
        "Ｅｎｔä jos hän asuu ugandassa?",
        # A Roman numeral NFKD-decomposes to several ASCII letters.
        "Entä jos hän asuu ugandassa Ⅷ?",
    ],
)
def test_other_compatibility_characters_do_not_crash(follow_up: str) -> None:
    """R03 correction 9 BLOCKER - the other compatibility-character examples

    named in the review (a ligature, full-width letters), plus a Roman
    numeral for a third independent case. None of these must raise.
    """
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-other-compatibility-chars",
    )


def test_unicode_fuzz_never_crashes_and_only_changes_substituted_spans() -> None:
    """R03 correction 9 BLOCKER - a fuzz loop over mixed Unicode insertions,

    in both NFC and NFD form, asserting only that nothing raises. (The
    stronger claim - the query changes only at the substituted span - is
    exercised directly by the span-based rewrite in
    `_canonicalize_finnish_anaphoric_market`, which slices the ORIGINAL
    message around each resolved span rather than re-deriving text; this
    loop is the adversarial input-coverage half of that guarantee.)
    """
    orchestrator = AIOrchestrator()
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")
    base = "Entä jos hän asuu nyt ugandassa mutta työskentelee tiimissä?"
    compatibility_characters = ["½", "¼", "Ⅷ", "ﬁ", "ﬂ", "ｅ", "Ａ", "①", "⁄", "́", "﻿"]
    random.seed(2026_09_18)

    for _ in range(200):
        characters = list(base)
        for _ in range(random.randint(0, 4)):
            position = random.randrange(len(characters))
            characters.insert(position, random.choice(compatibility_characters))
        variant = "".join(characters)
        for form in ("NFC", "NFD"):
            text = unicodedata.normalize(form, variant)
            orchestrator._build_retrieval_query_with_provenance(
                text, history, "r03", session_id="r03-c9-fuzz",
            )


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu ugandassakin?",
        "Entä jos hän asuu ugandassako?",
        "Entä jos hän asuu Ugandassakin?",
        "Entä jos hän asuu ugandassaan?",
        "Entä jos hän edustaa ugandaa?",
        "Entä jos hän asuu ugandana?",
    ],
)
def test_unsupported_case_forms_of_a_configured_market_are_not_trusted(follow_up: str) -> None:
    """R03 correction 9 SHOULD-FIX (i) (Fable on correction 8).

    A clitic ("-kin"/"-ko"), the inessive-possessive ("-ssaan"), partitive
    ("ugandaa") or essive ("ugandana") form of a CONFIGURED market used to
    give ``resolved, code=None, reason=no_place_evidence`` - i.e. fully
    trusted, keeping Tanzania - because none of these forms matched the old
    plain case-ending test. The new market-stem prefix check recognizes all
    of them as a real market in an unsupported form, so the follow-up keeps
    context but is never trusted.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c9-unsupported-market-form",
    )

    assert prior in query
    # The query is unchanged (never substituted), so it still contains the
    # ORIGINAL unsupported form verbatim - never the bare display name
    # "Uganda" as its own word, which would mean a (wrong) substitution ran.
    assert query.endswith(follow_up)
    assert not re.search(r"(?<!\w)Uganda(?!\w)", query)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän ei ole ostanut mitään 24 kuukauteen?",
        "Entä jos hän on sääntöjen mukaan johtaja?",
        "Entä jos hän maksaa tilille?",
        "Entä jos hän nousee tasolle?",
        "Entä jos hän ostaa sen jälkeen?",
        "Entä jos hän vierailee toimistossa?",
        "Entä jos hän asioi netissä?",
    ],
)
def test_ordinary_case_marked_nouns_outside_residence_context_are_trusted(follow_up: str) -> None:
    """R03 correction 9 SHOULD-FIX (over-fire) (Fable on correction 8).

    None of these tokens ("kuukauteen", "johtaja"-adjacent "mukaan",
    "tilille", "tasolle", "jälkeen", "toimistossa", "netissä") name a
    configured market or sit near a residence/location verb, so under the
    old plain case-ending residue test they made a realistic, ordinary
    follow-up ``unresolved`` for no real reason - the trusted path was
    unreachable. None of these is a place candidate any more.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c9-ordinary-noun-trusted",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_weak_residence_verb_multimodifier_complement_stays_unresolved_with_no_id() -> None:
    """R03 correction 9 acceptance check B2: "Entä jos hän työskentelee nyt

    pysyvästi atlantisissa?" is a residence/location-verb complement (the
    WEAK stem "työskentel-"), so it must stay ``unresolved`` with no
    ``prior_user_turn_id`` - never standalone, never trusted.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän työskentelee nyt pysyvästi atlantisissa?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c9-b2-weak-verb-multimodifier",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_finnish_anaphoric_asking_about_finland_stays_safely_standalone() -> None:
    """R03 correction 9 acceptance check: "…asuu Suomessa?" must stay safely

    standalone. "Suomessa" is capitalized and not a configured single-word
    inessive alias (the configured name is "Finland"), so it is an
    unrecognised capitalized place candidate - standalone, exactly like any
    other unrecognised capitalized place.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu Suomessa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-finland-standalone",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_negation_window_covers_the_perfect_tense_auxiliary() -> None:
    """R03 correction 9 NOTE 4 (Fable on correction 8).

    "Entä jos hän ei ole asunut ugandassa?" ("what if he has NOT lived in
    Uganda") used to resolve Uganda as trusted, because the negation check
    only looked at the token immediately after "ei" and missed the perfect
    tense's "ole" auxiliary sitting between "ei" and "asunut". The widened
    negation window reaches past "ole" to the residence-verb stem.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän ei ole asunut ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-negation-perfect-tense",
    )

    assert query == follow_up
    assert "Tanzania" not in query
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


def test_repeated_resolved_market_is_substituted_at_every_occurrence() -> None:
    """R03 correction 9 NOTE 5 (Fable on correction 8).

    Substitution used to be ``count=1``, so a second occurrence of the same
    exact resolved form was left untouched. Substitution is now by exact
    span for every occurrence collected during resolution.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu ugandassa ja työskentelee myös ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-repeated-market-both-spans",
    )

    assert query.count("Uganda") == 2
    assert "ugandassa" not in query
    assert "Tanzania" not in query
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_topic_shift_marker_reads_the_precomputed_finnish_decision() -> None:
    """R03 correction 9 NOTE 6 (Fable on correction 8).

    `_contains_topic_shift_marker` used to re-derive the Finnish decision
    from the already-canonicalized, lowercased message instead of reading
    the decision already computed (and acted on) for the original message.
    This exercises that path end to end: a message whose earned-trust
    decision is ``resolved`` with a market swap must still merge with the
    anchor as a topic-shift follow-up (proving the precomputed decision, not
    a fresh recomputation on the post-substitution text, drives the merge).
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-topic-shift-precomputed-decision",
    )

    assert query == "How does Forever pay bonuses to FBOs who live outside the country? Entä jos hän asuu Uganda?"
    assert provenance["status"] == "resolved_dependent_follow_up"


def test_audit_mode_rejects_a_multiturn_pack_before_running_the_audit(monkeypatch, tmp_path, capsys) -> None:
    pack = {"cases": [{"id": "stored-turn", "conversation": [{"question": "Earlier question"}]}]}
    monkeypatch.setattr(capture, "_load_pack", lambda *_: (pack, "pack-hash"))
    monkeypatch.setattr(capture, "_audit_active_index_generations", lambda *_: pytest.fail("audit must not run"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["capture", "--output", str(tmp_path / "capture.json"), "--audit-generations-only"],
    )

    assert capture.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "stored-turn" in payload["detail"]
