"""Bounded generation/numeric probe; NOT retrieval or full-chat validation.

Uses only excerpts transcribed in PRODUCTION_UI_BASELINE.md. No database,
application startup, shared cache, automatic consent, or secret retrieval.
"""
from __future__ import annotations

import json
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.prompts.builder import PromptBuilder  # noqa: E402
from app.retrieval.models import RetrievedDocument, RetrievalResult  # noqa: E402
from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims  # noqa: E402

AWS = r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
CASES = [
    ("BE_EN", "What about Belgium's office telephone number in the global directory?", "en",
     "You can also email support@foreverliving.nl or visit foreverliving.com."),
    ("BE_FR", "Quel est le numéro de téléphone du bureau en Belgique dans l'annuaire mondial ? Réponds en français.", "en",
     "Vous pouvez aussi envoyer un email à support@foreverliving.nl ou consulter foreverliving.com."),
    ("US_TYPO", "what is teh custmoer service phone numbr for teh United States office?", "en",
     "You can reach them to place orders, report discrepancies, or get clarification on policies and procedures."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-v3", action="store_true")
    args = parser.parse_args()
    name = "contact-scope-v3-compact-results.json" if args.scope_v3 else "captured-phone-component-results.json"
    output = ROOT / "docs/audits/2026-09-05" / name
    cases = list(CASES)
    if args.scope_v3:
        cases.extend([
            ("BE_RECEPTION", "Which number reaches reception for Belgium?", "en", None),
            ("BE_FR_SHORT", "Je veux appeler la réception du bureau belge. Quel numéro composer ?", "en", None),
            ("BE_BOTH", "Give me both the Belgium reception and order telephone numbers, including their location labels.", "en", None),
        ])
    report = {
        "scope": "Live generation with captured snippets plus local numeric checking only",
        "limitations": ["Not live retrieval", "Not full output pipeline", "One call per case",
                        "Original history not replayed", "Source URI and version not captured",
                        "Confidence 0.9 is a fixture value, not measured retrieval confidence",
                        "Production baseline model/cache provenance unknown"],
        "model": MODEL, "guardrail": "idy33rbs9v1i:1", "results": [],
    }
    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
    env = dict(os.environ, AWS_MAX_ATTEMPTS="1", AWS_PAGER="", PYTHONIOENCODING="utf-8", AWS_CLI_OUTPUT_ENCODING="UTF-8")
    for identifier, question, language, baseline in cases:
        if any(row["id"] == identifier for row in report["results"]):
            continue
        belgium = identifier.startswith("BE")
        content = (
            "Telephone Office +31 88 646 0200 (Reception, Netherlands) "
            "Telephone for Orders +03 808 1023 (Belgium for orders)"
            if belgium else
            "(e) The FBO who has questions or needs clarification should contact the Regional Sales "
            "Director/Area Sales Manager or call Customer Care at 1-888- 440-ALOE (2563)."
        )
        doc = RetrievedDocument(
            id=identifier, title="International-Sponsoring-Directory.pdf - Forever Belgium" if belgium else "US-EN-Company-Policy.pdf",
            content=content, source="", page="111-112" if belgium else "2-3",
            country="" if belgium else "US", language="en", score=None,
            metadata={"section_id": "sponsoring-053-belgium" if belgium else "1.01",
                      "access_scope": "global" if belgium else "local"},
        )
        evidence = RetrievalResult(documents=[doc], citations=[doc.to_source()], confidence=.9)
        # Suppress only the prompt builder's telemetry; no live app integrations run.
        with patch("app.prompts.builder.record_pipeline_metric"):
            prompt = PromptBuilder().build(user_question=question, conversation="", country="US",
                                           language=language, role="new_prospect", retrieval_result=evidence)
        request = {"modelId": MODEL, "system": [{"text": prompt.system_prompt}],
                   "messages": [{"role": "user", "content": [{"text": prompt.user_prompt}]}],
                   "inferenceConfig": {"maxTokens": 512},
                   "guardrailConfig": {"guardrailIdentifier": "idy33rbs9v1i", "guardrailVersion": "1"}}
        row = {"id": identifier, "question": question, "production_baseline_answer": baseline,
               "supplied_source": content, "prompt_version": prompt.prompt_version,
               "system_prompt_sha256": hashlib.sha256(prompt.system_prompt.encode()).hexdigest()}
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="askvera-phone-probe-") as temporary:
            request_path = Path(temporary) / "request.json"
            request_path.write_text(json.dumps(request, ensure_ascii=True), encoding="utf-8")
            try:
                result = subprocess.run([AWS, "bedrock-runtime", "converse", "--cli-input-json",
                                         "file://" + str(request_path), "--profile", "askvera-review",
                                         "--region", "us-east-1", "--output", "json",
                                         "--cli-read-timeout", "45"],
                                        env=env, capture_output=True, timeout=60)
                if result.returncode:
                    row["error"] = result.stderr.decode("utf-8", errors="replace").strip()
                else:
                    try:
                        response_text = result.stdout.decode("utf-8")
                        row["cli_output_encoding"] = "utf-8"
                    except UnicodeDecodeError:
                        response_text = result.stdout.decode("cp1252")
                        row["cli_output_encoding"] = "cp1252"
                    response = json.loads(response_text)
                    answer = "\n".join(block["text"] for block in response.get("output", {}).get("message", {}).get("content", []) if "text" in block)
                    row.update(candidate_raw_answer=answer, stop_reason=response.get("stopReason"),
                               usage=response.get("usage"),
                               unsupported_numeric_claim_count=len(unsupported_numeric_claims(answer, [doc])))
            except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                row["error"] = type(exc).__name__
        row["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["results"].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if "error" in row:
            break


if __name__ == "__main__":
    main()
