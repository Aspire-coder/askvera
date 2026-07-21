"""Extract section-sized chunks from policy PDFs.

This script is intentionally offline. It prepares cleaner source chunks that
can be reviewed before they are uploaded into a knowledge base.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


# Policies commonly use a mix of top-level headings ("1 Introduction"),
# one-digit subsections ("1.3."), and two-digit subsections ("11.01").
# Require a letter in the title so PDF page-number pairs are not headings.
SECTION_RE = re.compile(
    r"(?m)^(?P<section>\d{1,2}(?:\.\d{1,2})?)\.?\s+"
    r"(?P<title>(?:\([a-z0-9]+\)\s+)?[^\W\d_].+)$",
    flags=re.IGNORECASE,
)
INLINE_SUBSECTION_RE = re.compile(
    r"(?<!^)(?<=\s)(?=\d{1,2}\.\d{2}\.?\s+(?:\([a-z0-9]+\)\s+)?[^\W\d_])",
    flags=re.IGNORECASE,
)
INLINE_TOP_LEVEL_RE = re.compile(
    r"(?<!^)(?<=\s)(?=(?P<section>\d{1,2})\.\s+(?P<title>[^\W\d_]))"
)
LIST_ITEM_RE = re.compile(
    r"(?m)^(?P<label>\([a-z0-9]+\)|[a-z][.)])\s+(?P<title>.+)$",
    flags=re.IGNORECASE,
)
DEFINITION_ENTRY_RE = re.compile(
    r"(?m)^(?P<label>[^\n:]{2,100}?)\s*:\s+(?P<body>[^\n].*)$"
)
HEADER_RE = re.compile(r"Company Policies and the Code of Professional Conduct Revised \d+")
PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")
WHITESPACE_RE = re.compile(r"[ \t]+")
SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
MAX_SECTION_CHARS = 8_000
TEXT_REPLACEMENTS = {
    "â€™": "'",
    "â€œ": '"',
    "â€�": '"',
    "â€“": "-",
    "â€”": "-",
}


@dataclass(frozen=True)
class PolicySection:
    source_file: str
    country: str
    language: str
    section_id: str
    title: str
    start_page: int
    end_page: int
    content: str
    document_version: str = ""
    effective_date: str = ""
    status: str = "active"
    chunk_type: str = "section"
    parent_section_id: str = ""

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "source_file": self.source_file,
            "country": self.country,
            "country_code": self.country,
            "language": self.language,
            "section_id": self.section_id,
            "section_title": self.title,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "document_version": self.document_version,
            "effective_date": self.effective_date,
            "status": self.status,
            "document_type": "policy",
            "access_scope": "country",
            "chunk_type": self.chunk_type,
            "parent_section_id": self.parent_section_id,
        }


def _clean_page_text(text: str) -> str:
    text = HEADER_RE.sub("", text)
    for bad, good in TEXT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    lines = []
    for raw_line in text.splitlines():
        line = WHITESPACE_RE.sub(" ", raw_line).strip()
        if not line or PAGE_NUMBER_RE.match(line):
            continue
        lines.extend(_split_inline_section_headings(line))
    return "\n".join(lines)


def _split_inline_section_headings(line: str) -> list[str]:
    """Restore heading boundaries lost by PDF text extraction."""
    split_offsets = {match.start() for match in INLINE_SUBSECTION_RE.finditer(line)}
    split_offsets.update(
        match.start()
        for match in INLINE_TOP_LEVEL_RE.finditer(line)
        if match.group("title").isupper()
    )
    if not split_offsets:
        return [line]

    offsets = [0, *sorted(split_offsets), len(line)]
    return [
        line[offsets[index] : offsets[index + 1]].strip()
        for index in range(len(offsets) - 1)
        if line[offsets[index] : offsets[index + 1]].strip()
    ]


def _read_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Read and clean every text-bearing PDF page."""
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = _clean_page_text(page.extract_text() or "")
        if text:
            pages.append((index, text))
    return pages


def _read_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Read policy-body pages while keeping outlines out of section parsing."""
    return [
        (page_number, text)
        for page_number, text in _read_pdf_pages(pdf_path)
        if not _looks_like_contents_page(text)
    ]


def _looks_like_contents_page(text: str) -> bool:
    """Detect a dense numbered list without depending on its language."""
    lines = [line for line in text.splitlines() if line.strip()]
    heading_lines = sum(bool(SECTION_RE.match(line)) for line in lines)
    dotted_entries = sum(bool(re.search(r"\.{3,}\s*\d+\s*$", line)) for line in lines)
    heading_ratio = heading_lines / max(1, len(lines))
    average_line_chars = sum(len(line) for line in lines) / max(1, len(lines))
    return heading_lines >= 6 and (
        dotted_entries >= 3
        or (heading_ratio >= 0.75 and average_line_chars <= 160)
    )


def _looks_like_section_heading(match: re.Match[str]) -> bool:
    """Reject numbered prose while preserving language-neutral headings."""
    section_id = match.group("section")
    title = match.group("title").strip()
    if "." in section_id:
        return True

    letters = [character for character in title if character.isalpha()]
    uppercase_ratio = (
        sum(character.isupper() for character in letters) / len(letters)
        if letters
        else 0.0
    )
    title_is_uppercase = uppercase_ratio >= 0.75
    if len(title) > 100 and not title_is_uppercase:
        return False
    if title.endswith((".", ",", ";", ":")) and not title_is_uppercase:
        return False
    return True


def _iter_section_matches(page_text: str) -> Iterable[re.Match[str]]:
    for match in SECTION_RE.finditer(page_text):
        if _looks_like_section_heading(match):
            yield match


def extract_sections(
    pdf_path: Path,
    *,
    country: str,
    language: str,
    min_chars: int = 40,
    document_version: str = "",
    effective_date: str = "",
    status: str = "active",
) -> list[PolicySection]:
    all_pages = _read_pdf_pages(pdf_path)
    pages = [
        (page_number, text)
        for page_number, text in all_pages
        if not _looks_like_contents_page(text)
    ]
    full_text_parts: list[str] = []
    page_offsets: list[tuple[int, int, int]] = []
    cursor = 0

    for page_number, text in pages:
        start = cursor
        full_text_parts.append(text)
        cursor += len(text)
        end = cursor
        page_offsets.append((page_number, start, end))
        full_text_parts.append("\n")
        cursor += 1

    full_text = "".join(full_text_parts)
    matches = list(_iter_section_matches(full_text))
    sections: list[PolicySection] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        body = re.sub(r"\n{3,}", "\n\n", body)

        if len(body) < min_chars:
            continue

        start_page = _page_for_offset(page_offsets, start)
        end_page = _page_for_offset(page_offsets, max(start, end - 1))
        title = _normalize_title(match.group("title"))

        sections.extend(
            _split_oversized_section(
                source_file=pdf_path.name,
                country=country,
                language=language,
                section_id=match.group("section"),
                title=title,
                content=body,
                content_offset=start,
                page_offsets=page_offsets,
                document_version=document_version,
                effective_date=effective_date,
                status=status,
            )
        )

    outlines = _outline_chunks(
        all_pages,
        source_file=pdf_path.name,
        country=country,
        language=language,
        document_version=document_version,
        effective_date=effective_date,
        status=status,
    )
    front_matter = _front_matter_chunks(
        all_pages,
        source_file=pdf_path.name,
        country=country,
        language=language,
        document_version=document_version,
        effective_date=effective_date,
        status=status,
    )
    return _ensure_unique_section_ids([*front_matter, *outlines, *_expand_structured_chunks(sections)])


def _front_matter_chunks(
    pages: list[tuple[int, str]],
    *,
    source_file: str,
    country: str,
    language: str,
    document_version: str,
    effective_date: str,
    status: str,
) -> list[PolicySection]:
    """Preserve cover-page metadata independently from a long contents page."""
    if not pages:
        return []
    page_number, text = pages[0]
    content = text[: min(len(text), 1800)].strip()
    if not content:
        return []
    return [
        PolicySection(
            source_file=source_file,
            country=country,
            language=language,
            section_id=f"front-matter-page-{page_number}",
            title="Policy document front matter",
            start_page=page_number,
            end_page=page_number,
            content=content,
            document_version=document_version,
            effective_date=effective_date,
            status=status,
            chunk_type="document_front_matter",
        )
    ]


def _outline_chunks(
    pages: list[tuple[int, str]],
    *,
    source_file: str,
    country: str,
    language: str,
    document_version: str,
    effective_date: str,
    status: str,
) -> list[PolicySection]:
    """Preserve table-of-contents pages for section-location questions."""
    return [
        PolicySection(
            source_file=source_file,
            country=country,
            language=language,
            section_id=f"outline-page-{page_number}",
            title="Policy document outline",
            start_page=page_number,
            end_page=page_number,
            content=text,
            document_version=document_version,
            effective_date=effective_date,
            status=status,
            chunk_type="document_outline",
        )
        for page_number, text in pages
        if _looks_like_contents_page(text)
    ]


def _ensure_unique_section_ids(sections: list[PolicySection]) -> list[PolicySection]:
    """Keep identifiers stable and unique when numbering restarts in annexes."""
    occurrences: dict[str, int] = {}
    unique: list[PolicySection] = []
    for section in sections:
        occurrence = occurrences.get(section.section_id, 0) + 1
        occurrences[section.section_id] = occurrence
        if occurrence == 1:
            unique.append(section)
            continue
        unique.append(
            replace(
                section,
                section_id=f"{section.section_id}-occurrence-{occurrence}",
            )
        )
    return unique


def _page_for_offset(page_offsets: list[tuple[int, int, int]], offset: int) -> int:
    for page_number, start, end in page_offsets:
        if start <= offset <= end:
            return page_number
    return page_offsets[-1][0] if page_offsets else 1


def _normalize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    return title[:160]


def _split_oversized_section(
    *,
    source_file: str,
    country: str,
    language: str,
    section_id: str,
    title: str,
    content: str,
    content_offset: int,
    page_offsets: list[tuple[int, int, int]],
    document_version: str = "",
    effective_date: str = "",
    status: str = "active",
) -> list[PolicySection]:
    if len(content) <= MAX_SECTION_CHARS:
        return [
            PolicySection(
                source_file=source_file,
                country=country,
                language=language,
                section_id=section_id,
                title=title,
                start_page=_page_for_offset(page_offsets, content_offset),
                end_page=_page_for_offset(page_offsets, content_offset + len(content) - 1),
                content=content,
                document_version=document_version,
                effective_date=effective_date,
                status=status,
            )
        ]

    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(content):
        end = min(start + MAX_SECTION_CHARS, len(content))
        if end < len(content):
            boundary = content.rfind("\n", start, end)
            if boundary > start:
                end = boundary
        chunks.append((start, content[start:end].strip()))
        start = end
        while start < len(content) and content[start].isspace():
            start += 1

    return [
        PolicySection(
            source_file=source_file,
            country=country,
            language=language,
            section_id=f"{section_id}-part-{part_number}",
            title=_normalize_title(f"{title} (part {part_number})"),
            start_page=_page_for_offset(page_offsets, content_offset + chunk_start),
            end_page=_page_for_offset(
                page_offsets,
                content_offset + chunk_start + len(chunk) - 1,
            ),
            content=chunk,
            document_version=document_version,
            effective_date=effective_date,
            status=status,
            chunk_type="section_part",
            parent_section_id=section_id,
        )
        for part_number, (chunk_start, chunk) in enumerate(chunks, start=1)
        if chunk
    ]


def _compact_numeric_fact(line: str) -> bool:
    """Recognize a compact table/list row containing a numeric policy fact."""
    cleaned = " ".join(line.split())
    return (
        12 <= len(cleaned) <= 360
        and any(character.isdigit() for character in cleaned)
        and bool(re.search(r"[^\W\d_]", cleaned, flags=re.UNICODE))
    )


def _contextual_content(section: PolicySection, content: str) -> str:
    """Keep each atomic chunk understandable when retrieved on its own."""
    return f"Section {section.section_id}: {section.title}\n{content.strip()}"


def _definition_chunks(section: PolicySection) -> list[PolicySection]:
    """Create atomic chunks from language-neutral ``label: definition`` entries."""
    matches = [
        match
        for match in DEFINITION_ENTRY_RE.finditer(section.content)
        if any(character.isalpha() for character in match.group("label"))
        and not SECTION_RE.match(match.group(0))
        and not LIST_ITEM_RE.match(match.group(0))
    ]
    if not matches:
        return []

    parent_section_id = section.parent_section_id or section.section_id
    chunks: list[PolicySection] = []
    for index, match in enumerate(matches, start=1):
        end = matches[index].start() if index < len(matches) else len(section.content)
        content = section.content[match.start() : end].strip()
        if len(content) < 8:
            continue
        chunks.append(
            PolicySection(
                source_file=section.source_file,
                country=section.country,
                language=section.language,
                section_id=f"{section.section_id}-definition-{index}",
                title=_normalize_title(match.group("label")),
                start_page=section.start_page,
                end_page=section.end_page,
                content=_contextual_content(section, content),
                document_version=section.document_version,
                effective_date=section.effective_date,
                status=section.status,
                chunk_type="definition",
                parent_section_id=parent_section_id,
            )
        )
    return chunks


def _expand_structured_chunks(sections: list[PolicySection]) -> list[PolicySection]:
    """Add generic atomic chunks for list items and numeric table rows.

    The parent section remains available for context. Child chunks make short
    facts independently retrievable without relying on country, language, or
    policy-specific aliases.
    """

    expanded: list[PolicySection] = []
    for section in sections:
        expanded.append(section)
        expanded.extend(_definition_chunks(section))
        if section.chunk_type == "section_part":
            continue
        matches = list(LIST_ITEM_RE.finditer(section.content))

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(section.content)
            content = section.content[start:end].strip()
            if len(content) < 24:
                continue
            label = re.sub(r"[^a-z0-9]+", "", match.group("label").casefold()) or str(index + 1)
            expanded.append(
                PolicySection(
                    source_file=section.source_file,
                    country=section.country,
                    language=section.language,
                    section_id=f"{section.section_id}-{label}",
                    title=_normalize_title(match.group("title")),
                    start_page=section.start_page,
                    end_page=section.end_page,
                    content=_contextual_content(section, content),
                    document_version=section.document_version,
                    effective_date=section.effective_date,
                    status=section.status,
                    chunk_type="list_item",
                    parent_section_id=section.section_id,
                )
            )

        lines = [" ".join(line.split()) for line in section.content.splitlines()]
        fact_rows = [
            (index, line)
            for index, line in enumerate(lines[1:], start=1)
            if _compact_numeric_fact(line) and not LIST_ITEM_RE.match(line)
        ]
        if len(fact_rows) < 2:
            continue
        for row_number, line in fact_rows:
            expanded.append(
                PolicySection(
                    source_file=section.source_file,
                    country=section.country,
                    language=section.language,
                    section_id=f"{section.section_id}-fact-{row_number}",
                    title=_normalize_title(line[:160]),
                    start_page=section.start_page,
                    end_page=section.end_page,
                    content=_contextual_content(section, line),
                    document_version=section.document_version,
                    effective_date=section.effective_date,
                    status=section.status,
                    chunk_type="numeric_fact",
                    parent_section_id=section.section_id,
                )
            )
    return expanded


def write_jsonl(sections: list[PolicySection], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for section in sections:
            handle.write(json.dumps(asdict(section), ensure_ascii=False) + "\n")


def write_csv(sections: list[PolicySection], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "country",
                "country_code",
                "language",
                "section_id",
                "title",
                "start_page",
                "end_page",
                "document_version",
                "effective_date",
                "status",
                "document_type",
                "access_scope",
                "chunk_type",
                "parent_section_id",
                "content_length",
                "preview",
            ],
        )
        writer.writeheader()
        for section in sections:
            writer.writerow(
                {
                    "source_file": section.source_file,
                    "country": section.country,
                    "country_code": section.country,
                    "language": section.language,
                    "section_id": section.section_id,
                    "title": section.title,
                    "start_page": section.start_page,
                    "end_page": section.end_page,
                    "document_version": section.document_version,
                    "effective_date": section.effective_date,
                    "status": section.status,
                    "document_type": "policy",
                    "access_scope": "country",
                    "chunk_type": section.chunk_type,
                    "parent_section_id": section.parent_section_id,
                    "content_length": len(section.content),
                    "preview": section.content[:300],
                }
            )


def write_bedrock_files(sections: list[PolicySection], directory: Path) -> None:
    """Write one small text file per section with a matching metadata sidecar."""

    directory.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for section in sections:
        filename = _section_filename(section)
        text_path = directory / f"{filename}.txt"
        metadata_path = directory / f"{filename}.txt.metadata.json"

        text_path.write_text(_section_text(section), encoding="utf-8")
        metadata_path.write_text(
            json.dumps({"metadataAttributes": section.metadata}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest_rows.append(
            {
                **section.metadata,
                "text_file": text_path.name,
                "metadata_file": metadata_path.name,
                "content_length": len(section.content),
            }
        )

    manifest_path = directory / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_file",
                "country",
                "country_code",
                "language",
                "section_id",
                "section_title",
                "start_page",
                "end_page",
                "document_version",
                "effective_date",
                "status",
                "document_type",
                "access_scope",
                "chunk_type",
                "parent_section_id",
                "text_file",
                "metadata_file",
                "content_length",
            ],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)


def _section_filename(section: PolicySection) -> str:
    stem = Path(section.source_file).stem
    title = section.title[:60].lower()
    title = SAFE_FILENAME_RE.sub("-", title).strip("-")
    return f"{stem}.{section.section_id}.{title}"


def _section_text(section: PolicySection) -> str:
    page = str(section.start_page)
    if section.end_page != section.start_page:
        page = f"{section.start_page}-{section.end_page}"
    return "\n".join(
        [
            f"Document: {section.source_file}",
            f"Country: {section.country}",
            f"Language: {section.language}",
            f"Section: {section.section_id}",
            f"Title: {section.title}",
            f"Page: {page}",
            "",
            section.content,
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--country", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--output-dir", default=Path("outputs/policy_sections"), type=Path)
    parser.add_argument("--min-chars", default=40, type=int)
    parser.add_argument("--document-version", default="")
    parser.add_argument("--effective-date", default="")
    parser.add_argument("--status", default="active", choices=["active", "inactive"])
    parser.add_argument(
        "--bedrock-dir",
        type=Path,
        help="Optional folder for one-file-per-section Bedrock test ingestion output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sections = extract_sections(
        args.pdf,
        country=args.country,
        language=args.language,
        min_chars=args.min_chars,
        document_version=args.document_version,
        effective_date=args.effective_date,
        status=args.status,
    )

    stem = args.pdf.stem
    jsonl_path = args.output_dir / f"{stem}.sections.jsonl"
    csv_path = args.output_dir / f"{stem}.sections.csv"
    write_jsonl(sections, jsonl_path)
    write_csv(sections, csv_path)
    if args.bedrock_dir:
        write_bedrock_files(sections, args.bedrock_dir)

    print("Policy section extraction complete")
    print("----------------------------------")
    print(f"PDF: {args.pdf}")
    print(f"Sections: {len(sections)}")
    print(f"JSONL: {jsonl_path}")
    print(f"CSV: {csv_path}")
    if args.bedrock_dir:
        print(f"Bedrock test files: {args.bedrock_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
