"""Compare grounding behaviour between two code versions on the same index.

The question this answers: does the stricter unit rule delete facts a reader
needed, and does it stop units that were being accepted without support?

Three arms, and they are not interchangeable:

    1. existing index + current code       (main)
    2. existing index + candidate code     (this branch)
    3. candidate ingestion + candidate code

Arms 1 and 2 differ only in code, so each is one capture run against the index
as it stands. Arm 3 needs documents re-ingested with heading-carrying chunking
and is therefore a separate, separately approved exercise - it changes stored
data, not just behaviour. Nothing here re-ingests anything.

    # on main
    python scripts/run_grounding_comparison.py --capture out/current.json \\
        --i-have-approval-for-paid-model-calls
    # on the candidate branch
    python scripts/run_grounding_comparison.py --capture out/candidate.json \\
        --i-have-approval-for-paid-model-calls

    # offline, on the candidate branch (its rule is the oracle - see below)
    python scripts/run_grounding_comparison.py --evaluate out/current.json
    python scripts/run_grounding_comparison.py --evaluate out/candidate.json
    python scripts/run_grounding_comparison.py --compare out/current.json out/candidate.json

On the oracle. There is no ground truth for "was this figure really supported",
so one fixed rule is applied to both arms' answers: the structural rule in the
checkout doing the evaluating. Run --evaluate from the candidate branch and it
measures, for each arm, how many accepted figures that rule judges unsupported.
That is a comparison against a stated standard, not against truth, and the
figures whose decision CHANGED between arms are listed individually so a person
can adjudicate them. Adjudicating that list is the actual result; the totals
are how you find it.

No model calls happen without --i-have-approval-for-paid-model-calls.
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

DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "benchmark_cases.json"


def _figures(answer: str) -> list[str]:
    """Every figure in an answer, by the validator's own notion of a figure.

    Deliberately the validator's extractor rather than a regex of this
    script's own. A second definition of "a figure" would drift from the one
    that decides removals, and then the denominator would stop matching the
    numerator.
    """
    from app.validation.validators.numeric_grounding_validator import _extract_claims

    found: list[str] = []
    for claim in _extract_claims(answer or ""):
        if claim.number not in found:
            found.append(claim.number)
    return found


def capture(fixture: Path, limit: int, repeat: int) -> dict[str, Any]:
    """Run the cases through the real pipeline and record what came back.

    This is the paid step. It records the retrieved documents as well as the
    answer, because the offline evaluation needs the evidence the answer was
    built from, and the same capture is then read by whichever checkout is
    doing the evaluating.
    """
    import scripts.run_benchmark as benchmark
    import scripts.run_retrieval_canary as canary

    cases, fixture_hash = benchmark.load_fixture(fixture)
    if limit:
        cases = cases[:limit]

    records: list[dict[str, Any]] = []
    for sequence, case in enumerate(cases, start=1):
        for attempt in range(repeat):
            run = canary.run_pipeline_capture(case, sequence * 100 + attempt)
            response = run.response
            documents = run.retrieval.documents if run.retrieval else []
            metadata = response.metadata or {}
            records.append(
                {
                    "id": case.get("id"),
                    "attempt": attempt,
                    "question": case.get("question", ""),
                    "language": case.get("language", ""),
                    "country": case.get("country", ""),
                    "answer": response.answer or "",
                    "abstained": bool(metadata.get("fallback")),
                    # What this arm's own repair removed. Compared across arms
                    # this is the headline difference.
                    "removed_numeric_claims": list(run.removed_numeric_claims or []),
                    "citations": [
                        {
                            "section": str((citation or {}).get("section") or ""),
                            "country": str((citation or {}).get("country") or ""),
                        }
                        for citation in (response.citations or [])
                    ],
                    "expect_sections": case.get("expect_sections", []),
                    "expect_contains": case.get("expect_contains", []),
                    # The evidence, so evaluation needs no index and no model.
                    "documents": [
                        {
                            "content": str(getattr(document, "content", "") or ""),
                            "title": str(getattr(document, "title", "") or ""),
                            "country": str(getattr(document, "country", "") or ""),
                            "section_id": str(
                                (getattr(document, "metadata", {}) or {}).get("section_id") or ""
                            ),
                        }
                        for document in documents
                    ],
                }
            )
    return {"fixture_sha256": fixture_hash, "case_count": len(cases), "runs": records}


def _rehydrate(documents: list[dict[str, Any]]) -> list[Any]:
    from app.retrieval.models import RetrievedDocument

    return [
        RetrievedDocument(
            id=document.get("section_id") or "section",
            title=document.get("title", ""),
            content=document.get("content", ""),
            source="",
            page="",
            metadata={"section_id": document.get("section_id", "")},
        )
        for document in documents
    ]


def evaluate(capture_path: Path) -> dict[str, Any]:
    """Apply this checkout's rule to a capture, as a fixed oracle over both arms."""
    from app.validation.validators.numeric_grounding_validator import (
        numbers_present_in_sources,
        unsupported_numeric_claims,
    )
    import scripts.run_benchmark as benchmark

    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    per_run: list[dict[str, Any]] = []

    for record in payload["runs"]:
        documents = _rehydrate(record["documents"])
        answer = record["answer"]

        # Facts this arm removed, split by whether the evidence contains them.
        # A number the evidence does not hold was invented and removing it is
        # the system working; one it does hold was real, and the reader lost it.
        removed = list(record.get("removed_numeric_claims") or [])
        presence = numbers_present_in_sources(removed, documents) if removed else {}
        removed_present = [number for number, present in presence.items() if present]

        # Figures this arm kept that the oracle judges unsupported.
        accepted_unsupported = [
            claim.number for claim in unsupported_numeric_claims(answer, documents)
        ]

        cited = set(
            benchmark._section_keys(
                [(c["section"], c["country"]) for c in record.get("citations") or []]
            )
        )
        required = list(record.get("expect_sections") or [])
        per_run.append(
            {
                "id": record["id"],
                "attempt": record["attempt"],
                "figures": _figures(answer),
                "removed": removed,
                "removed_but_present_in_source": removed_present,
                "accepted_but_unsupported_by_oracle": accepted_unsupported,
                # Completeness: the facts the case says the answer must carry.
                "missing_expected_text": [
                    phrase
                    for phrase in (record.get("expect_contains") or [])
                    if phrase.lower() not in answer.lower()
                ],
                "uncited_required_sections": [
                    section for section in required if not benchmark._is_cited(section, cited)
                ],
                "abstained": bool(record.get("abstained")),
                "answer_characters": len(answer),
            }
        )

    return {
        "capture": str(capture_path),
        "fixture_sha256": payload.get("fixture_sha256", ""),
        "totals": {
            "runs": len(per_run),
            "correct_facts_removed": sum(
                len(run["removed_but_present_in_source"]) for run in per_run
            ),
            "invented_facts_removed": sum(
                len(run["removed"]) - len(run["removed_but_present_in_source"])
                for run in per_run
            ),
            "accepted_but_unsupported_by_oracle": sum(
                len(run["accepted_but_unsupported_by_oracle"]) for run in per_run
            ),
            "runs_missing_expected_text": sum(
                1 for run in per_run if run["missing_expected_text"]
            ),
            "runs_with_uncited_required_section": sum(
                1 for run in per_run if run["uncited_required_sections"]
            ),
            "abstentions": sum(1 for run in per_run if run["abstained"]),
        },
        "runs": per_run,
    }


def compare(first: Path, second: Path) -> dict[str, Any]:
    """Diff two evaluations and list every figure whose decision changed.

    The totals say whether something moved. The changed list is what a person
    actually reads: each entry is one figure that one arm kept and the other
    removed, with the case it came from.
    """
    left = evaluate(first)
    right = evaluate(second)

    left_runs = {(run["id"], run["attempt"]): run for run in left["runs"]}
    changed: list[dict[str, Any]] = []
    for run in right["runs"]:
        other = left_runs.get((run["id"], run["attempt"]))
        if other is None:
            continue
        newly_removed = sorted(set(run["removed"]) - set(other["removed"]))
        newly_kept = sorted(set(other["removed"]) - set(run["removed"]))
        if newly_removed or newly_kept:
            changed.append(
                {
                    "id": run["id"],
                    "attempt": run["attempt"],
                    "removed_only_by_second": newly_removed,
                    "removed_only_by_first": newly_kept,
                    # The half that matters most: a figure the second arm
                    # removed although the evidence contains it.
                    "newly_removed_but_present_in_source": [
                        number
                        for number in newly_removed
                        if number in run["removed_but_present_in_source"]
                    ],
                }
            )

    return {
        "first": left["totals"],
        "second": right["totals"],
        "changed_decisions": changed,
        "note": (
            "Totals locate the movement; the changed_decisions list is the result. "
            "Each entry needs a person to say whether the figure was really "
            "supported by the section it came from. The oracle is this checkout's "
            "rule, not ground truth."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="Run the pipeline and write a capture here.")
    parser.add_argument("--evaluate", type=Path, help="Score a capture offline.")
    parser.add_argument("--compare", type=Path, nargs=2, help="Diff two captures.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument(
        "--i-have-approval-for-paid-model-calls",
        action="store_true",
        help="Required for --capture. Capturing calls Bedrock once per case per repeat.",
    )
    args = parser.parse_args()

    if args.capture:
        if not args.i_have_approval_for_paid_model_calls:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason": (
                            "--capture makes paid model calls. Re-run with "
                            "--i-have-approval-for-paid-model-calls once that is approved."
                        ),
                    },
                    indent=2,
                )
            )
            return 2
        if args.load_ssm:
            from services.aws_clients import init_aws_clients

            init_aws_clients()
        payload = capture(args.fixture, args.limit, args.repeat)
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"status": "captured", "runs": len(payload["runs"])}, indent=2))
        return 0

    if args.evaluate:
        print(json.dumps(evaluate(args.evaluate)["totals"], indent=2))
        return 0

    if args.compare:
        print(json.dumps(compare(args.compare[0], args.compare[1]), indent=2))
        return 0

    parser.error("one of --capture, --evaluate or --compare is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
