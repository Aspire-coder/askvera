import json

from app.retrieval import glossary
from config import settings


def test_glossary_expands_reviewed_terms_without_matching_short_words(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["*"],
                        "language": ["*"],
                        "triggers": ["fpc", "preferred customer"],
                        "queries": ["Preferred Customer definition"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_QUERY_LIMIT", 4)
    glossary.load_glossary.cache_clear()

    assert glossary.glossary_queries("What is an FPC?", "US", "en") == [
        "Preferred Customer definition"
    ]
    assert glossary.glossary_queries("What is specific information?", "US", "en") == []


def test_glossary_respects_locale_metadata(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["CA"],
                        "language": ["fr"],
                        "triggers": ["pc"],
                        "queries": ["Client privilegie definition"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    glossary.load_glossary.cache_clear()

    assert glossary.glossary_queries("Que signifie PC?", "CA", "fr") == [
        "Client privilegie definition"
    ]
    assert glossary.glossary_queries("What is PC?", "US", "en") == []


def test_glossary_is_inactive_by_default(monkeypatch):
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", False)
    assert glossary.glossary_queries("How do I change sponsor?", "US", "en") == []


def test_vnext_can_enable_glossary_without_enabling_primary(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["*"],
                        "language": ["*"],
                        "triggers": ["fpc"],
                        "queries": ["Preferred Customer definition"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    glossary.load_glossary.cache_clear()

    assert glossary.glossary_queries("What is FPC?", "US", "en") == []
    assert glossary.glossary_queries("What is FPC?", "US", "en", enabled=True) == [
        "Preferred Customer definition"
    ]


def test_answer_hints_are_explicitly_vnext_only(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["*"],
                        "language": ["*"],
                        "triggers": ["fpc"],
                        "queries": ["Preferred Customer definition"],
                        "answer_hint": "FPC means Forever Preferred Customer.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    glossary.load_glossary.cache_clear()

    assert glossary.glossary_answer_hints("What is FPC?", "US", "en") == []
    assert glossary.glossary_answer_hints(
        "What is FPC?", "US", "en", enabled=True
    ) == ["FPC means Forever Preferred Customer."]


def test_glossary_skips_malformed_and_oversized_entries(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["US"],
                        "language": ["en"],
                        "triggers": ["pc"],
                        "queries": ["Preferred Customer definition"],
                    },
                    {
                        "country": ["US"],
                        "language": ["en"],
                        "triggers": ["x" * 161],
                        "queries": ["This entry must be ignored"],
                    },
                    "not-an-entry",
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    glossary.load_glossary.cache_clear()

    assert glossary.glossary_queries("What does PC mean?", "US", "en") == [
        "Preferred Customer definition"
    ]


def test_reviewed_glossary_handles_rank_typos_and_localized_cc_language(monkeypatch):
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_QUERY_LIMIT", 8)
    glossary.load_glossary.cache_clear()

    rank_queries = glossary.glossary_queries(
        "How to become a recognzied maanger?",
        "US",
        "en",
    )
    activity_queries = glossary.glossary_queries(
        "Wie setzen sich die 4 CC zusammen?",
        "DE",
        "de",
    )

    assert "Recognized Manager qualification requirements" in rank_queries
    assert (
        "Aktivitäts-Qualifikation persönliche und Non-Manager Case Credits"
        in activity_queries
    )
