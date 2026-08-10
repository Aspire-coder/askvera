"""Document quality checks performed before approved-content ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
import re

from pypdf import PdfReader

TABLE_GAP_RE = re.compile(r"\S\s{2,}\S")


class DocumentPreflightError(ValueError):
    """Raised when a document cannot complete bounded preflight safely."""


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


def analyze_pdf(
    path: Path,
    *,
    max_pages: int | None = None,
    max_extracted_characters: int | None = None,
) -> DocumentPreflight:
    """Summarize extraction quality and whether OCR/table handling is needed."""
    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    if max_pages is not None and page_count > max_pages:
        raise DocumentPreflightError(f"PDF exceeds the {max_pages}-page safety limit.")
    text_pages = 0
    empty_pages = 0
    table_pages = 0
    character_count = 0
    for page in reader.pages:
        plain = extract_pdf_page_text(page)
        layout = extract_pdf_page_text(page, preserve_layout=True)
        visible_chars = len("".join(plain.split()))
        character_count += visible_chars
        if max_extracted_characters is not None and character_count > max_extracted_characters:
            raise DocumentPreflightError("PDF extracted text exceeds the safety limit.")
        if visible_chars >= 40:
            text_pages += 1
        else:
            empty_pages += 1
        if is_table_like_layout(layout):
            table_pages += 1

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


def _analyze_pdf_process(
    path_value: str,
    max_pages: int | None,
    max_extracted_characters: int | None,
    result_queue,
) -> None:
    """Run parsing in an isolated process so a malformed PDF cannot block a worker."""
    try:
        result_queue.put(
            ("ok", analyze_pdf(
                Path(path_value),
                max_pages=max_pages,
                max_extracted_characters=max_extracted_characters,
            )),
        )
    except Exception as exc:  # Child process must return a safe failure to its parent.
        result_queue.put(("error", str(exc)))


def analyze_pdf_with_timeout(
    path: Path,
    *,
    timeout_seconds: int,
    max_pages: int | None = None,
    max_extracted_characters: int | None = None,
) -> DocumentPreflight:
    """Analyze a PDF with hard parser and extraction limits."""
    if timeout_seconds <= 0:
        raise DocumentPreflightError("PDF parser timeout must be greater than zero.")
    context = get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_analyze_pdf_process,
        args=(str(path), max_pages, max_extracted_characters, result_queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        raise DocumentPreflightError("PDF parsing exceeded the safety timeout.")
    try:
        status, payload = result_queue.get(timeout=1)
    except Empty as exc:
        raise DocumentPreflightError("PDF preflight did not return a result.") from exc
    finally:
        result_queue.close()
    if status != "ok":
        raise DocumentPreflightError(f"PDF preflight failed: {payload}")
    return payload
