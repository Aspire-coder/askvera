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


class _TextPage:
    """A readable page with no images."""

    def extract_text(self, extraction_mode=None):
        return "This page carries ordinary readable policy text about Case Credits."

    def get(self, key, default=None):
        return default


class _ScannedPage:
    """No extractable text, but an embedded image: a scanned page."""

    def extract_text(self, extraction_mode=None):
        return ""

    def get(self, key, default=None):
        if key == "/Resources":
            return {"/XObject": {"/Im0": {"/Subtype": "/Image"}}}
        return default


class _BlankPage:
    """Neither text nor image: a separator page, which is normal."""

    def extract_text(self, extraction_mode=None):
        return ""

    def get(self, key, default=None):
        if key == "/Resources":
            return {"/Font": {"/F1": {}}}
        return default


def _reader_for(pages):
    class _R:
        def __init__(self, _path: str):
            self.pages = list(pages)

    return _R


def test_one_scanned_page_among_readable_pages_requires_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reported defect: nine readable pages plus one scanned page.

    The previous rule required half the document to be unreadable, so this
    returned requires_ocr=False and the document was published with a page
    silently missing. A scanned fee table or eligibility rule would not exist
    as far as retrieval is concerned, and no amount of ranking work can find a
    passage that was never extracted.
    """
    pages = [_TextPage() for _ in range(9)] + [_ScannedPage()]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    report = analyze_pdf(Path("policy.pdf"))

    assert report.requires_ocr is True
    assert report.scanned_page_numbers == (10,)
    assert report.has_unextracted_pages is True
    assert report.text_coverage_ratio == 0.9


def test_a_blank_separator_page_does_not_require_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank pages are common and routing the document to OCR over one would
    cost money and reject documents that extracted perfectly well."""
    pages = [_TextPage() for _ in range(9)] + [_BlankPage()]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    report = analyze_pdf(Path("policy.pdf"))

    assert report.requires_ocr is False
    assert report.scanned_page_numbers == ()
    assert report.blank_page_numbers == (10,)
    assert report.has_unextracted_pages is False


def test_a_fully_scanned_document_still_requires_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [_ScannedPage() for _ in range(3)]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    report = analyze_pdf(Path("scan.pdf"))

    assert report.requires_ocr is True
    assert report.text_coverage_ratio == 0.0


def test_a_fully_readable_document_requires_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [_TextPage() for _ in range(4)]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    report = analyze_pdf(Path("policy.pdf"))

    assert report.requires_ocr is False
    assert report.text_coverage_ratio == 1.0
    assert report.has_unextracted_pages is False


def test_scanned_pages_are_reported_by_page_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reviewer needs to know which page to go and look at."""
    pages = [_TextPage(), _ScannedPage(), _TextPage(), _BlankPage(), _ScannedPage()]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    report = analyze_pdf(Path("policy.pdf"))

    assert report.scanned_page_numbers == (2, 5)
    assert report.blank_page_numbers == (4,)


def test_a_malformed_resource_tree_does_not_fail_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken PDF must degrade to "no image found", never raise."""

    class _HostilePage:
        def extract_text(self, extraction_mode=None):
            return ""

        def get(self, key, default=None):
            raise RuntimeError("malformed resource tree")

    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for([_HostilePage()]))

    report = analyze_pdf(Path("broken.pdf"))

    # text_pages == 0 still requires OCR, but via the whole-document rule
    # rather than by crashing on the resource lookup.
    assert report.requires_ocr is True
    assert report.scanned_page_numbers == ()


def test_coverage_is_reported_in_the_dict_form(monkeypatch: pytest.MonkeyPatch) -> None:
    """asdict() skips properties, so to_dict must add them explicitly."""
    pages = [_TextPage() for _ in range(9)] + [_ScannedPage()]
    monkeypatch.setattr(document_preflight, "PdfReader", _reader_for(pages))

    payload = analyze_pdf(Path("policy.pdf")).to_dict()

    assert payload["text_coverage_ratio"] == 0.9
    assert payload["has_unextracted_pages"] is True
    assert payload["scanned_page_numbers"] == (10,)


def test_a_page_with_no_content_stream_extracts_as_empty() -> None:
    """pypdf raises KeyError("/Contents") rather than returning empty text.

    Before this was handled, one such page aborted preflight for the whole
    document and surfaced to an admin as an unhandled upload error. An empty
    page is empty, not a failure.
    """

    class _NoContentPage:
        def extract_text(self, extraction_mode=None):
            raise KeyError("/Contents")

    assert extract_pdf_page_text(_NoContentPage()) == ""
    assert extract_pdf_page_text(_NoContentPage(), preserve_layout=True) == ""


def test_a_real_pdf_with_an_image_xobject_is_detected_as_scanned() -> None:
    """Exercises pypdf itself, not a stub.

    The stubs elsewhere in this file implement .get(); this confirms a real
    PageObject does too, so the detection cannot silently no-op in production.
    """
    io = pytest.importorskip("io")
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    page = writer.pages[0]
    image = DecodedStreamObject()
    image.set_data(b"\x00")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page.get("/Resources")[NameObject("/XObject")] = DictionaryObject(
        {NameObject("/Im0"): writer._add_object(image)}
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    real_page = pypdf.PdfReader(buffer).pages[0]
    assert document_preflight._page_has_image(real_page) is True
