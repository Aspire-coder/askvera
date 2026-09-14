"""B2: minimum amount to start as an FBO.

Covers the fail-before scenarios in the implementation brief section "B2." -
the old capture `[^.\\n]+` truncated a decimal value such as "9.440 TND" at
its first period, and the question trigger/label were too narrow to
recognise natural paraphrases or to distinguish first-order, ongoing,
joining-fee and rank-qualification questions from one another.
"""

import pytest

from utils.directory_fields import (
    canonical_requested_order_size,
    restore_missing_requested_order_size,
    correct_directory_source_contradictions,
)


def test_decimal_value_9_440_tnd_is_retained_exactly_not_truncated_at_the_dot() -> None:
    """Fail-before: the old `[^.\\n]+` capture stopped at the first period,
    truncating "9.440 TND" down to "9"."""
    answer = "Here is the ordering information for Tunisia."
    source = "Minimum order size FBO: 9.440 TND."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "How much do I need to start ordering as an FBO in Tunisia?"
    )

    assert changed is True
    # The full decimal value must survive intact - the old bug truncated it
    # to "9" at the first period.
    assert "Minimum order size FBO: 9.440 TND." in corrected
    assert not corrected.rstrip().endswith("FBO: 9.")


def test_cc_only_field_is_not_converted_to_money() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum CC for my first order?"
    )

    assert changed is True
    assert "0.200 CC" in corrected
    assert "USD" not in corrected and "EUR" not in corrected


def test_explicit_approximate_money_equivalent_is_kept() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC (approximately 750 MAD)."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum amount to become an FBO?"
    )

    assert changed is True
    assert "0.200 CC (approximately 750 MAD)" in corrected


def test_bare_dollar_sign_is_not_given_an_invented_currency() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: $100 worth of products."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "minimum order size FBO"
    )

    assert changed is True
    assert "$100 worth of products" in corrected
    assert "USD" not in corrected


def test_no_fee_stated_is_echoed_verbatim_not_reworded_as_free() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: No standing minimum."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum order size for a new FBO?"
    )

    assert changed is True
    assert "No standing minimum" in corrected
    assert "free" not in corrected.lower()


def test_decimal_value_followed_by_another_role_heading_stops_at_the_semicolon() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 9.440 TND; Preferred Customer: no minimum required."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum order size for a new FBO?"
    )

    assert changed is True
    assert "Minimum order size FBO: 9.440 TND." in corrected
    assert "Preferred Customer" not in corrected


def test_first_order_question_restores_first_order_field_not_ongoing() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC. After sponsorship: 25 CC ongoing minimum."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum first order size for a new FBO?"
    )

    assert changed is True
    assert "Minimum order size FBO: 0.200 CC." in corrected
    assert "25 CC ongoing minimum" not in corrected


def test_ongoing_order_question_restores_ongoing_field_not_first_order() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC. After sponsorship: 25 CC ongoing minimum."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the ongoing minimum order size after my first order?"
    )

    assert changed is True
    assert "After sponsorship: 25 CC ongoing minimum." in corrected
    assert "0.200 CC." not in corrected


def test_joining_fee_question_is_not_treated_as_an_order_size_question() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum joining fee to become an FBO?"
    )

    assert changed is False
    assert corrected == answer


def test_rank_qualification_question_is_not_treated_as_an_order_size_question() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum CC needed to qualify for Assistant Supervisor rank?"
    )

    assert changed is False
    assert corrected == answer


def test_preferred_customer_question_never_gets_an_fbo_figure() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum order size for a Preferred Customer?"
    )

    assert changed is False
    assert corrected == answer


def test_prospect_and_fbo_question_still_restores() -> None:
    answer = "I can share the general FBO requirement."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "How much do I need to start ordering as an FBO?"
    )

    assert changed is True
    assert "0.200 CC" in corrected


def test_two_markets_same_question_different_values() -> None:
    tunisia_source = "Minimum order size FBO: 9.440 TND."
    kenya_source = "Minimum order size FBO: 0.500 CC."
    question = "What is the minimum order size for a new FBO?"

    tunisia_corrected, tunisia_changed = restore_missing_requested_order_size(
        "Here is the ordering information.", [tunisia_source], question
    )
    kenya_corrected, kenya_changed = restore_missing_requested_order_size(
        "Here is the ordering information.", [kenya_source], question
    )

    assert tunisia_changed and kenya_changed
    assert "9.440 TND" in tunisia_corrected
    assert "0.500 CC" in kenya_corrected
    assert "9.440 TND" not in kenya_corrected
    assert "0.500 CC" not in tunisia_corrected


def test_mixed_first_order_and_contact_request_still_restores_order_size() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 9.440 TND."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum order size and the phone number for the FBO?"
    )

    assert changed is True
    assert "9.440 TND" in corrected


def test_paraphrase_smallest_order_amount_not_coded_against() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the smallest order amount I can place as a new FBO?"
    )

    assert changed is True
    assert "0.200 CC" in corrected


def test_paraphrase_typo_minumum_order_size() -> None:
    answer = "Here is the ordering information."
    source = "Minimum order size FBO: 0.200 CC."

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "whats the minumum order size for an fbo"
    )

    assert changed is True
    assert "0.200 CC" in corrected


def test_record_prose_runoff_with_no_boundary_is_still_not_appended() -> None:
    """Regression: a record whose minimum-order line runs straight into
    prose with no period/newline before the next real sentence must not be
    appended - the output validator would discard the whole answer."""
    answer = "A new FBO places a first order through the local office."
    source = (
        "Minimum order size FBO: 0,200CC (7 800DZD) and all first orders must be "
        "placed with the sponsoring office named in the"
    )

    corrected, changed = restore_missing_requested_order_size(
        answer, [source], "What is the minimum first order size for a new FBO?"
    )

    assert changed is False
    assert corrected == answer


# --- correct_directory_source_contradictions: DOTALL cross-record risk ----


def test_dotall_removed_prevents_cross_record_currency_pairing() -> None:
    """Fail-before: with re.DOTALL, the non-greedy `.*?` could bridge past an
    unrelated record boundary to the *nearest* "around/approximately CUR"
    phrase anywhere later in the source, pairing one country's CC value with
    a different country's currency equivalent."""
    source = (
        "Kenya sponsoring: minimum order is 0.200 CC.\n"
        "Delivery time is 3 days.\n"
        "Nigeria sponsoring: minimum order is 0.500 CC (approximately 900 NGN)."
    )
    answer = "For Kenya, the minimum order is 0.200 CC (approximately 200 USD)."

    corrected, changed = correct_directory_source_contradictions(answer, [source])

    assert "900 NGN" not in corrected
    assert changed is False
    assert corrected == answer


def test_same_line_correction_still_applies() -> None:
    """The narrower same-line match must not break the case it exists for."""
    source = "Minimum order size FBO: 0.200 CC (around 750 MAD)."
    answer = "The minimum order is 0.200 CC (around 600 MAD)."

    corrected, changed = correct_directory_source_contradictions(answer, [source])

    assert "around 750 MAD" in corrected
    assert "600 MAD" not in corrected
    assert changed is True


@pytest.mark.parametrize("answer", [
    "Individuals in the U.S. are prohibited from opting in as an FBO.",
    "In Italia non e possibile iscriversi come FBO.",
])
def test_fbo_policy_conflict_never_restores_a_historical_order_size(answer: str) -> None:
    source = "Minimum order size FBO: None."

    corrected, restored = restore_missing_requested_order_size(
        answer,
        [source],
        "What's the minimum order to become an FBO?",
        suppress_restore=True,
    )

    assert restored is False
    assert corrected == answer


def test_dedicated_fbo_minimum_order_uses_only_the_explicit_directory_field() -> None:
    source = (
        "Minimum order size FBO: Each order must be a minimum of SGD25.\n"
        "New sign up members need to buy a Starter Kit at the cost of SGD50.\n"
        "Payment methods accepted: Credit card, bank transfer."
    )

    answer = canonical_requested_order_size(source.splitlines(), "What's the minimum order to become an FBO?")

    assert answer == "Minimum order size FBO: Each order must be a minimum of SGD25."


def test_flattened_index_record_uses_its_explicit_fbo_minimum_only() -> None:
    source = (
        "ORDERING PRODUCTS � Minimum order size FBO: Each order must be a minimum of SGD25. "
        "Price list can be downloaded on www.forever.net.sg. � Delivery Cost: SGD12."
    )

    answer = canonical_requested_order_size([source], "What's the minimum order to become an FBO?")

    assert answer == "Minimum order size FBO: Each order must be a minimum of SGD25."


def test_conflicting_fbo_minimums_are_not_turned_into_an_answer() -> None:
    sources = [
        "Minimum order size FBO: Each order must be a minimum of SGD25.",
        "Minimum order size FBO: Each order must be a minimum of SGD50.",
    ]

    assert canonical_requested_order_size(sources, "What's the minimum order to become an FBO?") is None


@pytest.mark.parametrize(
    ("language", "question", "label"),
    [
        ("en", "What's the minimum order to become an FBO?", "Minimum order size FBO"),
        ("nl", "Wat is de minimale bestelling voor een FBO?", "Minimale bestelling voor FBO"),
        ("fr", "Quelle est la commande minimum pour devenir FBO?", "Commande minimum pour FBO"),
        ("de", "Was ist der Mindestbestellwert für einen FBO?", "Mindestbestellwert für FBO"),
        ("es", "Cuál es el pedido mínimo para ser FBO?", "Pedido mínimo para FBO"),
        ("it", "Qual è l'ordine minimo per diventare FBO?", "Ordine minimo per FBO"),
        ("da", "Hvad er minimumsbestilling for en FBO?", "Minimumsbestilling for FBO"),
        ("fi", "Mikä on FBO:n vähimmäistilaus?", "FBO:n vähimmäistilaus"),
        ("no", "Hva er minstebestilling for en FBO?", "Minimumsbestilling for FBO"),
        ("sv", "Vad är minsta beställning för en FBO?", "Minimibeställning för FBO"),
        ("ru", "Какой минимальный заказ для FBO?", "Минимальный заказ для FBO"),
        ("sr", "Koja je minimalna porudžbina za FBO?", "Minimalna porudžbina za FBO"),
    ],
)
def test_canonical_fbo_minimum_order_is_localized_for_every_supported_language(
    language: str,
    question: str,
    label: str,
) -> None:
    answer = canonical_requested_order_size(
        ["Minimum order size FBO: 50 Case Credits."],
        question,
        language=language,
    )

    assert answer == f"{label}: 50 Case Credits."
