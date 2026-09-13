"""INT6 localized directory-field follow-ups (offline and narrowly scoped)."""

import json
from pathlib import Path

from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections


def _history(question: str) -> str:
    return f"user: {question}\nvera: An earlier answer."


def _configured_languages() -> set[str]:
    config_path = Path(__file__).parents[2] / "config" / "policy_locales.json"
    return {language for locale in json.loads(config_path.read_text(encoding="utf-8"))["locales"] for language in locale["languages"]}


def test_every_configured_language_accepts_a_localized_field_continuation() -> None:
    examples = {
        "en": "And the shipping?", "fr": "Et la livraison ?", "es": "¿Y la entrega?",
        "de": "Und die Lieferkosten?", "nl": "En de verzendkosten?", "da": "Og hjemmesiden?",
        "fi": "Entä toimitus?", "it": "E la consegna?", "ru": "А доставка?",
        "no": "Og nettsiden?", "sr": "A isporuka?", "sv": "Och leveransen?",
    }
    assert set(examples) == _configured_languages()
    orchestrator = AIOrchestrator()
    for language, message in examples.items():
        assert orchestrator._is_directory_field_follow_up(message), language
        assert orchestrator._needs_history_context(message, _history("What is the delivery cost in Kenya?")), language


def test_localized_market_replacement_preserves_topic_and_replaces_market() -> None:
    orchestrator = AIOrchestrator()
    query = orchestrator._build_retrieval_query(
        "Et pour l'Ouganda ?", _history("Quel est le coût de livraison au Kenya ?"), "cid"
    )
    assert "Kenya" not in query
    assert "Ouganda" in query
    assert "livraison" in query.lower()
    assert opensearch_sections._directory_target_country_names(query, "US") == {"Uganda"}


def test_localized_ambiguous_office_contact_does_not_inherit_a_market() -> None:
    orchestrator = AIOrchestrator()
    assert not orchestrator._needs_history_context(
        "Hoe zit het met kantoor?", _history("Wat zijn de verzendkosten naar Kenia?")
    )
    assert not orchestrator._needs_history_context(
        "Qu'en est-il du bureau ?", _history("Quel est le coût de livraison au Kenya ?")
    )
    assert not orchestrator._needs_history_context(
        "Wie sieht es mit dem Büro aus?", _history("Wie hoch sind die Lieferkosten nach Kenia?")
    )


def test_localized_policy_field_phrase_is_not_a_directory_continuation() -> None:
    assert not AIOrchestrator()._is_directory_field_follow_up("Et la politique de livraison ?")
    assert not AIOrchestrator()._needs_history_context(
        "E la politica di consegna?", _history("Qual è il costo di consegna in Kenya?")
    )
    assert not AIOrchestrator()._needs_history_context(
        "Og leveringsretningslinjer?", _history("Hva er leveringskostnaden i Kenya?")
    )
    assert not AIOrchestrator()._needs_history_context(
        "Och leveransriktlinjer?", _history("Vad kostar leveransen i Kenya?")
    )
