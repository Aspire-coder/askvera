"""Summarize an offline live-vs-vNext retrieval comparison file."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# Support both `python -m scripts.evaluate_retrieval_shadow` and direct execution.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from app.retrieval.evaluation import promotion_gate, summarize_comparisons
except ModuleNotFoundError as exc:
    if exc.name != "botocore":
        raise
    module_spec = importlib.util.spec_from_file_location(
        "askvera_retrieval_evaluation", ROOT / "app" / "retrieval" / "evaluation.py"
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("could not load retrieval evaluation helpers") from exc
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    promotion_gate = module.promotion_gate
    summarize_comparisons = module.summarize_comparisons


def _load_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            records.append(value)
        return records

    if isinstance(parsed, dict):
        parsed = parsed.get("comparisons", parsed.get("records", []))
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("input must be a JSON array, JSONL objects, or an object with comparisons")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array, JSONL, or comparison wrapper")
    parser.add_argument("--output", type=Path, help="write the report to this JSON file")
    parser.add_argument("--min-same-section-rate", type=float, default=0.85)
    parser.add_argument("--min-evidence-overlap", type=float, default=0.70)
    parser.add_argument("--max-latency-ms", type=float, default=1500.0)
    parser.add_argument("--require-locale-gates", action="store_true")
    parser.add_argument("--enforce-gate", action="store_true")
    args = parser.parse_args()

    try:
        summary = summarize_comparisons(_load_records(args.input))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    passed, reasons = promotion_gate(
        summary,
        min_same_section_rate=args.min_same_section_rate,
        min_evidence_overlap=args.min_evidence_overlap,
        max_latency_ms=args.max_latency_ms,
        require_locale_gates=args.require_locale_gates,
    )
    report = {"summary": summary, "promotion_gate": {"passed": passed, "reasons": reasons}}
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if passed or not args.enforce_gate else 1


if __name__ == "__main__":
    sys.exit(main())
