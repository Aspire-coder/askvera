"""Offline proof that the US product documents stay inside US sessions.

Every row is built from the committed dry-run manifest by the real index-row
builder, and every filter is the real clause the retrieval code sends to
OpenSearch. A small evaluator applies those filter clauses in memory, so no
OpenSearch, Bedrock, database or AWS call is made. The evaluator refuses any
clause it does not understand, so a change to the query shape fails here
instead of silently passing.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from app.evidence import _has_current_locale_document, approve_evidence
from app.retrieval import cache_evidence, opensearch_sections
from app.retrieval.models import RetrievalResult, RetrievedDocument
from app.retrieval.opensearch_sections import (
    _directory_text_query,
    _exact_section_query,
    _hit_to_row,
    _text_query,
    _vector_query,
    is_approved_source,
)
from config import settings
from scripts.ingestion import load_policy_sections_to_opensearch as loader
from services import knowledge_generations
from services.market_config import load_policy_locales

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "ingestion" / "us-product-docs-20260924" / "manifest.json"
)
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
DOCUMENTS = MANIFEST["documents"]
SOURCE_URI_PREFIX = "s3://approved-knowledge/country/US"

# Every configured market, the legacy document code GB maps to, and markets the
# widget does not publish, so an unconfigured or malformed session is covered too.
CONFIGURED_MARKETS = sorted(load_policy_locales())
OTHER_MARKETS = sorted({*CONFIGURED_MARKETS, "UK", "MX", "PR", "AU", "IE", "ZA", ""} - {"US"})
ALL_LANGUAGES = sorted(
    {language for entry in load_policy_locales().values() for language in entry["languages"]}
    | {"en", "es", "fr", "pt", "en-US", "es-US", "en-GB", "fr-CA", ""}
)


# --- in-memory evaluation of OpenSearch filter clauses ---------------------------


def _field(row: dict[str, Any], path: str) -> Any:
    path = path.removesuffix(".keyword")
    value: Any = row
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _matches(clause: dict[str, Any], row: dict[str, Any]) -> bool:
    (kind, body), = clause.items()
    if kind == "term":
        (path, expected), = body.items()
        return _field(row, path) == expected
    if kind == "terms":
        (path, expected), = body.items()
        return _field(row, path) in expected
    if kind == "bool":
        unknown = set(body) - {"filter", "must", "should", "must_not", "minimum_should_match"}
        assert not unknown, f"unsupported bool keys {unknown}"
        required = [*body.get("filter", []), *body.get("must", [])]
        if not all(_matches(part, row) for part in required):
            return False
        if any(_matches(part, row) for part in body.get("must_not", [])):
            return False
        should = body.get("should", [])
        if should:
            minimum = body.get("minimum_should_match", 1 if not required else 0)
            return sum(_matches(part, row) for part in should) >= minimum
        return True
    raise AssertionError(f"filter clause {kind!r} is not evaluated offline; extend the evaluator")


def _filter_of(query: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the hard filter of a text, exact or knn query; scoring clauses are ignored."""
    inner = query["query"]
    if "knn" in inner:
        return inner["knn"]["embedding"]["filter"]["bool"]["filter"]
    return inner["bool"]["filter"]


def _admitted(query: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filters = _filter_of(query)
    return [row for row in rows if all(_matches(clause, row) for clause in filters)]


# --- rows exactly as the ingestion worker indexes them ---------------------------


def _index_rows(*, access_scope: str = "country", document_type: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for number, entry in enumerate(DOCUMENTS, start=1):
        fields = entry["form_fields"]
        section = {
            "source_file": entry["proposed_upload_filename"],
            "country": fields["country"],
            "language": fields["language"],
            "section_id": "doc-0001",
            "title": "FAST FACTS",
            "start_page": 1,
            "end_page": 1,
            "content": f"{entry['product']} fast facts.",
            "document_version": fields["document_version"],
            "effective_date": fields["effective_date"],
            "expiry_date": "",
            "status": "active",
        }
        row = loader._document(
            section,
            source_uri_prefix=SOURCE_URI_PREFIX,
            status="active",
            ingestion_id=f"us-product-{number:02d}",
            document_type=document_type or fields["document_type"],
            access_scope=access_scope,
        )
        rows.append(row)
    return rows


def _retrieved(row: dict[str, Any]) -> RetrievedDocument:
    """Mirror OpenSearchSectionProvider's row-to-document conversion for the gate."""
    converted = _hit_to_row({"_id": row["id"], "_score": 9.0, "_source": row})
    return RetrievedDocument(
        id=converted["id"],
        title=converted["section_title"],
        content=converted["content"],
        source=converted["source_uri"],
        country=converted["country"],
        language=converted["language"],
        score=0.95,
        metadata={
            **converted["metadata"],
            "access_scope": converted["access_scope"],
            "document_type": converted["document_type"],
        },
    )


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    # Building a row embeds its search text; a vector query embeds the question.
    monkeypatch.setattr(loader, "embed_text", lambda _text: [0.0])
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0])
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", True)
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)


def _enable_generation_pointer(monkeypatch, rows: list[dict[str, Any]]) -> None:
    """Publish every product generation, plus an unrelated CA policy, in the pointer table."""
    published = [
        {
            "country": row["country"],
            "language": row["language"],
            "document_type": row["document_type"],
            "access_scope": row["access_scope"],
            "active_ingestion_id": row["ingestion_id"],
        }
        for row in rows
    ]
    published.append({
        "country": "CA", "language": "en", "document_type": "policy",
        "access_scope": "country", "active_ingestion_id": "ca-policy",
    })
    monkeypatch.setattr(settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True)
    monkeypatch.setattr(knowledge_generations, "_active_generation_rows", lambda **_: list(published))


def _locale_queries(country: str, language: str) -> list[dict[str, Any]]:
    return [
        _text_query("What is in Forever Absorbent-D?", country, language, scope="locale"),
        _vector_query("What is in Forever Absorbent-D?", country, language, scope="locale"),
        _exact_section_query("doc-0001", country, language),
    ]


def _global_queries(country: str, language: str) -> list[dict[str, Any]]:
    return [
        _vector_query("Forever Absorbent-D", country, language, scope="global"),
        _directory_text_query("Forever Absorbent-D"),
    ]


# --- the manifest itself ---------------------------------------------------------


def test_manifest_scopes_every_document_to_us_english_country_availability():
    assert len(DOCUMENTS) == 24
    for entry in DOCUMENTS:
        fields = entry["form_fields"]
        assert (fields["country"], fields["language"], fields["access_scope"]) == ("US", "en", "country")
        assert fields["document_type"] not in {"policy", "office_directory", "international_sponsoring_directory"}
        assert fields["review_before_publish"] is True
        assert entry["expected_stable_document_id"].startswith("country:US:en:")
    assert len({entry["sha256"] for entry in DOCUMENTS}) == 24
    assert len({entry["expected_stable_document_id"] for entry in DOCUMENTS}) == 24


# --- query-time filters ----------------------------------------------------------


@pytest.mark.parametrize("pointer", [False, True], ids=["no-pointer", "generation-pointer"])
@pytest.mark.parametrize("country", OTHER_MARKETS)
def test_no_other_market_retrieves_the_documents_in_any_language(monkeypatch, country, pointer):
    rows = _index_rows()
    if pointer:
        _enable_generation_pointer(monkeypatch, rows)
    for language in ALL_LANGUAGES:
        for query in [*_locale_queries(country, language), *_global_queries(country, language)]:
            assert _admitted(query, rows) == [], (country, language)


@pytest.mark.parametrize("pointer", [False, True], ids=["no-pointer", "generation-pointer"])
@pytest.mark.parametrize("language", ["en", "en-US", "es", "es-US"])
def test_us_sessions_retrieve_them_in_english_and_through_the_spanish_fallback(monkeypatch, language, pointer):
    rows = _index_rows()
    if pointer:
        _enable_generation_pointer(monkeypatch, rows)
    for query in _locale_queries("US", language):
        assert len(_admitted(query, rows)) == 24
    # Country-scoped rows never enter the global (all-markets) channels, even for US.
    for query in _global_queries("US", language):
        assert _admitted(query, rows) == []


def test_us_spanish_sessions_lose_them_when_the_english_fallback_is_off(monkeypatch):
    monkeypatch.setattr(settings, "OPENSEARCH_ALLOW_ENGLISH_FALLBACK", False)
    rows = _index_rows()
    for query in _locale_queries("US", "es"):
        assert _admitted(query, rows) == []
    assert len(_admitted(_text_query("q", "US", "en"), rows)) == 24


def test_any_us_session_language_reaches_them_through_the_fallback():
    """The fallback is not limited to US's published languages: it is plain English fallback."""
    rows = _index_rows()
    for language in ("fr", "de", "pt"):
        assert len(_admitted(_text_query("q", "US", language), rows)) == 24


# --- evidence gate, citation authorization and the answer cache -------------------


@pytest.mark.parametrize("country", OTHER_MARKETS)
def test_evidence_gate_drops_them_for_every_other_market(country):
    documents = [_retrieved(row) for row in _index_rows()]
    for language in ALL_LANGUAGES:
        assert not _has_current_locale_document(documents, country, language), (country, language)
        decision = approve_evidence("What is in Forever Absorbent-D?", RetrievalResult(documents, [], 0.95), country, language)
        assert decision.evidence == []


def test_evidence_gate_keeps_them_for_us_english_and_spanish():
    documents = [_retrieved(row) for row in _index_rows()]
    for language in ("en", "es"):
        assert all(_has_current_locale_document([document], "US", language) for document in documents)


class _FilteringClient:
    """Answer a search by applying its hard filters to in-memory rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def search(self, *, index, body):
        del index
        admitted = _admitted(body, self.rows)
        return {"hits": {"hits": [{"_source": row} for row in admitted]}}


@pytest.mark.parametrize("pointer", [False, True], ids=["no-pointer", "generation-pointer"])
def test_citation_authorization_rejects_their_sources_outside_the_us(monkeypatch, pointer):
    rows = _index_rows()
    if pointer:
        _enable_generation_pointer(monkeypatch, rows)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: _FilteringClient(rows))
    uri = rows[0]["source_uri"]
    assert is_approved_source(uri, "US", "en")
    assert is_approved_source(uri, "US", "es")
    for country in OTHER_MARKETS:
        for language in ("en", "es", "fr"):
            assert not is_approved_source(uri, country, language), (country, language)


def test_cached_answers_built_on_them_are_not_restored_outside_the_us(monkeypatch):
    rows = _index_rows()
    monkeypatch.setattr(
        cache_evidence, "_active_generation_rows",
        lambda **_: [{"active_ingestion_id": row["ingestion_id"]} for row in rows],
    )
    cached = [asdict(_retrieved(row)) for row in rows[:3]]
    assert cache_evidence.restore_evidence(cached, "US", "en") is not None
    for country in OTHER_MARKETS:
        assert cache_evidence.restore_evidence(cached, country, "en") is None, country


# --- negative control: why access_scope must never be "global" -------------------


def test_global_availability_would_leak_them_to_every_market():
    """Proves the filters above are not vacuous: the same rows marked global do leak."""
    rows = _index_rows(access_scope="global")
    for country in ("CA", "GB", "DE"):
        leaked = _admitted(_vector_query("Forever Absorbent-D", country, "en", scope="global"), rows)
        assert len(leaked) == 24, country
        assert all(_has_current_locale_document([_retrieved(row)], country, "en") for row in rows)


# --- the product_information document type ---------------------------------------


def test_product_information_is_an_accepted_upload_type():
    from services.knowledge_ingestion import DOCUMENT_TYPES

    assert "product_information" in DOCUMENT_TYPES
    assert {entry["form_fields"]["document_type"] for entry in DOCUMENTS} == {"product_information"}


@pytest.mark.parametrize(
    ("document_type", "access_scope", "allowed"),
    [
        ("product_information", "country", True),
        ("product_information", "global", False),
        ("policy", "country", True),
        ("policy", "global", False),
        ("office_directory", "global", True),
        ("office_directory", "country", False),
    ],
)
def test_upload_scope_rules_keep_product_information_in_its_market(document_type, access_scope, allowed):
    from fastapi import HTTPException

    from api.admin_routes import _check_document_scope

    if allowed:
        _check_document_scope(document_type, access_scope)
    else:
        with pytest.raises(HTTPException) as error:
            _check_document_scope(document_type, access_scope)
        assert error.value.status_code == 400


def test_prompt_labels_product_sections_as_product_information_not_policy():
    from app.prompts.builder import _section_label

    assert _section_label({"document_type": "product_information"}, False) == "Product information"
    assert _section_label({"document_type": "policy"}, False) == "Policy"
    assert _section_label({"document_type": "office_directory"}, True) == "Directory"
