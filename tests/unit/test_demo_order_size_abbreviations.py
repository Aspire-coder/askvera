"""Minimum-order restoration keeps abbreviations inside the field value.

Found by the L9 journey replay: the Netherlands record states "Minimum order size
FBO: €50,00 in products excl. VAT and excl. literature." and the restored value
stopped at "excl.", dropping the VAT and literature conditions.
"""

from utils.directory_fields import restore_missing_requested_order_size

QUESTION = "What is the minimum order size for an FBO?"


def _restored(source: str) -> str:
    answer, _restored_flag = restore_missing_requested_order_size("Orders are placed online.", [source], QUESTION)
    return answer


def test_excl_abbreviation_keeps_the_vat_and_literature_conditions():
    source = "• Minimum order size FBO: €50,00 in products excl. VAT and excl. literature.\n• Delivery Cost: €5,00."

    assert "€50,00 in products excl. VAT and excl. literature" in _restored(source)
    assert "Delivery Cost" not in _restored(source)


def test_incl_and_approx_abbreviations_are_kept():
    source = "Minimum order size FBO: 2 CC incl. literature, approx. 150 EUR.\nPayment methods accepted: Cash."

    restored = _restored(source)
    assert "2 CC incl. literature, approx. 150 EUR" in restored
    assert "Cash" not in restored


def test_a_period_ending_the_line_after_an_amount_still_stops():
    restored = _restored("• Minimum order size FBO: €81.\n• Delivery Cost: N/A.")

    assert "€81" in restored
    assert "N/A" not in restored


def test_a_real_sentence_end_is_not_mistaken_for_an_abbreviation():
    source = "Minimum order size FBO: $100 worth of products when joining. Price list can be downloaded online."

    restored = _restored(source)
    assert "$100 worth of products when joining" in restored
    assert "Price list" not in restored


def test_abbreviation_at_the_end_of_the_line_does_not_run_into_the_next_record_line():
    restored = _restored("Minimum order size FBO: 50 EUR excl.\nForever Belgium\nMinimum order size FBO: 60 EUR.")

    assert "60 EUR" not in restored
