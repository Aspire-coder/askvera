"""Clock times must not steal subsequent clauses from their governing section."""

from pathlib import Path

import pytest

from scripts.ingestion.extract_policy_sections import (
    _clean_page_text,
    _iter_section_matches,
    extract_sections,
)


@pytest.mark.parametrize("time", ["23.59", "09.30", "0.00"])
@pytest.mark.parametrize("unit", ["hours", "hrs", "Uhr", "uur", "heures", "ore", "horas", "timmar"])
def test_clock_times_are_not_headings(time, unit):
    text = f"{time} {unit} on the last day of the month"
    assert list(_iter_section_matches(text)) == []
    assert _clean_page_text(f"Orders received by {text}") == f"Orders received by {text}"


@pytest.mark.parametrize("section", ["1.3", "13.01", "21.05.3", "23.59"])
def test_real_numbered_sections_remain_headings(section):
    assert [m.group("section") for m in _iter_section_matches(f"{section} Ordering requirements")] == [section]


@pytest.mark.parametrize("inline", [False, True])
def test_ordering_clauses_keep_governing_parent(inline):
    separator = " " if inline else "\n"
    text = _clean_page_text(
        "13.01 Ordering requirements\n"
        "b) Orders must arrive by" + separator + "23.59 hours on the last calendar day.\n"
        "d) Missing items must be reported within 14 days of receipt.\n"
        "f) The minimum order for FBOs is EUR 50 excluding taxes.\n"
        "14.01 Sponsor changes\n"
        "Separate sponsor-change requirements apply to this section."
    )
    sections = extract_sections(
        Path("not-read.pdf"), country="BE", language="en", extracted_pages=[(29, text)]
    )
    assert not any(s.section_id.startswith("23.59") for s in sections)
    for phrase in ["14 days of receipt", "EUR 50"]:
        owners = [s for s in sections if phrase in s.content and s.chunk_type in {"section", "list_item"}]
        assert owners
        assert all(s.section_id == "13.01" or s.parent_section_id == "13.01" for s in owners)
        assert all(s.start_page == 29 for s in owners)


def test_verified_benelux_ordering_excerpt():
    # Indexed English split page 29, supplied multilingual PDF page 134.
    text = _clean_page_text("""13. ORDERING PROCEDURES
13.01  a) Preferred Customers and FBO’s order directly from the Company at Discounted prices.
 b) All orders with appropriate payment must be submitted to Forever Living Products Benelux by
23.59 hours on the last calendar day of the applicable month to qualify for a bonus generated for
that month.
 d) Any discrepancy in condition or quantities must be reported to our Support Team no later than 14
days after the order has been received.
 f) The minimum order for FBO’s and FPC’s is € 50,00, not including taxes. For order amounts of
less than 2 CC Shipping and Handling costs will be charged.
14. RESPONSORING POLICIES
14.01  a) An existing FBO can responsor under a different Sponsor provided that, during the preceding
12 months, he/she has:
 1) Been an FBO, and
 2) Not purchased any Forever products, and
 3) Not sponsored any other individuals into the Forever business.
""")
    sections = extract_sections(
        Path("Benelux-Policy.pdf"), country="BE", language="en", extracted_pages=[(29, text)]
    )
    by_id = {s.section_id: s for s in sections}
    assert not any(key.startswith("23.59") for key in by_id)
    assert "14\ndays after the order has been received" in by_id["13.01-d"].content
    assert "€ 50,00, not including taxes" in by_id["13.01-f"].content
    assert by_id["13.01-f"].parent_section_id == "13.01"
