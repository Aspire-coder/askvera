"""Safety-focused tests for signal-based confidence scoring."""

from app.retrieval.confidence_signals import signal_confidence
from app.retrieval.models import RetrievedDocument


def _document(
    *,
    country: str = "GB",
    language: str = "en",
    score: float = 5.0,
    title: str = "Joining requirements",
    content: str = "No minimum capital investment is required to join as an FBO.",
    metadata: dict[str, object] | None = None,
) -> RetrievedDocument:
    return RetrievedDocument(
        id="section-1",
        title=title,
        content=content,
        source="s3://approved/policy.pdf",
        country=country,
        language=language,
        score=score,
        metadata={
            "access_scope": "country",
            "document_type": "policy",
            "section_id": "1.1-a",
            "section_title": title,
            "entity_tags": ["joining", "fees", "forever_business_owner"],
            "question_type_tags": ["pricing", "process"],
            "section_authority": "governing",
            **(metadata or {}),
        },
    )


def test_strong_governing_evidence_clears_existing_threshold() -> None:
    assessment = signal_confidence(
        [_document()],
        "Does it cost money to join as an FBO?",
        "GB",
        "en",
    )

    assert assessment.confidence >= 0.47
    assert assessment.signals["entity_match"] is True
    assert assessment.signals["locale_country_match"] is True


def test_wrong_country_policy_cannot_clear_existing_threshold() -> None:
    assessment = signal_confidence(
        [_document(country="GB")],
        "Does it cost money to join as an FBO?",
        "CA",
        "en",
    )

    assert assessment.confidence < 0.47
    assert assessment.signals["locale_country_match"] is False


def test_unrelated_evidence_cannot_clear_existing_threshold() -> None:
    assessment = signal_confidence(
        [
            _document(
                score=10.0,
                title="Product returns",
                content="Products must be returned within the approved period.",
                metadata={
                    "entity_tags": ["returns"],
                    "question_type_tags": ["timing"],
                    "section_authority": "governing",
                },
            )
        ],
        "How do I qualify as a Manager?",
        "GB",
        "en",
    )

    assert assessment.confidence < 0.47


def test_no_evidence_is_always_zero_confidence() -> None:
    assessment = signal_confidence([], "Can this cure cancer?", "US", "en")

    assert assessment.confidence == 0.0
    assert assessment.signals == {"has_evidence": False}


def test_global_directory_is_not_penalized_for_selected_market() -> None:
    directory = _document(
        country="GLOBAL",
        title="United Kingdom office",
        content="Telephone Office: +44 1234 567890",
        metadata={
            "access_scope": "global",
            "document_type": "office_directory",
            "entity_tags": ["contact_details"],
            "question_type_tags": ["contact"],
            "section_authority": "directory",
        },
    )

    assessment = signal_confidence(
        [directory],
        "What is the UK office telephone number?",
        "US",
        "en",
    )

    assert assessment.confidence >= 0.47
    assert assessment.signals["locale_country_match"] is True


def test_named_country_sponsoring_directory_clears_confidence_threshold() -> None:
    directory = _document(
        country="GLOBAL",
        score=1.5,
        title="International Sponsoring Directory - Forever Mexico",
        content="International sponsoring procedure for Forever Mexico.",
        metadata={
            "access_scope": "global",
            "document_type": "international_sponsoring_directory",
            "record_country": "Mexico",
            "entity_tags": ["international_sponsoring", "sponsoring"],
            "question_type_tags": ["contact"],
            "section_authority": "directory",
        },
    )

    assessment = signal_confidence(
        [directory],
        "How can I join Mexico through international sponsoring?",
        "US",
        "en",
    )

    assert assessment.confidence >= 0.35
    assert assessment.signals["directory_country_match"] is True


def test_confidence_uses_evidence_bounded_typo_repair_query() -> None:
    directory = _document(
        country="GLOBAL",
        score=1.5,
        title="International Sponsoring Directory - Forever Mexico",
        content="International sponsoring procedure for Forever Mexico.",
        metadata={
            "access_scope": "global",
            "document_type": "international_sponsoring_directory",
            "record_country": "Mexico",
            "entity_tags": ["international_sponsoring", "sponsoring"],
            "question_type_tags": ["contact"],
            "section_authority": "directory",
            "typo_ranking_applied": True,
            "ranking_query_used": "How can I join Mexico through international sponsoring?",
        },
    )

    assessment = signal_confidence(
        [directory],
        "How cn I join mexcio through internatinal sponsering?",
        "US",
        "en",
    )

    assert assessment.confidence >= 0.35
    assert assessment.signals["directory_country_match"] is True
    assert assessment.signals["alignment_used_safe_typo_query"] is True
