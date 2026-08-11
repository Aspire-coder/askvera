"""Extract globally available country sponsoring sections from a PDF."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

WELCOME_RE = re.compile(
    r"(?im)^\s*Welcome\s+to\s+Forever\s+(?P<country>[^!\r\n]{2,100})!\s*$"
)
SAFE_ID_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SponsoringRecord:
    source_file: str
    section_id: str
    title: str
    start_page: int
    end_page: int
    content: str
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
                "directory_section": "sponsoring",
                "directory_kind": "international_sponsoring",
                "record_country": self.record_country,
            },
        }


def _clean_page(text: str) -> str:
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    if any(marker in cleaned for marker in ("â", "Ã", "Â")):
        try:
            repaired = cleaned.encode("latin1").decode("utf-8")
        except UnicodeError:
            repaired = cleaned
        else:
            cleaned = repaired
    return cleaned


def _slug(value: str) -> str:
    return SAFE_ID_RE.sub("-", value.casefold()).strip("-")[:80]


def _page_for_offset(page_offsets: list[tuple[int, int, int]], offset: int) -> int:
    for page_number, start, end in page_offsets:
        if start <= offset < end:
            return page_number
    return page_offsets[-1][0]


def extract_directory(pdf_path: Path) -> list[SponsoringRecord]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = _clean_page(page.extract_text() or "")
        if text:
            pages.append((page_number, text))

    full_parts: list[str] = []
    page_offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for page_number, text in pages:
        start = cursor
        full_parts.append(text)
        cursor += len(text)
        full_parts.append("\n")
        cursor += 1
        page_offsets.append((page_number, start, cursor))

    full_text = "".join(full_parts)
    matches = list(WELCOME_RE.finditer(full_text))
    records: list[SponsoringRecord] = []
    for index, match in enumerate(matches):
        country = " ".join(match.group("country").split()).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        body = full_text[start:end].strip()
        body = re.sub(
            r"^Welcome\s+to\s+Forever\s+[^!]+!",
            f"Welcome to Forever {country}!",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        records.append(
            SponsoringRecord(
                source_file=pdf_path.name,
                section_id=f"sponsoring-{index + 1:03d}-{_slug(country)}",
                title=f"Forever {country}",
                start_page=_page_for_offset(page_offsets, start),
                end_page=_page_for_offset(page_offsets, max(start, end - 1)),
                content=body,
                record_country=country,
            )
        )
    if not records:
        raise ValueError("No country sponsoring sections were found in the PDF.")
    return records


def _write_outputs(records: list[SponsoringRecord], output_dir: Path, source_stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{source_stem}.directory.jsonl"
    csv_path = output_dir / f"{source_stem}.directory.csv"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_row(), ensure_ascii=False) + "\n")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["section_id", "title", "record_country", "start_page", "end_page", "content"],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "section_id": record.section_id,
                    "title": record.title,
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
    parser.add_argument("--expected-records", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = extract_directory(args.pdf)
    if args.expected_records and len(records) != args.expected_records:
        raise ValueError(f"Expected {args.expected_records} records; found {len(records)}.")
    jsonl_path, csv_path = _write_outputs(records, args.output_dir, args.pdf.stem)
    print("Global sponsoring directory extraction complete")
    print("-----------------------------------------------")
    print(f"PDF: {args.pdf}")
    print(f"Records: {len(records)}")
    print(f"Pages: {records[0].start_page} - {records[-1].end_page}")
    print(f"Largest record: {max(len(record.content) for record in records)} characters")
    print(f"JSONL: {jsonl_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
