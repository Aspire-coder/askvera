"""No Comprehend placeholder type reaches the reader.

Live demo run (Mali delivery-cost answer): the output scrub masked part of the
office hours as ``[DATE_TIME]`` and the delivered answer showed
"(Mon-Fri, 8:00 am-12:00 pm and [DATE_TIME])". ``scrub_pii`` writes
``[{entity type}]`` for every type Comprehend detects, but the cleanup only
recognised ADDRESS, EMAIL, PHONE, NAME, PII and the sensitive financial types.
"""

import pytest

from services.pii import remove_unresolved_pii_placeholders


@pytest.mark.parametrize("token", [
    "DATE_TIME", "AGE", "URL", "USERNAME", "PASSWORD", "IP_ADDRESS", "PASSPORT_NUMBER",
    "DRIVER_ID", "CREDIT_DEBIT_CVV", "INTERNATIONAL_BANK_ACCOUNT_NUMBER", "UK_NATIONAL_INSURANCE_NUMBER",
])
def test_every_comprehend_placeholder_type_is_removed(token):
    cleaned = remove_unresolved_pii_placeholders(f"The office replies within one day [{token}].")

    assert f"[{token}]" not in cleaned
    assert "The office replies within one day" in cleaned


def test_mali_hours_placeholder_leaves_no_dangling_conjunction():
    answer = ("You can contact the Mali office at +223 44 90 05 41 (Mon-Fri, 8:00 am-12:00 pm and [DATE_TIME]) "
              "or email contact@foreversenegal.com.")

    cleaned = remove_unresolved_pii_placeholders(answer)

    assert "[DATE_TIME]" not in cleaned
    assert "and)" not in cleaned
    assert "(Mon-Fri, 8:00 am-12:00 pm)" in cleaned
    assert "+223 44 90 05 41" in cleaned and "contact@foreversenegal.com" in cleaned


def test_ordinary_bracketed_text_and_markdown_links_are_untouched():
    answer = "See [Section 4.02] and [the policy](https://example.com). Ages [18+] apply."

    assert remove_unresolved_pii_placeholders(answer) == answer


def test_existing_placeholder_types_still_removed():
    cleaned = remove_unresolved_pii_placeholders("Call [PHONE] or write to [EMAIL].\nBank: [BANK_ACCOUNT]")

    assert "[PHONE]" not in cleaned and "[EMAIL]" not in cleaned and "[BANK_ACCOUNT]" not in cleaned
