"""Extract global office and staff directory records from a search-ready PDF."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


HEADER_RE = re.compile(r"^International Office Directory[^\n]*$", re.MULTILINE)
PAGE_RE = re.compile(r"^Page \d+$", re.MULTILINE)
OFFICE_RECORD_RE = re.compile(
    r"(?m)^(?P<title>[^\n]+)\nCountry\n(?P<record_country>[^\n]+)$"
)
STAFF_RECORD_RE = re.compile(
    r"(?m)^(?P<title>[^\n]+)\nOperating Country\n(?P<record_country>[^\n]+)$"
)
SAFE_ID_RE = re.compile(r"[^a-z0-9]+")
WRAPPED_EMAIL_RE = re.compile(
    r"([\w.+-]+@[\w.-]+)\n([A-Za-z0-9-]{1,20}\.[A-Za-z]{2,})",
    re.UNICODE,
)
WRAPPED_EMAIL_AT_RE = re.compile(
    r"([\w.+-]+)\n(@[\w.-]+\.[A-Za-z]{2,})",
    re.UNICODE,
)


@dataclass(frozen=True)
class DirectoryRecord:
    source_file: str
    section_id: str
    title: str
    start_page: int
    end_page: int
    content: str
    record_type: str
    record_country: str

    def to_row(self) -> dict[str, object]:
        return {
            "source_file": self.source_file,
            "country": "GLOBAL",
            "language": "en",
            "section_id": self.section_id,
            "title": self.title,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "content": self.content,
            "metadata": {
                "directory_section": self.record_type,
                "record_country": self.record_country,
            },
        }


def _clean_page(text: str) -> str:
    text = HEADER_RE.sub("", text)
    text = PAGE_RE.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    cleaned = WRAPPED_EMAIL_RE.sub(r"\1\2", cleaned)
    return WRAPPED_EMAIL_AT_RE.sub(r"\1\2", cleaned)


def _page_for_offset(page_offsets: list[tuple[int, int, int]], offset: int) -> int:
    for page_number, start, end in page_offsets:
        if start <= offset <= end:
            return page_number
    return page_offsets[-1][0]


def _slug(value: str) -> str:
    return SAFE_ID_RE.sub("-", value.casefold()).strip("-")[:80]


def _extract_group(
    *,
    source_file: str,
    record_type: str,
    pages: list[tuple[int, str]],
    pattern: re.Pattern[str],
) -> list[DirectoryRecord]:
    full_text_parts: list[str] = []
    page_offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for page_number, text in pages:
        start = cursor
        full_text_parts.append(text)
        cursor += len(text)
        page_offsets.append((page_number, start, cursor))
        full_text_parts.append("\n")
        cursor += 1

    full_text = "".join(full_text_parts)
    matches = list(pattern.finditer(full_text))
    records: list[DirectoryRecord] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        title = " ".join(match.group("title").split())
        record_country = " ".join(match.group("record_country").split())
        records.append(
            DirectoryRecord(
                source_file=source_file,
                section_id=f"{record_type}-{index + 1:03d}-{_slug(title)}",
                title=title,
                start_page=_page_for_offset(page_offsets, start),
                end_page=_page_for_offset(page_offsets, max(start, end - 1)),
                content=content,
                record_type=record_type,
                record_country=record_country,
            )
        )
    return records


def extract_directory(pdf_path: Path) -> tuple[list[DirectoryRecord], list[DirectoryRecord]]:
    reader = PdfReader(str(pdf_path))
    office_pages: list[tuple[int, str]] = []
    staff_pages: list[tuple[int, str]] = []
    section = ""

    for page_number, page in enumerate(reader.pages, start=1):
        text = _clean_page(page.extract_text() or "")
        if not text:
            continue
        if "Country Office Contact Details" in text and "Source worksheet:" in text:
            section = "office"
        if "Staff Contact Details" in text and "Source worksheet:" in text:
            section = "staff"
        if section == "office":
            office_pages.append((page_number, text))
        elif section == "staff":
            staff_pages.append((page_number, text))

    office_records = _extract_group(
        source_file=pdf_path.name,
        record_type="office",
        pages=office_pages,
        pattern=OFFICE_RECORD_RE,
    )
    staff_records = _extract_group(
        source_file=pdf_path.name,
        record_type="staff",
        pages=staff_pages,
        pattern=STAFF_RECORD_RE,
    )
    return office_records, staff_records


def _write_outputs(records: list[DirectoryRecord], output_dir: Path, source_stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{source_stem}.directory.jsonl"
    csv_path = output_dir / f"{source_stem}.directory.csv"
    rows = [record.to_row() for record in records]

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "section_id",
                "title",
                "record_type",
                "record_country",
                "start_page",
                "end_page",
                "content",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "section_id": record.section_id,
                    "title": record.title,
                    "record_type": record.record_type,
                    "record_country": record.record_country,
                    "start_page": record.start_page,
                    "end_page": record.end_page,
                    "content": record.content,
                }
            )
    return jsonl_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-office-records", type=int, default=0)
    parser.add_argument("--expected-staff-records", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    office_records, staff_records = extract_directory(args.pdf)
    if args.expected_office_records and len(office_records) != args.expected_office_records:
        raise ValueError(
            f"Expected {args.expected_office_records} office records; found {len(office_records)}."
        )
    if args.expected_staff_records and len(staff_records) != args.expected_staff_records:
        raise ValueError(
            f"Expected {args.expected_staff_records} staff records; found {len(staff_records)}."
        )

    records = [*office_records, *staff_records]
    jsonl_path, csv_path = _write_outputs(records, args.output_dir, args.pdf.stem)
    print("Global directory extraction complete")
    print("------------------------------------")
    print(f"PDF: {args.pdf}")
    print(f"Office records: {len(office_records)}")
    print(f"Staff records: {len(staff_records)}")
    print(f"Total records: {len(records)}")
    print(f"JSONL: {jsonl_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
