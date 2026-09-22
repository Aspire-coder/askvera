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
    """R03 correction 11 CHANGE (was trusted at e3b399a/correction 7).

    T2's ``no capitalised non-initial token`` rule (see the module docstring
    on the trusted shapes) reads "Sponsored Recognized Manager" and
    "Recognized Managereita" as capitalised non-initial tokens, exactly like
    an unrecognised proper-noun place would read, so this follow-up no
    longer earns T2's trust. It still keeps the prior turn as ordinary,
    untrusted context (``unresolved``, no ``prior_user_turn_id``) - only the
    provenance status changed, not which turn is retrieved.
    """
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
    assert provenance == {"provenance": "runtime", "status": "unresolved"}
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
        "Entä jos hän on nyt pysyvästi tiimissä?",
    ],
)
def test_unsupported_finnish_place_shape_keeps_context_but_is_unresolved(follow_up: str) -> None:
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
        "Entä jos hän on atlantisissa?",
        "Entä jos hän on nyt atlantisissa?",
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
    ["Entä jos hän on nyt tiimissä?", "Entä jos hän on nyt johdossa?", "Entä jos hän on nyt verkostossa?"],
)
def test_bounded_finnish_location_phrase_does_not_scan_ordinary_nouns(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-location-noun",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_bounded_finnish_location_phrase_without_history_stays_standalone() -> None:
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu nyt ugandassa?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, "", "r03", session_id="r03-finnish-location-no-history",
    )

    assert query == follow_up
    assert provenance == {"provenance": "runtime", "status": "not_dependent"}


@pytest.mark.parametrize(
    "follow_up",
    ["Entä jos hän on tiimissä?", "Entä jos hän on johdossa?", "Entä jos hän on verkostossa?"],
)
def test_lowercase_finnish_noun_after_on_keeps_context(follow_up: str) -> None:
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-finnish-lowercase-noun",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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
    preceding "ss" for exactly this reason, so "tiimissään" itself is still
    correctly read as non-place.

    R03 correction 11 CHANGE: the follow-up as a whole is no longer trusted,
    though not because of "tiimissään" - the T2 shape's separate
    ``no capitalised non-initial token`` rule reads "Sponsored Recognized
    Manager" and "Recognized Managereita" as capitalised non-initial tokens
    and withholds trust. Context is still kept (``unresolved``, no
    ``prior_user_turn_id``) - only the provenance status changed.
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
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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

    R03 correction 11 CHANGE: no longer trusted as a market swap. "vuotta"
    ("years") sits between the verb and the place and is not one of T1's
    closed temporal/aspectual adverbs, so the message no longer fits T1's
    exact shape - it keeps context (``unresolved``) rather than substituting
    Uganda. The point of this test - no crash, no misaligned span - still
    holds and is asserted directly.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän on ½ vuotta ugandassa?"
    history = _history("How does Forever Tanzania pay bonuses to FBOs who live outside the country?")

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, history, "r03", session_id="r03-c9-nfkd-expanding-character",
    )

    assert "Tanzania" in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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
def test_ordinary_case_marked_nouns_outside_residence_context_are_unresolved(follow_up: str) -> None:
    """R03 correction 9 SHOULD-FIX (over-fire) (Fable on correction 8);

    R03 CORRECTION 11 CHANGE (was trusted from correction 9 through
    correction 10).

    None of these tokens ("kuukauteen", "johtaja"-adjacent "mukaan",
    "tilille", "tasolle", "jälkeen", "toimistossa", "netissä") names a
    configured market, so correction 9's narrower residue test correctly
    stopped treating them as place candidates and correction 10 kept this
    trusted. Correction 11 inverts the default: T2 (the only shape trusted
    with no market to substitute) withholds trust from ANY locative-case-
    shaped token, without asking whether a residence verb governs it, and
    several of these words happen to end in the same illative-approximation
    shape ("...een"/"...aan") as a real place, or in a genuine (but
    non-residence) case ending ("-lle", "-ssa"). This is the documented,
    accepted cost of the narrower default (see R03-CORRECTION-11): a false
    ``unresolved`` only costs the trusted fallback ordering, so these fall
    back to keeping context without being trusted, rather than being chased
    with another special case.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c9-ordinary-noun-trusted",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän on narniassa?",
        "Entä jos hän on nyt narniassa töissä?",
    ],
)
def test_olla_forms_govern_a_locative_complement_as_a_weak_location_verb(follow_up: str) -> None:
    """R03 correction 10 (Fable review of correction 9, commit 6f87124).

    Correction 9's residence/location verb vocabulary left out olla ("to
    be") entirely, which is the single most common way to say someone IS
    somewhere. That wrongly promoted "Entä jos hän on atlantisissa?" and an
    unrecognised-place probe like "on narniassa?" to a TRUSTED resolved
    follow-up keeping Tanzania - an unknown place upgraded into trusted
    resolution of the prior market, which R03 forbids. Olla now counts as a
    weak location verb for an inessive/adessive complement, so an unknown
    place after "on" keeps context but is never trusted.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c10-olla-locative-complement",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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


def test_repeated_market_mention_outside_the_t1_shape_stays_unresolved() -> None:
    """R03 correction 9 NOTE 5 (Fable on correction 8) established that a

    repeated occurrence of the same resolved market form should ALSO be
    substituted, once substitution is trusted at all.

    R03 CORRECTION 11 CHANGE: substitution is no longer trusted here at all.
    T1 (the only shape trusted to swap a market) requires EXACTLY ONE
    configured-market token, with everything after it drawn from the fixed
    function-word vocabulary; a second literal "ugandassa" in the trailing
    clause is not one of those function words, so the message no longer fits
    T1's shape. It keeps the prior Tanzania anchor for ordinary, untrusted
    context instead of substituting either occurrence.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu ugandassa ja työskentelee myös ugandassa?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c9-repeated-market-both-spans",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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


# --- R03 correction 11: the reviewer's correction-10 repros -----------------
# Every case below used to resolve TRUSTED (either substituting the wrong
# market, or keeping Tanzania trusted with no market to substitute) because
# residue detection missed the specific Finnish shape. Correction 11 grants
# trust only through the two narrow shapes (T1/T2); none of these fits
# either one, so all of them now keep the prior anchor as ordinary,
# untrusted context - never wrongly trusted, never the wrong market.


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän ei ole ugandassa?",
        "Entä jos hän ei ole ollut ugandassa?",
        "Entä jos hän ei ole koskaan asunut ugandassa?",
    ],
)
def test_negated_olla_forms_are_never_trusted_regardless_of_gap(follow_up: str) -> None:
    """A negated "to be" claim about a configured market used to resolve

    TRUSTED to that market, because the windowed negation check (built for
    "ei asu"/"ei ole asunut") never included olla's own stems and could
    still be outrun by an adverb between the negation and the verb
    ("koskaan" pushing "asunut" to offset 3). T1 now disqualifies on ANY
    negation token anywhere in the message, with no window to outrun.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c11-negated-olla",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert "Uganda" not in query
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


@pytest.mark.parametrize(
    "follow_up",
    [
        "Entä jos hän asuu narniassakin?",
        "Entä jos hän asuu suomessakin?",
        "Entä jos hän asuu suomestakin?",
    ],
)
def test_clitic_on_an_unconfigured_place_is_never_trusted(follow_up: str) -> None:
    """A clitic ("-kin") on a place that names no configured market used to

    resolve TRUSTED with no market to substitute (``no_place_evidence``),
    because the clitic suffix itself does not end in a case ending, so the
    old residue test never saw the token underneath as place-shaped. T2 now
    strips this closed set of clitics before checking for a case ending, so
    the stripped form ("narniassa", "suomessa", "suomesta") is still caught
    as locative-case-bearing and withholds T2's trust.
    """
    orchestrator = AIOrchestrator()
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c11-clitic-unconfigured-place",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_verb_after_place_word_order_is_never_trusted() -> None:
    """T1 requires the verb to precede the place (as the configured form

    always has it); "hän narniassa asuu" swaps that order, so the old
    residue test's verb-window lookup (which only looked BACKWARD from the
    place for a verb) still fired and resolved with no market to substitute
    even though a real, unresolved place is sitting right there. T2's
    locative-case check does not depend on word order at all and correctly
    withholds trust.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän narniassa asuu?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c11-verb-after-place",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_adverb_gap_wider_than_the_old_fixed_window_is_never_trusted() -> None:
    """"asuu nyt jo monta vuotta narniassa" separates the verb from the

    unresolved place by four tokens, two of which ("monta", "vuotta") are
    not adverbs at all - wider than the fixed verb/negation windows earlier
    corrections tuned to the examples reviewed at the time. T1's sequential
    adverb-then-verb-then-adverb-then-place shape has no window to outrun:
    the first non-adverb, non-configured-place token ("monta") simply ends
    the match, so this never reaches a trusted substitution.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu nyt jo monta vuotta narniassa?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c11-adverb-gap",
    )

    assert prior in query
    assert query.endswith(follow_up)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


def test_hyphenated_compound_name_never_matches_the_wrong_markets_stem() -> None:
    """"Pohjois-Koreassa" (North Korea) used to resolve TRUSTED to KR (South

    Korea), because the old tokenizer split the hyphenated compound into
    "pohjois" and "koreassa", and "koreassa" alone is South Korea's
    configured inessive form. `_finnish_shape_words` keeps an internal
    hyphen inside one token for T1's purposes, so "pohjois-koreassa" is
    checked (and rejected) as a WHOLE token against the configured map -
    it is not equal to "koreassa" - and T1 fails to find any configured
    place at all rather than silently matching the wrong market on half the
    word.
    """
    orchestrator = AIOrchestrator()
    follow_up = "Entä jos hän asuu Pohjois-Koreassa?"
    prior = "How does Forever Tanzania pay bonuses to FBOs who live outside the country?"

    query, provenance = orchestrator._build_retrieval_query_with_provenance(
        follow_up, _history(prior), "r03", session_id="r03-c11-hyphenated-compound",
    )

    assert prior in query
    # The query is unchanged (never substituted), so it still contains the
    # ORIGINAL compound verbatim - never a bare "Korea" display name on its
    # own, which would mean a (wrong) substitution ran.
    assert query.endswith(follow_up)
    assert not re.search(r"(?<!\w)Korea(?!\w)", query)
    assert provenance == {"provenance": "runtime", "status": "unresolved"}


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
