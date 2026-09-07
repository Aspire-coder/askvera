"""Offline cleanup/validation replay, not a live governance or retrieval test."""
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.governance.models import GovernanceAction, GovernanceDecision
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.response.models import ChatResponse
from app.retrieval.models import RetrievedDocument, RetrievalResult
from utils.validators import ChatRequest


def main():
    folder = ROOT / "docs/audits/2026-09-05"
    saved = json.loads((folder / "contact-scope-v3-compact-results.json").read_text(encoding="utf-8"))
    governance = Mock()
    governance.evaluate.return_value = GovernanceDecision(
        allowed=True, action=GovernanceAction.ALLOW, provider="offline-mock")
    rows = []
    with patch("services.pii._detect_pii_entities", return_value=[]), patch(
        "services.aws_clients.get_aws_clients", side_effect=RuntimeError("Cloud access forbidden in replay")
    ):
        orchestrator = AIOrchestrator(governance=governance)
        for row in saved["results"]:
            belgium = row["id"].startswith("BE")
            doc = RetrievedDocument(
                id=row["id"], title="International-Sponsoring-Directory.pdf - Forever Belgium" if belgium else "US-EN-Company-Policy.pdf",
                content=row["supplied_source"], source="", language="en", country="" if belgium else "US",
                page="111-112" if belgium else "2-3", score=.9,
                metadata={"section_id": "sponsoring-053-belgium" if belgium else "1.01",
                          "access_scope": "global" if belgium else "local",
                          **({"directory_kind": "international_sponsoring"} if belgium else {})})
            evidence = RetrievalResult([doc], [doc.to_source()], .9)
            body = ChatRequest(message=row["question"], sessionId="offline-replay", country="US", language="en")
            response = ChatResponse(answer=row["candidate_raw_answer"], citations=evidence.sources,
                                    suggestions=[], cards=[], confidence=.9, metadata={}, correlation_id="offline")
            cleaned = orchestrator._secure_and_complete_response(
                response, evidence, "en", "offline", user_question=body.message, country="US")
            final = orchestrator._validate_response(cleaned, body, "offline", retrieval_result=evidence)
            rows.append({"id": row["id"], "question": row["question"], "raw_answer": row["candidate_raw_answer"],
                         "after_cleanup": cleaned.answer, "after_validation": final.answer,
                         "metadata": final.metadata, "citations": final.citations})
    report = {"scope": "Saved output replay through real cleanup and validation helpers",
              "mocks": ["Governance allows output", "External PII detection returns no entities"],
              "limits": ["No retrieval/publication check", "No full chat or live safety verification",
                         "Source URI unavailable in captured evidence; left empty"], "results": rows}
    (folder / "contact-output-replay-fixed.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
