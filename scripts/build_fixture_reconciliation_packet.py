"""Build an offline source-ground-truth reconciliation packet.

The packet compares held-out fixture labels and retrieved candidate IDs with
sections extracted directly from the supplied source PDFs. It does not infer or
rewrite ground truth. Cases with missing or competing passages remain marked for
review so false labels cannot silently become release criteria.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_paraphrase_profile_evaluation import (  # noqa: E402
    _directory_target_aliases,
    _normalized_country_label,
    _section_matches,
    normalize_fixture,
)


def load_source_rows(root: Path) -> list[dict[str, Any]]:
    """Load extracted policy and directory records from one audit folder."""
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain an object")
            payload["audit_source"] = str(path)
            rows.append(payload)
    if not rows:
        raise ValueError(f"No source JSONL files found under {root}")
    return rows


def _case_source_rows(case: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restrict policy evidence to the runtime market while retaining globals."""
    country = str(case.get("country") or "").upper()
    aliases = {country, "UK" if country == "GB" else country}
    return [
        row
        for row in rows
        if str(row.get("country") or "").upper() == "GLOBAL"
        or str(row.get("country") or "").upper() in aliases
    ]


def _compact_source(row: dict[str, Any], *, max_chars: int = 900) -> dict[str, Any]:
    content = " ".join(str(row.get("content") or "").split())
    return {
        "source_file": row.get("source_file", ""),
        "country": row.get("country", ""),
        "language": row.get("language", ""),
        "section_id": row.get("section_id", ""),
        "title": row.get("title", ""),
        "record_country": (row.get("metadata") or {}).get("record_country", ""),
        "start_page": row.get("start_page", ""),
        "end_page": row.get("end_page", ""),
        "content_excerpt": content[:max_chars],
    }


def _label_matches_source(
    row: dict[str, Any],
    label: str,
    case: dict[str, Any],
) -> bool:
    """Match real directory IDs to data-driven fixture country aliases."""
    if _section_matches(str(row.get("section_id") or ""), label):
        return True
    if str(case.get("scope") or "") != "global_directory":
        return False
    if not str(label).casefold().startswith("sponsoring-directory-"):
        return False
    target = str(case.get("target_country") or "")
    aliases = _directory_target_aliases(target, list(case.get("relevant_sections") or []))
    record_country = _normalized_country_label(
        str((row.get("metadata") or {}).get("record_country") or "")
    )
    return bool(record_country and record_country in aliases)


def reconcile_case(
    case: dict[str, Any],
    report_case: dict[str, Any] | None,
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return source existence and retrieved-passage evidence for one case."""
    available = _case_source_rows(case, source_rows)
    labels = list(case.get("relevant_sections") or [])
    label_matches = {
        label: [
            _compact_source(row)
            for row in available
            if _label_matches_source(row, str(label), case)
        ][:5]
        for label in labels
    }
    governing = str(case.get("governing_section") or "")
    governing_matches = [
        _compact_source(row)
        for row in available
        if governing and _label_matches_source(row, governing, case)
    ][:5]

    profiles: dict[str, Any] = {}
    for profile in ("current", "candidate"):
        candidates = list(
            (((report_case or {}).get(profile) or {}).get("candidate_metrics") or {}).get(
                "top_candidates"
            )
            or []
        )
        candidate_passages: list[dict[str, Any]] = []
        for candidate in candidates[:5]:
            candidate_id = str(candidate.get("id") or "")
            candidate_section = str(candidate.get("section_id") or "")
            matches = [
                row
                for row in available
                if str(row.get("section_id") or "") == candidate_section
                and (
                    not candidate_id
                    or str(row.get("id") or "") == candidate_id
                    or not row.get("id")
                )
            ]
            candidate_passages.append(
                {
                    "rank": candidate.get("rank"),
                    "reported_id": candidate_id,
                    "reported_section_id": candidate_section,
                    "source_matches": [_compact_source(row) for row in matches[:2]],
                }
            )
        profiles[profile] = candidate_passages

    missing_labels = [label for label, matches in label_matches.items() if not matches]
    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "country": case.get("country"),
        "language": case.get("language"),
        "scope": case.get("scope"),
        "expected_behavior": case.get("expected_behavior"),
        "relevant_sections": labels,
        "governing_section": governing or None,
        "label_matches": label_matches,
        "governing_matches": governing_matches,
        "missing_labels": missing_labels,
        "status": "source_ids_found" if not missing_labels and (not governing or governing_matches) else "needs_review",
        **profiles,
    }


def build_packet(
    fixture: dict[str, Any],
    report: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a packet without altering fixture labels."""
    normalized, changes = normalize_fixture(fixture)
    report_by_id = {str(row.get("id")): row for row in report.get("cases") or []}
    cases = [
        reconcile_case(case, report_by_id.get(str(case.get("id"))), source_rows)
        for case in normalized.get("cases") or []
    ]
    return {
        "normalization_changes": changes,
        "summary": {
            "cases": len(cases),
            "source_ids_found": sum(case["status"] == "source_ids_found" for case in cases),
            "needs_review": sum(case["status"] == "needs_review" for case in cases),
        },
        "cases": cases,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Held-out fixture source reconciliation",
        "",
        "> Read-only packet generated from source-PDF extraction. It does not rewrite fixture labels or declare semantic correctness.",
        "",
        f"- Cases: {packet['summary']['cases']}",
        f"- All declared source IDs found: {packet['summary']['source_ids_found']}",
        f"- Needs review: {packet['summary']['needs_review']}",
        "",
    ]
    for case in packet["cases"]:
        lines.extend(
            [
                f"## {case['id']} - {case['status']}",
                "",
                f"**Question:** {case['question']}",
                "",
                f"**Locale/scope:** {case['country']}/{case['language']} - {case['scope']}",
                "",
                f"**Declared labels:** {', '.join(case['relevant_sections']) or 'None'}",
                "",
                f"**Missing labels:** {', '.join(case['missing_labels']) or 'None'}",
                "",
            ]
        )
        for label, matches in case["label_matches"].items():
            lines.append(f"### Declared label `{label}`")
            lines.append("")
            if not matches:
                lines.extend(["No matching source section was extracted.", ""])
                continue
            for match in matches:
                lines.extend(
                    [
                        f"- `{match['section_id']}` - {match['title']} (pages {match['start_page']}-{match['end_page']})",
                        f"  - {match['content_excerpt']}",
                    ]
                )
            lines.append("")
        for profile in ("current", "candidate"):
            lines.extend([f"### {profile.title()} top retrieved passages", ""])
            for candidate in case[profile]:
                passages = candidate["source_matches"]
                if not passages:
                    lines.append(
                        f"- Rank {candidate['rank']}: `{candidate['reported_section_id']}` - source passage not found locally"
                    )
                    continue
                passage = passages[0]
                lines.extend(
                    [
                        f"- Rank {candidate['rank']}: `{passage['section_id']}` - {passage['title']}",
                        f"  - {passage['content_excerpt']}",
                    ]
                )
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    packet = build_packet(
        json.loads(args.fixture.read_text(encoding="utf-8")),
        json.loads(args.report.read_text(encoding="utf-8")),
        load_source_rows(args.source_root),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fixture-reconciliation.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "fixture-reconciliation.md").write_text(
        render_markdown(packet),
        encoding="utf-8",
    )
    print(json.dumps(packet["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
