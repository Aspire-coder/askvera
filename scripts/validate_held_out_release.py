"""Refuse to treat an unfinished fixture as held-out release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


MINIMUMS = {
    "local_policy": 8, "global_directory": 8, "cross_market_refusal": 3,
    "follow_up": 3, "non_english": 6, "new_country": 12,
    "numeric_role_condition": 8,
}


def validate(payload: dict[str, Any]) -> list[str]:  # noqa: C901
    cases = payload.get("cases")
    if payload.get("schema_version") != 1 or not isinstance(cases, list):
        return ["Fixture must use schema_version 1 and contain a cases list."]
    errors: list[str] = []
    if payload.get("status") != "approved_and_frozen":
        errors.append("Fixture is not approved_and_frozen.")
    if len(cases) < 24:
        errors.append(f"At least 24 cases are required; found {len(cases)}.")
    identifiers: set[str] = set()
    coverage: Counter[str] = Counter()
    countries: set[str] = set()
    for number, case in enumerate(cases, 1):
        label = str(case.get("id") or f"case {number}") if isinstance(case, dict) else f"case {number}"
        if not isinstance(case, dict):
            errors.append(f"{label}: case is not an object.")
            continue
        if not str(case.get("id") or "").strip() or case["id"] in identifiers:
            errors.append(f"{label}: id must be non-empty and unique.")
        identifiers.add(case.get("id", ""))
        if case.get("evaluation_set") != "held_out":
            errors.append(f"{label}: evaluation_set must be held_out.")
        for field in ("question", "country", "language", "role", "intent_group", "source_evidence", "provenance"):
            if not str(case.get(field) or "").strip():
                errors.append(f"{label}: missing {field}.")
        expected = case.get("expected")
        if not isinstance(expected, dict) or expected.get("kind") not in {"answer", "abstain"}:
            errors.append(f"{label}: expected.kind must be answer or abstain.")
        elif expected.get("kind") == "answer" and (not expected.get("required_sections") or expected.get("must_cite") is not True):
            errors.append(f"{label}: answer case needs a cited required source section.")
        review = case.get("independent_review")
        if not isinstance(review, dict) or not all(str(review.get(key) or "").strip() for key in ("source_selector", "question_author", "approved_at")):
            errors.append(f"{label}: independent review is incomplete.")
        tags = case.get("coverage")
        if not isinstance(tags, list):
            errors.append(f"{label}: coverage must be a list.")
            tags = []
        for tag in set(map(str, tags)):
            coverage[tag] += 1
        if "new_country" in tags:
            countries.add(str(case.get("country") or "").upper())
    for dimension, minimum in MINIMUMS.items():
        actual = len(countries) if dimension == "new_country" else coverage[dimension]
        if actual < minimum:
            errors.append(f"Coverage {dimension} requires {minimum}; found {actual}.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    raw = args.fixture.read_bytes()
    errors = validate(json.loads(raw))
    if errors:
        print("NOT READY", *[f"- {error}" for error in errors], sep="\n")
        return 1
    print(f"READY sha256={hashlib.sha256(raw).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
