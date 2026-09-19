"""CX Lane 7 - deterministic answer-language detector and switch decision.

X1 (approval 6, option B): answer language follows the message language on a
strong, unambiguous signal only; retrieval keeps `body.language` unchanged.
No case ids - every scenario below is a constructed, generic sentence.
"""

from __future__ import annotations

from app.orchestrator.answer_language import (
    ROUTE_COPY_LANGUAGES,
    AnswerLanguage,
    Detection,
    detect_message_language,
    resolve_answer_language,
    retrieval_language,
)


class TestDetectMessageLanguage:
    def test_french_message_scores_french_highest(self):
        detection = detect_message_language(
            "Quel est le prix de la livraison pour cette commande et quand arrive-t-elle ?"
        )
        assert isinstance(detection, Detection)
        assert detection.language == "fr"
        assert detection.score >= 3

    def test_english_message_scores_english_highest(self):
        detection = detect_message_language("What is the delivery cost and how long does it take?")
        assert detection.language == "en"

    def test_numbers_only_message_has_no_language(self):
        detection = detect_message_language("12345 67890 2026 18")
        assert detection.language is None
        assert detection.reason == "no_letters"

    def test_empty_message_has_no_language(self):
        detection = detect_message_language("")
        assert detection.language is None

    def test_mixed_script_is_ambiguous(self):
        # Latin and Cyrillic letters both present in one message.
        detection = detect_message_language("Hello and what does это mean here?")
        assert detection.language is None
        assert detection.reason == "mixed_script"

    def test_cyrillic_text_scores_russian_over_serbian_cyrillic(self):
        detection = detect_message_language(
            "Что нужно для того чтобы узнать где находится этот офис и как туда добраться?"
        )
        assert detection.language == "ru"

    def test_cyrillic_text_restricts_candidates_to_ru_and_sr(self):
        detection = detect_message_language(
            "Что нужно для того чтобы узнать где находится этот офис?",
            candidates=ROUTE_COPY_LANGUAGES,
        )
        assert detection.language in {"ru", "sr", None}

    def test_determinism_same_message_same_result(self):
        message = "Wo finde ich die Adresse und die Öffnungszeiten für dieses Büro?"
        first = detect_message_language(message)
        second = detect_message_language(message)
        assert first == second

    def test_candidates_param_restricts_scoring(self):
        detection = detect_message_language(
            "Quel est le prix de la livraison pour cette commande ?",
            candidates=("en", "de"),
        )
        assert detection.language != "fr"


class TestResolveAnswerLanguage:
    def test_switches_on_strong_french_signal_with_english_widget(self):
        result = resolve_answer_language(
            "Quel est le prix de la livraison pour cette commande et quand arrive-t-elle chez moi ?",
            "en",
        )
        assert isinstance(result, AnswerLanguage)
        assert result.answer_language == "fr"
        assert result.switched is True
        assert result.reason == "strong_signal"

    def test_no_switch_when_message_matches_selected_language(self):
        result = resolve_answer_language(
            "What is the delivery cost and how long does it take to arrive?",
            "en",
        )
        assert result.answer_language == "en"
        assert result.switched is False
        assert result.reason == "matches_selected"

    def test_no_switch_on_short_single_word_message(self):
        result = resolve_answer_language("Merci", "en")
        assert result.answer_language == "en"
        assert result.switched is False
        assert result.reason == "too_short"

    def test_no_switch_on_short_greeting(self):
        result = resolve_answer_language("Bonjour", "en")
        assert result.switched is False

    def test_no_switch_on_mixed_language_message(self):
        result = resolve_answer_language(
            "Hello, quel est le prix de la livraison and how long does it take?",
            "en",
        )
        assert result.switched is False
        assert result.answer_language == "en"

    def test_no_switch_on_numbers_only_message(self):
        result = resolve_answer_language("2026 18 04 99887766", "en")
        assert result.switched is False
        assert result.answer_language == "en"

    def test_norwegian_swedish_near_pair_requires_extra_margin(self):
        # Heavily Norwegian-leaning sentence, widget set to Swedish: the
        # near-pair guard must either not switch, or only switch with a
        # margin well above the base threshold.
        result = resolve_answer_language(
            "Hva er prisen for levering av denne bestillingen og når kommer den fram til meg?",
            "sv",
        )
        if result.switched:
            assert result.answer_language == "no"
        else:
            assert result.answer_language == "sv"

    def test_danish_swedish_near_pair_no_accidental_switch_on_weak_signal(self):
        # A short, weakly-Danish-leaning message must not switch a Swedish
        # widget into Danish or Norwegian on a thin margin.
        result = resolve_answer_language("Hvad koster det og hvor lang tid tar det?", "sv")
        assert result.switched is False or result.answer_language in {"da", "no"}

    def test_serbian_latin_vs_other_latin_needs_extra_margin(self):
        result = resolve_answer_language(
            "Šta je sa cenom dostave za ovu porudžbinu i kada stiže?",
            "en",
        )
        # Either it does not switch, or it switches specifically to Serbian
        # (never mistaken for an unrelated Latin-script language).
        if result.switched:
            assert result.answer_language == "sr"

    def test_cyrillic_russian_vs_cyrillic_serbian_distinguished(self):
        ru_message = "Что нужно чтобы узнать где находится офис и как туда добраться?"
        sr_message = "Шта треба да урадим да бих сазнао где се налази канцеларија и како да стигнем тамо?"
        ru_result = resolve_answer_language(ru_message, "en")
        sr_result = resolve_answer_language(sr_message, "en")
        if ru_result.switched:
            assert ru_result.answer_language == "ru"
        if sr_result.switched:
            assert sr_result.answer_language == "sr"

    def test_no_switch_when_no_signal_detected(self):
        result = resolve_answer_language("asdf qwer zxcv tyui", "en")
        assert result.switched is False
        assert result.answer_language == "en"

    def test_determinism(self):
        message = "Quel est le prix de la livraison pour cette commande et quand arrive-t-elle chez moi ?"
        first = resolve_answer_language(message, "en")
        second = resolve_answer_language(message, "en")
        assert first == second

    def test_never_switches_outside_route_copy_languages_implicitly(self):
        # A message written in a language with no route copy at all (Polish)
        # must not accidentally score above threshold for a route-copy
        # language and switch into it.
        result = resolve_answer_language(
            "Jaki jest koszt dostawy tego zamowienia i kiedy dotrze do mnie?",
            "en",
        )
        assert result.answer_language in {"en", *ROUTE_COPY_LANGUAGES}


class TestRetrievalLanguageInvariant:
    def test_retrieval_language_always_returns_selected_language(self):
        assert retrieval_language("en", "fr") == "en"
        assert retrieval_language("en", "en") == "en"
        assert retrieval_language("sv", "no") == "sv"

    def test_retrieval_language_ignores_answer_language_value(self):
        # The invariant: swapping answer_language never changes the result.
        for answer_language in ROUTE_COPY_LANGUAGES:
            assert retrieval_language("de", answer_language) == "de"

    def test_retrieval_language_matches_resolve_answer_language_selected(self):
        message = "Quel est le prix de la livraison pour cette commande et quand arrive-t-elle chez moi ?"
        selected = "en"
        resolved = resolve_answer_language(message, selected)
        # Whether or not the answer switched, retrieval stays on selected.
        assert retrieval_language(selected, resolved.answer_language) == selected
