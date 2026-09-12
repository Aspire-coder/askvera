"""Governing-passage recall, outcome labels and pinned repair rescoring, offline.

"passed" mixes retrieval, generation, repair and citation into one bit. This
reads benchmark artifacts that already exist and reports three things
separately from it:

* recall - whether each answerable case's governing section was retrieved at
  rank 1 and within the final retrieved documents (at most five), from every
  run's recorded ``sections``. Recall at 30 needs the selector's candidate
  list, which only artifacts with run capture contain; otherwise it is
  reported as not measurable, never estimated.
* outcomes - the runner's automated diagnostic outcome for each run, computed
  here for artifacts that predate it. Automated classification, not manual
  adjudication.
* pinned repair - figures that numeric repair removed, re-classified with one
  or more named presence functions against local source extractions, so two
  arms can be compared under the same function.

Reads only: no network, no model calls, no database, and no artifact or
fixture is modified. ``--output`` refuses to replace an existing file.
Outcome labels use configured copy and never ask for a translation. As a
second line of defence, the copy translator - the one path into Bedrock that
labelling could reach - is replaced while the report is built, and every
attempt is counted in ``translation_attempts_blocked``, which must be 0.

Matching conventions (stated in every report):

* ``strict`` - the required key is one of the retrieved document's own keys.
  This is how score_run decides retrieval_hit.
* ``parent_covers_child`` - also counts a retrieved parent whose identifier is
  the required section's prefix followed by "-" or ".", in the same market
  ("NO:17.08" covers "NO:17.08-c"). This is run_benchmark._is_cited, the rule
  applied to citations. It is an upper bound: a parent row need not contain
  the child's text.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_VERSION = 1
DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "held_out_source_linked_pack.json"
NOT_MEASURABLE_AT_30 = "not measurable: candidates not captured"
CANDIDATE_LIMIT = 30
FINAL_LIMIT = 5
CONVENTIONS = {
    "strict": "required key equals a key of a retrieved document; the rule score_run uses for retrieval_hit",
    "parent_covers_child": "strict, or a retrieved parent in the same market whose id followed by '-' or '.' "
                           "prefixes the required id; run_benchmark._is_cited, the citation rule; an upper bound",
    "at_1": "the first retrieved document only",
    "at_5": "the final retrieved documents recorded in sections (after the selector and parent-child binding, "
            "before approve_evidence), at most five",
    "at_30": "the selector candidate list from capture.final_retrieval.candidate_sections; its sections are "
             "parent-preferring, so only parent_covers_child is measurable",
}
# Artifact section keys use the index's country, which differs from the
# extraction folder for Great Britain.
_EXTRACTION_FOLDERS = {"UK": "GB"}


@lru_cache(maxsize=1)
def benchmark() -> Any:
    """The runner module, loaded by path so its conventions are used, not copied."""
    spec = importlib.util.spec_from_file_location("run_benchmark_for_recall", PROJECT_ROOT / "scripts" / "run_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rank_groups(section_keys: list[str]) -> list[list[str]]:
    """Regroup a run's flat ``sections`` into one key list per retrieved document, in rank order.

    run_benchmark._section_keys writes each document's bare key followed by its
    country-qualified key, so a qualified key belongs to the document before it
    when their bare parts match.
    """
    groups: list[list[str]] = []
    for key in section_keys:
        bare = key.split(":", 1)[1] if ":" in key else None
        if bare is not None and groups and groups[-1][0] == bare:
            groups[-1].append(key)
        else:
            groups.append([key])
    return groups


def _fraction_covered(required: list[str], keys: set[str], parent_covers_child: bool) -> float:
    covered = [
        section for section in required
        if (benchmark()._is_cited(section, keys) if parent_covers_child else section in keys)
    ]
    return len(covered) / len(required)


def run_recall(run: dict[str, Any], required: list[str]) -> dict[str, Any]:
    groups = rank_groups([str(key) for key in run.get("sections") or []])
    result: dict[str, Any] = {"retrieved_documents": len(groups)}
    for label, parent in (("strict", False), ("parent_covers_child", True)):
        for limit in (1, FINAL_LIMIT):
            keys = {key for group in groups[:limit] for key in group}
            result[f"{label}_at_{limit}"] = _fraction_covered(required, keys, parent)
    candidates = ((run.get("capture") or {}).get("final_retrieval") or {}).get("candidate_sections")
    if isinstance(candidates, list):
        keys = set(benchmark()._section_keys([
            (str(candidate.get("section") or ""), str(candidate.get("country") or ""))
            for candidate in candidates[:CANDIDATE_LIMIT]
            if isinstance(candidate, dict)
        ]))
        result["parent_covers_child_at_30"] = _fraction_covered(required, keys, True)
    else:
        result["parent_covers_child_at_30"] = NOT_MEASURABLE_AT_30
    recorded = run.get("retrieval_hit")
    result["recorded_retrieval_hit"] = recorded
    result["strict_at_5_agrees_with_recorded_retrieval_hit"] = (
        None if recorded is None else (result["strict_at_5"] == 1.0) == bool(recorded)
    )
    return result


def _pack_case(pack_cases: dict[str, dict[str, Any]], identifier: str) -> dict[str, Any]:
    if identifier not in pack_cases:
        raise ValueError(f"Artifact case {identifier!r} is not in the fixture; refusing to guess its expectation.")
    return pack_cases[identifier]


def _required_sections(pack_case: dict[str, Any]) -> list[str]:
    return [str(value) for value in (pack_case["expected"].get("required_sections") or [])]


_RECALL_METRICS = ("strict_at_1", "strict_at_5", "parent_covers_child_at_1", "parent_covers_child_at_5", "parent_covers_child_at_30")


def recall_report(artifact: dict[str, Any], pack_cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in artifact["cases"]:
        pack_case = _pack_case(pack_cases, str(case["id"]))
        required = _required_sections(pack_case)
        if pack_case["expected"]["kind"] != "answer" or not required:
            reason = "expects an abstention" if pack_case["expected"]["kind"] != "answer" else "names no governing section"
            rows.append({"id": case["id"], "status": "not_applicable", "reason": reason})
            continue
        rows.append({
            "id": case["id"],
            "status": "measured",
            "required_sections": required,
            "runs": [run_recall(run, required) for run in case["runs"]],
        })
    measured = [run for row in rows if row["status"] == "measured" for run in row["runs"]]
    aggregate: dict[str, Any] = {
        "cases_measured": sum(1 for row in rows if row["status"] == "measured"),
        "cases_not_applicable": sum(1 for row in rows if row["status"] == "not_applicable"),
        "runs_measured": len(measured),
    }
    for metric in _RECALL_METRICS:
        values = [run[metric] for run in measured if isinstance(run[metric], float)]
        if not values:
            aggregate[metric] = NOT_MEASURABLE_AT_30 if metric.endswith("_at_30") else "no measured runs"
            continue
        full = sum(1 for value in values if value == 1.0)
        aggregate[metric] = {
            "full_hits": f"{full}/{len(values)}",
            "mean_fraction": round(sum(values) / len(values), 4),
            "runs_not_measurable": len(measured) - len(values),
        }
    disagreements = [row["id"] for row in rows if row["status"] == "measured"
                     for run in row["runs"] if run["strict_at_5_agrees_with_recorded_retrieval_hit"] is False]
    aggregate["strict_at_5_disagrees_with_recorded_retrieval_hit"] = disagreements
    return {"aggregate": aggregate, "cases": rows}


def outcomes_report(artifact: dict[str, Any], pack_cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    module = benchmark()
    rows = []
    for case in artifact["cases"]:
        pack_case = _pack_case(pack_cases, str(case["id"]))
        for index, run in enumerate(case["runs"], start=1):
            recorded = run.get("diagnostic_outcome")
            label = recorded if isinstance(recorded, dict) else module.classify_outcome(
                run, language=str(pack_case["language"]), required_sections=_required_sections(pack_case)
            )
            rows.append({
                "id": case["id"],
                "run": index,
                "expected_kind": pack_case["expected"]["kind"],
                "passed": run.get("passed"),
                "outcome": label["outcome"],
                "basis": label["basis"],
                "declining_copy": label.get("declining_copy"),
                "label_source": "recorded_by_runner" if isinstance(recorded, dict) else "computed_offline",
            })
    counts = dict.fromkeys(module.OUTCOMES, 0)
    by_expected: dict[str, dict[str, int]] = {}
    by_passed: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[row["outcome"]] += 1
        by_expected.setdefault(row["expected_kind"], dict.fromkeys(module.OUTCOMES, 0))[row["outcome"]] += 1
        by_passed.setdefault(str(row["passed"]).lower(), dict.fromkeys(module.OUTCOMES, 0))[row["outcome"]] += 1
    return {
        "method": "automated heuristic classification (run_benchmark.classify_outcome); not manual adjudication",
        "classification_version": module.OUTCOME_CLASSIFICATION_VERSION,
        "runs": len(rows),
        "counts": counts,
        "by_expected_kind": by_expected,
        "by_passed": by_passed,
        "runs_detail": rows,
    }


class ExtractionIndex:
    """Section text from local extractions, keyed by market, language and section id."""

    def __init__(self, root: Path, pack: dict[str, Any]) -> None:
        self.root = root
        self._declared = {
            str(entry.get("extraction_file") or "").replace("\\", "/"): str(entry.get("extraction_sha256") or "")
            for entry in pack.get("source_extractions") or []
        }
        self._sections: dict[tuple[str, str], dict[str, str]] = {}
        self.files: dict[str, dict[str, Any]] = {}

    def _paths(self, country: str, language: str) -> list[Path]:
        if country == "GLOBAL":
            return sorted((self.root / "tmp" / "askvera-global-sponsoring").glob("*.directory.jsonl"))
        folder = _EXTRACTION_FOLDERS.get(country, country)
        return sorted((self.root / "outputs" / "chunk-comparison-full" / "current" / folder / language).glob("*.sections.jsonl"))

    def _load(self, country: str, language: str) -> dict[str, str]:
        key = (country, "" if country == "GLOBAL" else language)
        if key not in self._sections:
            sections: dict[str, str] = {}
            for path in self._paths(country, language):
                raw = path.read_bytes()
                relative = path.relative_to(self.root).as_posix()
                digest = hashlib.sha256(raw).hexdigest()
                declared = self._declared.get(relative)
                self.files[relative] = {
                    "sha256": digest,
                    "declared_in_fixture": declared is not None,
                    "matches_fixture_hash": None if declared is None else declared == digest,
                }
                for line in raw.decode("utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        sections.setdefault(str(row.get("section_id") or ""), str(row.get("content") or ""))
            self._sections[key] = sections
        return self._sections[key]

    def content(self, country: str, language: str, section_id: str) -> str | None:
        return self._load(country.upper(), language.lower()).get(section_id)


def _extraction_documents(run: dict[str, Any], language: str, index: ExtractionIndex) -> tuple[list[Any], list[str]]:
    documents, unavailable = [], []
    for group in rank_groups([str(key) for key in run.get("sections") or []]):
        qualified = next((key for key in group if ":" in key), None)
        if qualified is None:
            unavailable.append(group[0])
            continue
        country, section = qualified.split(":", 1)
        content = index.content(country, language, section)
        if content is None:
            unavailable.append(qualified)
        else:
            documents.append(SimpleNamespace(content=content))
    return documents, unavailable


def pinned_repair_report(
    artifact: dict[str, Any],
    pack_cases: dict[str, dict[str, Any]],
    index: ExtractionIndex,
    functions: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    total_runs = 0
    for case in artifact["cases"]:
        pack_case = _pack_case(pack_cases, str(case["id"]))
        for number, run in enumerate(case["runs"], start=1):
            total_runs += 1
            removed = [str(value) for value in run.get("removed_numeric_claims") or []]
            if not removed:
                continue
            documents, unavailable = _extraction_documents(run, str(pack_case["language"]), index)
            rows.append({
                "id": case["id"],
                "run": number,
                "removed_numeric_claims": removed,
                "recorded_present_arm_own_function": list(run.get("removed_but_present_in_source") or []),
                "sections_rescored": len(documents),
                "sections_unavailable": unavailable,
                "present_by_function": {
                    label: [figure for figure, present in function(removed, documents).items() if present]
                    for label, function in functions.items()
                },
            })
    aggregate: dict[str, Any] = {
        "recorded_arm_own_function": _repair_counts(
            [bool(row["recorded_present_arm_own_function"]) for row in rows], total_runs
        ),
    }
    for label in functions:
        aggregate[label] = _repair_counts([bool(row["present_by_function"][label]) for row in rows], total_runs)
    return {
        "runs": total_runs,
        "aggregate": aggregate,
        "incomplete_rows": [f"{row['id']}#{row['run']}" for row in rows if row["sections_unavailable"]],
        "runs_detail": rows,
    }


def _repair_counts(supported_flags: list[bool], total_runs: int) -> dict[str, str]:
    rate = benchmark()._rate
    supported = sum(1 for flag in supported_flags if flag)
    return {
        "repair_fired": rate(len(supported_flags), total_runs),
        "repair_removed_supported_figure": rate(supported, total_runs),
        "repair_removed_invented_figure": rate(len(supported_flags) - supported, total_runs),
    }


def _labelled_paths(values: list[str], option: str) -> dict[str, Path]:
    labelled: dict[str, Path] = {}
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise ValueError(f"{option} needs LABEL=PATH, got {value!r}.")
        if label in labelled:
            raise ValueError(f"{option} label {label!r} is used twice.")
        labelled[label] = Path(path)
    return labelled


@contextmanager
def offline_copy() -> Iterator[dict[str, int]]:
    """Refuse and count every copy translation while the block runs.

    app.evidence.localized_conversation_response asks Bedrock to translate copy
    with no reviewed locale version. app.evidence binds the translator by name,
    so both it and services.controlled_copy are replaced. A refused attempt
    returns None, so callers fall back to the English source.
    """
    import app.evidence as evidence
    import services.controlled_copy as controlled_copy

    counter = {"translation_attempts_blocked": 0}

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        counter["translation_attempts_blocked"] += 1
        return None

    originals = (evidence.localize_reviewed_copy, controlled_copy.localize_reviewed_copy)
    evidence.localize_reviewed_copy = refuse
    controlled_copy.localize_reviewed_copy = refuse
    try:
        yield counter
    finally:
        evidence.localize_reviewed_copy, controlled_copy.localize_reviewed_copy = originals


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    with offline_copy() as guard:
        report = _build_report(args)
    report["translation_attempts_blocked"] = guard["translation_attempts_blocked"]
    return report


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    raw_fixture = args.fixture.read_bytes()
    pack = json.loads(raw_fixture)
    pack_cases = {str(case["id"]): case for case in pack["cases"]}
    functions: dict[str, Any] = {}
    identities: dict[str, Any] = {}
    if args.extraction_root is not None:
        module = benchmark()
        validators = _labelled_paths(args.presence_validator, "--presence-validator")
        if not validators:
            module.configure_pinned_presence(None)
            functions["application"] = module._pinned_presence_function()
        for label, path in validators.items():
            functions[label] = module.load_presence_function(path)
        identities = {label: module.presence_function_identity(function) for label, function in functions.items()}
    index = ExtractionIndex(args.extraction_root, pack) if args.extraction_root is not None else None
    artifacts = {}
    for label, path in _labelled_paths(args.artifact, "--artifact").items():
        raw = path.read_bytes()
        artifact = json.loads(raw)
        artifacts[label] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "recorded_summary": {
                key: artifact.get("summary", {}).get(key)
                for key in ("correct", "retrieval_hit", "repeat", "fixture_sha256", "repair_fired",
                            "repair_removed_supported_figure", "repair_removed_invented_figure")
            },
            "recall": recall_report(artifact, pack_cases),
            "outcomes": outcomes_report(artifact, pack_cases),
            "pinned_repair": (
                pinned_repair_report(artifact, pack_cases, index, functions) if index is not None
                else "not computed: no --extraction-root given"
            ),
        }
    return {
        "report": "held_out_governing_recall",
        "version": REPORT_VERSION,
        "fixture": {"path": str(args.fixture), "sha256": hashlib.sha256(raw_fixture).hexdigest()},
        "conventions": CONVENTIONS,
        "presence_functions": identities,
        "extraction_files": index.files if index is not None else {},
        "pinned_repair_limits": (
            "Rescored against local extraction rows for each run's recorded sections, not the indexed chunk "
            "text the run saw; a section missing from the extractions is listed and cannot contribute, so "
            "'invented' can be overstated for incomplete rows."
        ),
        "artifacts": artifacts,
    }


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return "yes" if value == 1.0 else ("no" if value == 0.0 else f"{value:.2f}")
    if value == NOT_MEASURABLE_AT_30:
        return "n/m"
    return "" if value is None else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Governing recall report v{report['version']}", "",
        f"Translation attempts blocked: {report['translation_attempts_blocked']}", "",
    ]
    for label, entry in report["artifacts"].items():
        lines += [f"## {label} (`{entry['sha256'][:8]}`)", "",
                  "| Case | Required | strict@1 | strict@5 | parent@1 | parent@5 | parent@30 | recorded hit |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for row in entry["recall"]["cases"]:
            short = str(row["id"])[7:9]
            if row["status"] != "measured":
                lines.append(f"| {short} | n/a ({row['reason']}) | | | | | | |")
                continue
            for run in row["runs"]:
                lines.append(
                    f"| {short} | {', '.join(row['required_sections'])} | {_cell(run['strict_at_1'])} | "
                    f"{_cell(run['strict_at_5'])} | {_cell(run['parent_covers_child_at_1'])} | "
                    f"{_cell(run['parent_covers_child_at_5'])} | {_cell(run['parent_covers_child_at_30'])} | "
                    f"{_cell(run['recorded_retrieval_hit'])} |"
                )
        lines += ["", "```", json.dumps(entry["recall"]["aggregate"], indent=2), "```", "",
                  "| Case | Expected | Passed | Outcome | Basis |", "| --- | --- | --- | --- | --- |"]
        for row in entry["outcomes"]["runs_detail"]:
            lines.append(f"| {str(row['id'])[7:9]} | {row['expected_kind']} | {row['passed']} | {row['outcome']} | {row['basis']} |")
        lines += ["", "```", json.dumps({key: entry["outcomes"][key] for key in ("counts", "by_expected_kind", "by_passed")}, indent=2), "```", ""]
        if isinstance(entry["pinned_repair"], dict):
            functions = list(report["presence_functions"])
            lines += ["| Case | Removed | Recorded present (arm's own) | " + " | ".join(f"Present ({name})" for name in functions)
                      + " | Unavailable sections |", "| --- | --- | --- | " + " | ".join("---" for _ in functions) + " | --- |"]
            for row in entry["pinned_repair"]["runs_detail"]:
                lines.append(
                    f"| {str(row['id'])[7:9]} | {', '.join(row['removed_numeric_claims'])} | "
                    f"{', '.join(row['recorded_present_arm_own_function']) or '-'} | "
                    + " | ".join(', '.join(row['present_by_function'][name]) or '-' for name in functions)
                    + f" | {', '.join(row['sections_unavailable']) or '-'} |"
                )
            lines += ["", "```", json.dumps(entry["pinned_repair"]["aggregate"], indent=2), "```", ""]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifact", action="append", default=[], required=True, help="LABEL=PATH of a benchmark artifact; repeatable.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--extraction-root", type=Path, default=None,
                        help="Repository root holding outputs/chunk-comparison-full and tmp/askvera-global-sponsoring.")
    parser.add_argument("--presence-validator", action="append", default=[],
                        help="LABEL=PATH of a numeric_grounding_validator.py to rescore removals with; repeatable.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, default=None, help="Write here instead of stdout; an existing file is refused.")
    args = parser.parse_args(argv)
    try:
        report = build_report(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Recall report failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    text = render_markdown(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        sys.stdout.write(text)
        return 0
    try:
        with open(args.output, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        print(f"Recall report refused: {args.output} already exists.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
