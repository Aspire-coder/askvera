"""Extract section-sized chunks from policy PDFs.

This script is intentionally offline. It prepares cleaner source chunks that
can be reviewed before they are uploaded into a knowledge base.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


# Policies commonly use a mix of top-level headings ("1 Introduction"),
# one-digit subsections ("1.3."), and two-digit subsections ("11.01").
# Require a letter in the title so PDF page-number pairs are not headings.
SECTION_RE = re.compile(
    r"(?m)^(?P<section>\d{1,2}(?:\.\d{1,2})?)\.?\s+(?P<title>[^\W\d_].+)$"
)
LETTERED_RE = re.compile(r"(?m)^\((?P<section>[a-z])\)\s+(?P<title>.+)$")
HEADER_RE = re.compile(r"Company Policies and the Code of Professional Conduct Revised \d+")
PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")
WHITESPACE_RE = re.compile(r"[ \t]+")
SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
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

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "source_file": self.source_file,
            "country": self.country,
            "language": self.language,
            "section_id": self.section_id,
            "section_title": self.title,
            "start_page": self.start_page,
            "end_page": self.end_page,
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
        lines.append(line)
    return "\n".join(lines)


def _read_pages(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = _clean_page_text(page.extract_text() or "")
        if text and not _looks_like_contents_page(text):
            pages.append((index, text))
    return pages


def _looks_like_contents_page(text: str) -> bool:
    """Detect a dense numbered list without depending on its language."""
    heading_lines = sum(
        bool(SECTION_RE.match(line))
        for line in text.splitlines()
    )
    return heading_lines >= 6


def _iter_section_matches(page_text: str) -> Iterable[re.Match[str]]:
    yield from SECTION_RE.finditer(page_text)


def extract_sections(
    pdf_path: Path,
    *,
    country: str,
    language: str,
    min_chars: int = 40,
) -> list[PolicySection]:
    pages = _read_pages(pdf_path)
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

        sections.append(
            PolicySection(
                source_file=pdf_path.name,
                country=country,
                language=language,
                section_id=match.group("section"),
                title=title,
                start_page=start_page,
                end_page=end_page,
                content=body,
            )
        )

    return _merge_lettered_subsections(sections)


def _page_for_offset(page_offsets: list[tuple[int, int, int]], offset: int) -> int:
    for page_number, start, end in page_offsets:
        if start <= offset <= end:
            return page_number
    return page_offsets[-1][0] if page_offsets else 1


def _normalize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    return title[:160]


def _merge_lettered_subsections(sections: list[PolicySection]) -> list[PolicySection]:
    """Split large numbered sections into lettered chunks when useful.

    Some policy documents put important rules under 4.01(a), 4.01(b), etc.
    This keeps the numbered section and also creates precise child chunks.
    """

    expanded: list[PolicySection] = []
    for section in sections:
        expanded.append(section)
        matches = list(LETTERED_RE.finditer(section.content))
        if len(matches) < 2:
            continue

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(section.content)
            content = section.content[start:end].strip()
            if len(content) < 40:
                continue
            expanded.append(
                PolicySection(
                    source_file=section.source_file,
                    country=section.country,
                    language=section.language,
                    section_id=f"{section.section_id}{match.group('section')}",
                    title=_normalize_title(match.group("title")),
                    start_page=section.start_page,
                    end_page=section.end_page,
                    content=content,
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
                "language",
                "section_id",
                "title",
                "start_page",
                "end_page",
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
                    "language": section.language,
                    "section_id": section.section_id,
                    "title": section.title,
                    "start_page": section.start_page,
                    "end_page": section.end_page,
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
                "language",
                "section_id",
                "section_title",
                "start_page",
                "end_page",
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
