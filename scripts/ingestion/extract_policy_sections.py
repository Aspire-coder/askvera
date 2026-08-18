"""Extract section-sized chunks from policy PDFs.

This script is intentionally offline. It prepares cleaner source chunks that
can be reviewed before they are uploaded into a knowledge base.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.document_preflight import extract_pdf_page_text, is_table_like_layout  # noqa: E402


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
VNEXT_MAX_SECTION_CHARS = 2_000
VNEXT_SECTION_OVERLAP_CHARS = 200
VNEXT_R4_MAX_PARENT_CHARS = MAX_SECTION_CHARS
VNEXT_R4_MAX_SUBSECTION_NUMBER = 30
VNEXT_R4_MAX_DEFINITIONS_PER_PARENT = 6
VNEXT_R4_MAX_LIST_ITEMS_PER_PARENT = 6
VNEXT_R4_MAX_NUMERIC_FACTS_PER_PARENT = 6
VNEXT_R4_MAX_CHILDREN_PER_PARENT = 8
CHUNK_PROFILES = {
    "current": (MAX_SECTION_CHARS, 0),
    "vnext": (VNEXT_MAX_SECTION_CHARS, VNEXT_SECTION_OVERLAP_CHARS),
    "vnext_r4": (VNEXT_R4_MAX_PARENT_CHARS, 0),
}
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
    chunk_profile: str = "current"

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
            "authority_level": (
                "governing"
                if self.chunk_type in {"section", "section_part", "definition"}
                else "supporting"
                if self.chunk_type in {"list_item", "numeric_fact", "table_row"}
                else "navigational"
            ),
            "parent_section_id": self.parent_section_id,
            "chunk_profile": self.chunk_profile,
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


def _read_pdf_pages(
    pdf_path: Path,
    *,
    chunk_profile: str = "current",
) -> list[tuple[int, str]]:
    """Read and clean every text-bearing PDF page."""
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        raw_text = extract_pdf_page_text(page)
        if chunk_profile.startswith("vnext"):
            layout_text = extract_pdf_page_text(page, preserve_layout=True)
            if is_table_like_layout(layout_text):
                raw_text = layout_text
        text = _clean_page_text(raw_text)
        if text:
            pages.append((index, text))
    return pages


def _read_pages(pdf_path: Path, *, chunk_profile: str = "current") -> list[tuple[int, str]]:
    """Read policy-body pages while keeping outlines out of section parsing."""
    return [
        (page_number, text)
        for page_number, text in _read_pdf_pages(pdf_path, chunk_profile=chunk_profile)
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


def _uppercase_ratio(value: str) -> float:
    letters = [character for character in value if character.isalpha()]
    if not letters:
        return 0.0
    return sum(character.isupper() for character in letters) / len(letters)


def _r4_section_matches(page_text: str) -> list[re.Match[str]]:
    """Reject common list-number and time-value false headings.

    The original and r3 profiles intentionally retain their historical parser.
    r4 only accepts plausible decimal subsection numbers and suppresses repeated
    top-level numbers unless the repeated heading is visually authoritative.
    """
    accepted: list[re.Match[str]] = []
    seen_top_level: set[str] = set()
    for match in _iter_section_matches(page_text):
        section_id = match.group("section")
        if "." in section_id:
            _, subsection = section_id.split(".", 1)
            if int(subsection) > VNEXT_R4_MAX_SUBSECTION_NUMBER:
                continue
            accepted.append(match)
            continue

        if section_id in seen_top_level and _uppercase_ratio(match.group("title")) < 0.75:
            continue
        seen_top_level.add(section_id)
        accepted.append(match)
    return accepted


def extract_sections(
    pdf_path: Path,
    *,
    country: str,
    language: str,
    min_chars: int = 40,
    document_version: str = "",
    effective_date: str = "",
    status: str = "active",
    chunk_profile: str = "current",
) -> list[PolicySection]:
    if chunk_profile not in CHUNK_PROFILES:
        raise ValueError(f"Unknown chunk profile: {chunk_profile}")

    all_pages = _read_pdf_pages(pdf_path, chunk_profile=chunk_profile)
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
    matches = (
        _r4_section_matches(full_text)
        if chunk_profile == "vnext_r4"
        else list(_iter_section_matches(full_text))
    )
    sections: list[PolicySection] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        body = re.sub(r"\n{3,}", "\n\n", body)

        if len(body) < min_chars:
            continue

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
                chunk_profile=chunk_profile,
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
        chunk_profile=chunk_profile,
    )
    front_matter = _front_matter_chunks(
        all_pages,
        source_file=pdf_path.name,
        country=country,
        language=language,
        document_version=document_version,
        effective_date=effective_date,
        status=status,
        chunk_profile=chunk_profile,
    )
    expanded = [
        *front_matter,
        *outlines,
        *_expand_structured_chunks(sections, chunk_profile=chunk_profile),
    ]
    return _ensure_unique_section_ids(_bound_vnext_chunks(expanded))


def _front_matter_chunks(
    pages: list[tuple[int, str]],
    *,
    source_file: str,
    country: str,
    language: str,
    document_version: str,
    effective_date: str,
    status: str,
    chunk_profile: str = "current",
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
            chunk_profile=chunk_profile,
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
    chunk_profile: str = "current",
) -> list[PolicySection]:
    """Preserve table-of-contents pages for section-location questions."""
    chunks: list[PolicySection] = []
    for page_number, text in pages:
        if not _looks_like_contents_page(text):
            continue

        if chunk_profile == "current" or len(text) <= VNEXT_MAX_SECTION_CHARS:
            page_parts = [text]
        else:
            page_parts = _split_vnext_text(text)

        for part_number, content in enumerate(page_parts, start=1):
            base_id = f"outline-page-{page_number}"
            is_split = len(page_parts) > 1
            chunks.append(
                PolicySection(
                    source_file=source_file,
                    country=country,
                    language=language,
                    section_id=f"{base_id}-part-{part_number}" if is_split else base_id,
                    title="Policy document outline",
                    start_page=page_number,
                    end_page=page_number,
                    content=content,
                    document_version=document_version,
                    effective_date=effective_date,
                    status=status,
                    chunk_type="document_outline",
                    parent_section_id=base_id if is_split else "",
                    chunk_profile=chunk_profile,
                )
            )
    return chunks


def _split_vnext_text(
    content: str,
    *,
    max_chars: int = VNEXT_MAX_SECTION_CHARS,
    overlap_chars: int = VNEXT_SECTION_OVERLAP_CHARS,
) -> list[str]:
    """Split auxiliary policy text with the vNext structural boundaries."""
    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        if end < len(content):
            boundaries = [
                (content.rfind("\n\n", start, end), 0),
                (content.rfind("\n", start, end), 0),
                (content.rfind(". ", start, end), 2),
            ]
            boundary, suffix_length = max(boundaries)
            if boundary > start + max_chars // 2:
                end = boundary + suffix_length

        chunk = content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(content):
            break

        start = max(end - overlap_chars, start + 1)
        while start < end and not content[start].isspace():
            start += 1
        while start < len(content) and content[start].isspace():
            start += 1
    return chunks


def _bound_vnext_chunks(sections: list[PolicySection]) -> list[PolicySection]:
    """Apply the vNext size ceiling after contextual child chunks are added."""
    bounded: list[PolicySection] = []
    for section in sections:
        max_chars = (
            VNEXT_R4_MAX_PARENT_CHARS
            if section.chunk_profile == "vnext_r4"
            and section.chunk_type in {"section", "section_part"}
            else VNEXT_MAX_SECTION_CHARS
        )
        if (
            not section.chunk_profile.startswith("vnext")
            or len(section.content) <= max_chars
        ):
            bounded.append(section)
            continue

        parent_section_id = section.parent_section_id or section.section_id
        bounded.extend(
            replace(
                section,
                section_id=f"{section.section_id}-part-{part_number}",
                content=content,
                parent_section_id=parent_section_id,
            )
            for part_number, content in enumerate(
                _split_vnext_text(
                    section.content,
                    max_chars=max_chars,
                    overlap_chars=0 if section.chunk_profile == "vnext_r4" else VNEXT_SECTION_OVERLAP_CHARS,
                ),
                start=1,
            )
        )
    return bounded


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
    chunk_profile: str = "current",
) -> list[PolicySection]:
    try:
        max_chars, overlap_chars = CHUNK_PROFILES[chunk_profile]
    except KeyError as exc:
        raise ValueError(f"Unknown chunk profile: {chunk_profile}") from exc

    if len(content) <= max_chars:
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
                chunk_profile=chunk_profile,
            )
        ]

    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        if end < len(content):
            if chunk_profile == "current":
                boundary = content.rfind("\n", start, end)
                if boundary > start:
                    end = boundary
            else:
                boundaries = [
                    (content.rfind("\n\n", start, end), 0),
                    (content.rfind("\n", start, end), 0),
                    (content.rfind(". ", start, end), 2),
                ]
                boundary, suffix_length = max(boundaries)
                if boundary > start + max_chars // 2:
                    end = boundary + suffix_length
        chunks.append((start, content[start:end].strip()))
        if end >= len(content):
            break
        start = max(end - overlap_chars, start + 1)
        while start < end and not content[start].isspace():
            start += 1
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
            chunk_profile=chunk_profile,
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
                chunk_profile=section.chunk_profile,
            )
        )
    return chunks


def _parent_section_id(section: PolicySection) -> str:
    return section.parent_section_id or section.section_id


def _structured_child_parent_id(section: PolicySection, profile: str) -> str:
    if profile == "vnext_r4":
        return _parent_section_id(section)
    return section.section_id


def _bounded_children(
    children: list[PolicySection],
    *,
    chunk_type: str,
    limit: int,
) -> list[PolicySection]:
    return [child for child in children if child.chunk_type == chunk_type][:limit]


def _balanced_r4_children(children: list[PolicySection]) -> list[PolicySection]:
    groups = [
        _bounded_children(
            children,
            chunk_type="definition",
            limit=VNEXT_R4_MAX_DEFINITIONS_PER_PARENT,
        ),
        _bounded_children(
            children,
            chunk_type="list_item",
            limit=VNEXT_R4_MAX_LIST_ITEMS_PER_PARENT,
        ),
        _bounded_children(
            children,
            chunk_type="numeric_fact",
            limit=VNEXT_R4_MAX_NUMERIC_FACTS_PER_PARENT,
        ),
    ]
    selected: list[PolicySection] = []
    for position in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if position < len(group):
                selected.append(group[position])
                if len(selected) >= VNEXT_R4_MAX_CHILDREN_PER_PARENT:
                    return selected
    return selected


def _expand_structured_chunks(
    sections: list[PolicySection],
    *,
    chunk_profile: str | None = None,
) -> list[PolicySection]:
    """Add generic atomic chunks for list items and numeric table rows.

    The parent section remains available for context. Child chunks make short
    facts independently retrievable without relying on country, language, or
    policy-specific aliases.
    """

    profile = chunk_profile or (sections[0].chunk_profile if sections else "current")
    expanded: list[PolicySection] = []
    r4_children: dict[str, list[PolicySection]] = {}
    for section in sections:
        expanded.append(section)
        generated: list[PolicySection] = []
        generated.extend(_definition_chunks(section))
        if section.chunk_type == "section_part" and section.chunk_profile == "current":
            expanded.extend(generated)
            continue
        matches = list(LIST_ITEM_RE.finditer(section.content))

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(section.content)
            content = section.content[start:end].strip()
            if len(content) < 24:
                continue
            label = re.sub(r"[^a-z0-9]+", "", match.group("label").casefold()) or str(index + 1)
            generated.append(
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
                    parent_section_id=_structured_child_parent_id(section, profile),
                    chunk_profile=section.chunk_profile,
                )
            )

        lines = [" ".join(line.split()) for line in section.content.splitlines()]
        fact_rows = [
            (index, line)
            for index, line in enumerate(lines[1:], start=1)
            if _compact_numeric_fact(line) and not LIST_ITEM_RE.match(line)
        ]
        if len(fact_rows) < 2:
            if profile == "vnext_r4":
                r4_children.setdefault(_parent_section_id(section), []).extend(generated)
            else:
                expanded.extend(generated)
            continue
        for row_number, line in fact_rows:
            generated.append(
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
                    parent_section_id=_structured_child_parent_id(section, profile),
                    chunk_profile=section.chunk_profile,
                )
            )
        if profile == "vnext_r4":
            r4_children.setdefault(_parent_section_id(section), []).extend(generated)
        else:
            expanded.extend(generated)

    if profile == "vnext_r4":
        for children in r4_children.values():
            expanded.extend(_balanced_r4_children(children))
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
                "chunk_profile",
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
                    "chunk_profile": section.chunk_profile,
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
        "--chunk-profile",
        default="current",
        choices=sorted(CHUNK_PROFILES),
        help="Use 'vnext' only for an isolated comparison package and index.",
    )
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
        chunk_profile=args.chunk_profile,
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
    print(f"Chunk profile: {args.chunk_profile}")
    print(f"JSONL: {jsonl_path}")
    print(f"CSV: {csv_path}")
    if args.bedrock_dir:
        print(f"Bedrock test files: {args.bedrock_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
