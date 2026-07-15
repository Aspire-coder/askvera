"""Evaluate local keyword/BM25-style section search against the ASK Vera workbook.

This approximates the lexical side of an OpenSearch hybrid search without AWS.
It helps decide whether a controlled search index is likely to outperform a
managed vector-only retrieval path for exact policy questions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.I)
SECTION_RE = re.compile(r"\b(?:sec|section)\.?\s*([0-9]+(?:\.[0-9]+)?[a-z]?)", re.I)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "who",
}

QUESTION_COLUMNS = ["test question", "question", "prompt", "user question"]
TEST_ID_COLUMNS = ["test id", "id", "case id", "test case id"]
EXPECTED_SOURCE_COLUMNS = [
    "expected citation / source (ca policy may 2026)",
    "expected citation",
    "expected source",
    "source",
    "document",
    "expected document",
]
TEST_TYPE_COLUMNS = ["test type", "retrieval test type", "evaluation type", "qa type"]


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value).lower())


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


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOPWORDS]


def _expected_sections(value: str) -> list[str]:
    return [section.lower() for section in SECTION_RE.findall(value)]


def _section_matches(expected_sections: list[str], section_id: str, text: str) -> bool:
    haystack = f"{section_id} {text}".lower()
    for section in expected_sections:
        base = re.sub(r"[a-z]$", "", section)
        if section in haystack or base in haystack:
            return True
        if re.match(rf"^{re.escape(base)}[a-z]$", section_id.lower()):
            return True
    return False


def _important_phrases(query: str) -> list[str]:
    tokens = _tokens(query)
    phrases: list[str] = []
    for size in [4, 3, 2]:
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[index : index + size])
            if len(phrase) >= 8:
                phrases.append(phrase)
    return phrases


def _load_sections(path: Path) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                section = json.loads(line)
                section["search_text"] = " ".join(
                    [
                        _text(section.get("section_id")),
                        _text(section.get("title")),
                        _text(section.get("content")),
                    ]
                )
                sections.append(section)
    return sections


def _idf(sections: list[dict[str, Any]]) -> dict[str, float]:
    count = max(1, len(sections))
    frequencies: Counter[str] = Counter()
    for section in sections:
        frequencies.update(set(_tokens(_text(section.get("search_text")))))
    return {token: math.log((1 + count) / (1 + frequency)) + 1 for token, frequency in frequencies.items()}


def search_sections(query: str, sections: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    idf = _idf(sections)
    query_tokens = _tokens(query)
    phrases = _important_phrases(query)
    scored: list[tuple[float, dict[str, Any]]] = []

    for section in sections:
        search_text = _text(section.get("search_text")).lower()
        section_tokens = Counter(_tokens(search_text))
        score = 0.0
        for token in query_tokens:
            if token in section_tokens:
                score += idf.get(token, 1.0) * (1 + math.log(1 + section_tokens[token]))
        for phrase in phrases:
            if phrase in search_text:
                score += 10 + sum(idf.get(token, 1.0) for token in _tokens(phrase))
        title = _text(section.get("title")).lower()
        for token in query_tokens:
            if token in _tokens(title):
                score += idf.get(token, 1.0) * 1.5
        if score > 0:
            scored.append((round(score, 4), section))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for rank, (score, section) in enumerate(scored[:top_k], start=1):
        results.append({"rank": rank, "score": score, **section})
    return results


def _load_dataframe(path: Path, sheet_name: str):
    import pandas as pd

    return pd.read_excel(path, sheet_name=sheet_name)


def evaluate(args: argparse.Namespace) -> list[dict[str, Any]]:
    sections = _load_sections(args.sections_jsonl)
    frame = _load_dataframe(args.xlsx, args.sheet)
    columns = [str(column) for column in frame.columns]

    question_col = _find_column(columns, QUESTION_COLUMNS)
    test_id_col = _find_column(columns, TEST_ID_COLUMNS)
    expected_col = _find_column(columns, EXPECTED_SOURCE_COLUMNS)
    test_type_col = _find_column(columns, TEST_TYPE_COLUMNS)
    if not question_col or not expected_col:
        raise RuntimeError(f"Could not find required columns. Columns: {columns}")

    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        question = _text(row.get(question_col))
        if not question:
            continue
        test_type = _text(row.get(test_type_col) if test_type_col else "")
        expected_source = _text(row.get(expected_col))
        if test_type.lower() != "retrieval":
            rows.append(
                {
                    "test_id": _text(row.get(test_id_col) if test_id_col else "", f"row-{index + 2}"),
                    "test_type": test_type,
                    "question": question,
                    "expected_source": expected_source,
                    "status": "SKIP_NON_RETRIEVAL_EXPECTATION",
                    "top_section": "",
                    "top_title": "",
                    "top_score": "",
                    "matching_ranks": "",
                }
            )
            continue

        expected_sections = _expected_sections(expected_source)
        results = search_sections(question, sections, args.top_k)
        matching_ranks = [
            result["rank"]
            for result in results
            if _section_matches(expected_sections, _text(result.get("section_id")), _text(result.get("title")) + " " + _text(result.get("content")))
        ]
        top = results[0] if results else {}
        rows.append(
            {
                "test_id": _text(row.get(test_id_col) if test_id_col else "", f"row-{index + 2}"),
                "test_type": test_type,
                "question": question,
                "expected_source": expected_source,
                "status": "PASS_SECTION" if matching_ranks else "FAIL_SECTION_NOT_FOUND",
                "top_section": _text(top.get("section_id")),
                "top_title": _text(top.get("title")),
                "top_score": top.get("score", ""),
                "matching_ranks": ", ".join(map(str, matching_ranks)),
            }
        )
    return rows


def write_outputs(rows: list[dict[str, Any]], output_dir: Path) -> Path:
    from datetime import datetime, timezone

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"local_section_eval_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    return path


def print_summary(rows: list[dict[str, Any]]) -> None:
    counts = Counter(row["status"] for row in rows)
    retrieval_rows = [row for row in rows if row["test_type"].lower() == "retrieval"]
    retrieval_counts = Counter(row["status"] for row in retrieval_rows)
    print()
    print("Local section search evaluation summary")
    print("---------------------------------------")
    print(f"Total cases: {len(rows)}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    print()
    print("Retrieval-only score")
    print("--------------------")
    print(f"Retrieval cases: {len(retrieval_rows)}")
    for status, count in sorted(retrieval_counts.items()):
        print(f"{status}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sections-jsonl", type=Path, required=True)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--sheet", default="Test Cases")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/local_section_eval"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = evaluate(args)
    output = write_outputs(rows, args.output_dir)
    print_summary(rows)
    print()
    print(f"CSV report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
