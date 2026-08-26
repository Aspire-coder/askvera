"""Audit extracted retrieval chunks without creating or modifying an index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


MAX_CHARS_BY_PROFILE = {"current": 8_000, "vnext": 2_000}
MOJIBAKE_MARKERS = ("â€™", "â€œ", "â€�", "â€“", "â€”", "�")
DANGLING_FIELD_RE = re.compile(
    r"(?im)^\s*(?:telephone(?:\s+for\s+orders|\s+office)?|business\s+hours"
    r"(?:\s+office|\s+product\s+cent(?:er|re))?|email|website|"
    r"minimum\s+order\s+size(?:\s+fbo)?)\s*:\s*$"
)
MID_WORD_START_RE = re.compile(r"^[a-zà-öø-ÿ]")


def _issue(
    code: str,
    severity: str,
    record: dict[str, Any],
    detail: str,
) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "source_file": str(record.get("source_file", "")),
        "country": str(record.get("country", "")),
        "language": str(record.get("language", "")),
        "section_id": str(record.get("section_id", "")),
        "detail": detail,
    }


def audit_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:  # noqa: C901
    materialized = list(records)
    issues: list[dict[str, str]] = []
    identities: Counter[tuple[str, str, str, str]] = Counter()
    content_hashes: defaultdict[
        tuple[str, str, str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    sections_by_document: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)

    for record in materialized:
        identity = (
            str(record.get("source_file", "")),
            str(record.get("country", "")),
            str(record.get("language", "")),
            str(record.get("section_id", "")),
        )
        identities[identity] += 1
        sections_by_document[identity[:3]].add(identity[3])
        content = str(record.get("content", "")).strip()
        if content:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            content_hashes[(*identity[:3], content_hash)].append(record)

    for record in materialized:
        content = str(record.get("content", "")).strip()
        title = str(record.get("title", "")).strip()
        section_id = str(record.get("section_id", "")).strip()
        source_file = str(record.get("source_file", ""))
        country = str(record.get("country", ""))
        language = str(record.get("language", ""))
        document_key = (source_file, country, language)

        for field_name, value in (
            ("source_file", source_file),
            ("country", country),
            ("language", language),
            ("section_id", section_id),
            ("title", title),
            ("content", content),
        ):
            if not value:
                issues.append(
                    _issue(
                        "missing_required_field",
                        "error",
                        record,
                        f"Required field is empty: {field_name}",
                    )
                )

        start_page = record.get("start_page")
        end_page = record.get("end_page")
        if (
            isinstance(start_page, int)
            and isinstance(end_page, int)
            and (start_page < 1 or end_page < start_page)
        ):
            issues.append(
                _issue(
                    "invalid_page_range",
                    "error",
                    record,
                    f"Invalid page range: {start_page}-{end_page}",
                )
            )

        chunk_profile = str(record.get("chunk_profile", "current"))
        max_chars = MAX_CHARS_BY_PROFILE.get(chunk_profile)
        if max_chars and len(content) > max_chars:
            issues.append(
                _issue(
                    "oversized_chunk",
                    "error",
                    record,
                    f"{len(content)} characters exceeds {chunk_profile} limit {max_chars}",
                )
            )

        parent_id = str(record.get("parent_section_id", "")).strip()
        if parent_id and parent_id not in sections_by_document[document_key]:
            issues.append(
                _issue(
                    "parent_chunk_not_materialized",
                    "warning",
                    record,
                    f"Parent ID {parent_id!r} is not a standalone chunk in this export",
                )
            )

        found_markers = [marker for marker in MOJIBAKE_MARKERS if marker in content]
        if found_markers:
            issues.append(
                _issue(
                    "mojibake",
                    "error",
                    record,
                    f"Encoding artifacts found: {', '.join(found_markers)}",
                )
            )

        if DANGLING_FIELD_RE.search(content):
            issues.append(
                _issue(
                    "dangling_directory_field",
                    "error",
                    record,
                    "A structured directory label has no value on the same line",
                )
            )

        if (
            str(record.get("chunk_type", "")) == "section_part"
            and MID_WORD_START_RE.search(content)
        ):
            issues.append(
                _issue(
                    "possible_mid_sentence_start",
                    "warning",
                    record,
                    f"Section part starts with lowercase text: {content[:80]!r}",
                )
            )

    for identity, count in identities.items():
        if count <= 1:
            continue
        source_file, country, language, section_id = identity
        issues.append(
            {
                "code": "duplicate_section_id",
                "severity": "error",
                "source_file": source_file,
                "country": country,
                "language": language,
                "section_id": section_id,
                "detail": f"Section identity appears {count} times",
            }
        )

    for duplicate_records in content_hashes.values():
        unique_ids = sorted(
            {str(record.get("section_id", "")) for record in duplicate_records}
        )
        if len(unique_ids) <= 1:
            continue
        first = duplicate_records[0]
        issues.append(
            _issue(
                "duplicate_content",
                "warning",
                first,
                f"Identical content appears under section IDs: {', '.join(unique_ids)}",
            )
        )

    severity_counts = Counter(issue["severity"] for issue in issues)
    code_counts = Counter(issue["code"] for issue in issues)
    return {
        "summary": {
            "records": len(materialized),
            "errors": severity_counts["error"],
            "warnings": severity_counts["warning"],
            "issue_counts": dict(sorted(code_counts.items())),
        },
        "issues": issues,
    }


def _load_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.jsonl")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                records.append(
                    {
                        "source_file": str(path),
                        "section_id": f"line-{line_number}",
                        "_parse_error": str(exc),
                    }
                )
    return records


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Extracted chunk quality audit",
        "",
        f"- Records: {summary['records']}",
        f"- Errors: {summary['errors']}",
        f"- Warnings: {summary['warnings']}",
        "",
        "## Issue counts",
        "",
    ]
    if summary["issue_counts"]:
        lines.extend(
            f"- `{code}`: {count}"
            for code, count in summary["issue_counts"].items()
        )
    else:
        lines.append("- No issues detected.")
    lines.extend(["", "## Details", ""])
    if not report["issues"]:
        lines.append("No issues detected.")
    else:
        for issue in report["issues"]:
            lines.append(
                f"- **{issue['severity'].upper()} `{issue['code']}`** - "
                f"{issue['country']}/{issue['section_id']} in "
                f"`{issue['source_file']}`: {issue['detail']}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = audit_records(_load_records(args.source_root))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "chunk-quality-audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "chunk-quality-audit.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
