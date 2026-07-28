"""Tests for language-neutral document ingestion preflight checks."""

from services.document_preflight import extract_pdf_page_text, is_table_like_layout


class _Page:
    def extract_text(self, extraction_mode=None):
        if extraction_mode == "layout":
            return "Name        Phone\nOffice      123\nEmail       test@example.com"
        return "Name Phone Office 123 Email test@example.com"


class _LegacyPage:
    def extract_text(self, **kwargs):
        if kwargs:
            raise TypeError("layout mode unsupported")
        return "plain text"


def test_table_like_layout_detects_repeated_aligned_rows() -> None:
    assert is_table_like_layout(
        "Name        Phone\nOffice      123\nEmail       test@example.com"
    )
    assert not is_table_like_layout("This is an ordinary paragraph with normal spacing.")


def test_layout_extraction_uses_parser_layout_mode() -> None:
    assert "Name        Phone" in extract_pdf_page_text(_Page(), preserve_layout=True)


def test_layout_extraction_falls_back_for_legacy_parser() -> None:
    assert extract_pdf_page_text(_LegacyPage(), preserve_layout=True) == "plain text"
