"""Inspect a PDF before ingestion and report OCR or table-extraction needs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.document_preflight import analyze_pdf  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = analyze_pdf(args.pdf)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("Document ingestion preflight")
        print("----------------------------")
        print(f"PDF: {args.pdf}")
        print(f"Pages: {report.page_count}")
        print(f"Text pages: {report.text_page_count}")
        print(f"Empty or image-only pages: {report.empty_page_count}")
        print(f"Table-like pages: {report.table_like_page_count}")
        print(f"Extracted characters: {report.extracted_character_count}")
        print(f"OCR required: {report.requires_ocr}")
        print(f"Table-aware extraction recommended: {report.table_aware_extraction_recommended}")
    return 2 if report.requires_ocr else 0


if __name__ == "__main__":
    raise SystemExit(main())
