"""Lane 4 tests: config/conversation_routes.json coverage and app.response.cx_render.

The message-key table in docs/conversation-quality/phase3/CX_LANES.md is
binding and parsed here rather than retyped, so this test file stays in sync
with that doc instead of silently drifting from it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.response import cx_render
from app.response.cx_render import join_list, mixed_language_or_empty, render
from config.directory_field_vocabulary import (
    ADDRESS,
    BUSINESS_HOURS,
    DELIVERY_COST,
    DELIVERY_TIME,
    EMAIL,
    FAX,
    ORDER_PHONE,
    PAYMENT_METHODS,
    PHONE,
    WEBSITE,
)

ROOT = Path(__file__).parents[2]
ROUTES_PATH = ROOT / "config" / "conversation_routes.json"
CX_LANES_PATH = ROOT / "docs" / "conversation-quality" / "phase3" / "CX_LANES.md"

# The 12 locales CX_LANES.md and config/conversation_routes.json both fix.
LOCALES = ["en", "fr", "es", "de", "nl", "it", "da", "fi", "no", "sr", "sv", "ru"]

# The ten canonical directory field keys utils/directory_fields.py already
# tracks (config/directory_field_vocabulary.py's own constants, imported
# above rather than retyped) -- Lane 4 owns one field_label_<field> message
# key per field, for every locale.
CANONICAL_FIELDS = [
    PHONE,
    ORDER_PHONE,
    EMAIL,
    WEBSITE,
    ADDRESS,
    BUSINESS_HOURS,
    PAYMENT_METHODS,
    DELIVERY_COST,
    DELIVERY_TIME,
    FAX,
]


def _parse_cx_lanes_message_keys() -> dict[str, set[str]]:
    """Parse the "Message keys" table in CX_LANES.md: key -> placeholder names.

    Returns literal keys only -- the templated `suggest_topic_<name>` row is
    expanded using the concrete key names its own "Used by" cell lists
    (`suggest_topic_delivery_cost` etc.), never retyped by hand here.
    """
    text = CX_LANES_PATH.read_text(encoding="utf-8")
    section = text.split("## Message keys", 1)[1]
    section = section.split("\n## ", 1)[0]

    keys: dict[str, set[str]] = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 3:
            continue
        raw_key, placeholder_col, rest_col = cols[0], cols[1], cols[2]
        key = raw_key.strip("`")
        placeholders = set(re.findall(r"\{(\w+)\}", placeholder_col))
        if "<name>" in key:
            # Expand the closed set of concrete suggest_topic_* keys named in
            # the "Used by" cell for this templated row.
            for concrete in re.findall(r"`([a-z_]+)`", rest_col):
                keys[concrete] = set()
            continue
        keys[key] = placeholders
    assert keys, "failed to parse any keys from CX_LANES.md Message keys table"
    return keys


CX_LANES_KEYS = _parse_cx_lanes_message_keys()


def _routes() -> dict:
    return json.loads(ROUTES_PATH.read_text(encoding="utf-8"))["locales"]


def _placeholders_in(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", template))


class TestCxLanesKeyCoverage:
    def test_cx_lanes_table_parsed_the_expected_keys(self) -> None:
        # Guards the parser itself: if CX_LANES.md's table shape changes in a
        # way the regex above stops understanding, this fails loudly instead
        # of silently checking zero keys.
        assert CX_LANES_KEYS.keys() >= {
            "evidence_missing_detail",
            "dependency_unavailable",
            "cross_market_policy_scope",
            "international_directory_note",
            "personal_account_limit",
            "partial_answer_gap",
            "clarify_field",
            "clarify_country",
            "clarify_role",
            "repair_ack",
            "contact_offer",
            "suggest_intro",
            "suggest_topic_delivery_cost",
            "suggest_topic_payment_methods",
            "suggest_topic_contact",
            "suggest_topic_returns",
        }

    def test_every_cx_lanes_key_present_in_all_12_locales(self) -> None:
        routes = _routes()
        for key in CX_LANES_KEYS:
            for locale in LOCALES:
                responses = routes[locale]["responses"]
                assert key in responses, f"{key!r} missing for locale {locale!r}"
                assert str(responses[key]).strip(), f"{key!r} empty for locale {locale!r}"

    def test_every_locales_placeholders_match_english_per_key(self) -> None:
        routes = _routes()
        for key, expected_placeholders in CX_LANES_KEYS.items():
            english_placeholders = _placeholders_in(routes["en"]["responses"][key])
            assert english_placeholders == expected_placeholders, key
            for locale in LOCALES:
                locale_placeholders = _placeholders_in(routes[locale]["responses"][key])
                assert locale_placeholders == english_placeholders, (key, locale)

    def test_field_labels_present_for_every_canonical_field_and_locale(self) -> None:
        routes = _routes()
        for field in CANONICAL_FIELDS:
            key = f"field_label_{field}"
            for locale in LOCALES:
                responses = routes[locale]["responses"]
                assert key in responses, f"{key!r} missing for locale {locale!r}"
                assert str(responses[key]).strip()

    def test_dependency_unavailable_matches_bedrock_error_alias_per_locale(self) -> None:
        routes = _routes()
        for locale in LOCALES:
            responses = routes[locale]["responses"]
            assert responses["dependency_unavailable"] == responses["bedrock_error"]


class TestRender:
    def test_render_fills_english_placeholder(self) -> None:
        text = render("evidence_missing_detail", "en", topic="delivery cost")
        assert "delivery cost" in text
        assert "{topic}" not in text

    def test_render_uses_reviewed_copy_for_route_locale(self) -> None:
        text = render("repair_ack", "fr")
        routes = _routes()
        assert text == routes["fr"]["responses"]["repair_ack"]

    def test_render_fills_placeholder_for_a_reviewed_non_english_locale(self) -> None:
        text = render("cross_market_policy_scope", "de", country="Austria")
        assert "Austria" in text
        assert "{country}" not in text

    def test_unknown_key_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            render("not_a_real_key", "en")

    def test_never_returns_empty_even_for_unconfigured_language(self, monkeypatch) -> None:
        monkeypatch.setattr(cx_render, "localize_reviewed_copy", lambda *a, **k: None)
        text = render("repair_ack", "xx")
        assert text.strip()
        # Falls back to the English floor.
        assert text == render("repair_ack", "en")


class TestUnconfiguredLanguageTranslationPath:
    def test_arabic_path_uses_mocked_translator_and_fills_placeholder(self, monkeypatch) -> None:
        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            assert language == "ar"
            # A faithful mock: carries the protected sentinel through and
            # wraps the rest in a recognizably different (mocked) string.
            return f"[AR] {source_text}"

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("evidence_missing_detail", "ar", topic="fees")
        assert text.startswith("[AR] ")
        assert "fees" in text
        assert "{topic}" not in text
        assert "⟦" not in text and "⟩" not in text

    def test_portuguese_path_uses_mocked_translator_and_fills_placeholder(self, monkeypatch) -> None:
        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            assert language == "pt"
            return f"[PT] {source_text}"

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("contact_offer", "pt", contact="Customer Care")
        assert text.startswith("[PT] ")
        assert "Customer Care" in text
        assert "{contact}" not in text

    def test_mocked_translation_dropping_a_placeholder_falls_back_to_english(self, monkeypatch) -> None:
        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            # Drops the sentinel entirely -- a lossy/unsafe translation.
            return "a mistranslation with no placeholder at all"

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("evidence_missing_detail", "ar", topic="fees")
        assert text == render("evidence_missing_detail", "en", topic="fees")

    def test_mocked_translation_duplicating_a_placeholder_falls_back_to_english(self, monkeypatch) -> None:
        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            # Duplicates the sentinel -- also unsafe.
            return source_text + source_text

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("evidence_missing_detail", "ar", topic="fees")
        assert text == render("evidence_missing_detail", "en", topic="fees")

    def test_mocked_translation_altering_a_placeholder_falls_back_to_english(self, monkeypatch) -> None:
        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            # Alters the sentinel's case -- exact-match check must catch this.
            return source_text.lower()

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("evidence_missing_detail", "ar", topic="fees")
        assert text == render("evidence_missing_detail", "en", topic="fees")

    def test_mocked_translation_failure_falls_back_to_english(self, monkeypatch) -> None:
        monkeypatch.setattr(cx_render, "localize_reviewed_copy", lambda *a, **k: None)
        text = render("repair_ack", "ar")
        assert text == render("repair_ack", "en")

    def test_no_placeholder_key_still_goes_through_translator_for_unconfigured_language(
        self, monkeypatch
    ) -> None:
        calls = []

        def fake_translate(source_text: str, language: str, response_key: str = "") -> str:
            calls.append((source_text, language, response_key))
            return f"[XX] {source_text}"

        monkeypatch.setattr(cx_render, "localize_reviewed_copy", fake_translate)
        text = render("suggest_intro", "xx")
        assert calls, "localize_reviewed_copy was never called"
        assert text.startswith("[XX] ")


class TestJoinList:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_two_items_join_without_a_comma(self, locale: str) -> None:
        joined = join_list(["a", "b"], locale)
        assert joined.startswith("a")
        assert joined.endswith("b")
        assert ", " not in joined

    @pytest.mark.parametrize("locale", LOCALES)
    def test_three_items_join_with_commas_and_one_conjunction(self, locale: str) -> None:
        joined = join_list(["a", "b", "c"], locale)
        assert joined.count(", ") == 1
        assert joined.startswith("a, b")
        assert joined.endswith("c")

    def test_single_item_returned_unchanged(self) -> None:
        assert join_list(["only"], "fr") == "only"

    def test_empty_list_returns_empty_string(self) -> None:
        assert join_list([], "en") == ""

    def test_unconfigured_language_falls_back_to_english_separators(self) -> None:
        assert join_list(["a", "b", "c"], "xx") == join_list(["a", "b", "c"], "en")

    def test_russian_uses_its_own_conjunction(self) -> None:
        joined = join_list(["a", "b"], "ru")
        assert "и" in joined  # Cyrillic "and"


class TestMixedLanguageOrEmpty:
    def test_empty_string_is_flagged(self) -> None:
        assert mixed_language_or_empty("", "en") is True
        assert mixed_language_or_empty("   ", "ru") is True

    def test_latin_text_for_russian_is_flagged(self) -> None:
        assert mixed_language_or_empty("This is plain English text.", "ru") is True

    def test_cyrillic_text_for_english_is_flagged(self) -> None:
        assert mixed_language_or_empty("Это текст.", "en") is True

    def test_cyrillic_text_for_russian_is_not_flagged(self) -> None:
        assert mixed_language_or_empty("Это текст.", "ru") is False

    def test_latin_text_for_english_is_not_flagged(self) -> None:
        assert mixed_language_or_empty("This is fine.", "en") is False

    def test_digits_only_text_is_not_flagged_on_script_grounds(self) -> None:
        assert mixed_language_or_empty("12345", "ru") is False
        assert mixed_language_or_empty("12345", "en") is False


def test_join_alternatives_is_a_localized_choice():
    from app.response.cx_render import join_alternatives

    assert join_alternatives(["shipping cost", "shopping cost"], "en") == "shipping cost or shopping cost"
    assert join_alternatives(["a", "b", "c"], "es") == "a, b o c"
    assert join_alternatives(["a", "b"], "de") == "a oder b"
    assert join_alternatives(["a", "b"], "fi") == "a vai b"
    assert join_alternatives(["a", "b"], "ru") == "a или b"
    assert join_alternatives(["a", "b"], "pt") == "a or b"
    assert join_alternatives(["only"], "fr") == "only"
    assert join_alternatives([], "en") == ""
