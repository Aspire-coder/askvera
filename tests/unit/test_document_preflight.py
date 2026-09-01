"""Tests for language-neutral document ingestion preflight checks."""

from pathlib import Path

import pytest

from services import document_preflight
from services.document_preflight import (
    DocumentPreflightError,
    analyze_pdf,
    extract_pdf_page_text,
    is_table_like_layout,
)


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


class _Reader:
    def __init__(self, _path: str):
        self.pages = [_Page(), _Page()]


def test_preflight_rejects_pdf_over_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_preflight, "PdfReader", _Reader)

    with pytest.raises(DocumentPreflightError, match="page safety limit"):
        analyze_pdf(Path("policy.pdf"), max_pages=1)


def test_preflight_rejects_pdf_over_text_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_preflight, "PdfReader", _Reader)

    with pytest.raises(DocumentPreflightError, match="text exceeds"):
        analyze_pdf(Path("policy.pdf"), max_extracted_characters=10)


class _CleanPage:
    def extract_text(self, extraction_mode=None):
        return "This is ordinary policy text with no decoding problems."


class _GarbledPage:
    def extract_text(self, extraction_mode=None):
        return "The policy was ge�mplementeerd to protect FBOs."


class _CleanReader:
    def __init__(self, _path: str):
        self.pages = [_CleanPage(), _CleanPage()]


class _GarbledReader:
    def __init__(self, _path: str):
        self.pages = [_CleanPage(), _GarbledPage()]


def test_preflight_does_not_flag_cleanly_decoded_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_preflight, "PdfReader", _CleanReader)

    report = analyze_pdf(Path("policy.pdf"))

    assert report.garbled_character_count == 0
    assert report.encoding_corruption_detected is False


def test_preflight_flags_a_pdf_with_an_undecodable_font_glyph(monkeypatch: pytest.MonkeyPatch) -> None:
    """A source PDF whose embedded font cannot map a glyph to a real character
    (commonly an accented letter) leaves a Unicode replacement character behind.
    No extraction library can recover the original character - this can only be
    detected and flagged for a corrected source document, not silently fixed."""
    monkeypatch.setattr(document_preflight, "PdfReader", _GarbledReader)

    report = analyze_pdf(Path("policy.pdf"))

    assert report.garbled_character_count == 1
    assert report.encoding_corruption_detected is True
