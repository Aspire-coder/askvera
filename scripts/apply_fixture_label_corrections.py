"""Apply reviewed label-only corrections to a retrieval evaluation fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ALLOWED_FIELDS = {
    "relevant_sections",
    "relevant_section_ids",
    "governing_section",
    "scope",
    "notes",
    "label_verified",
    "verified_against",
    "required_source_files",
    "target_country",
}


def apply_corrections(
    fixture: dict[str, Any], corrections_document: dict[str, Any]
) -> dict[str, Any]:
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Fixture must contain a cases list")

    corrections = corrections_document.get("corrections")
    if not isinstance(corrections, dict):
        raise ValueError("Corrections document must contain a corrections object")

    case_by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
    unknown_case_ids = sorted(set(corrections) - set(case_by_id))
    if unknown_case_ids:
        raise ValueError(f"Unknown correction case IDs: {', '.join(unknown_case_ids)}")

    for case_id, updates in corrections.items():
        if not isinstance(updates, dict):
            raise ValueError(f"Corrections for {case_id} must be an object")
        unsupported_fields = sorted(set(updates) - ALLOWED_FIELDS)
        if unsupported_fields:
            raise ValueError(
                f"Unsupported correction fields for {case_id}: "
                f"{', '.join(unsupported_fields)}"
            )
        case_by_id[case_id].update(updates)
        case_by_id[case_id]["label_verified"] = True

    fixture["label_corrections_version"] = corrections_document.get("version", "")
    fixture["label_corrections_applied"] = sorted(corrections)
    return fixture


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    corrections = json.loads(args.corrections.read_text(encoding="utf-8"))
    corrected = apply_corrections(fixture, corrections)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(corrected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    print(f"SHA-256: {_sha256(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
