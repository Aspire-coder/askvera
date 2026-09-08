"""Which country a question is about.

Getting this wrong is not a retrieval inconvenience: it routes a reader to
another country's policy. A distributor in the Democratic Republic of the Congo
asking about their own market was answered from the Republic of Congo, because
the configured name is "Democratic Republic of Congo" and the country is
usually written with a "the". The full name then failed to match and matching
fell through to the substring "Congo", which belongs to the other country.

Both are supported markets, so this was not an unsupported-country fallback -
it was one supported market silently answering for another.
"""

from __future__ import annotations

import pytest

from services.market_config import find_market_mentions


# --- the defect ------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Democratic Republic of the Congo",
        "What is the minimum order in the Democratic Republic of the Congo?",
        "Democratic Republic of Congo",
        "Congo-Kinshasa",
    ],
)
def test_the_democratic_republic_resolves_to_its_own_market(question: str) -> None:
    assert find_market_mentions(question) == {"CD"}


@pytest.mark.parametrize(
    "question",
    ["Republic of Congo", "Congo", "Congo-Brazzaville"],
)
def test_the_republic_of_congo_still_resolves_to_its_own_market(question: str) -> None:
    """The fix must not push the ambiguity the other way."""
    assert find_market_mentions(question) == {"CG"}


# --- overlapping names -----------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Guinea", {"GN"}),
        ("Equatorial Guinea", {"GQ"}),
        ("China", {"CN"}),
        ("Hong Kong SAR China", {"HK"}),
        ("Reunion", {"RE"}),
        ("R\u00e9union", {"RE"}),
        ("La R\u00e9union", {"RE"}),
    ],
)
def test_a_longer_name_wins_over_a_name_inside_it(question: str, expected: set) -> None:
    """141 configured names contain another market's name. Longest wins."""
    assert find_market_mentions(question) == expected


# --- filler words ----------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("the Netherlands", {"NL"}),
        ("the United Kingdom", {"GB"}),
        ("orders in the United States", {"US"}),
    ],
)
def test_an_article_does_not_change_the_market(question: str, expected: set) -> None:
    assert find_market_mentions(question) == expected


# --- multiple countries ----------------------------------------------------


def test_two_markets_in_one_question_are_both_returned() -> None:
    assert find_market_mentions("I sell in Belgium and the Netherlands") == {"BE", "NL"}


def test_a_market_and_its_container_are_not_conflated() -> None:
    """Naming both must return both, not collapse to the shorter."""
    assert find_market_mentions("Guinea and Equatorial Guinea") == {"GN", "GQ"}


# --- nothing to resolve ----------------------------------------------------


@pytest.mark.parametrize(
    "question",
    ["What are the delivery charges?", "", "   ", "How do I sponsor someone?"],
)
def test_a_question_naming_no_market_resolves_to_none(question: str) -> None:
    """A follow-up turn usually names no market; carry-forward is not this
    function's job, and inventing a market here would be worse than none."""
    assert find_market_mentions(question) == set()


def test_an_unconfigured_country_is_not_substituted() -> None:
    """A country the catalogue does not carry must not borrow another's code.

    Narnia is not a market. The requirement is that nothing is returned, rather
    than the nearest-looking configured market.
    """
    assert find_market_mentions("What is the delivery cost in Narnia?") == set()


# --- a known gap, recorded rather than hidden ------------------------------


@pytest.mark.xfail(
    reason=(
        "Catalogue gap: 'DR Congo' and 'DRC' are not configured names for CD, so "
        "matching falls through to the substring 'Congo' and returns CG - the "
        "wrong country. Fixing it means adding approved aliases to "
        "market_name_aliases.json, which is a data decision about which "
        "abbreviations are official, not a code change."
    ),
    strict=True,
)
def test_the_common_abbreviation_resolves_to_the_democratic_republic() -> None:
    assert find_market_mentions("DR Congo") == {"CD"}
