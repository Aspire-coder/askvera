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
