"""Freeze captured selector inputs for isolated experiments; no AWS calls."""

import argparse
import hashlib
import json
from pathlib import Path


def extract_selector(row):
    matches = []
    for call in row.get("model_calls", []):
        inputs = call.get("input_text", {})
        if call.get("operation") != "Converse" or not isinstance(inputs, dict):
            continue
        systems = inputs.get("system", [])
        if any(isinstance(value, str) and value.startswith("You select evidence for ASK Vera.")
               for value in systems):
            matches.append(call)
    if len(matches) != 1:
        raise ValueError("Expected exactly one captured selector call")
    call = matches[0]
    inputs = call["input_text"]
    messages = inputs.get("messages", [])
    if not messages or not all(message.get("text") for message in messages):
        raise ValueError("Selector messages are missing")
    if not call.get("output_text"):
        raise ValueError("Selector output is missing")
    serialized = json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "id": row["id"], "country": row["country"], "question": row["question"],
        "language": row.get("language"), "side": row.get("side"),
        "repeat": row.get("repeat"), "model": call.get("model"),
        "input_sha256": hashlib.sha256(serialized).hexdigest(),
        "input_text": inputs, "recorded_output": call["output_text"],
        "expected_decision": None,
        "review_note": "Unscored capture, not ground truth. Verify against source before evaluation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = []
    for path in args.captures:
        record = extract_selector(json.loads(path.read_text(encoding="utf-8")))
        record["capture_file"] = path.name
        record["capture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(record)
    # Never overwrite evidence from a previous experiment.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump({"scope": __doc__, "cases": records}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Frozen {len(records)} selector captures; no model calls made.")


if __name__ == "__main__":
    main()
