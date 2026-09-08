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


def _provenance(fixture_hash: str) -> dict[str, Any]:
    """What was run, so a result can be tied to the code that produced it.

    A capture with no provenance is a number without a claim attached: nobody
    can tell later which commit, which index or which model it describes.
    """
    import subprocess

    from config import settings

    def _git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=HARNESS_ROOT, capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except Exception:
            return ""

    return {
        "harness_commit": _git("rev-parse", "HEAD"),
        "harness_dirty": bool(_git("status", "--porcelain")),
        "fixture_sha256": fixture_hash,
        "opensearch_index": getattr(settings, "OPENSEARCH_INDEX", ""),
        "bedrock_model_id": getattr(settings, "BEDROCK_MODEL_ID", ""),
        "chunk_profile": getattr(settings, "ADMIN_INGESTION_CHUNK_PROFILE", ""),
        "generation_pointer_enabled": bool(
            getattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
        ),
    }


def _select(cases: list[dict[str, Any]], wanted: list[str]) -> list[dict[str, Any]]:
    """Restrict to named cases, refusing a name that is not in the fixture.

    A pilot has to be chosen, not taken from the top of the file. The first six
    turns of this fixture are scope refusals, which carry no figures at all and
    would measure a grounding rule against answers that contain nothing for it
    to judge.
    """
    if not wanted:
        return cases
    by_id = {case["id"]: case for case in cases}
    missing = [identifier for identifier in wanted if identifier not in by_id]
    if missing:
        raise SystemExit(f"--case names not in the fixture: {missing}")
    return [by_id[identifier] for identifier in wanted]


# Provenance fields that must match for a resume to be legitimate. A capture
# assembled from two fixtures, two commits or two indexes is one file that
# describes no single experiment - and it would carry the NEW run's provenance
# at the top, so nothing downstream could tell.
_RESUME_MUST_MATCH = (
    "fixture_sha256",
    "harness_commit",
    "opensearch_index",
    "bedrock_model_id",
    "chunk_profile",
)


def _load_checkpoint(
    path: Path, provenance: dict[str, Any]
) -> tuple[list[dict[str, Any]], set[tuple[str, int]]]:
    """Resume, refusing to mix incompatible runs. Checked before any model call.

    Incomplete attempts are KEPT, marked superseded rather than deleted. They
    are evidence of what was paid for and what happened, and a replay writes
    new records beside them instead of quietly overwriting the evidence of the
    first attempt.
    """
    if not path.exists():
        return [], set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    existing = payload.get("provenance") or {}

    mismatched = {
        field: (existing.get(field), provenance.get(field))
        for field in _RESUME_MUST_MATCH
        if existing.get(field) != provenance.get(field)
    }
    if mismatched:
        raise SystemExit(
            "refusing to resume: the existing capture was produced under "
            f"different conditions {mismatched}. Start a new capture file."
        )
    if existing.get("harness_dirty") or provenance.get("harness_dirty"):
        raise SystemExit(
            "refusing to resume across a dirty working tree: the commit matches "
            "but the code may not. Commit or stash, then start a new capture."
        )

    records = list(payload.get("runs") or [])
    complete = {
        (str(record["id"]), int(record["attempt"]))
        for record in records
        if record.get("is_final_turn") and not record.get("superseded")
    }
    for record in records:
        key = (str(record["id"]), int(record["attempt"]))
        if key not in complete:
            # Kept, not dropped. The replay adds records; this one stays as the
            # history of an attempt that did not finish.
            record["superseded"] = True
    return records, complete


def _count_model_calls():
    """Wrap the Bedrock client so every invocation is counted, retries included.

    A turn is not a call and a turn limit is not a budget. This counts what was
    actually invoked, in this process only, and restores the client afterwards.
    Returns (counter, restore).
    """
    from services.aws_clients import get_aws_clients

    counter = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    try:
        runtime = get_aws_clients().bedrock_runtime
    except Exception:
        return counter, (lambda: None)

    original = runtime.converse

    def _counted(*args, **kwargs):
        counter["calls"] += 1
        response = original(*args, **kwargs)
        usage = (response or {}).get("usage") or {}
        counter["input_tokens"] += int(usage.get("inputTokens") or 0)
        counter["output_tokens"] += int(usage.get("outputTokens") or 0)
        return response

    runtime.converse = _counted

    def _restore() -> None:
        runtime.converse = original

    return counter, _restore


def freeze(
    fixture: Path,
    repeat: int,
    max_turns: int,
    checkpoint: Path,
    cases_wanted: list[str],
    resume: bool,
) -> dict[str, Any]:
    """Capture what numeric repair was given, per turn, with validated resume.

    Turn identity comes from the CONVERSATION RUNNER, not from the capture
    hook. A turn that refuses early, or answers from cache, never reaches
    repair and so never fires the hook - and counting hook calls as turns made
    a later answer inherit an earlier turn's expectation, undercounted the
    requests actually made, and let the last captured turn mark a conversation
    complete when its final turn was never captured.

    Every turn is now recorded, including one that did not reach repair, which
    is marked rather than omitted.

    Grounding is NOT disabled. Every safeguard runs exactly as in production;
    the hook only observes, and its return value is discarded.
    """
    from app.orchestrator import chat_orchestrator
    import scripts.run_benchmark as benchmark
    import scripts.run_retrieval_canary as canary

    cases, fixture_hash = benchmark.load_fixture(fixture)
    cases = _select(cases, cases_wanted)

    provenance = _provenance(fixture_hash)
    # Validated BEFORE any model call, so an incompatible resume costs nothing.
    records, completed = _load_checkpoint(checkpoint, provenance) if resume else ([], set())
    if records:
        print(json.dumps({"resumed_turns": len(records), "completed_attempts": len(completed)}))

    counter, restore_client = _count_model_calls()
    attempted_turns = 0
    captured: dict[str, dict[str, Any]] = {}

    def _write(status: str) -> None:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(
            json.dumps(
                _finish(records, provenance, fixture_hash, attempted_turns, counter, status),
                indent=2,
            ),
            encoding="utf-8",
        )

    def _hook(answer: str, documents: list[Any], correlation_id: str) -> None:
        """Only records what repair saw. It decides nothing about turn order."""
        captured[correlation_id] = {
            "answer": answer,
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

    original_hook = chat_orchestrator.pre_repair_capture_hook
    chat_orchestrator.pre_repair_capture_hook = _hook
    try:
        for sequence, case in enumerate(cases, start=1):
            turns = _turns(case)
            for attempt in range(repeat):
                if (case["id"], attempt) in completed:
                    continue
                if max_turns and attempted_turns + len(turns) > max_turns:
                    _write("max_turns reached")
                    return _finish(
                        records, provenance, fixture_hash, attempted_turns, counter,
                        "max_turns reached",
                    )
                captured.clear()
                try:
                    run = canary.run_pipeline_capture(case, sequence * 100 + attempt)
                except BaseException:
                    # The turns already performed were paid for. Reconciliation
                    # normally happens after the runner returns, and on this
                    # path it never will - so without this, an interruption
                    # loses every turn of the case, which is the failure this
                    # whole design exists to avoid.
                    #
                    # Only captured turns can be recovered here: a turn that
                    # refused left no capture and the runner never reported it,
                    # so the attempt is marked as partially observed rather
                    # than presented as a complete account of what ran.
                    for index, (correlation_id, capture) in enumerate(captured.items()):
                        records.append(
                            {
                                "id": case["id"],
                                "attempt": attempt,
                                "turn_index": index,
                                "is_final_turn": False,
                                "correlation_id": correlation_id,
                                "language": case.get("language", ""),
                                "country": case.get("country", ""),
                                "reached_repair": True,
                                "answer": capture["answer"],
                                "documents": capture["documents"],
                                "final_answer": "",
                                "abstained": False,
                                "citations": [],
                                "expected": (
                                    _expectations(turns[index]["expected"])
                                    if index < len(turns)
                                    else {}
                                ),
                                # Turn indexes here are the order captures
                                # arrived, which equals turn order only if no
                                # earlier turn refused. Recorded, never scored.
                                "attempt_interrupted": True,
                                "superseded": True,
                            }
                        )
                    attempted_turns += len(captured)
                    _write("interrupted")
                    raise
                # Every turn the runner actually performed, in order. This is
                # the authority on how many there were and which is last.
                responses = list(getattr(run, "prior_responses", ()) or []) + [run.response]
                attempted_turns += len(responses)

                for index, response in enumerate(responses):
                    correlation_id = str(getattr(response, "correlation_id", "") or "")
                    capture = captured.get(correlation_id)
                    expectation = (
                        _expectations(turns[index]["expected"]) if index < len(turns) else {}
                    )
                    records.append(
                        {
                            "id": case["id"],
                            "attempt": attempt,
                            "turn_index": index,
                            "is_final_turn": index == len(responses) - 1,
                            "correlation_id": correlation_id,
                            "language": case.get("language", ""),
                            "country": case.get("country", ""),
                            # False means this turn never reached numeric repair
                            # - a refusal, a cache hit, an early return. It is
                            # recorded rather than omitted, because omitting it
                            # is what shifted every later expectation.
                            "reached_repair": capture is not None,
                            "answer": (capture or {}).get("answer", ""),
                            "documents": (capture or {}).get("documents", []),
                            # The text a reader would have seen for this turn,
                            # kept separately: it is not what repair was given.
                            "final_answer": str(getattr(response, "answer", "") or ""),
                            "abstained": bool(
                                (getattr(response, "metadata", None) or {}).get("fallback")
                            ),
                            "citations": [
                                {
                                    "section": str((citation or {}).get("section") or ""),
                                    "country": str((citation or {}).get("country") or ""),
                                }
                                for citation in (getattr(response, "citations", None) or [])
                            ],
                            "expected": expectation,
                        }
                    )
                    _write("in progress")
    finally:
        chat_orchestrator.pre_repair_capture_hook = original_hook
        restore_client()

    payload = _finish(records, provenance, fixture_hash, attempted_turns, counter, "complete")
    _write("complete")
    return payload


def _finish(
    records: list[dict[str, Any]],
    provenance: dict[str, Any],
    fixture_hash: str,
    attempted_turns: int,
    counter: dict[str, int],
    status: str,
) -> dict[str, Any]:
    reached = sum(1 for record in records if record.get("reached_repair"))
    return {
        "provenance": provenance,
        "fixture_sha256": fixture_hash,
        "turns_recorded": len(records),
        "turns_attempted_this_run": attempted_turns,
        "turns_that_reached_repair": reached,
        "status": status,
        "captured_at_boundary": "pre_numeric_repair",
        # Measured, not estimated. Includes retries and every stage.
        "model_calls_this_run": counter["calls"],
        "input_tokens_this_run": counter["input_tokens"],
        "output_tokens_this_run": counter["output_tokens"],
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
    skipped = {"superseded": 0, "did_not_reach_repair": 0}
    for record in payload["runs"]:
        # A superseded record is the history of an interrupted attempt; a turn
        # that never reached repair has no evidence to score. Both are kept in
        # the capture and neither is scored, because scoring them would count
        # turns the rule was never asked about.
        if record.get("superseded"):
            skipped["superseded"] += 1
            continue
        if not record.get("reached_repair", True):
            skipped["did_not_reach_repair"] += 1
            continue
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
        "provenance": payload.get("provenance", {}),
        "validator_loaded_from": str(loaded_from),
        # Two blocks, not one, because they answer different questions and
        # only the first is isolated. Repair is a pure function of this frozen
        # input, so its numbers differ between arms only because the rule
        # differs. Answer quality describes the captured answers themselves,
        # which the arm being scored did not produce - it is the same for both
        # arms by construction, and it is here to characterise the sample, not
        # to compare arms. Mixing them invites reading a fixed number as a
        # result.
        "repair": {
            "turns": len(per_run),
            "figures_removed": sum(len(run["removed"]) for run in per_run),
            "removed_and_present_in_evidence": sum(
                len(run["removed_and_present_in_evidence"]) for run in per_run
            ),
            "removed_and_absent_from_evidence": sum(
                len(run["removed_and_absent_from_evidence"]) for run in per_run
            ),
        },
        "pre_repair_sample_characteristics": {
            "turns": len(per_run),
            "turns_missing_required_text": sum(
                1 for run in per_run if run["missing_required_text"]
            ),
            "turns_with_forbidden_text": sum(
                1 for run in per_run if run["present_forbidden_text"]
            ),
            "turns_with_uncited_required_section": sum(
                1 for run in per_run if run["uncited_required_sections"]
            ),
            "abstentions": sum(1 for run in per_run if run["abstained"]),
            "note": (
                "Measured on the PRE-REPAIR text, which is not what a reader "
                "sees: repair, restoration, formatting and governance all run "
                "after this point. It characterises the captured sample and "
                "measures neither arm. Final answers are captured separately "
                "in each record's final_answer, and answer quality as "
                "delivered needs the end-to-end run."
            ),
        },
        "skipped": skipped,
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
        "first": {"arm": left.get("validator_loaded_from"), "repair": left["repair"]},
        "second": {"arm": right.get("validator_loaded_from"), "repair": right["repair"]},
        "provenance": {
            "first": left.get("provenance", {}),
            "second": right.get("provenance", {}),
        },
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
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Case id to include. Repeatable. A pilot is chosen, not taken from the top.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an existing capture. Required to write to a file that exists.",
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
        if args.freeze.exists() and not args.resume:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason": (
                            f"{args.freeze} already exists. Pass --resume to continue it, "
                            "or choose another path. Overwriting a capture destroys turns "
                            "that were paid for."
                        ),
                    },
                    indent=2,
                )
            )
            return 2
        if args.load_ssm:
            from services.aws_clients import init_aws_clients

            init_aws_clients()
        payload = freeze(
            args.fixture,
            args.repeat,
            args.max_turns,
            args.freeze,
            args.case,
            args.resume,
        )
        args.freeze.parent.mkdir(parents=True, exist_ok=True)
        args.freeze.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "turns_recorded": payload["turns_recorded"],
                    "turns_attempted_this_run": payload["turns_attempted_this_run"],
                    "turns_that_reached_repair": payload["turns_that_reached_repair"],
                    "model_calls_this_run": payload["model_calls_this_run"],
                    "input_tokens_this_run": payload["input_tokens_this_run"],
                    "output_tokens_this_run": payload["output_tokens_this_run"],
                    "provenance": payload["provenance"],
                },
                indent=2,
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
                    "repair": result["repair"],
                    "pre_repair_sample_characteristics": result[
                        "pre_repair_sample_characteristics"
                    ],
                    "skipped": result["skipped"],
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
