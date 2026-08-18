"""Create deterministic train, validation, and holdout splits for reviewed labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def _group_key(row: dict[str, str]) -> str:
    sections = "|".join(sorted(value.strip().casefold() for value in row.get("expected_section_ids", "").split(";") if value.strip()))
    documents = "|".join(sorted(value.strip().casefold() for value in row.get("expected_document_names", "").split(";") if value.strip()))
    return "|".join(
        (
            row.get("country", "").strip().casefold(),
            row.get("language", "").strip().casefold(),
            sections or documents or row.get("case_id", "").strip(),
        )
    )


def _split_for(group_key: str) -> str:
    value = int(hashlib.sha256(group_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if value < 60:
        return "train"
    if value < 80:
        return "validation"
    return "holdout"


def split_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        enriched = dict(row)
        group_key = _group_key(row)
        enriched["split_group"] = group_key
        enriched["split"] = _split_for(group_key)
        result.append(enriched)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.labels.open(newline="", encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("label_status", "").casefold() == "approved"]
    output_rows = split_rows(rows)
    fields = list(output_rows[0]) if output_rows else ["case_id", "split_group", "split"]
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)
    counts = {split: sum(row["split"] == split for row in output_rows) for split in ("train", "validation", "holdout")}
    print({"approved_cases": len(output_rows), "groups": len({row["split_group"] for row in output_rows}), "counts": counts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
