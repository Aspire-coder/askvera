"""Run a page-level retrieval evaluation from the ASK Vera test spreadsheet.

This script intentionally tests retrieval only. It does not call the model,
run prompt building, or validate generated answers. The goal is to answer a
clean question for every test case: did retrieval return the expected source
page or section before generation ever starts?
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


QUESTION_COLUMNS = ["test question", "question", "prompt", "user question"]
TEST_ID_COLUMNS = ["test id", "id", "case id", "test case id"]
COUNTRY_COLUMNS = ["country", "market"]
LANGUAGE_COLUMNS = ["language", "lang"]
ROLE_COLUMNS = ["user role", "role"]
EXPECTED_SOURCE_COLUMNS = [
    "expected citation / source (ca policy may 2026)",
    "expected citation",
    "expected source",
    "source",
    "document",
    "expected document",
]
EXPECTED_PAGE_COLUMNS = [
    "expected page",
    "page",
    "pages",
    "expected pages",
    "source page",
    "expected source page",
]


@dataclass(frozen=True)
class RetrievedSourceSnapshot:
    """Small, report-friendly shape for one retrieved source."""

    rank: int
    title: str
    page: str
    score: float | None
    source: str
    excerpt: str


@dataclass(frozen=True)
class RetrievalEvaluationRow:
    """One evaluated spreadsheet test row."""

    test_id: str
    question: str
    country: str
    language: str
    role: str
    expected_source: str
    expected_pages: str
    status: str
    retrieval_confidence: float
    top_title: str
    top_page: str
    top_score: float | None
    top_excerpt: str
    source_count: int
    matching_source_ranks: str
    matching_page_ranks: str
    sources_json: str
    error: str = ""


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip().lower() == "nan"


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {_normalize_header(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for column in columns:
        header = _normalize_header(column)
        if any(candidate in header for candidate in candidates):
            return column
    return None


def _text(value: Any, default: str = "") -> str:
    if _is_blank(value):
        return default
    return str(value).strip()


def _country_code(value: Any, default: str) -> str:
    raw = _text(value, default)
    lookup = {"canada": "CA", "ca": "CA", "united states": "US", "usa": "US", "us": "US"}
    return lookup.get(raw.lower(), raw)


def _language_code(value: Any, default: str) -> str:
    raw = _text(value, default)
    lookup = {"english": "en", "en": "en", "french": "fr", "fr": "fr", "fr-ca": "fr"}
    return lookup.get(raw.lower(), raw)


def _normalize_page(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    number_match = re.search(r"\d+(?:\.0+)?", raw)
    if number_match:
        return str(int(float(number_match.group(0))))
    return raw.lower()


def _expected_pages(value: Any) -> list[str]:
    raw = _text(value)
    if not raw:
        return []
    pages: set[str] = set()
    for start, end in re.findall(r"(\d+)\s*[-–]\s*(\d+)", raw):
        for page in range(int(start), int(end) + 1):
            pages.add(str(page))
    for match in re.findall(r"\d+(?:\.0+)?", raw):
        pages.add(str(int(float(match))))
    return sorted(pages, key=lambda item: int(item) if item.isdigit() else item)


def _expected_sections(value: Any) -> list[str]:
    raw = _text(value)
    if not raw:
        return []
    return [
        section.lower()
        for section in re.findall(r"\b(?:sec|section)\.?\s*([0-9]+(?:\.[0-9]+)?[a-z]?)", raw, re.I)
    ]


def _has_document_expectation(expected_source: str) -> bool:
    expected = expected_source.lower()
    return ".pdf" in expected or "document" in expected or "policy.pdf" in expected


def _source_matches(expected_source: str, snapshot: RetrievedSourceSnapshot) -> bool:
    expected = expected_source.lower()
    if not expected:
        return False
    haystack = f"{snapshot.title} {snapshot.source}".lower()
    if ".pdf" in expected:
        expected_name = Path(expected).name
        return expected_name in haystack
    return any(token in haystack for token in re.findall(r"[a-z0-9][a-z0-9._-]{2,}", expected))


def _section_matches(expected_sections: list[str], snapshot: RetrievedSourceSnapshot) -> bool:
    if not expected_sections:
        return False
    excerpt = snapshot.excerpt.lower()
    for section in expected_sections:
        base_section = re.sub(r"[a-z]$", "", section)
        patterns = {
            rf"\b{re.escape(section)}\b",
            rf"\b{re.escape(base_section)}\b",
            rf"\b{re.escape(base_section)}\s*\([a-z]\)",
        }
        if any(re.search(pattern, excerpt) for pattern in patterns):
            return True
    return False


def _safe_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _snapshot_sources(result: Any, top_k: int) -> list[RetrievedSourceSnapshot]:
    snapshots: list[RetrievedSourceSnapshot] = []
    for index, document in enumerate(result.documents[:top_k], start=1):
        snapshots.append(
            RetrievedSourceSnapshot(
                rank=index,
                title=document.title,
                page=_normalize_page(document.page),
                score=_safe_float(document.score),
                source=document.source,
                excerpt=(document.excerpt or document.content or "")[:500],
            )
        )
    return snapshots


def _status_for(
    *,
    snapshots: list[RetrievedSourceSnapshot],
    expected_source: str,
    expected_pages_list: list[str],
    expected_sections: list[str],
) -> tuple[str, list[int], list[int]]:
    if not snapshots:
        return "FAIL_NO_RESULT", [], []

    has_document_expectation = _has_document_expectation(expected_source)
    matching_source_ranks = [
        snapshot.rank
        for snapshot in snapshots
        if has_document_expectation and _source_matches(expected_source, snapshot)
    ]
    matching_page_ranks = [
        snapshot.rank
        for snapshot in snapshots
        if expected_pages_list and snapshot.page in expected_pages_list
    ]
    matching_section_ranks = [
        snapshot.rank for snapshot in snapshots if _section_matches(expected_sections, snapshot)
    ]

    if expected_pages_list and matching_page_ranks:
        return "PASS_PAGE", matching_source_ranks, matching_page_ranks
    if expected_sections and matching_section_ranks:
        return "PASS_SECTION_HINT", matching_source_ranks, matching_section_ranks
    if expected_sections:
        return "FAIL_SECTION_NOT_FOUND", [], []
    if matching_source_ranks:
        if expected_pages_list:
            return "PASS_DOC_WRONG_PAGE", matching_source_ranks, []
        return "PASS_DOC_ONLY_NEEDS_EXPECTED_PAGE", matching_source_ranks, []
    if expected_pages_list or expected_source:
        return "FAIL_WRONG_SOURCE", [], []
    return "UNSCORABLE_MISSING_EXPECTED_SOURCE", [], []


def _load_dataframe(xlsx_path: Path, sheet_name: str):
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - depends on runtime
        raise RuntimeError("pandas is required to read the Excel test plan.") from exc
    return pd.read_excel(xlsx_path, sheet_name=sheet_name)


def inspect_workbook(xlsx_path: Path) -> None:
    import pandas as pd

    workbook = pd.ExcelFile(xlsx_path)
    print(f"Workbook: {xlsx_path}")
    print(f"Sheets: {', '.join(workbook.sheet_names)}")
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(xlsx_path, sheet_name=sheet, nrows=3)
        print()
        print(f"[{sheet}]")
        print("Columns:")
        for column in frame.columns:
            print(f"  - {column}")


def evaluate(args: argparse.Namespace) -> list[RetrievalEvaluationRow]:
    from app.retrieval import retrieval_service
    from config import settings

    if args.kb_id:
        settings.BEDROCK_KB_ID = args.kb_id
    if args.data_source_id:
        settings.BEDROCK_DATA_SOURCE_ID = args.data_source_id
        settings.BEDROCK_DATASOURCE_ID = args.data_source_id

    frame = _load_dataframe(args.xlsx, args.sheet)
    columns = [str(column) for column in frame.columns]

    question_col = _find_column(columns, QUESTION_COLUMNS)
    if question_col is None:
        raise RuntimeError(f"Could not find a question column. Columns: {columns}")

    test_id_col = _find_column(columns, TEST_ID_COLUMNS)
    country_col = _find_column(columns, COUNTRY_COLUMNS)
    language_col = _find_column(columns, LANGUAGE_COLUMNS)
    role_col = _find_column(columns, ROLE_COLUMNS)
    expected_source_col = _find_column(columns, EXPECTED_SOURCE_COLUMNS)
    expected_page_col = _find_column(columns, EXPECTED_PAGE_COLUMNS)

    rows: list[RetrievalEvaluationRow] = []
    for row_index, row in frame.iterrows():
        question = _text(row.get(question_col))
        if not question:
            continue

        test_id = _text(row.get(test_id_col) if test_id_col else "", f"row-{row_index + 2}")
        country = _country_code(row.get(country_col) if country_col else "", args.country)
        language = _language_code(row.get(language_col) if language_col else "", args.language)
        role = _text(row.get(role_col) if role_col else "", args.role)
        expected_source = _text(row.get(expected_source_col) if expected_source_col else "")
        expected_page_text = _text(row.get(expected_page_col) if expected_page_col else "")
        expected_pages_list = _expected_pages(expected_page_text)
        expected_sections = _expected_sections(expected_source)
        correlation_id = f"retrieval-eval-{test_id}-{uuid4()}"

        try:
            result = retrieval_service.retrieve(
                message=question,
                country=country,
                language=language,
                role=role,
                correlation_id=correlation_id,
            )
            snapshots = _snapshot_sources(result, args.top_k)
            status, matching_source_ranks, matching_page_ranks = _status_for(
                snapshots=snapshots,
                expected_source=expected_source,
                expected_pages_list=expected_pages_list,
                expected_sections=expected_sections,
            )
            top = snapshots[0] if snapshots else RetrievedSourceSnapshot(0, "", "", None, "", "")
            rows.append(
                RetrievalEvaluationRow(
                    test_id=test_id,
                    question=question,
                    country=country,
                    language=language,
                    role=role,
                    expected_source=expected_source,
                    expected_pages=", ".join(expected_pages_list),
                    status=status,
                    retrieval_confidence=round(float(result.confidence), 4),
                    top_title=top.title,
                    top_page=top.page,
                    top_score=top.score,
                    top_excerpt=top.excerpt,
                    source_count=len(snapshots),
                    matching_source_ranks=", ".join(map(str, matching_source_ranks)),
                    matching_page_ranks=", ".join(map(str, matching_page_ranks)),
                    sources_json=json.dumps([asdict(snapshot) for snapshot in snapshots], ensure_ascii=False),
                )
            )
        except Exception as exc:  # keep going so one AWS/test failure does not hide the rest
            rows.append(
                RetrievalEvaluationRow(
                    test_id=test_id,
                    question=question,
                    country=country,
                    language=language,
                    role=role,
                    expected_source=expected_source,
                    expected_pages=", ".join(expected_pages_list),
                    status="ERROR",
                    retrieval_confidence=0.0,
                    top_title="",
                    top_page="",
                    top_score=None,
                    top_excerpt="",
                    source_count=0,
                    matching_source_ranks="",
                    matching_page_ranks="",
                    sources_json="[]",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    return rows


def write_outputs(rows: list[RetrievalEvaluationRow], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    csv_path = output_dir / f"retrieval_eval_{timestamp}.csv"
    json_path = output_dir / f"retrieval_eval_{timestamp}.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))

    json_path.write_text(
        json.dumps([asdict(row) for row in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return csv_path, json_path


def print_summary(rows: list[RetrievalEvaluationRow]) -> None:
    from config import settings

    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    print()
    print("Retrieval evaluation summary")
    print("----------------------------")
    print(f"Knowledge Base ID: {settings.BEDROCK_KB_ID}")
    print(f"Data Source ID: {settings.BEDROCK_DATA_SOURCE_ID}")
    print(f"Total cases: {len(rows)}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ASK Vera retrieval against spreadsheet test cases.")
    parser.add_argument("--xlsx", type=Path, required=True, help="Path to the ASK Vera test workbook.")
    parser.add_argument("--sheet", default="Test Cases", help="Worksheet name containing test cases.")
    parser.add_argument("--country", default="CA", help="Default country code when the sheet is blank.")
    parser.add_argument("--language", default="en", help="Default language code when the sheet is blank.")
    parser.add_argument("--role", default="new_prospect", help="Default user role when the sheet is blank.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieved sources to store per test.")
    parser.add_argument("--kb-id", default="", help="Override the Bedrock Knowledge Base ID for this test run.")
    parser.add_argument(
        "--data-source-id",
        default="",
        help="Override the Bedrock data source ID for this test run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "retrieval_eval",
        help="Directory for CSV and JSON reports.",
    )
    parser.add_argument("--inspect", action="store_true", help="Only print workbook sheets/columns and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.xlsx.exists():
        print(f"Workbook not found: {args.xlsx}", file=sys.stderr)
        return 2
    if args.inspect:
        inspect_workbook(args.xlsx)
        return 0

    rows = evaluate(args)
    if not rows:
        print("No test rows were evaluated.", file=sys.stderr)
        return 1
    csv_path, json_path = write_outputs(rows, args.output_dir)
    print_summary(rows)
    print()
    print(f"CSV report: {csv_path}")
    print(f"JSON report: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
