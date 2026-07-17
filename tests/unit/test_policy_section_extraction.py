"""Regression coverage for generic policy-heading formats."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ingestion"
    / "extract_policy_sections.py"
)
SPEC = importlib.util.spec_from_file_location("policy_section_extractor", SCRIPT_PATH)
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


def test_section_match_supports_common_numbering_layouts() -> None:
    text = "\n".join(
        [
            "1 Introduction",
            "1.3. Customer definitions",
            "11.01 General policy",
            "2 3",
        ]
    )

    matches = list(extractor._iter_section_matches(text))

    assert [match.group("section") for match in matches] == ["1", "1.3", "11.01"]


def test_contents_page_heuristic_ignores_dense_numbered_lists() -> None:
    contents = "\n".join(
        [
            "1 Introduction",
            "2 Definitions",
            "3 Preferred Customer",
            "4 Marketing Plan",
            "5 Manager Status",
            "6 Leadership Bonus",
        ]
    )

    assert extractor._looks_like_contents_page(contents) is True


def test_contents_page_heuristic_keeps_policy_page_with_several_sections() -> None:
    policy_page = "\n".join(
        [
            "3 Preferred Customer",
            "3.01 Preferred Customer is solely a consumer of approved products.",
            "Supporting policy text that continues across several lines.",
            "3.02 Preferred Customers purchase products at a discount.",
            "Additional explanatory policy text for this section.",
            "3.03 A Preferred Customer may opt in to the Marketing Plan.",
            "More approved policy information appears here.",
            "3.04 Qualification requirements are described below.",
            "4 Marketing Plan",
            "4.01 Sales volume determines the achieved sales level.",
            "Detailed policy language continues on the page.",
        ]
    )

    assert extractor._looks_like_contents_page(policy_page) is False


def test_top_level_numbered_prose_is_not_a_section_heading() -> None:
    text = "\n".join(
        [
            "18 or older, may enter into an agreement with the company.",
            "50 or 60 case credits are required for the three levels.",
            "18 Legal requirements",
            "21 RESPONSIBILITY, WARRANTY,",
            "18.01 Individual arbitration",
        ]
    )

    matches = list(extractor._iter_section_matches(text))

    assert [match.group("section") for match in matches] == ["18", "21", "18.01"]


def test_duplicate_section_ids_receive_stable_occurrence_suffixes() -> None:
    sections = [
        extractor.PolicySection("policy.pdf", "IT", "it", "1", "Main", 1, 1, "Main"),
        extractor.PolicySection("policy.pdf", "IT", "it", "1", "Annex", 2, 2, "Annex"),
    ]

    unique = extractor._ensure_unique_section_ids(sections)

    assert [section.section_id for section in unique] == ["1", "1-occurrence-2"]


def test_oversized_sections_are_split_into_bounded_parts() -> None:
    content = "1 General\n" + ("Approved policy text.\n" * 1_000)

    sections = extractor._split_oversized_section(
        source_file="policy.pdf",
        country="DE",
        language="de",
        section_id="1",
        title="General",
        content=content,
        content_offset=0,
        page_offsets=[(1, 0, len(content) + 1)],
    )

    assert len(sections) > 1
    assert all(len(section.content) <= extractor.MAX_SECTION_CHARS for section in sections)
    assert sections[0].section_id == "1-part-1"


def test_numeric_table_rows_become_country_agnostic_atomic_facts() -> None:
    parent = extractor.PolicySection(
        source_file="policy.pdf",
        country="NL",
        language="nl",
        section_id="4.01",
        title="Marketingplan",
        start_page=8,
        end_page=8,
        content="4.01 Marketingplan\nAssistant Supervisor 2 CC in twee maanden\nSupervisor 10 CC in één maand\nManager 120 CC in twee maanden",
        document_version="2025-05",
        effective_date="2025-06-15",
    )

    chunks = extractor._expand_structured_chunks([parent])
    facts = [chunk for chunk in chunks if chunk.chunk_type == "numeric_fact"]

    assert len(facts) == 3
    assert any("Supervisor 10 CC" in fact.content for fact in facts)
    assert all(fact.parent_section_id == "4.01" for fact in facts)
    assert all(fact.metadata["status"] == "active" for fact in facts)
