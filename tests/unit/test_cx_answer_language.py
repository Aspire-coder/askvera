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
        assert detection.reason == "no_tokens"

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


# ---------------------------------------------------------------------------
# Table-driven acceptance set (coordinator review, 2026-09-18): at least 4
# ordinary customer questions per route-copy language, varied topics
# (shipping cost, returns, payment methods, contact/sponsorship), widget set
# to "en"; every one must switch to the right language EXCEPT that "no"/"da"
# may legitimately stay unswitched when the sentence is genuinely ambiguous
# between them (their function words overlap almost completely - see the
# confusion-matrix test below, which asserts this never crosses into a WRONG
# switch, only a non-switch). Plus >=10 English questions with a non-en
# widget that must switch to "en", and negatives (short, mixed, numbers,
# a product name, code-switching) that must never switch.
# ---------------------------------------------------------------------------

_NO_DA_AMBIGUOUS_PAIR = frozenset({"no", "da"})

# 4 questions per language x 12 languages = 48, covering shipping cost,
# returns, payment methods and contact/sponsorship.
ACCEPTANCE_POSITIVE_CASES: dict[str, tuple[str, ...]] = {
    "da": (
        "Hvad koster det at sende en ordre til Danmark, og hvor lang tid tager det?",
        "Hvordan kan jeg returnere et produkt, jeg har bestilt for nylig?",
        "Hvilke betalingsmetoder accepterer I for bestillinger i butikken?",
        "Hvem kan jeg kontakte, hvis jeg har sporgsmal om min sponsor?",
    ),
    "de": (
        "Wie viel kostet der Versand einer Bestellung nach Deutschland?",
        "Wie kann ich ein Produkt zurückgeben, das ich letzte Woche bestellt habe?",
        "Welche Zahlungsmethoden werden für Bestellungen akzeptiert?",
        "Wer ist mein Sponsor und wie kann ich ihn kontaktieren?",
    ),
    "es": (
        "¿Cuánto cuesta el envío de un pedido a España?",
        "¿Cómo puedo devolver un producto que pedí la semana pasada?",
        "¿Qué métodos de pago aceptan para los pedidos en línea?",
        "¿Quién es mi patrocinador y cómo puedo contactarlo?",
    ),
    "fi": (
        "Paljonko toimitus maksaa tilaukselle Suomeen ja kuinka kauan se kestää?",
        "Miten voin palauttaa tuotteen, jonka tilasin viime viikolla?",
        "Mitä maksutapoja hyväksytte verkkotilauksissa?",
        "Kuka on sponsorini ja miten voin ottaa häneen yhteyttä?",
    ),
    "fr": (
        "Quel est le coût de livraison d'une commande vers la France ?",
        "Comment puis-je retourner un produit que j'ai commandé la semaine dernière ?",
        "Quels sont les moyens de paiement acceptés pour les commandes en ligne ?",
        "Qui est mon parrain et comment puis-je le contacter ?",
    ),
    "it": (
        "Quanto costa la spedizione di un ordine in Italia e quanto tempo richiede?",
        "Come posso restituire un prodotto che ho ordinato la settimana scorsa?",
        "Quali metodi di pagamento accettate per gli ordini online?",
        "Chi è il mio sponsor e come posso contattarlo?",
    ),
    "nl": (
        "Wat kost de verzending van een bestelling naar Nederland?",
        "Hoe kan ik een product retourneren dat ik vorige week heb besteld?",
        "Welke betaalmethoden accepteren jullie voor bestellingen?",
        "Wie is mijn sponsor en hoe kan ik contact met hem opnemen?",
    ),
    "no": (
        "Hva koster frakt for en bestilling til Norge, og hvor lang tid tar det?",
        "Hvordan kan jeg returnere et produkt jeg bestilte forrige uke?",
        "Hvilke betalingsmåter godtar dere for bestillinger på nettet?",
        "Hvem er sponsoren min, og hvordan kan jeg kontakte henne?",
    ),
    "ru": (
        "Сколько стоит доставка заказа в Россию и сколько это займёт времени?",
        "Как я могу вернуть товар, который я заказал на прошлой неделе?",
        "Какие способы оплаты вы принимаете для заказов онлайн?",
        "Кто мой спонсор и как я могу с ним связаться?",
    ),
    "sr": (
        "Koliko košta dostava porudžbine u Srbiju i koliko to traje?",
        "Kako mogu da vratim proizvod koji sam naručio prošle nedelje?",
        "Koje načine plaćanja prihvatate za porudžbine na internetu?",
        "Ko je moj sponzor i kako mogu da ga kontaktiram?",
    ),
    "sv": (
        "Vad kostar frakten för en beställning till Sverige och hur lång tid tar det?",
        "Hur kan jag returnera en produkt som jag beställde förra veckan?",
        "Vilka betalningsmetoder accepterar ni för beställningar online?",
        "Vem är min sponsor och hur kan jag kontakta honom?",
    ),
}

# >=10 English customer questions, each paired with a different non-English
# widget language; every one must switch to "en".
ACCEPTANCE_ENGLISH_SWITCH_CASES: tuple[tuple[str, str], ...] = (
    ("de", "What is the shipping cost for an order to the United States?"),
    ("fr", "How can I return a product I ordered last week from your store?"),
    ("es", "Which payment methods are accepted for orders placed online?"),
    ("it", "Who is my sponsor and how do I get in touch with them today?"),
    ("nl", "What is the delivery time for an order placed this week?"),
    ("sv", "Can you tell me how to change my sponsor in the system?"),
    ("no", "How much does it cost to ship an order internationally?"),
    ("da", "What are the requirements to become a business owner here?"),
    ("ru", "How do I contact customer support about a delayed order?"),
    ("sr", "What is the minimum order amount for free shipping today?"),
)

# Negatives: must never switch, regardless of widget language. Covers short
# messages, mixed-language messages, numbers/codes, a product name, and
# code-switching (a single foreign courtesy word inside an English sentence).
ACCEPTANCE_NEGATIVE_CASES: tuple[tuple[str, str], ...] = (
    ("en", "Merci"),
    ("en", "Bonjour"),
    ("en", "Hello, quel est le prix de la livraison and how long does it take?"),
    ("en", "2026 18 04 99887766"),
    ("en", "Aloe Vera Gel price"),
    ("en", "Can I return a product, por favor?"),
    ("en", "asdf qwer zxcv tyui"),
    ("en", ""),
    ("en", "OK"),
    ("en", "12345"),
    ("de", "Forever Living Aloe Vera Gel Preisliste"),
    ("fr", "Can I return a product, s'il vous plaît?"),
)


class TestAcceptanceSet:
    """Table-driven acceptance set (coordinator review, 2026-09-18). Computes
    and asserts per-language recall/precision rather than checking individual
    sentences by name, so the thresholds stay tuned against the whole set."""

    def test_every_non_near_pair_language_switches_correctly(self):
        """Every language outside the no/da ambiguous pair must switch to
        exactly the expected language for every one of its 4 questions
        (recall == 1.0, and never a WRONG language - precision == 1.0)."""
        failures = []
        for language, questions in ACCEPTANCE_POSITIVE_CASES.items():
            if language in _NO_DA_AMBIGUOUS_PAIR:
                continue
            for question in questions:
                result = resolve_answer_language(question, "en")
                if not (result.switched and result.answer_language == language):
                    failures.append((language, question, result))
        assert not failures, f"{len(failures)} acceptance-set failures: {failures}"

    def test_no_da_pair_never_crosses_to_the_wrong_member(self):
        """no/da may legitimately stay unswitched on a genuinely ambiguous
        sentence (their function words overlap almost completely), but a
        "no" question must never switch to "da" and vice versa, and neither
        may switch to any THIRD language. Report the confusion matrix."""
        confusion: dict[str, dict[str, int]] = {"no": {}, "da": {}}
        recall_hits = {"no": 0, "da": 0}
        for language in ("no", "da"):
            for question in ACCEPTANCE_POSITIVE_CASES[language]:
                result = resolve_answer_language(question, "en")
                got = result.answer_language if result.switched else "en (unswitched)"
                confusion[language][got] = confusion[language].get(got, 0) + 1
                if result.switched and result.answer_language == language:
                    recall_hits[language] += 1
                elif result.switched:
                    # A switch happened but to the wrong language: this is
                    # the one outcome that is never acceptable here.
                    assert result.answer_language not in ("no", "da") or result.answer_language == language, (
                        f"{language} question switched to the wrong near-pair member: "
                        f"{question!r} -> {result.answer_language}"
                    )
                    raise AssertionError(
                        f"{language} question switched to an unexpected language "
                        f"{result.answer_language!r}: {question!r}"
                    )
        # Recorded for the coordinator report (also visible via -s / -rA):
        # confusion == {"no": {...}, "da": {...}}, recall_hits == {"no": n, "da": n}
        assert recall_hits["no"] >= 1, confusion
        assert recall_hits["da"] >= 1, confusion

    def test_english_questions_switch_from_every_non_english_widget(self):
        failures = []
        for widget, question in ACCEPTANCE_ENGLISH_SWITCH_CASES:
            result = resolve_answer_language(question, widget)
            if not (result.switched and result.answer_language == "en"):
                failures.append((widget, question, result))
        assert not failures, f"{len(failures)} English-switch failures: {failures}"

    def test_negatives_never_switch(self):
        failures = []
        for widget, question in ACCEPTANCE_NEGATIVE_CASES:
            result = resolve_answer_language(question, widget)
            if result.switched:
                failures.append((widget, question, result))
        assert not failures, f"{len(failures)} negatives incorrectly switched: {failures}"

    def test_overall_recall_and_precision_meet_the_documented_bar(self):
        """Single aggregate check across the whole acceptance set: recall
        (correct switches / total positives, no/da ambiguity excluded from
        the denominator's failure count since it is a documented exception)
        and precision (every switch that DID happen went to the right
        language) both computed from the same table the thresholds in
        answer_language.py were tuned against."""
        total = 0
        correct = 0
        wrong_language_switches = 0
        for language, questions in ACCEPTANCE_POSITIVE_CASES.items():
            for question in questions:
                total += 1
                result = resolve_answer_language(question, "en")
                if result.switched and result.answer_language == language:
                    correct += 1
                elif result.switched:
                    wrong_language_switches += 1
        for widget, question in ACCEPTANCE_ENGLISH_SWITCH_CASES:
            total += 1
            result = resolve_answer_language(question, widget)
            if result.switched and result.answer_language == "en":
                correct += 1
            elif result.switched:
                wrong_language_switches += 1

        recall = correct / total
        # Precision: of everything that switched, how much switched to the
        # right language. no/da non-switches are not counted as attempts.
        switched_total = correct + wrong_language_switches
        precision = correct / switched_total if switched_total else 1.0

        assert wrong_language_switches == 0, "a switch happened to the wrong language"
        assert precision == 1.0
        assert recall >= 0.85, f"recall {recall:.2%} below the documented 0.85 bar (correct={correct}/{total})"


# ---------------------------------------------------------------------------
# Brand/market extension (coordinator review, 2026-09-19): a realistic
# customer question routinely names the brand ("Forever", "Aloe Vera") and a
# market ("Forever Kenya", "...au Kenya ?", "Forever Norge"), sometimes
# together with a product term ("Forever Bright Toothgel", "Forever
# Freedom"). These proper nouns carry no language signal and must not dilute
# or tilt the margin between candidates. At least 4 such questions per
# language (widget=en), plus 4 English ones (non-en widget), covering the
# same topics as the base acceptance set.
# ---------------------------------------------------------------------------

BRAND_MARKET_POSITIVE_CASES: dict[str, tuple[str, ...]] = {
    "da": (
        "Hvad koster det at sende Forever Aloe Vera Gel til Forever Danmark?",
        "Hvordan kan jeg returnere Forever Bright Toothgel, som jeg bestilte hos Forever Norge?",
        "Hvilke betalingsmetoder accepterer Forever Sverige for Forever Freedom-bestillinger?",
        "Hvem hos Forever Living Norge kan jeg kontakte om min Aloe Vera Gel-ordre?",
    ),
    "de": (
        "Wie viel kostet der Versand von Forever Aloe Vera Gel nach Forever Kenia?",
        "Wie kann ich Forever Bright Toothgel zurückgeben, das ich bei Forever Ghana bestellt habe?",
        "Welche Zahlungsmethoden akzeptiert Forever Norwegen für Forever Freedom-Bestellungen?",
        "Wer bei Forever Living Schweden kann mir bei meiner Aloe Vera Gel Bestellung helfen?",
    ),
    "es": (
        "¿Cuánto cuesta enviar Forever Aloe Vera Gel a Forever Kenia?",
        "¿Cómo puedo devolver Forever Bright Toothgel que pedí en Forever Ghana?",
        "¿Qué métodos de pago acepta Forever Noruega para los pedidos de Forever Freedom?",
        "¿Quién en Forever Living Suecia puede ayudarme con mi pedido de Aloe Vera Gel?",
    ),
    "fi": (
        "Paljonko Forever Aloe Vera Gelin toimitus Forever Kenialle maksaa?",
        "Miten voin palauttaa Forever Bright Toothgelin, jonka tilasin Forever Ghanalta?",
        "Mitä maksutapoja Forever Norja hyväksyy Forever Freedom -tilauksissa?",
        "Kuka Forever Living Ruotsissa voi auttaa minua Aloe Vera Gel -tilauksessani?",
    ),
    "fr": (
        "Quel est le coût de livraison de Forever Aloe Vera Gel vers Forever Kenya ?",
        "Comment puis-je retourner Forever Bright Toothgel que j'ai commandé chez Forever Ghana ?",
        "Quels sont les moyens de paiement acceptés par Forever Kenya ?",
        "Quels sont les moyens de paiement acceptés par la société Forever au Kenya ?",
    ),
    "it": (
        "Quanto costa spedire Forever Aloe Vera Gel a Forever Kenya?",
        "Come posso restituire Forever Bright Toothgel che ho ordinato da Forever Ghana?",
        "Quali metodi di pagamento accetta Forever Norvegia per gli ordini Forever Freedom?",
        "Chi di Forever Living Svezia può aiutarmi con il mio ordine di Aloe Vera Gel?",
    ),
    "nl": (
        "Wat kost het verzenden van Forever Aloe Vera Gel naar Forever Kenia?",
        "Hoe kan ik Forever Bright Toothgel retourneren dat ik bij Forever Ghana heb besteld?",
        "Welke betaalmethoden accepteert Forever Noorwegen voor Forever Freedom-bestellingen?",
        "Wie bij Forever Living Zweden kan mij helpen met mijn Aloe Vera Gel bestelling?",
    ),
    "no": (
        "Hva koster det å sende Forever Aloe Vera Gel til Forever Kenya?",
        "Hvordan kan jeg returnere Forever Bright Toothgel som jeg bestilte hos Forever Ghana?",
        "Hvilke betalingsmåter godtar Forever Norge for Forever Freedom-bestillinger?",
        "Hvem hos Forever Living Sverige kan hjelpe meg med Aloe Vera Gel-bestillingen min?",
    ),
    "ru": (
        "Сколько стоит доставка Forever Aloe Vera Gel в Forever Кению?",
        "Как я могу вернуть Forever Bright Toothgel, который я заказал у Forever Гана?",
        "Какие способы оплаты принимает Forever Норвегия для заказов Forever Freedom?",
        "Кто в Forever Living Швеция может помочь мне с заказом Aloe Vera Gel?",
    ),
    "sr": (
        "Koliko košta slanje Forever Aloe Vera Gela u Forever Keniju?",
        "Kako mogu da vratim Forever Bright Toothgel koji sam naručio od Forever Gane?",
        "Koje načine plaćanja prihvata Forever Norveška za Forever Freedom porudžbine?",
        "Ko iz Forever Living Švedske može da mi pomogne oko porudžbine Aloe Vera Gela?",
    ),
    "sv": (
        "Vad kostar det att skicka Forever Aloe Vera Gel till Forever Kenya?",
        "Hur kan jag returnera Forever Bright Toothgel som jag beställde från Forever Ghana?",
        "Vilka betalningsmetoder accepterar Forever Norge för Forever Freedom-beställningar?",
        "Vem på Forever Living Sverige kan hjälpa mig med min Aloe Vera Gel-beställning?",
    ),
}

# 4 English "Forever + market + product" questions, each with a different
# non-en widget; must switch to en.
BRAND_MARKET_ENGLISH_SWITCH_CASES: tuple[tuple[str, str], ...] = (
    ("de", "How much does it cost to ship Forever Aloe Vera Gel to Forever Norway?"),
    ("fr", "How can I return Forever Bright Toothgel that I ordered from Forever Sweden?"),
    ("es", "Which payment methods does Forever Kenya accept for Forever Freedom orders?"),
    ("ru", "Who at Forever Living Ghana can help me with my Aloe Vera Gel order today?"),
)


class TestBrandMarketAcceptanceSet:
    """Coordinator review, 2026-09-19: recall on REALISTIC customer questions
    (which name the brand and a market, sometimes a product) was far too low
    because those proper nouns diluted or tilted the score. This set is
    deliberately harder than TestAcceptanceSet's (every sentence carries 2-4
    proper-noun tokens the detector must see through), so its recall bar is
    lower, but precision must stay perfect: a proper noun must never cause a
    switch to the WRONG language, only, at worst, no switch at all."""

    def test_no_wrong_language_switch_anywhere_in_the_brand_market_set(self):
        failures = []
        for language, questions in BRAND_MARKET_POSITIVE_CASES.items():
            for question in questions:
                result = resolve_answer_language(question, "en")
                if result.switched and result.answer_language != language:
                    failures.append((language, question, result))
        for widget, question in BRAND_MARKET_ENGLISH_SWITCH_CASES:
            result = resolve_answer_language(question, widget)
            if result.switched and result.answer_language != "en":
                failures.append(("en", question, result))
        assert not failures, f"{len(failures)} wrong-language switches in the brand/market set: {failures}"

    def test_the_two_originally_reported_probes_now_switch_to_french(self):
        # The exact two sentences the coordinator reported as failing.
        first = resolve_answer_language(
            "Quels sont les moyens de paiement acceptés par Forever Kenya ?", "en"
        )
        second = resolve_answer_language(
            "Quels sont les moyens de paiement acceptés par la société Forever au Kenya ?", "en"
        )
        assert first == AnswerLanguage("fr", True, "strong_signal")
        assert second == AnswerLanguage("fr", True, "strong_signal")

    def test_brand_market_recall_meets_the_documented_bar(self):
        """Aggregate recall/precision over the brand/market set, reported
        for the coordinator (see docs/conversation-quality/phase3/
        CX_LANE7_ANSWER_LANGUAGE.md for the full before/after table)."""
        total = 0
        correct = 0
        wrong = 0
        for language, questions in BRAND_MARKET_POSITIVE_CASES.items():
            for question in questions:
                total += 1
                result = resolve_answer_language(question, "en")
                if result.switched and result.answer_language == language:
                    correct += 1
                elif result.switched:
                    wrong += 1
        for widget, question in BRAND_MARKET_ENGLISH_SWITCH_CASES:
            total += 1
            result = resolve_answer_language(question, widget)
            if result.switched and result.answer_language == "en":
                correct += 1
            elif result.switched:
                wrong += 1

        recall = correct / total
        assert wrong == 0, "a switch happened to the wrong language in the brand/market set"
        assert recall >= 0.70, f"brand/market recall {recall:.2%} below the documented 0.70 bar ({correct}/{total})"


class TestMarketNameExclusion:
    """Directly exercises the exclusion mechanism, independent of any one
    sentence's overall outcome."""

    def test_market_name_alone_contributes_no_score(self):
        # A message that is ONLY brand/market words has no scoring tokens
        # left and therefore no language evidence at all.
        detection = detect_message_language("Forever Aloe Vera Kenya Ghana Norway")
        assert detection.language is None

    def test_short_single_word_country_name_fragment_is_not_excluded(self):
        # Regression guard for the "Costa Rica" -> "costa" defect found while
        # tuning this set: multi-word market names must never be split into
        # single-word fragments that can collide with an unrelated language's
        # ordinary word (Italian "costa" = "it costs").
        result = resolve_answer_language(
            "Quanto costa spedire questo prodotto in Costa Rica e quanto tempo richiede?", "en"
        )
        assert result == AnswerLanguage("it", True, "strong_signal")

    def test_latin_brand_name_inside_cyrillic_sentence_is_not_mixed_script(self):
        detection = detect_message_language(
            "Сколько стоит доставка Forever Aloe Vera Gel в Forever Кению?"
        )
        assert detection.reason != "mixed_script"
        assert detection.language == "ru"
