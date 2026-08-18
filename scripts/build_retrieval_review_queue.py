"""Build a stratified human-review queue without inventing evidence labels."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def _tags(row: dict[str, Any]) -> str:
    question = str(row.get("question") or "")
    tags: list[str] = []
    if re.search(r"\d", question):
        tags.append("numeric")
    if re.search(r"\b(?:rm|fpc|fbo|pc|cc)\b", question, flags=re.I):
        tags.append("abbreviation")
    if re.search(r"\b\w*(?:maanger|recognzied|becoem|ssitant)\w*\b", question, flags=re.I):
        tags.append("misspelling")
    if len(question.split()) <= 5:
        tags.append("vague_or_short")
    return " | ".join(tags or ["general"])


def build_queue(
    inventory: list[dict[str, Any]],
    reviewed_case_ids: set[str],
    *,
    target: int,
) -> list[dict[str, Any]]:
    """Round-robin unreviewed unique questions across country/language groups."""
    seen_fingerprints: set[str] = set()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in inventory:
        # Retrieval relevance labels are meaningful only for knowledge-answer
        # cases. Conversation, safety, support and intentional fallback routes
        # have their own evaluation contracts and must not dilute recall.
        if str(row.get("evaluation_group") or "").strip() != "knowledge_answer":
            continue
        case_id = str(row.get("case_id") or "")
        fingerprint = str(row.get("question_fingerprint") or case_id)
        if case_id in reviewed_case_ids or fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        groups[(str(row.get("country") or ""), str(row.get("language") or ""))].append(row)

    selected: list[dict[str, Any]] = []
    keys = sorted(groups)
    while len(selected) < target and any(groups.values()):
        for key in keys:
            if groups[key] and len(selected) < target:
                selected.append(groups[key].pop(0))

    return [
        {
            "case_id": row.get("case_id", ""),
            "case_index": row.get("case_index", ""),
            "country": row.get("country", ""),
            "language": row.get("language", ""),
            "question": row.get("question", ""),
            "coverage_tags": _tags(row),
            "expected_document_ids": "",
            "expected_section_ids": "",
            "label_status": "needs_review",
            "reviewer": "",
            "review_notes": "",
        }
        for row in selected
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--target", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = [
        json.loads(line)
        for line in args.inventory.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with args.labels.open(newline="", encoding="utf-8-sig") as handle:
        reviewed = {
            str(row.get("case_id") or "")
            for row in csv.DictReader(handle)
            if str(row.get("label_status") or "").strip().lower() == "approved"
        }
    needed = max(0, int(args.target) - len(reviewed))
    queue = build_queue(inventory, reviewed, target=needed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(queue[0]) if queue else []
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(queue)
    coverage = sorted({(row["country"], row["language"]) for row in queue})
    print(
        json.dumps(
            {
                "approved": len(reviewed),
                "queued": len(queue),
                "target": args.target,
                "country_language_groups": len(coverage),
            },
            indent=2,
        )
    )
    print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
