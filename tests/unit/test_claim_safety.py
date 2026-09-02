import json
from pathlib import Path

from services.claim_safety import (
    classify_claim_scope,
    localized_claim_response,
)


def test_product_disease_claim_uses_reviewed_copy_without_retrieval():
    response, scope = localized_claim_response(
        "Does a Forever Aloe product cure cancer?",
        "medical_claim",
        "US",
        "en",
    )

    assert scope == "product_disease_claim"
    assert response and "can't confirm" in response


def test_generic_health_question_keeps_existing_medical_route():
    response, scope = localized_claim_response(
        "I have a fever",
        "medical_claim",
        "CA",
        "en",
    )

    assert response is None
    assert scope == "medical_claim"


def test_policy_question_is_not_reclassified_as_product_claim():
    response, scope = localized_claim_response(
        "Can an FBO claim that aloe cures cancer?",
        "knowledge",
        "US",
        "en",
    )

    assert response is None
    assert scope == "knowledge"


def test_product_claim_is_localized_without_encoding_corruption():
    response, scope = localized_claim_response(
        "Est-ce qu'un produit Aloe soigne le cancer?",
        "medical_claim",
        "CA",
        "fr",
    )

    assert scope == "product_disease_claim"
    assert response and "d\u00e9sol" in response
    assert "\ufffd" not in response
    assert "\u00c3" not in response


def test_every_configured_language_has_clean_product_claim_copy():
    path = Path(__file__).parents[2] / "config" / "claim_safety.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    for language in payload["responses"]:
        response, scope = localized_claim_response(
            "Does an aloe product cure cancer?",
            "medical_claim",
            "US",
            language,
        )
        assert scope == "product_disease_claim"
        assert response, language
        assert "\ufffd" not in response, language
        assert "\u00c3" not in response, language


def test_classification_accepts_language_variants():
    assert classify_claim_scope(
        "Does an aloe product treat cancer?", "medical_claim", "en-US"
    ) == "product_disease_claim"
