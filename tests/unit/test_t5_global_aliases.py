from services.market_config import find_market_mentions


def test_localized_uganda_alias_routes_to_uganda_market() -> None:
    assert find_market_mentions("Et pour l'Ouganda ?") == {"UG"}
    assert find_market_mentions("Und die Frage für Oeganda?") == {"UG"}


def test_england_remains_unmapped_without_owner_decision() -> None:
    assert "GB" not in find_market_mentions("What is the office address in England?")
