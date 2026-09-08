"""Compare grounding behaviour between two code versions on the same evidence.

The question: does the stricter unit rule change which figures survive, and in
which direction? Both directions need measuring separately. Removing a figure
the evidence contains and keeping one the evidence does not support are
different failures with different costs, and neither is universally worse than
the other - that depends on the question, the market and who is reading.

TWO SEPARATE EXERCISES, and conflating them is how generation noise gets
reported as a validator effect.

  A. repair-only comparison (offline, free, isolates the change)
     Freeze one set of pre-repair answers and their evidence. Score that same
     frozen set with each arm's validator. Every difference is the validator,
     because the input is byte-identical.

  B. end-to-end evaluation (paid, includes generation variance)
     Run the full pipeline per arm. Answers differ for reasons that have
     nothing to do with grounding, so this measures the system, not the rule.

Do A first. It is free once the freeze exists and it answers the narrow
question. Do B only if A shows something worth spending on.

    # once, paid: pre-repair answers plus the evidence they were built from
    python scripts/run_grounding_comparison.py --preflight
    python scripts/run_grounding_comparison.py --freeze out/frozen.json \\
        --load-ssm --i-have-approval-for-paid-model-calls --max-turns 6

    # free, once per arm, against isolated worktrees
    python scripts/run_grounding_comparison.py --score out/frozen.json \\
        --app-root ../askvera-main      --out out/main.json
    python scripts/run_grounding_comparison.py --score out/frozen.json \\
        --app-root .                    --out out/candidate.json
    python scripts/run_grounding_comparison.py --compare out/main.json out/candidate.json

Scoring loads the application code from --app-root and reports the file it
actually loaded, so an arm that silently scored itself is visible rather than
assumed. The harness is one version - this file - deliberately: a baseline that
runs a different harness measures the harness too.

On labels. The scoring rule is a stated standard, not ground truth. This
reports whether a figure appears in the evidence, which is mechanical, and
whether a rule accepted it, which is that rule's opinion. Neither says the
figure was correct. Every changed decision needs a person to open the section
and adjudicate it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(__file__).resolve().parents[1]
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

DEFAULT_FIXTURE = HARNESS_ROOT / "tests" / "fixtures" / "benchmark_cases.json"


# --- fixture reading -------------------------------------------------------
#
# The benchmark stores expectations in case["expected"], and a conversation
# case carries its own per-turn expectations. An earlier version of this script
# read case["expect_contains"] and case["expect_sections"], which do not exist
# in the fixture at all - so completeness and citation metrics were empty for
# every case and reported as zero problems. Reading the wrong field is worse
# than not measuring, because it looks like a measurement.


def _turns(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Every turn a case puts through the pipeline, in order.

    A conversation case is its prior turns PLUS its own question, which is the
    final turn - see _score_prior_turns in run_benchmark, which scores
    case["conversation"] against the prior responses and the case's own
    expectation against the last. Returning only the conversation turns
    undercounted the fixture by one execution and, worse, would have scored the
    answer against the wrong turn's expectation.

    Note the two fixtures disagree about what "conversation" holds: the canary
    fixture uses a list of strings, the benchmark a list of objects carrying
    per-turn expectations. Both are handled, because a harness that silently
    reads one shape as the other produces numbers with nothing behind them.
    """
    turns: list[dict[str, Any]] = []
    for turn in case.get("conversation") or []:
        if isinstance(turn, str):
            turns.append({"question": turn, "expected": {}})
        else:
            turns.append(
                {
                    "question": str(turn.get("question") or ""),
                    "expected": dict(turn.get("expected") or {}),
                }
            )
    turns.append(
        {
            "question": str(case.get("question") or ""),
            "expected": dict(case.get("expected") or {}),
        }
    )
    return turns


def _expectations(expected: dict[str, Any]) -> dict[str, Any]:
    """The fixture's expectation block, with its own field names and types.

    must_cite is a BOOLEAN - "the answer must carry a citation" - and not a
    list of sections. Treating it as a list raised a TypeError on the first
    preflight, which is the cheapest possible place to find it. The sections a
    citation must cover are required_sections, and must_cite is what says
    whether citing them is required at all.
    """
    return {
        "kind": str(expected.get("kind") or ""),
        "must_contain": list(expected.get("must_contain") or []),
        "must_not_contain": list(expected.get("must_not_contain") or []),
        "required_sections": [str(value) for value in (expected.get("required_sections") or [])],
        "must_cite": bool(expected.get("must_cite")),
    }


def preflight(fixture: Path, repeat: int, arms: int) -> dict[str, Any]:
    """What a run would cost, before anyone approves it. Makes no calls."""
    import scripts.run_benchmark as benchmark

    cases, fixture_hash = benchmark.load_fixture(fixture)
    turn_counts = {case["id"]: len(_turns(case)) for case in cases}
    turns = sum(turn_counts.values())
    with_expectations = sum(
        1
        for case in cases
        for turn in _turns(case)
        if any(
            _expectations(turn["expected"])[key]
            for key in ("must_contain", "must_not_contain", "required_sections")
        )
    )
    return {
        "fixture": str(fixture),
        "fixture_sha256": fixture_hash,
        "cases": len(cases),
        "turns": turns,
        "conversation_cases": {k: v for k, v in turn_counts.items() if v > 1},
        "repeat": repeat,
        "arms": arms,
        "turn_executions": turns * repeat * arms,
        "turns_carrying_expectations": with_expectations,
        "note": (
            "turn_executions counts turns put through the pipeline. Paid model "
            "calls per turn are not 1: routing, planning, evidence selection, "
            "generation, retries and repair each may call. Treat this as a "
            "lower bound and measure the real rate on a --max-turns run first."
        ),
    }


# --- freezing --------------------------------------------------------------


def freeze(fixture: Path, repeat: int, max_turns: int, checkpoint: Path) -> dict[str, Any]:
    """Capture pre-repair answers and the evidence behind them, once.

    Numeric grounding is neutralised for the duration so the pipeline returns
    what the model produced rather than what repair left. That is the whole
    point: both arms must score the same input, and an answer that one arm's
    repair has already trimmed is not the same input.

    Writes a checkpoint after every turn, so an interrupted run is resumable
    and a bounded run is genuinely bounded rather than bounded on paper.
    """
    from app.validation.validators import numeric_grounding_validator as grounding
    import scripts.run_benchmark as benchmark
    import scripts.run_retrieval_canary as canary

    cases, fixture_hash = benchmark.load_fixture(fixture)

    original = grounding.unsupported_numeric_claims
    grounding.unsupported_numeric_claims = lambda answer, documents: []
    records: list[dict[str, Any]] = []
    executed = 0
    try:
        for sequence, case in enumerate(cases, start=1):
            turns = _turns(case)
            if max_turns and executed + len(turns) * repeat > max_turns:
                break
            for attempt in range(repeat):
                run = canary.run_pipeline_capture(case, sequence * 100 + attempt)
                response = run.response
                documents = run.retrieval.documents if run.retrieval else []
                executed += len(turns)
                records.append(
                    {
                        "id": case.get("id"),
                        "attempt": attempt,
                        "turns": len(turns),
                        "language": case.get("language", ""),
                        "country": case.get("country", ""),
                        # Pre-repair, because grounding is neutralised above.
                        "answer": response.answer or "",
                        "abstained": bool((response.metadata or {}).get("fallback")),
                        "citations": [
                            {
                                "section": str((citation or {}).get("section") or ""),
                                "country": str((citation or {}).get("country") or ""),
                            }
                            for citation in (response.citations or [])
                        ],
                        # The final turn's expectations, which is what the
                        # answer is judged against.
                        "expected": _expectations(turns[-1]["expected"]),
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
                payload = {
                    "fixture_sha256": fixture_hash,
                    "turn_executions": executed,
                    "grounding_neutralised": True,
                    "runs": records,
                }
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    finally:
        grounding.unsupported_numeric_claims = original

    return {
        "fixture_sha256": fixture_hash,
        "turn_executions": executed,
        "grounding_neutralised": True,
        "runs": records,
    }


# --- scoring ---------------------------------------------------------------


def _load_application(app_root: Path):
    """Import the grounding validator from a specific checkout, and prove it.

    Two arms that both scored the candidate would agree perfectly and mean
    nothing, so the module's resolved path is returned and reported.
    """
    resolved = app_root.resolve()
    if not (resolved / "app" / "validation" / "validators").is_dir():
        raise SystemExit(f"--app-root does not look like a checkout: {resolved}")

    # Python will not re-import a package that is already loaded, so if some
    # other checkout's `app` is in sys.modules the --app-root asked for is a
    # fiction. Refuse when that is the case rather than reporting numbers from
    # the wrong tree; allow it when the loaded package is already the one
    # requested, which is what happens under a test runner.
    loaded_package = sys.modules.get("app")
    if loaded_package is not None:
        roots = [Path(path).resolve().parent for path in getattr(loaded_package, "__path__", [])]
        if not any(root == resolved for root in roots):
            raise SystemExit(
                "an application package from a different checkout is already "
                f"imported ({roots or 'unknown'}); run --score in a fresh process "
                "so --app-root decides which code loads"
            )
    else:
        sys.path.insert(0, str(resolved))

    from app.validation.validators import numeric_grounding_validator as grounding

    loaded = Path(grounding.__file__).resolve()
    if resolved not in loaded.parents:
        raise SystemExit(
            f"--app-root was {resolved} but the validator loaded from {loaded}"
        )
    return grounding, loaded


def _rehydrate(grounding_module, documents: list[dict[str, Any]]) -> list[Any]:
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


def _cited_keys(citations: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for citation in citations:
        section = str(citation.get("section") or "")
        country = str(citation.get("country") or "")
        if section:
            keys.add(section)
            if country:
                keys.add(f"{country.upper()}:{section}")
    return keys


def _is_cited(required: str, cited: set[str]) -> bool:
    if required in cited:
        return True
    # A cited descendant satisfies a required ancestor section.
    return any(key.startswith(f"{required}-") or key.startswith(f"{required}.") for key in cited)


def score(frozen_path: Path, app_root: Path) -> dict[str, Any]:
    """Apply one arm's rule to the frozen set. No model calls, no index."""
    grounding, loaded_from = _load_application(app_root)
    payload = json.loads(frozen_path.read_text(encoding="utf-8"))

    per_run: list[dict[str, Any]] = []
    for record in payload["runs"]:
        documents = _rehydrate(grounding, record["documents"])
        answer = record["answer"]
        expected = record.get("expected") or {}

        removed = [claim.number for claim in grounding.unsupported_numeric_claims(answer, documents)]
        presence = grounding.numbers_present_in_sources(removed, documents) if removed else {}
        cited = _cited_keys(record.get("citations") or [])
        # Citation correctness is only asserted where the case asks for it.
        # required_sections names the passages; must_cite says whether the
        # answer has to cite them. Scoring citations on a case that does not
        # require them would invent failures.
        required = (
            list(expected.get("required_sections") or [])
            if expected.get("must_cite")
            else []
        )

        per_run.append(
            {
                "id": record["id"],
                "attempt": record["attempt"],
                "removed": removed,
                # Mechanical: does the string occur in the evidence. NOT a
                # judgement that the removal was wrong - the figure may appear
                # in an unrelated row.
                "removed_and_present_in_evidence": [
                    number for number, present in presence.items() if present
                ],
                "removed_and_absent_from_evidence": [
                    number for number, present in presence.items() if not present
                ],
                "missing_required_text": [
                    phrase
                    for phrase in (expected.get("must_contain") or [])
                    if phrase.lower() not in answer.lower()
                ],
                "present_forbidden_text": [
                    phrase
                    for phrase in (expected.get("must_not_contain") or [])
                    if phrase.lower() in answer.lower()
                ],
                "uncited_required_sections": [
                    section for section in required if not _is_cited(section, cited)
                ],
                "abstained": bool(record.get("abstained")),
            }
        )

    return {
        "frozen": str(frozen_path),
        "app_root": str(app_root.resolve()),
        "validator_loaded_from": str(loaded_from),
        "totals": {
            "runs": len(per_run),
            "figures_removed": sum(len(run["removed"]) for run in per_run),
            "removed_and_present_in_evidence": sum(
                len(run["removed_and_present_in_evidence"]) for run in per_run
            ),
            "removed_and_absent_from_evidence": sum(
                len(run["removed_and_absent_from_evidence"]) for run in per_run
            ),
            "runs_missing_required_text": sum(1 for run in per_run if run["missing_required_text"]),
            "runs_with_forbidden_text": sum(1 for run in per_run if run["present_forbidden_text"]),
            "runs_with_uncited_required_section": sum(
                1 for run in per_run if run["uncited_required_sections"]
            ),
            "abstentions": sum(1 for run in per_run if run["abstained"]),
        },
        "qualification": (
            "Every count here is mechanical. 'present in evidence' means the "
            "string occurs in a retrieved section, which is not the same as the "
            "figure being correct for the question asked, and 'removed' is one "
            "rule's opinion. No number in this report labels a figure correct "
            "or invented; only source adjudication can."
        ),
        "runs": per_run,
    }


def compare(first: Path, second: Path) -> dict[str, Any]:
    """Diff two scored arms. The changed list is the result; totals locate it."""
    left = json.loads(first.read_text(encoding="utf-8"))
    right = json.loads(second.read_text(encoding="utf-8"))

    if left.get("frozen") != right.get("frozen"):
        raise SystemExit(
            "the two arms scored different frozen sets; a comparison across "
            "different inputs measures the inputs"
        )
    if left.get("validator_loaded_from") == right.get("validator_loaded_from"):
        raise SystemExit(
            "both arms loaded the validator from the same file, so this "
            f"compares nothing: {left.get('validator_loaded_from')}"
        )

    left_runs = {(run["id"], run["attempt"]): run for run in left["runs"]}
    changed: list[dict[str, Any]] = []
    for run in right["runs"]:
        other = left_runs.get((run["id"], run["attempt"]))
        if other is None:
            continue
        only_second = sorted(set(run["removed"]) - set(other["removed"]))
        only_first = sorted(set(other["removed"]) - set(run["removed"]))
        if only_second or only_first:
            changed.append(
                {
                    "id": run["id"],
                    "attempt": run["attempt"],
                    "removed_only_by_second": only_second,
                    "removed_only_by_first": only_first,
                    "of_those_present_in_evidence": sorted(
                        set(only_second) & set(run["removed_and_present_in_evidence"])
                    ),
                    "adjudication": "unreviewed",
                }
            )

    return {
        "first": {"arm": left.get("validator_loaded_from"), "totals": left["totals"]},
        "second": {"arm": right.get("validator_loaded_from"), "totals": right["totals"]},
        "changed_decisions": changed,
        "note": (
            "Each changed decision is unreviewed until a person opens the section "
            "the figure came from and records whether the evidence establishes it. "
            "The totals cannot decide that, and neither arm's rule is ground truth."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="Estimate the run. Makes no calls.")
    parser.add_argument("--freeze", type=Path, help="Capture pre-repair answers and evidence.")
    parser.add_argument("--score", type=Path, help="Score a frozen set with one arm.")
    parser.add_argument("--app-root", type=Path, help="Checkout to load the validator from.")
    parser.add_argument("--out", type=Path, help="Where to write a scored arm.")
    parser.add_argument("--compare", type=Path, nargs=2, help="Diff two scored arms.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--arms", type=int, default=2, help="Preflight only.")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=0,
        help="Stop before exceeding this many turn executions. 0 means no bound.",
    )
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument(
        "--i-have-approval-for-paid-model-calls",
        action="store_true",
        help="Required for --freeze. An acknowledgement, not a cap: use --max-turns for that.",
    )
    args = parser.parse_args()

    if args.preflight:
        print(json.dumps(preflight(args.fixture, args.repeat, args.arms), indent=2))
        return 0

    if args.freeze:
        if not args.i_have_approval_for_paid_model_calls:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason": "--freeze makes paid model calls. Run --preflight first.",
                    },
                    indent=2,
                )
            )
            return 2
        if not args.max_turns:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason": (
                            "--max-turns is required. The approval flag acknowledges "
                            "spending; it does not bound it."
                        ),
                    },
                    indent=2,
                )
            )
            return 2
        if args.load_ssm:
            from services.aws_clients import init_aws_clients

            init_aws_clients()
        payload = freeze(args.fixture, args.repeat, args.max_turns, args.freeze)
        args.freeze.parent.mkdir(parents=True, exist_ok=True)
        args.freeze.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"status": "frozen", "turn_executions": payload["turn_executions"]}, indent=2
            )
        )
        return 0

    if args.score:
        if not args.app_root:
            parser.error("--score requires --app-root")
        result = score(args.score, args.app_root)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "validator_loaded_from": result["validator_loaded_from"],
                    "totals": result["totals"],
                    "qualification": result["qualification"],
                },
                indent=2,
            )
        )
        return 0

    if args.compare:
        print(json.dumps(compare(args.compare[0], args.compare[1]), indent=2))
        return 0

    parser.error("one of --preflight, --freeze, --score or --compare is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
