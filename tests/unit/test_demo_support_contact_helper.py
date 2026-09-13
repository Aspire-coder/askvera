"""B3: helpful customer-care details without losing the answer.

Pure-helper tests only, per the worker B scope: no orchestrator wiring, no
lookups, no invented values. `build_support_contact_supplement` echoes
already-approved fields; `remove_unrequested_directory_fields`'s
`keep_labels` keyword protects an explicitly approved supplement from being
deleted again by cleanup.
"""

from utils.directory_fields import (
    build_support_contact_supplement,
    remove_unrequested_directory_fields,
)


def test_care_recommending_answer_gets_a_contact_block() -> None:
    fields = {
        "Country": "Kenya",
        "Telephone Office": "+254 712 434 328",
        "Email": "info@forever-kenya.example",
    }

    result = build_support_contact_supplement("Some answer.", fields, True)

    assert result is not None
    block, labels = result
    assert "Telephone Office: +254 712 434 328" in block
    assert "Email: info@forever-kenya.example" in block
    assert set(labels) == {"Telephone Office", "Email"}


def test_no_approved_contact_returns_none() -> None:
    fields = {"Country": "Kenya"}

    assert build_support_contact_supplement("Some answer.", fields, True) is None


def test_answer_without_care_recommendation_adds_nothing() -> None:
    fields = {"Telephone Office": "+254 712 434 328"}

    assert build_support_contact_supplement("Some answer.", fields, False) is None


def test_at_most_one_phone_and_order_phone_is_never_chosen() -> None:
    fields = {
        "Telephone Office": "+254 712 434 328",
        "Telephone for Orders": "+254 700 000 000",
    }

    block, labels = build_support_contact_supplement("Some answer.", fields, True)

    assert "Telephone Office: +254 712 434 328" in block
    assert "+254 700 000 000" not in block
    assert labels == ["Telephone Office"]


def test_at_most_one_email_or_website() -> None:
    fields = {
        "Email": "info@forever-kenya.example",
        "Website": "www.forever-kenya.example",
    }

    block, labels = build_support_contact_supplement("Some answer.", fields, True)

    assert len(labels) == 1


def test_hours_only_included_when_requested() -> None:
    fields = {
        "Telephone Office": "+254 712 434 328",
        "Business Hours Office": "09:00 - 17:00 (Mon - Fri)",
    }

    without_hours = build_support_contact_supplement("Some answer.", fields, True)
    with_hours = build_support_contact_supplement(
        "Some answer.", fields, True, hours_requested=True
    )

    assert "Business Hours Office" not in without_hours[0]
    assert "Business Hours Office: 09:00 - 17:00 (Mon - Fri)" in with_hours[0]


def test_international_prefix_preserved_verbatim() -> None:
    fields = {"Telephone Office": "+44 20 7946 0958"}

    block, _labels = build_support_contact_supplement("Some answer.", fields, True)

    assert "+44 20 7946 0958" in block


def test_cleanup_keeps_an_approved_supplement_while_removing_other_unrequested_fields() -> None:
    """The supplement must not be deleted again by the same cleanup pass that
    strips unrequested fields from the rest of the answer."""
    answer = (
        "The main answer text.\n\n"
        "Telephone Office: +254 712 434 328\n"
        "Business Hours Office: 09:00 - 17:00 (Mon - Fri)\n"
    )

    focused, changed = remove_unrequested_directory_fields(
        answer,
        "What is the delivery cost?",
        keep_labels=["Telephone Office"],
    )

    assert "Telephone Office: +254 712 434 328" in focused
    assert "Business Hours Office" not in focused
    assert changed is True


def test_cleanup_without_keep_labels_removes_the_supplement_like_any_other_field() -> None:
    """Regression: keep_labels must be opt-in, not a silent default."""
    answer = "The main answer text.\n\nTelephone Office: +254 712 434 328\n"

    focused, changed = remove_unrequested_directory_fields(answer, "What is the delivery cost?")

    assert "Telephone Office" not in focused
    assert changed is True
