"""Tests for country-independent approved-document ingestion."""

from pathlib import Path

import pytest

from services.knowledge_ingestion import (
    MAX_CHUNK_CHARS,
    ExtractedPage,
    build_sections,
    extract_pages,
    safe_filename,
    validate_upload,
)


def test_safe_filename_removes_paths_and_unsafe_characters() -> None:
    assert safe_filename("../../Benelux product facts (final).PDF") == "Benelux-product-facts-final.pdf"


def test_validate_upload_rejects_unknown_type_and_empty_file() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload("payload.exe", 20)
    with pytest.raises(ValueError, match="empty"):
        validate_upload("guide.pdf", 0)


def test_plain_text_extraction_and_generic_section_chunking(tmp_path: Path) -> None:
    source = tmp_path / "product.md"
    source.write_text("PRODUCT BENEFITS\nAloe Vera Gel supports everyday wellness.\n\nUSAGE\nTake 30 ml daily.", encoding="utf-8")

    sections = build_sections(
        extract_pages(source),
        filename=source.name,
        country="BE",
        language="en",
        document_type="product_information",
        version="2026.1",
    )

    assert len(sections) == 2
    assert sections[0]["title"] == "PRODUCT BENEFITS"
    assert sections[0]["metadata"]["document_type"] == "product_information"
    assert sections[1]["content"] == "Take 30 ml daily."


def test_long_sections_have_bounded_overlapping_chunks() -> None:
    content = "PRODUCT DETAILS\n" + "Useful product information. " * 500
    sections = build_sections(
        [ExtractedPage(3, content)],
        filename="facts.txt",
        country="GLOBAL",
        language="en",
        document_type="product_information",
    )

    assert len(sections) > 1
    assert all(len(section["content"]) <= MAX_CHUNK_CHARS for section in sections)
    assert all(section["start_page"] == 3 for section in sections)
