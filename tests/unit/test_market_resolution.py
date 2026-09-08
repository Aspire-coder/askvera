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


# --- the abbreviation, contained rather than merely recorded ---------------
#
# Two separate decisions. Recognising "DR Congo" as CD is catalogue data -
# which abbreviations are official is not mine to decide. Not answering as CG
# is a safety property, and that is code.


@pytest.mark.parametrize("question", ["DR Congo", "dr congo", "orders in DR Congo"])
def test_an_unrecognised_qualifier_does_not_route_to_the_other_congo(question: str) -> None:
    """The substitution, closed.

    "Congo" also sits inside "Democratic Republic of Congo", so it is only safe
    on its own. With an unrecognised word in front of it the mention is
    ambiguous, and returning nothing lets the caller ask which country is
    meant. Answering as CG was the wrong country's policy.
    """
    assert find_market_mentions(question) == set()


def test_an_unknown_abbreviation_resolves_to_nothing_rather_than_a_neighbour() -> None:
    """DRC fails differently from "DR Congo": it contains no country name at
    all, so it never matched anything. Recorded because the two look like one
    defect and are not."""
    assert find_market_mentions("DRC") == set()


def test_a_neutral_word_before_a_shared_name_still_resolves() -> None:
    """The guard must not swallow ordinary sentences."""
    for question in ("delivery in Congo", "orders for Congo", "Congo delivery cost"):
        assert find_market_mentions(question) == {"CG"}, question


@pytest.mark.xfail(
    reason=(
        "Catalogue gap, now contained rather than dangerous: 'DR Congo' returns "
        "nothing instead of the wrong country. Recognising it as CD means adding "
        "approved aliases to market_name_aliases.json - a decision about which "
        "abbreviations are official, not a code change."
    ),
    strict=True,
)
def test_the_common_abbreviation_resolves_to_the_democratic_republic() -> None:
    assert find_market_mentions("DR Congo") == {"CD"}


# --- the guard's own cost ---------------------------------------------------


def test_the_name_index_is_built_once() -> None:
    """The shared-stem calculation compares every configured name against every
    other - 3,216 names, about ten million comparisons. Measured at 913ms when
    it ran per call, on a function every request uses. It is cached; this fails
    if someone removes that."""
    import time

    from services.market_config import _market_name_index

    find_market_mentions("warm the cache")
    started = time.perf_counter()
    for _ in range(50):
        find_market_mentions("What is the delivery cost in Belgium?")
    per_call_ms = (time.perf_counter() - started) / 50 * 1000

    assert per_call_ms < 25, f"{per_call_ms:.1f}ms per call suggests the index is rebuilt"
    assert _market_name_index.cache_info().maxsize == 1


def test_every_overlapping_pair_resolves_both_ways() -> None:
    """Generated from the catalogue rather than hand-picked.

    Guinea and Equatorial Guinea passing establishes two cases. This checks
    every configured name that sits inside a different market's name: the
    longer name alone must give the longer market, and both named together must
    give both.
    """
    from services.market_config import _market_name_index

    names, _, _ = _market_name_index()
    pairs = [
        (short, long)
        for short in names
        for long in names
        if short != long
        and f" {short} " in f" {long} "
        and names[short] != names[long]
        and len(names[short]) == 1
        and len(names[long]) == 1
    ]

    assert len(pairs) > 100, "the catalogue should still contain overlapping names"
    for short, long in pairs:
        assert find_market_mentions(long) == set(names[long]), long
        assert find_market_mentions(f"{short} and {long}") == set(names[short]) | set(
            names[long]
        ), (short, long)
