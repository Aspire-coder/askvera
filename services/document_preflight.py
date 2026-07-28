"""Document quality checks performed before approved-content ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from pypdf import PdfReader

TABLE_GAP_RE = re.compile(r"\S\s{2,}\S")


@dataclass(frozen=True)
class DocumentPreflight:
    page_count: int
    text_page_count: int
    empty_page_count: int
    table_like_page_count: int
    extracted_character_count: int
    requires_ocr: bool
    table_aware_extraction_recommended: bool

    def to_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def extract_pdf_page_text(page, *, preserve_layout: bool = False) -> str:
    """Extract one page, falling back when the installed parser lacks layout mode."""
    if preserve_layout:
        try:
            return page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            pass
    return page.extract_text() or ""


def is_table_like_layout(text: str) -> bool:
    """Identify pages with repeated aligned columns without language-specific words."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    aligned_rows = sum(bool(TABLE_GAP_RE.search(line)) for line in lines)
    return aligned_rows >= 3 and aligned_rows / max(1, len(lines)) >= 0.12


def analyze_pdf(path: Path) -> DocumentPreflight:
    """Summarize extraction quality and whether OCR/table handling is needed."""
    reader = PdfReader(str(path))
    text_pages = 0
    empty_pages = 0
    table_pages = 0
    character_count = 0
    for page in reader.pages:
        plain = extract_pdf_page_text(page)
        layout = extract_pdf_page_text(page, preserve_layout=True)
        visible_chars = len("".join(plain.split()))
        character_count += visible_chars
        if visible_chars >= 40:
            text_pages += 1
        else:
            empty_pages += 1
        if is_table_like_layout(layout):
            table_pages += 1

    page_count = len(reader.pages)
    requires_ocr = page_count > 0 and (
        text_pages == 0 or empty_pages / page_count >= 0.5
    )
    return DocumentPreflight(
        page_count=page_count,
        text_page_count=text_pages,
        empty_page_count=empty_pages,
        table_like_page_count=table_pages,
        extracted_character_count=character_count,
        requires_ocr=requires_ocr,
        table_aware_extraction_recommended=table_pages > 0,
    )
