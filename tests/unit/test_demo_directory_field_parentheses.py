"""Regression tests: unrequested directory labels inside a parenthetical aside.

``remove_unrequested_directory_fields``'s generic pattern removes from an
unrequested "Label:" to the end of its line. That is correct when the label
starts its own line, but when the label instead sits inside a parenthetical
aside within a sentence - "...at +223 44 90 05 41 (Business Hours: 08:00 am
- 12:00 pm)." - cutting to end-of-line drops the sentence's closing text and
leaves an unmatched "(" behind. The output validator's
``incomplete_ending_reason`` then flags that as a CRITICAL incomplete answer
and the user gets a fallback instead of the correct answer.

Live case: "What is the delivery cost in Mali?" (requested field
delivery_cost) with a complete model answer ending in a Business-Hours aside
after the phone number. Before the fix this function truncated the answer to
end on an unmatched "(" (see MALI_RAW / test_removes_unrequested_hours_...).
"""

import time

import pytest

from app.response.quality import incomplete_ending_reason
from utils.directory_fields import remove_unrequested_directory_fields


MALI_RAW = (
    "# Delivery Cost in Mali\n\n"
    "According to Forever Living's Mali office, delivery costs are structured by location:\n\n"
    "- **2,000 francs CFA** until the highway (Maristes)\n"
    "- **3,000 francs CFA** from Maristes to Thiaroye\n"
    "- **4,000 francs CFA** around Petit Mbao, Keur Mbaye Fall, and Keur Massar\n\n"
    "The average lead time for orders to arrive is within a day.\n\n"
    "If you'd like to place an order or confirm delivery to your specific location, "
    "you can contact the Mali office at **+223 44 90 05 41** "
    "(Business Hours: 08:00 am – 12:00 pm and 1:00 pm – 4:00 pm, Monday–Friday)."
)


def test_removes_unrequested_hours_parenthetical_without_truncating_the_sentence() -> None:
    cleaned, changed = remove_unrequested_directory_fields(MALI_RAW, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned.count("(") == cleaned.count(")")
    assert "2,000 francs CFA" in cleaned
    assert "3,000 francs CFA" in cleaned
    assert "Maristes" in cleaned
    assert "+223 44 90 05 41" in cleaned
    assert "Business Hours" not in cleaned
    assert "4:00 pm" not in cleaned
    assert cleaned.endswith("**.")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_output_validator_reports_unclosed_paren_on_the_unfixed_head_behaviour() -> None:
    # Reproduces the bug directly: the pre-fix line-wide removal cut from the
    # unrequested "Business Hours:" label to end-of-line, which - because the
    # label sat inside a parenthetical aside - left the sentence ending on the
    # aside's now-unmatched "(". This is the exact truncated text the live
    # capture showed reaching the output validator before this fix.
    truncated = MALI_RAW[: MALI_RAW.rindex("(Business Hours")] + "("
    reason = incomplete_ending_reason(truncated, "en")
    assert reason is not None
    assert reason.startswith("unclosed_paren")


def test_removes_fax_parenthetical_inside_phone_sentence() -> None:
    answer = "Telephone Office: +254 20 123 (Fax: +254 20 999)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the office phone in Kenya?")

    assert changed is True
    assert cleaned == "Telephone Office: +254 20 123."
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_removes_nested_parens_inside_the_removed_parenthetical() -> None:
    answer = "Contact the office (see Business Hours: 08:00 am (Mon-Fri) - 12:00 pm)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned == "Contact the office."
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_unclosed_open_paren_drops_tail_and_reterminates_sentence() -> None:
    answer = "Contact the office (Business Hours: 08:00 am - 12:00 pm"

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned == "Contact the office."
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_parenthetical_without_a_label_is_left_untouched() -> None:
    answer = "Contact us (Maristes) for help."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the office phone in Kenya?")

    assert changed is False
    assert cleaned == answer


def test_requested_hours_keeps_the_parenthetical() -> None:
    answer = "Call **+223 44 90 05 41** (Business Hours: 08:00 am - 12:00 pm, Monday-Friday)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What are the business hours in Mali?")

    assert changed is False
    assert cleaned == answer
    assert "Business Hours" in cleaned


def test_line_start_business_hours_label_still_removed_as_before() -> None:
    answer = (
        "Delivery cost: 2.000 francs CFA (Maristes).\n"
        "Business Hours: 08.00 am - 12.00 pm\n"
        "Email: contact@x.com"
    )

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned == "Delivery cost: 2.000 francs CFA (Maristes)."


def test_keep_labels_still_protects_a_parenthetical_label() -> None:
    answer = "Call **+223 44 90 05 41** (Business Hours: 08:00 am - 12:00 pm)."

    # `changed` may report True even when a protected label leaves the text
    # untouched (a pre-existing quirk of the underlying regex substitution
    # unrelated to this fix); what matters here is that the content itself,
    # including the parenthetical, survives intact.
    cleaned, _changed = remove_unrequested_directory_fields(
        answer, "What is the delivery cost in Mali?", keep_labels=["Business Hours"]
    )

    assert cleaned == answer


def test_prose_without_labels_is_untouched() -> None:
    answer = "Delivery usually arrives within a day, and returns are free of charge."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is False
    assert cleaned == answer


def test_time_of_day_is_not_mistaken_for_a_label() -> None:
    answer = "Contact office at 08:00 for info."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the office phone in Kenya?")

    assert changed is False
    assert cleaned == answer


# --- Fable's follow-up review: the whole-parenthetical removal above can
# also delete requested content that follows the unrequested label inside
# the same "(...)" - see C1/C2/C3 below. Only the unrequested label's own
# segment must go, not the rest of the aside.


def test_requested_phone_after_unrequested_hours_in_same_parens_survives() -> None:
    # C1: "Business Hours" is unrequested, but the phone number that follows
    # it inside the same parenthetical, separated by ";", was asked for and
    # must not be deleted along with it.
    answer = "Contact the office (Business Hours: 8-12; the phone number is +254 20 123)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the office phone in Kenya?")

    assert changed is True
    assert "+254 20 123" in cleaned
    assert "Business Hours" not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    assert cleaned.count("**") % 2 == 0
    assert incomplete_ending_reason(cleaned, "en") is None


def test_requested_email_label_after_unrequested_hours_in_same_parens_survives() -> None:
    # C1 variant: the requested field is itself a labelled "Label: value"
    # segment, not free prose, sharing the parenthetical with an unrequested
    # one.
    answer = "Contact the office (Business Hours: 08:00-12:00; Email: contact@x.com)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the email address in Kenya?")

    assert changed is True
    assert "Email: contact@x.com" in cleaned
    assert "Business Hours" not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_legit_prose_after_unrequested_hours_in_same_parens_survives() -> None:
    # C1 variant: what follows the unrequested label is ordinary prose, not
    # another field - it must survive exactly as before.
    answer = (
        "Call +223 44 (Business Hours: 8-12; deliveries within a day; "
        "2,000 CFA to Maristes)."
    )

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert "deliveries within a day" in cleaned
    assert "2,000 CFA to Maristes" in cleaned
    assert "Business Hours" not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_unclosed_paren_far_into_the_line_keeps_the_text_before_it() -> None:
    # C2: the unmatched "(" opens long before the unrequested labels; the
    # text between "(" and the first label must survive, not just the text
    # before the "(" itself.
    answer = (
        "Prices (CFA apply. Business Hours: 08:00 am - 12:00 pm. "
        "Phone: +223 44 90 05 41"
    )

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert "Prices" in cleaned
    assert "CFA apply" in cleaned
    assert "Business Hours" not in cleaned
    assert "+223 44 90 05 41" not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_multiline_parenthetical_leaves_no_stray_closing_paren() -> None:
    # C3: the parenthetical aside itself wraps onto a second physical line;
    # removing it must not leave an orphan ")" on the continuation line.
    answer = "Contact the office (Business Hours: 08:00 am\n- 12:00 pm, Monday-Friday)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned == "Contact the office."
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_bold_marker_split_by_removed_parenthetical_stays_balanced() -> None:
    # C3 variant: the removed clause carries away one half of a "**...**"
    # bold pair whose other half sits just outside the aside.
    answer = "**Call +223 44 (Business Hours: 8-12**)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned.count("**") % 2 == 0
    assert cleaned.count("(") == cleaned.count(")")
    assert "Business Hours" not in cleaned
    assert incomplete_ending_reason(cleaned, "en") is None


def test_only_unrequested_segment_in_parens_removed_leaving_other_segments() -> None:
    answer = "Call +223 44 (Phone: +223 00 11 22; Business Hours: 8-12)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What are the business hours in Mali?")

    assert changed is True
    assert "Business Hours: 8-12" in cleaned
    assert "Phone" not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


def test_all_segments_unrequested_removes_the_whole_parenthetical() -> None:
    answer = "Call +223 44 (Business Hours: 8-12; Phone: +223 00 11 22)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost in Mali?")

    assert changed is True
    assert cleaned == "Call +223 44."
    assert cleaned.count("(") == cleaned.count(")")
    assert incomplete_ending_reason(cleaned, "en") is None


# --- Fable's W9b review (F1-F4). F1: the scan stopped at the first
# unrequested label in a paragraph when that label was at line start or
# protected, so a later parenthetical label fell back to the line-wide cut
# and the live "ends on '('" defect returned. F2: the outermost unclosed "("
# was used, so a stray "(" on an earlier line swallowed the real aside. F3:
# any "." + space split a clause, so fragments of an unrequested value
# ("9-1", "12", "0722 123 456") survived. F4: the bold compensation was
# always prepended, producing "****".

PHONE_Q = "What is the office phone in Kenya?"
COST_Q = "What is the delivery cost in Mali?"

# (id, answer, question, keep_labels, expected, must_keep, must_drop, balanced)
# ``balanced`` is False only where the input itself carries a stray "(" that
# lies outside any aside and must be left alone.
W9C_CASES = [
    (
        "F1 line-start unrequested label then parenthetical label",
        "Fax: +254 20 999\nCall +254 20 123 (Business Hours: 8-12).",
        PHONE_Q, (), "Call +254 20 123.", ("+254 20 123",), ("999", "Business Hours", "8-12"), True,
    ),
    (
        "F1 protected label then parenthetical label",
        "Business Hours: 8-12\nCall +223 44 (Fax: 123).",
        COST_Q, ("Business Hours",), "Business Hours: 8-12\nCall +223 44.",
        ("Business Hours: 8-12", "+223 44"), ("Fax", "123"), True,
    ),
    (
        "F1 protected and unrequested label in the same parenthetical",
        "Call (Business Hours: 8-12; Fax: 1).",
        COST_Q, ("Business Hours",), "Call (Business Hours: 8-12).",
        ("Business Hours: 8-12",), ("Fax", ": 1"), True,
    ),
    (
        "F2 unclosed paren on an earlier line",
        "Prices (see below apply to Bamako.\nCall +223 44 (Business Hours: 8-12).",
        COST_Q, (), "Prices (see below apply to Bamako.\nCall +223 44.",
        ("Prices (see below apply to Bamako.", "Call +223 44"), ("Business Hours", "8-12"), False,
    ),
    (
        "F2 emoticon on an earlier line",
        "Sorry :( we are closed.\nCall +223 44 (Business Hours: 8-12).",
        COST_Q, (), "Sorry :( we are closed.\nCall +223 44.",
        ("Sorry :( we are closed.", "Call +223 44"), ("Business Hours", "8-12"), False,
    ),
    (
        "F2 emoticon on an earlier line, aside itself unclosed",
        "Sorry :( we are closed.\nCall +223 44 (Business Hours: 8-12",
        COST_Q, (), "Sorry :( we are closed.\nCall +223 44.",
        ("Sorry :( we are closed.", "Call +223 44"), ("Business Hours", "8-12"), False,
    ),
    (
        "F2 unclosed aside ends at its own line",
        "- Call (Business Hours: 8-12\n- Free returns",
        COST_Q, (), "- Call.\n- Free returns", ("- Free returns",), ("Business Hours", "8-12"), True,
    ),
    (
        "F3 a.m./p.m. hours",
        "Call +223 44 (Business Hours: 9 a.m. – 5 p.m., Mon–Fri).",
        COST_Q, (), "Call +223 44.", ("+223 44",), ("p.m", "Mon", "5"), True,
    ),
    (
        "F3 Sat. abbreviation",
        "Call +223 44 (Business Hours: 8-12, Sat. 9-1).",
        COST_Q, (), "Call +223 44.", ("+223 44",), ("Sat", "9-1"), True,
    ),
    (
        "F3 second sentence continues the hours",
        "Call +223 44 (Business Hours: 8-12. Saturday 9-1).",
        COST_Q, (), "Call +223 44.", ("+223 44",), ("Saturday", "9-1"), True,
    ),
    (
        "F3 fax extension",
        "Call +254 20 123 (Fax: +254 20 999 ext. 12).",
        PHONE_Q, (), "Call +254 20 123.", ("+254 20 123",), ("999", "ext", "12)"), True,
    ),
    (
        "F3 fax then Mob. number",
        "Call +254 20 123 (Fax: +254 20 999 / Mob. 0722 123 456).",
        PHONE_Q, (), "Call +254 20 123.", ("+254 20 123",), ("999", "Mob", "0722", "456"), True,
    ),
    (
        "F3 unlabelled mobile number after hours",
        "Contact (Business Hours: 8-12. Mobile 0722 123 456).",
        COST_Q, (), "Contact.", ("Contact",), ("Mobile", "0722", "8-12"), True,
    ),
    (
        "F4 bold opens in kept clause and closes in dropped clause",
        "Call (**the phone is +254 20 123; Business Hours: 8-12**).",
        PHONE_Q, (), "Call (**the phone is +254 20 123**).",
        ("+254 20 123",), ("****", "Business Hours", "8-12"), True,
    ),
    (
        "F4 bold opens in dropped clause and closes in kept clause",
        "Call (Business Hours: **8-12; the phone** is +254 20 123).",
        PHONE_Q, (), "Call (**the phone** is +254 20 123).",
        ("the phone", "+254 20 123"), ("****", "Business Hours", "8-12"), True,
    ),
    (
        "F2 same-line emoticon keeps its own text",
        "Call :( (Business Hours: 8-12\nNext line.",
        COST_Q, (), "Call :(.\nNext line.", ("Call :(", "Next line."), ("Business Hours", "8-12"), False,
    ),
]


@pytest.mark.parametrize(
    "answer, question, keep_labels, expected, must_keep, must_drop, balanced",
    [pytest.param(*case[1:], id=case[0]) for case in W9C_CASES],
)
def test_w9c_review_cases_remove_only_the_unrequested_clause(
    answer, question, keep_labels, expected, must_keep, must_drop, balanced
) -> None:
    cleaned, changed = remove_unrequested_directory_fields(answer, question, keep_labels=keep_labels)

    assert changed is True
    assert cleaned == expected
    for kept in must_keep:
        assert kept in cleaned
    for dropped in must_drop:
        assert dropped not in cleaned
    assert cleaned.count("**") % 2 == 0
    if balanced:
        assert cleaned.count("(") == cleaned.count(")")
        assert incomplete_ending_reason(cleaned, "en") is None


def test_f1_exact_line_start_fax_then_parenthetical_hours_phone_question() -> None:
    # Exact probe_w9b.py J2 input: W9b stopped at the line-start "Fax:" and
    # returned "Call +254 20 123 (" (unclosed_paren).
    answer = "Fax: +254 20 999\nCall +254 20 123 (Business Hours: 8-12)."

    cleaned, changed = remove_unrequested_directory_fields(answer, "What is the office phone in Kenya?")

    assert changed is True
    assert cleaned == "Call +254 20 123."
    assert incomplete_ending_reason(cleaned, "en") is None


def test_f1_exact_protected_hours_line_then_parenthetical_fax_cost_question() -> None:
    # Exact probe_w9b.py J2 keep_labels input: W9b stopped at the protected
    # "Business Hours:" line and returned "Business Hours: 8-12\nCall +223 44 (".
    answer = "Business Hours: 8-12\nCall +223 44 (Fax: 123)."

    cleaned, changed = remove_unrequested_directory_fields(
        answer, "What is the delivery cost in Mali?", keep_labels=["Business Hours"]
    )

    assert changed is True
    assert cleaned == "Business Hours: 8-12\nCall +223 44."
    assert incomplete_ending_reason(cleaned, "en") is None


def test_f1_exact_protected_and_unrequested_label_in_same_parenthetical() -> None:
    # Exact probe_w9b.py J4 input: W9b left "Fax: 1" in place because the
    # first label in the paragraph was protected.
    answer = "Call (Business Hours: 8-12; Fax: 1)."

    cleaned, _changed = remove_unrequested_directory_fields(
        answer, "What is the delivery cost in Mali?", keep_labels=["Business Hours"]
    )

    assert cleaned == "Call (Business Hours: 8-12)."
    assert "Fax" not in cleaned
    assert incomplete_ending_reason(cleaned, "en") is None


def test_w9c_requested_phone_clause_still_kept_next_to_unrequested_hours() -> None:
    answer = "Contact the office (Business Hours: 8-12; the phone number is +254 20 123)."

    cleaned, changed = remove_unrequested_directory_fields(answer, PHONE_Q)

    assert changed is True
    assert cleaned == "Contact the office (the phone number is +254 20 123)."
    assert incomplete_ending_reason(cleaned, "en") is None


def test_w9c_new_prose_after_a_full_stop_is_still_its_own_clause() -> None:
    answer = "Call +223 44 (Business Hours: 8-12. Orders over 50,000 CFA ship free)."

    cleaned, _changed = remove_unrequested_directory_fields(answer, COST_Q)

    assert cleaned == "Call +223 44 (Orders over 50,000 CFA ship free)."


def test_w9c_label_after_short_abbreviation_still_splits() -> None:
    answer = "Call (Business Hours: 8-12 am. Phone: +254 20 123)."

    cleaned, _changed = remove_unrequested_directory_fields(answer, PHONE_Q)

    assert cleaned == "Call (Phone: +254 20 123)."


# --- Fable's W9c review. N1: a "Label: value" line inside a multi-line aside
# was not its own clause, so one unrequested label dragged the requested line
# with it and the whole answer came back empty. N2: any 1-3 letter word before
# "." counted as an abbreviation, so a new capitalised sentence after "pm." was
# swallowed with the unrequested hours.


def test_w9d_label_line_inside_multiline_aside_is_its_own_clause() -> None:
    answer = "Business Hours: 8-12 (Mon-Fri\nFax: 999\nPhone: +254 20 123)"

    cleaned, changed = remove_unrequested_directory_fields(answer, PHONE_Q)

    assert changed is True
    assert cleaned == "Phone: +254 20 123)"
    assert "999" not in cleaned and "Business Hours" not in cleaned


@pytest.mark.parametrize(
    ("answer", "question", "expected"),
    [
        pytest.param(
            "Call (Business Hours: 9 am - 5 pm. Delivery is 2,000 CFA)", COST_Q,
            "Call (Delivery is 2,000 CFA)", id="pm then capitalised prose",
        ),
        pytest.param(
            "Call (Business Hours: 9 a.m. - 5 p.m. Delivery is 2,000 CFA)", COST_Q,
            "Call (Delivery is 2,000 CFA)", id="p.m. then capitalised prose",
        ),
        pytest.param(
            "Call (Business Hours: 8-12 every day. The phone number is +254 20 123)", PHONE_Q,
            "Call (The phone number is +254 20 123)", id="short word then requested phone sentence",
        ),
    ],
)
def test_w9d_new_sentence_after_meridiem_or_short_word_is_kept(answer, question, expected) -> None:
    cleaned, changed = remove_unrequested_directory_fields(answer, question)

    assert changed is True
    assert cleaned == expected
    assert "Business Hours" not in cleaned
    assert incomplete_ending_reason(cleaned, "en") is None


def test_w9d_capitalised_weekday_abbreviation_still_continues_the_hours() -> None:
    answer = "Call +223 44 (Business Hours: 8-12, Tues. 9-1)."

    cleaned, _changed = remove_unrequested_directory_fields(answer, COST_Q)

    assert cleaned == "Call +223 44."


def test_w9c_live_mali_case_exact_result() -> None:
    cleaned, changed = remove_unrequested_directory_fields(MALI_RAW, COST_Q)

    assert changed is True
    assert cleaned.endswith("you can contact the Mali office at **+223 44 90 05 41**.")
    assert cleaned == MALI_RAW[: MALI_RAW.rindex(" (Business Hours")] + "."
    assert incomplete_ending_reason(cleaned, "en") is None


W9C_PERF_INPUTS = [
    ("many asides", ("Call +223 44 (Business Hours: 8-12; " + "deliveries within a day, " * 40 + "ok). ") * 60),
    ("unclosed at end", "x " * 25000 + "(Business Hours: 8-12"),
    ("20k nested unclosed", "(" * 20000 + "Business Hours: 8-12" + " word." * 5000),
    ("3000 nested fax", "(Fax: 1; " * 3000 + ")" * 3000),
    ("kept nested chain", "(a; Fax: 1; " * 3000 + ")" * 3000),
    ("unclosed per word", "(Fax: 1 " * 6000),
    ("many sibling asides", "Call (Fax: 1) " * 4000),
    ("dotted aside", "(Business Hours: " + "a. " * 16000 + ")"),
]


@pytest.mark.parametrize("text", [pytest.param(text, id=name) for name, text in W9C_PERF_INPUTS])
def test_w9c_large_inputs_finish_quickly(text) -> None:
    started = time.perf_counter()
    cleaned, _changed = remove_unrequested_directory_fields(text, COST_Q)
    elapsed = time.perf_counter() - started

    assert len(text) >= 30000
    assert elapsed < 2.0
    assert "Business Hours" not in cleaned
    assert "Fax" not in cleaned
