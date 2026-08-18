"""Parse and inventory historical AskVera interactions for retrieval QA.

The parser is deliberately strict: malformed rows are reported and never
silently dropped. Historical answers are evidence for regression analysis, not
ground truth; only reviewed expected answers or substantive reviewer comments
are treated as answer-quality guidance.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


HISTORY_FIELDS = (
    "created_at",
    "correlation_id",
    "session_id",
    "country",
    "language",
    "traffic_source",
    "question",
    "answer",
    "topic",
    "confidence",
    "source_count",
    "tokens",
    "fallback",
    "failure_layer",
    "rating",
    "comment",
    "expected_answer",
)

_NON_SUBSTANTIVE_COMMENTS = re.compile(
    r"^(?:test|testing|testing the|response feedback|changes?)\b",
    re.IGNORECASE,
)
_CONVERSATION_QUESTIONS = re.compile(
    r"^(?:hi|hello|hey|how are you|who are you|thank you|thanks)[!?.\s]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatasetIssue:
    """One source-row problem that requires review."""

    line_number: int
    code: str
    detail: str


@dataclass(frozen=True)
class InteractionCase:
    """Normalized, loss-minimizing representation of one historical turn."""

    case_index: int
    source_line: int
    case_id: str
    created_at: str
    correlation_id: str
    session_id: str
    country: str
    language: str
    traffic_source: str
    question: str
    normalized_question: str
    question_fingerprint: str
    historical_answer: str
    topic: str
    historical_confidence: float
    historical_source_count: int
    historical_tokens: int
    historical_fallback: bool
    historical_failure_layer: str
    rating: int | None
    reviewer_comment: str
    expected_answer: str
    evaluation_group: str
    review_state: str
    has_review_guidance: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    values = re.split(r"(?<!\\)\|", stripped[1:-1])
    return [value.replace(r"\|", "|").strip() for value in values]


def _normalize_question(value: str) -> str:
    normalized = re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE)
    return " ".join(normalized.split())


def _parse_bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "y"}


def _parse_rating(value: str) -> int | None:
    cleaned = value.replace("\\", "").strip()
    if cleaned in {"1", "+1"}:
        return 1
    if cleaned == "-1":
        return -1
    return None


def _evaluation_group(question: str, fallback: bool, failure_layer: str) -> str:
    layer = failure_layer.casefold()
    if layer in {"local_guardrail", "risk_policy", "sensitive_pii_input", "aws_guardrail"}:
        return "safety"
    if _CONVERSATION_QUESTIONS.match(question.strip()):
        return "conversation"
    if "support" in question.casefold() and any(
        phrase in question.casefold()
        for phrase in ("talk to", "speak to", "human", "ticket", "request")
    ):
        return "support"
    if fallback:
        return "retrieval_or_validation_fallback"
    return "knowledge_answer"


def _review_state(rating: int | None, comment: str, expected_answer: str) -> str:
    if expected_answer:
        return "expected_answer_present"
    if comment and not _NON_SUBSTANTIVE_COMMENTS.match(comment):
        return "reviewer_guidance_present"
    if rating == -1:
        return "negative_without_guidance"
    if rating == 1:
        return "helpful_regression_case"
    return "unreviewed"


def parse_interaction_history(path: Path) -> tuple[list[InteractionCase], list[DatasetIssue]]:
    """Parse a Markdown interaction table while accounting for every data row."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    issues: list[DatasetIssue] = []
    if len(lines) < 2:
        return [], [DatasetIssue(1, "MISSING_TABLE", "The input does not contain a Markdown table.")]

    header = tuple(value.casefold() for value in _split_markdown_row(lines[0]))
    if header != HISTORY_FIELDS:
        issues.append(
            DatasetIssue(
                1,
                "UNEXPECTED_HEADER",
                f"Expected {len(HISTORY_FIELDS)} fields but found: {header}",
            )
        )

    cases: list[InteractionCase] = []
    for line_number, line in enumerate(lines[2:], start=3):
        if not line.strip():
            continue
        values = _split_markdown_row(line)
        if len(values) != len(HISTORY_FIELDS):
            issues.append(
                DatasetIssue(
                    line_number,
                    "FIELD_COUNT",
                    f"Expected {len(HISTORY_FIELDS)} fields, found {len(values)}.",
                )
            )
            continue
        row = dict(zip(HISTORY_FIELDS, values, strict=True))
        try:
            confidence = float(row["confidence"] or 0.0)
            source_count = int(row["source_count"] or 0)
            tokens = int(row["tokens"] or 0)
        except ValueError as exc:
            issues.append(DatasetIssue(line_number, "INVALID_NUMBER", str(exc)))
            continue

        normalized_question = _normalize_question(row["question"])
        fingerprint_source = "|".join(
            [row["country"].upper(), row["language"].lower(), normalized_question]
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:20]
        rating = _parse_rating(row["rating"])
        comment = row["comment"].strip()
        expected_answer = row["expected_answer"].strip()
        fallback = _parse_bool(row["fallback"])
        case_index = len(cases) + 1
        cases.append(
            InteractionCase(
                case_index=case_index,
                source_line=line_number,
                case_id=row["correlation_id"] or f"history-row-{line_number}",
                created_at=row["created_at"],
                correlation_id=row["correlation_id"],
                session_id=row["session_id"],
                country=row["country"].upper(),
                language=row["language"].split("-", 1)[0].lower(),
                traffic_source=row["traffic_source"],
                question=row["question"],
                normalized_question=normalized_question,
                question_fingerprint=fingerprint,
                historical_answer=row["answer"],
                topic=row["topic"],
                historical_confidence=confidence,
                historical_source_count=source_count,
                historical_tokens=tokens,
                historical_fallback=fallback,
                historical_failure_layer=row["failure_layer"],
                rating=rating,
                reviewer_comment=comment,
                expected_answer=expected_answer,
                evaluation_group=_evaluation_group(
                    row["question"],
                    fallback,
                    row["failure_layer"],
                ),
                review_state=_review_state(rating, comment, expected_answer),
                has_review_guidance=bool(
                    expected_answer
                    or (comment and not _NON_SUBSTANTIVE_COMMENTS.match(comment))
                ),
            )
        )
    return cases, issues


def dataset_summary(cases: list[InteractionCase], issues: list[DatasetIssue]) -> dict[str, Any]:
    """Return stable coverage counts for CI and human review."""
    counts: dict[str, int] = {}
    review_counts: dict[str, int] = {}
    for case in cases:
        counts[case.evaluation_group] = counts.get(case.evaluation_group, 0) + 1
        review_counts[case.review_state] = review_counts.get(case.review_state, 0) + 1
    return {
        "case_count": len(cases),
        "issue_count": len(issues),
        "unique_question_fingerprints": len({case.question_fingerprint for case in cases}),
        "rated_count": sum(case.rating is not None for case in cases),
        "helpful_count": sum(case.rating == 1 for case in cases),
        "not_helpful_count": sum(case.rating == -1 for case in cases),
        "review_guidance_count": sum(case.has_review_guidance for case in cases),
        "evaluation_groups": dict(sorted(counts.items())),
        "review_states": dict(sorted(review_counts.items())),
    }
