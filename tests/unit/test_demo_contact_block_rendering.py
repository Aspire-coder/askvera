"""Contact-block lines must render as separate rows in the widget, not collapse.

Found while reviewing Fable's W21 residual note: the widget's markdown
renderer (widget-wrapper/src/renderers/MarkdownRenderer.tsx, ``parseBlocks``)
only starts a new visual paragraph at a *blank* line or a recognised block
marker (heading, bullet, ordered item, table, quote, code fence, rule). Two
plain "Label: value" lines joined by a single "\\n" - what
``build_support_contact_supplement`` and ``restore_missing_directory_contacts``
both produced before this fix - fall into ``paragraph.push(line)`` on both
lines and are flushed together as one paragraph joined by ``" "``:

    "Office & Product Center Address: ... Telephone Office: ... Email: ..."

instead of three separate rows. A bullet line ("- Label: value") is matched
by the renderer's bullet regex *before* it ever reaches the plain-paragraph
branch, so each bulleted line always becomes its own list item regardless of
blank-line separation. This file locks in that every appended block with two
or more fields uses that bullet form; a single field is left as plain text,
since one line has nothing to collapse into.

Offline only: no widget build, no browser, no deployment. The renderer rule
above is read directly from MarkdownRenderer.tsx, not executed here.
"""

from __future__ import annotations

import re

import pytest

from utils.directory_fields import (
    build_support_contact_supplement,
    restore_missing_directory_contacts,
)

_KENYA_FIELDS = {
    "Office & Product Center Address": "Kenya Reinsurance Plaza, 4th floor Taifa Rd. CBD",
    "Telephone Office": "+254 20 2026869 / +254 20 2026873",
    "Email": "info@foreverea.com",
    "Website": "www.foreverliving.com",
}


def _would_collapse(block: str) -> bool:
    """Port of the one property of MarkdownRenderer.parseBlocks that matters here.

    Two consecutive lines collapse into one paragraph (joined by a space)
    unless the second is blank or itself matches the bullet marker the
    renderer checks before falling into ``paragraph.push(line)``.
    """
    lines = [line for line in block.split("\n")]
    for previous, current in zip(lines, lines[1:]):
        if not previous.strip() or not current.strip():
            continue
        if re.match(r"^[-*]\s+", current.strip()):
            continue
        return True
    return False


def test_two_fields_do_not_collapse_in_the_widget_renderer() -> None:
    block, _ = build_support_contact_supplement(
        "Some answer.", {"Telephone Office": "+254 712 434 328", "Email": "info@forever-kenya.example"}, True
    )
    assert not _would_collapse(block)
    assert block.split("\n") == [
        "- Telephone Office: +254 712 434 328",
        "- Email: info@forever-kenya.example",
    ]


def test_single_field_is_plain_text_no_bullet() -> None:
    block, _ = build_support_contact_supplement("Some answer.", {"Telephone Office": "+254 712 434 328"}, True)
    assert block == "Telephone Office: +254 712 434 328"
    assert not block.startswith("- ")


def test_three_fields_all_bulleted_and_none_collapse() -> None:
    block, labels = build_support_contact_supplement(
        "Some answer.",
        {
            "Telephone Office": "+254 20 2026869",
            "Email": "info@foreverea.com",
            "Business Hours Office": "09:00 - 17:00 (Mon - Fri)",
        },
        True,
        hours_requested=True,
    )
    assert not _would_collapse(block)
    assert len(labels) == 3
    for line in block.split("\n"):
        assert line.startswith("- ")


@pytest.mark.parametrize("language", ["en", "fr", "de", "es"])
def test_localized_multi_field_block_still_bulleted(language: str) -> None:
    block, _ = build_support_contact_supplement(
        "Some answer.",
        {"Telephone Office": "+254 20 2026869", "Email": "info@foreverea.com"},
        True,
        language=language,
    )
    assert not _would_collapse(block)
    assert all(line.startswith("- ") for line in block.split("\n"))


def test_restore_missing_directory_contacts_multi_field_append_is_bulleted() -> None:
    """Three fields (address, phone, website) are missing and appended together.

    Same live shape as demo-fixes-check-04-fr-kenya-uganda-followup turn1,
    in English: only the email was already stated, so address, office phone
    and website are all appended in one pass.
    """
    answer = "You can reach the Kenya office at: Email: info@foreverea.com"
    corrected, restored = restore_missing_directory_contacts(answer, [_KENYA_FIELDS], "contact info")
    assert len(restored) >= 2
    appended = corrected[len(answer):].strip()
    assert not _would_collapse(appended)
    for line in appended.split("\n"):
        if line.strip():
            assert line.startswith("- ")


def test_restore_missing_directory_contacts_single_field_append_is_plain() -> None:
    """Only Email is missing here; whatever else this pass corrects in place,
    the appended tail must be the single plain "Email: ..." line, not a
    bulleted list of one."""
    answer = (
        "Office & Product Center Address: Kenya Reinsurance Plaza, 4th floor Taifa Rd. CBD\n"
        "Website: www.foreverliving.com\n"
        "Telephone Office: +254 20 2026869 / +254 20 2026873"
    )
    corrected, restored = restore_missing_directory_contacts(answer, [_KENYA_FIELDS], "email")
    assert "Email" in restored
    appended = corrected[len(answer):].strip()
    assert appended == "Email: info@foreverea.com"
    assert not appended.startswith("- ")
