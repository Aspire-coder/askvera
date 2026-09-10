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
    garbled_character_count: int = 0
    encoding_corruption_detected: bool = False
    # Page numbers (1-based) carrying an image but no extractable text. These
    # are scanned pages inside an otherwise readable document.
    scanned_page_numbers: tuple[int, ...] = ()
    # Page numbers with neither text nor an image: genuinely blank separators,
    # which are normal and do not warrant OCR.
    blank_page_numbers: tuple[int, ...] = ()
    # Page numbers with no text whose image content could not be established,
    # because the resource tree could not be read or nests beyond the depth
    # cap. Deliberately not folded into blank_page_numbers: "we found nothing"
    # and "we could not look" support opposite decisions, and only one of them
    # is safe to publish unread.
    undetermined_page_numbers: tuple[int, ...] = ()
    # Page numbers carrying an image and only a little text: a readable heading
    # above a body this parser could not read. Reported rather than treated as
    # scanned, because a page with an image is not by itself evidence of
    # missing content - policy pages carry letterheads - and forcing OCR on
    # every one of them would hold documents that are entirely fine.
    low_text_image_page_numbers: tuple[int, ...] = ()

    @property
    def text_coverage_ratio(self) -> float:
        """Share of pages that yielded extractable text."""
        if self.page_count <= 0:
            return 0.0
        return round(self.text_page_count / self.page_count, 4)

    @property
    def has_unextracted_pages(self) -> bool:
        """True when a page may hold content this parser could not read.

        Undetermined pages count. Treating them as readable asserts the one
        thing preflight failed to establish.
        """
        return bool(self.scanned_page_numbers) or bool(self.undetermined_page_numbers)

    def to_dict(self) -> dict[str, object]:
        # The derived values are included explicitly because asdict() skips
        # properties, and coverage is the number a reviewer actually wants.
        return {
            **asdict(self),
            "text_coverage_ratio": self.text_coverage_ratio,
            "has_unextracted_pages": self.has_unextracted_pages,
        }


def extract_pdf_page_text(page, *, preserve_layout: bool = False) -> str:
    """Extract one page, falling back when the installed parser lacks layout mode.

    A page carrying no content stream raises KeyError("/Contents") rather than
    returning empty text. That is an empty page, not a failure, and it must not
    abort preflight for the entire document - which is what happened before,
    surfacing to an admin as an unhandled upload error with no explanation.
    """
    if preserve_layout:
        try:
            return page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            pass  # Parser lacks layout mode; fall through to plain extraction.
        except KeyError:
            return ""
    try:
        return page.extract_text() or ""
    except KeyError:
        return ""


def is_table_like_layout(text: str) -> bool:
    """Identify pages with repeated aligned columns without language-specific words."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    aligned_rows = sum(bool(TABLE_GAP_RE.search(line)) for line in lines)
    return aligned_rows >= 3 and aligned_rows / max(1, len(lines)) >= 0.12


# How much of a page's image content this parser was able to establish.
# "unknown" is not "none": a resource tree that cannot be read says nothing
# about whether the page holds a scan, and treating silence as absence is what
# lets an unreadable page be filed as blank.
_IMAGE_PRESENT = "image"
_IMAGE_ABSENT = "none"
_IMAGE_UNKNOWN = "unknown"

# Form XObjects can nest. The depth cap stops a malformed or hostile PDF whose
# forms refer to each other from looping; real documents nest a few levels.
_MAX_XOBJECT_DEPTH = 6


def _resolve(value):
    """Follow a PDF indirect reference to the object it points at."""
    return value.get_object() if hasattr(value, "get_object") else value


def _page_image_state(page) -> str:
    """Report whether a page embeds an image, or that it could not be told.

    Resources are inspected rather than pypdf's `page.images`, which decodes
    pixel data and is far too slow to run over every page of every upload.

    Images are looked for inside Form XObjects too. A scan placed in a form -
    which is how plenty of tools emit a scanned page - has no image XObject
    directly on the page, so a top-level-only check reports the page as
    imageless and the caller then records a page it cannot read as blank.
    """
    try:
        resources = _resolve(page.get("/Resources"))
        if resources is None:
            return _IMAGE_ABSENT
        return _xobject_image_state(_resolve(resources.get("/XObject")), 0)
    except Exception:  # noqa: BLE001 - a malformed resource tree must not fail preflight.
        # Previously this returned False, so a page whose resources could not
        # be parsed was indistinguishable from one with no image, and a
        # scanned page that failed to parse was published as a blank
        # separator with its content silently missing from the corpus.
        return _IMAGE_UNKNOWN


def _xobject_image_state(xobjects, depth: int) -> str:
    """Walk an XObject dictionary, descending into nested forms."""
    if xobjects is None:
        return _IMAGE_ABSENT
    if depth >= _MAX_XOBJECT_DEPTH:
        return _IMAGE_UNKNOWN
    state = _IMAGE_ABSENT
    for key in xobjects:
        entry = _resolve(xobjects[key])
        subtype = entry.get("/Subtype")
        if subtype == "/Image":
            return _IMAGE_PRESENT
        if subtype == "/Form":
            nested = _resolve(_resolve(entry.get("/Resources")) or {})
            nested_state = _xobject_image_state(
                _resolve(nested.get("/XObject")) if hasattr(nested, "get") else None,
                depth + 1,
            )
            if nested_state == _IMAGE_PRESENT:
                return _IMAGE_PRESENT
            if nested_state == _IMAGE_UNKNOWN:
                state = _IMAGE_UNKNOWN
    return state


# A full page of policy text runs to thousands of characters. A page holding
# only a heading sits far below that, so text between the 40-character "has any
# text" bar and this one, alongside an image, is the shape of a readable header
# over an unreadable body.
LOW_TEXT_PAGE_CHARACTERS = 250


def _page_has_image(page) -> bool:
    """True when a page embeds an image, directly or inside a form."""
    return _page_image_state(page) == _IMAGE_PRESENT


def _garbled_character_count(text: str) -> int:
    """Count Unicode replacement characters left by an undecodable PDF glyph.

    This happens when a PDF's embedded font has a broken or missing
    character mapping for a specific glyph (commonly an accented letter).
    The original character is permanently lost at the PDF level - no
    extraction library can recover it, since none of them ever received the
    correct code point. This can only be caught and flagged, not fixed.
    """
    return text.count("�")


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
    garbled_count = 0
    scanned_pages: list[int] = []
    blank_pages: list[int] = []
    undetermined_pages: list[int] = []
    low_text_image_pages: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        plain = extract_pdf_page_text(page)
        layout = extract_pdf_page_text(page, preserve_layout=True)
        visible_chars = len("".join(plain.split()))
        character_count += visible_chars
        garbled_count += _garbled_character_count(plain)
        if max_extracted_characters is not None and character_count > max_extracted_characters:
            raise DocumentPreflightError("PDF extracted text exceeds the safety limit.")
        if visible_chars >= 40:
            text_pages += 1
            # A page is only checked for images when it has almost no text, so
            # a readable heading above a scanned table counted as fully
            # extracted and nothing recorded that its body was never read.
            # This does not decide anything; it makes the case visible.
            if visible_chars < LOW_TEXT_PAGE_CHARACTERS and _page_image_state(page) == _IMAGE_PRESENT:
                low_text_image_pages.append(number)
        else:
            empty_pages += 1
            # Separating scanned pages from blank ones is the whole point. A
            # page with an image and no text is content this parser cannot
            # see; a page with neither is a separator and needs nothing.
            # A page whose image content could not be established is recorded
            # as unreadable rather than blank. Calling it blank asserts there
            # is nothing to recover, which is the one thing that was not
            # determined, and it would leave the page out of the corpus with
            # no trace.
            state = _page_image_state(page)
            if state == _IMAGE_PRESENT:
                scanned_pages.append(number)
            elif state == _IMAGE_UNKNOWN:
                undetermined_pages.append(number)
            else:
                blank_pages.append(number)
        if is_table_like_layout(layout):
            table_pages += 1

    # A single scanned page is enough. The previous rule required half the
    # document to be unreadable, so nine readable pages plus one scanned page
    # reported requires_ocr=False and the document was published with a page
    # silently missing -- a scanned fee table or eligibility rule would simply
    # not exist as far as retrieval was concerned. Retrieval cannot rank a
    # passage that was never extracted.
    # An undetermined page counts towards OCR for the same reason it is not
    # called blank: it may hold content nobody can currently read.
    requires_ocr = page_count > 0 and (
        text_pages == 0 or bool(scanned_pages) or bool(undetermined_pages)
    )
    return DocumentPreflight(
        page_count=page_count,
        text_page_count=text_pages,
        empty_page_count=empty_pages,
        table_like_page_count=table_pages,
        extracted_character_count=character_count,
        requires_ocr=requires_ocr,
        table_aware_extraction_recommended=table_pages > 0,
        garbled_character_count=garbled_count,
        encoding_corruption_detected=garbled_count > 0,
        scanned_page_numbers=tuple(scanned_pages),
        blank_page_numbers=tuple(blank_pages),
        undetermined_page_numbers=tuple(undetermined_pages),
        low_text_image_page_numbers=tuple(low_text_image_pages),
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
