from __future__ import annotations

from services import knowledge_generations


def test_active_generation_ids_isolates_locale_and_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_generations,
        "_active_generation_rows",
        lambda: [
            {
                "country": "CA",
                "language": "fr",
                "document_type": "policy",
                "access_scope": "country",
                "active_ingestion_id": "ca-fr",
            },
            {
                "country": "US",
                "language": "en",
                "document_type": "policy",
                "access_scope": "country",
                "active_ingestion_id": "us-en",
            },
            {
                "country": "GLOBAL",
                "language": "en",
                "document_type": "office_directory",
                "access_scope": "global",
                "active_ingestion_id": "directory-en",
            },
        ],
    )

    assert knowledge_generations.active_generation_ids(
        countries={"CA"},
        languages={"fr"},
        access_scope="country",
    ) == {"ca-fr"}
    assert knowledge_generations.active_generation_ids(
        countries={"GLOBAL"},
        languages={"en"},
        access_scope="global",
        document_type="office_directory",
    ) == {"directory-en"}


def test_active_generation_ids_returns_no_cross_language_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        knowledge_generations,
        "_active_generation_rows",
        lambda: [
            {
                "country": "CA",
                "language": "en",
                "document_type": "policy",
                "access_scope": "country",
                "active_ingestion_id": "ca-en",
            }
        ],
    )

    assert knowledge_generations.active_generation_ids(
        countries={"CA"},
        languages={"fr"},
        access_scope="country",
    ) == set()
