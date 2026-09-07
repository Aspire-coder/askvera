"""Offline captured-input checks; not model generation or production verification."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.retrieval.governing_rules import prioritize_activity_rule  # noqa: E402
from app.retrieval.source_binding import EvidenceSource, validate_support  # noqa: E402


def captured_rows(case):
    message = case["input_text"]["messages"][0]["text"][0]
    body = message.split("Candidate sections:\n", 1)[1].rsplit("\n\nSelect up to ", 1)[0]
    rows = []
    for block in re.split(r"(?m)(?=^Candidate \d+\n)", body):
        if not block.strip():
            continue
        header, content = block.split("\nText:\n", 1)
        fields = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        rows.append({"id": header.splitlines()[0], "section_id": fields["Section"],
                     "section_title": fields["Title"], "access_scope": fields["Access scope"],
                     "document_type": fields["Document type"], "content": content.strip()})
    return rows


def probe(case):
    rows = captured_rows(case)
    ordered = prioritize_activity_rule(case["question"], rows, case["language"])
    # These identities refer to frozen CAPTURES, not claimed live document versions.
    sources = [EvidenceSource("capture:" + case["capture_sha256"], case["input_sha256"],
                              row["section_id"], case["country"], row["content"]) for row in rows]
    result = {"id": case["id"], "question": case["question"],
              "before": [row["section_id"] for row in rows[:5]],
              "after": [row["section_id"] for row in ordered[:5]],
              "same_candidate_set": sorted(row["id"] for row in rows) == sorted(row["id"] for row in ordered)}
    rule_index = next(index for index, row in enumerate(rows) if row["section_id"] == "4.03")
    rule = sources[rule_index]
    other = next(source for source in sources if source.binding_id != rule.binding_id)
    # Membership proof deliberately uses literal captured text, not an invented gold answer.
    quote = rule.content
    bound = [{"source_id": rule.binding_id, "quote": quote}]
    result["valid_binding_survives_reorder"] = validate_support(bound, sources) == validate_support(bound, sources[::-1])
    try:
        validate_support([{"source_id": other.binding_id, "quote": quote}], sources)
    except ValueError:
        result["wrong_binding_rejected"] = True
    else:
        result["wrong_binding_rejected"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(args.fixture.read_text(encoding="utf-8"))
    results = [probe(case) for case in frozen["cases"]]
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump({"scope": __doc__, "results": results}, handle, ensure_ascii=False, indent=2)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
