import json
from pathlib import Path

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


def test_joined_approved_term_adds_only_the_reviewed_spaced_phrase(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["*"],
                        "language": ["*"],
                        "triggers": ["recognized manager", "preferred customer"],
                        "queries": ["broader experimental expansion"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_ENABLED", False)
    glossary.load_glossary.cache_clear()

    assert glossary.approved_joined_term_queries(
        "How can I become a recognizedmanager?", "US", "en"
    ) == ["recognized manager"]
    assert glossary.glossary_queries(
        "How can I become a recognizedmanager?", "US", "en"
    ) == []


def test_joined_term_matching_does_not_fuzz_or_expand_normal_phrases(tmp_path, monkeypatch):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "country": ["*"],
                        "language": ["*"],
                        "triggers": ["recognized manager"],
                        "queries": ["unused"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "OPENSEARCH_GLOSSARY_PATH", str(path))
    glossary.load_glossary.cache_clear()

    assert glossary.approved_joined_term_queries(
        "How can I become a recognized manager?", "US", "en"
    ) == []
    assert glossary.approved_joined_term_queries(
        "How can I become a recognizdmanager?", "US", "en"
    ) == []


def test_production_glossary_has_no_english_only_entries() -> None:
    """Regression guard: three entries (including the arbitration/class-
    action-waiver one) were previously scoped to language: ["en"], so an
    English trigger word typed by a user on a non-English-configured market
    (a real scenario - most markets default to a non-English language)
    would never expand, even though every other entry uses ["*"]. If a
    genuinely locale-restricted entry is added later, update this test
    deliberately rather than widen it reflexively.
    """
    path = Path(settings.OPENSEARCH_GLOSSARY_PATH)
    payload = json.loads(path.read_text(encoding="utf-8"))

    non_wildcard = [
        entry["id"]
        for entry in payload["entries"]
        if entry.get("language") != ["*"]
    ]
    assert non_wildcard == []
