"""Deterministic/local proof: closed-class function words never become
market-alias match patterns.

Reproduces the defect on the real, checked-in ``config/market_name_aliases.json``
(Estonian "Tai" for Thailand colliding with Finnish "tai" = "or") and proves
the guard removes only that collision - real market names, including short
ones that happen to also be content nouns in another language ("Mali",
"Chile", "Togo"), still resolve; "Thailand" itself, spelled correctly or with
the common near-miss/localized spellings, still resolves to TH.
"""

from __future__ import annotations

import pytest

from config.alias_function_word_guard import (
    filter_function_word_aliases,
    is_function_word_alias,
)
from services import market_config


# ---------------------------------------------------------------------------
# Reproduction: the "tai" defect against the real, unmodified config on disk.
# ---------------------------------------------------------------------------

FINNISH_TAI_SENTENCES = [
    "Voinko maksaa kortilla tai käteisellä?",
    "Onko toimitus tai nouto mahdollista?",
    "Haluaisin tietää hinnan tai toimitusajan.",
]


@pytest.mark.parametrize("message", FINNISH_TAI_SENTENCES)
def test_finnish_tai_no_longer_names_thailand(message: str) -> None:
    """Before this change these all resolved to {'TH'} via the Estonian CLDR
    alias "Tai"; an ordinary Finnish "or" question names no market."""
    assert market_config.find_market_mentions(message) == set()


def test_directory_target_country_names_no_longer_returns_thailand_for_tai() -> None:
    """The exact reproduction the coordinator ran on base code:
    ``_directory_target_country_names`` no longer sends a Finnish "or"
    question to the Thailand directory record."""
    from app.retrieval.opensearch_sections import _directory_target_country_names

    assert _directory_target_country_names(
        "Voinko maksaa kortilla tai käteisellä?", "FI"
    ) == set()


# ---------------------------------------------------------------------------
# Positive controls: genuine Thailand spellings still resolve to TH.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Thailand",
        "Tailand",
        "Tailandia",
        # The Finnish spelling a user would actually write for Thailand.
        "Thaimaa",
    ],
)
def test_genuine_thailand_spellings_still_resolve(message: str) -> None:
    assert market_config.find_market_mentions(message) == {"TH"}


# ---------------------------------------------------------------------------
# Every other market's common name still matches (sample of 10 markets).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message, expected_code",
    [
        ("Finland", "FI"),
        ("France", "FR"),
        ("Germany", "DE"),
        ("United Kingdom", "GB"),
        ("Kenya", "KE"),
        ("Mali", "ML"),
        ("Chile", "CL"),
        ("Peru", "PE"),
        ("Togo", "TG"),
        ("United States", "US"),
    ],
)
def test_sampled_markets_still_resolve(message: str, expected_code: str) -> None:
    assert market_config.find_market_mentions(message) == {expected_code}


# ---------------------------------------------------------------------------
# The excluded-alias list is exactly what the audit found.
# ---------------------------------------------------------------------------


def test_excluded_aliases_match_audit_exactly() -> None:
    """docs/conversation-quality/phase2/ALIAS_COLLISION_AUDIT.md's full scan
    of config/market_name_aliases.json against this repo's reviewed
    closed-class vocabulary (config.reference_vocabulary's
    LOCALIZED_NON_CONTENT_TOKENS, chat_orchestrator's
    LOCALIZED_FOLLOW_UP_FUNCTION_WORDS/LOCALIZED_FOLLOW_UP_STOP_WORDS, plus
    this module's Finnish "tai" supplement) found exactly one collision:
    TH's Estonian name "Tai"."""
    import json

    path = market_config.DEFAULT_MARKETS_CONFIG_PATH.with_name("market_name_aliases.json")
    raw = json.loads(path.read_text(encoding="utf-8"))["names"]

    _filtered, excluded = filter_function_word_aliases(raw)

    assert excluded == (("TH", "Tai"),)


# ---------------------------------------------------------------------------
# Guard unit behavior, isolated from the real config file.
# ---------------------------------------------------------------------------


def test_is_function_word_alias_true_for_finnish_tai() -> None:
    assert is_function_word_alias("Tai") is True
    assert is_function_word_alias("tai") is True
    assert is_function_word_alias("TAI") is True


@pytest.mark.parametrize("alias", ["Thailand", "Tailandia", "Mali", "Chile", "Turkey"])
def test_is_function_word_alias_false_for_real_content_words(alias: str) -> None:
    """Genuine country names - including ones that are also content nouns in
    another language (Chile/"chili", Turkey/"the bird") - are never excluded.
    That ambiguity is a documented, accepted limitation, not this guard's job."""
    assert is_function_word_alias(alias) is False


def test_filter_function_word_aliases_removes_only_the_colliding_alias() -> None:
    names = {
        "TH": ["Thailand", "Tai", "Tailandia"],
        "FR": ["France", "Francia"],
    }

    filtered, excluded = filter_function_word_aliases(names)

    assert filtered == {
        "TH": ["Thailand", "Tailandia"],
        "FR": ["France", "Francia"],
    }
    assert excluded == (("TH", "Tai"),)


def test_filter_function_word_aliases_is_multiword_safe() -> None:
    """A closed-class word never fires inside a multi-word alias - only a
    single-token alias that IS a function word, whole, is excluded."""
    names = {"US": ["United States", "Und So Weiter Land"]}

    filtered, excluded = filter_function_word_aliases(names)

    assert filtered == names
    assert excluded == ()


def test_filter_function_word_aliases_handles_edge_input_without_crashing() -> None:
    names = {"XX": ["", "   ", "123", "!!!"], "YY": []}

    filtered, excluded = filter_function_word_aliases(names)

    assert filtered == names
    assert excluded == ()


def test_is_function_word_alias_handles_empty_and_unknown_input() -> None:
    assert is_function_word_alias("") is False
    assert is_function_word_alias("   ") is False
    assert is_function_word_alias("Zzyzzxqplo") is False
