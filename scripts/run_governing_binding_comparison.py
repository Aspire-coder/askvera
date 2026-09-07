"""Two-factor selector experiment. Frozen inputs only; not the live chatbot."""

import argparse
import json
from pathlib import Path
import sys
import time
from dataclasses import asdict

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_selector_fixed_comparison import build_cases, digest, parse_output  # noqa: E402
from scripts.selector_binding_adapter import assessment, prepare_requests, structural_decision  # noqa: E402
from app.retrieval.source_binding import EvidenceSource  # noqa: E402


def execute_call(client, model, item):
    start = time.monotonic()
    response = client.converse(modelId=model, **item["request"], inferenceConfig={"maxTokens": 512})
    raw = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
    record = {"output": raw, "usage": response.get("usage"), "stop_reason": response.get("stopReason"),
              "duration_ms": round((time.monotonic() - start) * 1000, 2)}
    try:
        if item["variant"] == "structural":
            record["validated_decision"] = asdict(structural_decision(
                parse_output(raw), item["case"], item["rows"],
                [EvidenceSource(**source) for source in item["sources"]]))
        record["passed"], record["assessment"] = assessment(
            parse_output(raw), item["case"], item["variant"], item["rows"],
            [EvidenceSource(**source) for source in item["sources"]])
    except (ValueError, TypeError, KeyError):
        record.update(passed=False, assessment="unparseable or invalid output")
    if response.get("stopReason") != "end_turn":
        record.update(passed=False, assessment="incomplete model response")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--experiment", choices=["factors", "target-scope", "bound-verdict", "structural"], default="factors")
    parser.add_argument("--repeats", type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    frozen = json.loads(args.fixture.read_text(encoding="utf-8"))
    cases = build_cases(frozen)
    # Additional paraphrases declared before calls; exploratory, not independent held-out gold.
    cases += [{**cases[0], "id": "new-active-condition", "polarity": "ANSWER_FACT", "question": "How do I become Active?"},
              {**cases[0], "id": "de-active-condition", "language": "de", "polarity": "ANSWER_FACT",
               "question": "Welche Voraussetzungen muss ich erfuellen, um diesen Monat aktiv zu sein?"}]
    variants = ("current", "ranking", "binding", "combined")
    if args.experiment in {"target-scope", "bound-verdict", "structural"}:
        variants = ("combined", {"target-scope": "scoped", "bound-verdict": "verdict", "structural": "structural"}[args.experiment])
        # Same missing-rule evidence, questions invert background versus requested property.
        cases += [{**cases[5], "id": "activity-background-retention",
                   "question": "I am Active this month. Does that mean I keep my sales rank permanently?"},
                  {**cases[3], "id": "activity-background-termination",
                   "question": "I kept my sales rank but was inactive this month. Is my business automatically terminated?"}]
    if args.experiment == "structural":
        # Fresh exploratory wordings fixed before invocation; same captured Canada evidence.
        cases += [
            {**cases[0], "id": "fresh-activity-carryover", "polarity": "ANSWER_NO",
             "question": "Can I stay Active this month just because I was Active last month?"},
            {**cases[0], "id": "fresh-monthly-condition", "polarity": "ANSWER_FACT",
             "question": "What must an FBO do to qualify as Active in their home company for the month?"},
            {**cases[0], "id": "fresh-cc-cash", "expected": False, "governing_sections": [],
             "question": "Exactly how many Canadian dollars will four Active Case Credits cost me?"},
            {**cases[3], "id": "fresh-inactivity-closure", "expected": False,
             "question": "I missed this month's order. Will Forever close my business without my asking?"},
        ]
    requests = prepare_requests(cases, digest(frozen), variants)
    model = frozen["cases"][0]["model"]
    if any(case["model"] != model for case in frozen["cases"]):
        raise ValueError("Mixed captured models")
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": __doc__, "model": model, "region": "us-east-1", "fixture_hash": digest(frozen),
                "cases": cases, "requests": requests, "repeats": args.repeats,
                "candidate_variant": args.experiment,
                "maximum_calls": len(requests) * args.repeats, "inferenceConfig": {"maxTokens": 512},
                "script_hash": digest(Path(__file__).read_text(encoding="utf-8")),
                "adapter_hash": digest(Path(__file__).with_name("selector_binding_adapter.py").read_text(encoding="utf-8"))}
    root = Path(__file__).resolve().parents[1]
    manifest["helper_hashes"] = {name: digest((root / "app/retrieval" / name).read_text(encoding="utf-8"))
                                 for name in ("source_binding.py", "governing_rules.py", "evidence_decision.py")}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.execute:
        print(f"Prepared {len(variants)}-variant experiment; zero model calls.")
        return
    session = boto3.Session(profile_name="askvera-review", region_name="us-east-1")
    client = session.client("bedrock-runtime", config=Config(
        connect_timeout=5, read_timeout=45, retries={"mode": "adaptive", "total_max_attempts": 1}))
    for repeat in range(1, args.repeats + 1):
        for item in (requests if repeat % 2 else requests[::-1]):
            record = {"id": item["case"]["id"], "question": item["case"]["question"],
                      "side": item["variant"], "repeat": repeat, "request_hash": item["request_sha256"]}
            try:
                record.update(execute_call(client, model, item))
            except (BotoCoreError, ClientError) as exc:
                record.update(error_type=type(exc).__name__, passed=False)
                if isinstance(exc, ClientError):
                    record["error_code"] = exc.response.get("Error", {}).get("Code")
            target = args.output / f'{record["side"]}-{repeat}-{record["id"]}.json'
            target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({key: record.get(key) for key in ("id", "side", "repeat", "passed", "error_type")}), flush=True)
            if "error_type" in record:
                return


if __name__ == "__main__":
    main()
