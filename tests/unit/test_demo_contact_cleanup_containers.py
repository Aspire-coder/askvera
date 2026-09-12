"""Output cleanup must not leave an empty contact container behind.

Tracker row 27 (Burkina Faso office address, screenshot image8): the answer
ended "You can reach them at:" followed by a bullet reading "- **". Replayed
through the real cleanup chain, a contact line carrying only a sensitive
placeholder loses the token inline and keeps its markdown ("- **** - **"), and
removing whole placeholder lines leaves the lead-in introducing nothing.

Only containers emptied by this cleanup are removed. Real addresses, surviving
contact lines and lead-ins that still introduce content are untouched.
"""

from app.response.quality import remove_or_replace_contact_placeholders
from services.pii import remove_unresolved_pii_placeholders

ADDRESS = "The Forever Living office address for Burkina Faso is:\n\n**Dapoya, Secteur 3, Dimdolodomb – 01 BP 5070 Ouaga 01, Burkina Faso**"
LEAD_IN = "You can reach them at:"


def _clean(answer: str, country: str = "BF") -> str:
    # Same order and conditions as ChatOrchestrator._secure_and_complete_response:
    # the contact step's text is only adopted when it reports a change.
    contact_safe, changes = remove_or_replace_contact_placeholders(answer, country)
    return remove_unresolved_pii_placeholders(contact_safe if changes else answer)


def _has_markup_only_line(text: str) -> bool:
    return any(line.strip() and not any(ch.isalnum() for ch in line) for line in text.splitlines())


def test_sensitive_placeholder_bullet_leaves_no_markup_only_line():
    cleaned = _clean(f"{ADDRESS}\n\n{LEAD_IN}\n- **[BANK_ACCOUNT]** - **")

    assert not _has_markup_only_line(cleaned), cleaned
    assert LEAD_IN not in cleaned
    assert "Dapoya, Secteur 3, Dimdolodomb – 01 BP 5070 Ouaga 01" in cleaned


def test_lead_in_is_dropped_when_every_contact_line_under_it_was_removed():
    cleaned = _clean(f"{ADDRESS}\n\n{LEAD_IN}\n- **Phone:** [PHONE]\n- **Email:** [EMAIL]")

    assert LEAD_IN not in cleaned
    assert cleaned.endswith("Burkina Faso**")


def test_lead_in_is_dropped_but_following_paragraph_is_kept():
    hours = "Business hours are 08.30 am – 16.30 pm Monday to Friday."
    cleaned = _clean(f"{ADDRESS}\n\n{LEAD_IN}\n- [PHONE]\n\n{hours}")

    assert LEAD_IN not in cleaned
    assert hours in cleaned


def test_lead_in_is_kept_when_a_contact_line_survives():
    cleaned = _clean(f"{ADDRESS}\n\n{LEAD_IN}\n- **Phone:** [PHONE]\n- **Office phone:** +226 25 30 00 00")

    assert LEAD_IN in cleaned
    assert "+226 25 30 00 00" in cleaned
    assert "[PHONE]" not in cleaned


def test_lead_in_is_kept_when_a_placeholder_resolves_to_a_reviewed_contact():
    cleaned = _clean(f"{ADDRESS}\n\n{LEAD_IN}\n- Website: [URL]", country="NL")

    assert LEAD_IN in cleaned
    assert "[URL]" not in cleaned


def test_nothing_changes_when_no_placeholder_was_removed():
    answer = f"{ADDRESS}\n\nSteps to follow:"

    assert _clean(answer) == answer


def test_real_bold_markup_and_dashes_survive():
    answer = f"{ADDRESS}\n\n{LEAD_IN}\n- **Phone:** +226 25 30 00 00 – **Fax:** +226 25 30 00 01"

    assert _clean(answer) == answer


def test_personal_placeholders_still_never_survive():
    cleaned = _clean("Call me on [PHONE] or write to [EMAIL].\n- **[NAME]**")

    assert "[PHONE]" not in cleaned and "[EMAIL]" not in cleaned and "[NAME]" not in cleaned
    assert not _has_markup_only_line(cleaned)
