"""Safety-preserving helpers for isolated retrieval-vNext evaluation."""

from __future__ import annotations

import re
import unicodedata

from app.evidence_contract import EvidenceContractResult, parse_evidence_contract
from app.retrieval.models import RetrievedDocument
from app.validation.validators.numeric_grounding_validator import (
    MeasurableClaim,
    unsupported_numeric_claims,
)


def _normalized_number_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).replace(",", ".")


def _contains_number(text: str, number: str) -> bool:
    normalized_text = _normalized_number_text(text)
    normalized_number = _normalized_number_text(number).strip()
    if not normalized_number:
        return False
    return bool(
        re.search(
            rf"(?<![\d.]){re.escape(normalized_number)}(?![\d.])",
            normalized_text,
        )
    )


def _claim_time_is_cited(claim: MeasurableClaim, documents: list[RetrievedDocument]) -> bool:
    times = re.findall(r"(?<!\d)(\d{1,2})[:.]([0-5]\d)(?!\d)", claim.context)
    for hour, minute in times:
        source_pattern = re.compile(
            rf"(?<!\d){re.escape(hour)}[:.]{re.escape(minute)}(?!\d)"
        )
        if any(source_pattern.search(_normalized_number_text(document.content)) for document in documents):
            return True
    return False


def parse_vnext_evidence_contract(
    text: str,
    documents: list[RetrievedDocument],
) -> EvidenceContractResult:
    """Repair only malformed smart-quote pairs, then apply the strict contract."""
    result = parse_evidence_contract(text, documents)
    if result.reason != "invalid_json":
        return result
    repaired = re.sub(r"([„“])([^\"\n]{1,160})\"", r"\1\2”", text or "")
    return parse_evidence_contract(repaired, documents)


def vnext_unsupported_numeric_claims(
    answer: str,
    question: str,
    documents: list[RetrievedDocument],
    evidence_ids: tuple[str, ...],
) -> list[MeasurableClaim]:
    """Keep numeric review only when neither user input nor cited evidence supports it."""
    unsupported = unsupported_numeric_claims(answer, documents)
    cited_documents = [document for document in documents if document.id in set(evidence_ids)]
    return [
        claim
        for claim in unsupported
        if not _contains_number(question, claim.number)
        and not any(_contains_number(document.content, claim.number) for document in cited_documents)
        and not _claim_time_is_cited(claim, cited_documents)
    ]
