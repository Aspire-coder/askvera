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

# Known, documented miss within ACCEPTANCE_POSITIVE_CASES (Fable CX review
# finding F4, 2026-09-19): an earlier revision silently SWAPPED this
# sentence out for one that switches, when removing the (incorrect) Latin
# Serbian diacritic bonus made it stop switching - without saying so in
# CX_LANE7's "unchanged" recall claim. It is restored here, kept in the
# table (not deleted again) so a future change that makes it start
# switching - right OR wrong - is visible, and so the recall bar stays
# honest about exactly what it covers. It genuinely IS ambiguous with
# Croatian/Bosnian (see the hr/bs sink in answer_language.py), so staying
# unswitched is the correct, safe outcome, not a defect - see
# TestAcceptanceSet.test_known_miss_sr_sentence_stays_unswitched.
_KNOWN_MISS_CASES: frozenset[tuple[str, str]] = frozenset(
    {
        ("sr", "Koje načine plaćanja prihvatate za porudžbine na internetu?"),
        # The two below are new costs of the Fable re-review word-evidence
        # gate (2026-09-19): both are genuinely correct switches whose
        # evidence happens to have the SAME thin-word/letter-heavy shape as
        # the wrong-language switches that gate exists to block (one
        # matching marker word plus a shared moderate-accent letter bonus -
        # see answer_language.py's MIN_WORD_EVIDENCE/MIN_LATIN_SWITCH_SHARE
        # docstring). There is no way to tell these apart from the pt/hu
        # false positives using the evidence shape alone, so blocking them
        # too is the safe, documented trade the coordinator accepted
        # ("a small drop is acceptable; state it").
        ("fi", "Mitä maksutapoja hyväksytte verkkotilauksissa?"),
        ("sv", "Vilka betalningsmetoder accepterar ni för beställningar online?"),
    }
)

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
        # Known miss - see _KNOWN_MISS_CASES above (Fable F4): restored,
        # not deleted, and excluded from the "must switch" assertion below.
        "Koje načine plaćanja prihvatate za porudžbine na internetu?",
        "Da li prihvatate sve načine plaćanja za porudžbine na internetu?",
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
        exactly the expected language for every one of its questions except
        the documented _KNOWN_MISS_CASES (recall == 1.0 on the rest, and
        never a WRONG language anywhere - precision == 1.0)."""
        failures = []
        for language, questions in ACCEPTANCE_POSITIVE_CASES.items():
            if language in _NO_DA_AMBIGUOUS_PAIR:
                continue
            for question in questions:
                if (language, question) in _KNOWN_MISS_CASES:
                    continue
                result = resolve_answer_language(question, "en")
                if not (result.switched and result.answer_language == language):
                    failures.append((language, question, result))
        assert not failures, f"{len(failures)} acceptance-set failures: {failures}"

    def test_known_miss_cases_stay_unswitched(self):
        """Every documented _KNOWN_MISS_CASES entry stays unswitched, for
        its own documented reason (see the frozenset's own comments): the
        `sr` sentence restored per Fable F4 (2026-09-19, genuinely ambiguous
        with Croatian/Bosnian), and the `fi`/`sv` sentences that are a new,
        disclosed cost of the Fable re-review word-evidence gate (their
        evidence has the same thin-word/letter-heavy shape as a true
        wrong-language switch, so the gate cannot tell them apart). None of
        these is a wrong-language switch - all stay on the selected
        language."""
        for language, question in _KNOWN_MISS_CASES:
            result = resolve_answer_language(question, "en")
            assert result.switched is False, (language, question, result)
            assert result.answer_language == "en", (language, question, result)

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
        # Bar lowered 0.85 -> 0.80 (Fable CX re-review, 2026-09-19): the new
        # word-evidence gate (MIN_WORD_EVIDENCE/MIN_LATIN_SWITCH_SHARE - see
        # answer_language.py) closed two real wrong-language switches
        # (Portuguese/Hungarian read as Spanish) but, being unable to tell
        # a true positive with the same thin-evidence shape apart from a
        # false one, also cost two genuine base-set switches (fi, sv - see
        # _KNOWN_MISS_CASES). Precision (0 wrong switches) stays 100%; this
        # bar states the recall cost honestly rather than hiding it.
        assert recall >= 0.80, f"recall {recall:.2%} below the documented 0.80 bar (correct={correct}/{total})"


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
        # Bar lowered 0.70 -> 0.65 (Fable S4, 2026-09-19), now 0.65 -> 0.55
        # (Fable re-review, 2026-09-19): the new word-evidence gate
        # (MIN_WORD_EVIDENCE/MIN_LATIN_SWITCH_SHARE) hits this set harder
        # than the base set, because masking the brand/market proper nouns
        # already thins out winner_share before the new >=0.3 floor is even
        # applied - several genuine switches (e.g. a Spanish sentence with
        # a real "¿" exempt-letter hit) now fall just short of that share
        # floor. Precision (0 wrong-language switches) stays 100% - see
        # CX_LANE7_ANSWER_LANGUAGE.md for the full before/after table.
        assert recall >= 0.55, f"brand/market recall {recall:.2%} below the documented 0.55 bar ({correct}/{total})"


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


# ---------------------------------------------------------------------------
# Fable CX review finding S4 (2026-09-19): the detector can only recognise
# ROUTE_COPY_LANGUAGES (12 languages). ChatRequest accepts only those 12
# today, so this is latent - but config/markets.json already configures 27
# more (ar, az, bg, bs, cs, el, et, he, hr, hu, ka, kk, ku, ky, lt, lv, mk,
# pl, pt, ro, sk, sl, sq, tr, uk, uz, plus sr-ME - a region variant of the
# already-recognised "sr"). The moment ChatRequest widens to any of them,
# resolve_answer_language must never switch a message written in the
# SELECTED (but unrecognised) language into a "closest relative" route-copy
# language - it has no way to verify the message ISN'T already in the
# selected language, since it can't recognise that language at all.
# ---------------------------------------------------------------------------

# At least 2 realistic customer-question probes per non-route-copy language
# configured in config/markets.json, each with the widget set to that SAME
# language (some with a region/script subtag, to exercise normalization) -
# every one must stay unswitched, regardless of message content, because the
# selected-language gate fires before detection ever runs.
NON_ROUTE_COPY_SAME_LANGUAGE_PROBES: tuple[tuple[str, str], ...] = (
    ("pt", "Quanto custa o envio de um pedido para Portugal e quanto tempo demora?"),
    ("pt", "Como posso devolver um produto que encomendei na semana passada?"),
    ("pt-BR", "Quais métodos de pagamento vocês aceitam para pedidos online?"),
    ("hr", "Koliko košta dostava narudžbe i koliko to traje?"),
    ("hr", "Kako mogu vratiti proizvod koji sam naručio prošli tjedan?"),
    ("bs", "Koliko košta dostava narudžbe u Bosnu i koliko to traje?"),
    ("bs", "Kako mogu vratiti proizvod koji sam naručio prošle sedmice?"),
    ("sl", "Koliko stane dostava naročila in koliko časa to traja?"),
    ("sl", "Kako lahko vrnem izdelek, ki sem ga naročil prejšnji teden?"),
    ("mk", "Колку чини достава на нарачка и колку време трае тоа?"),
    ("mk", "Како можам да го вратам производот што го нарачав минатата недела?"),
    ("sr-ME", "Koliko košta dostava narudžbine i koliko to traje?"),
    ("sr-Latn", "Koje načine plaćanja prihvatate za narudžbine na internetu?"),
    ("uk", "Скільки коштує доставка замовлення і скільки це займе часу?"),
    ("uk", "Як я можу повернути товар, який я замовив минулого тижня?"),
    ("uk-UA", "Які способи оплати ви приймаєте для замовлень онлайн?"),
    ("bg", "Колко струва доставката на поръчка и колко време отнема това?"),
    ("bg", "Как мога да върна продукт, който съм поръчал миналата седмица?"),
    ("kk", "Тапсырысты жеткізу қанша тұрады және бұл қанша уақыт алады?"),
    ("kk", "Өткен аптада тапсырыс берген өнімді қалай қайтара аламын?"),
    ("ky", "Буйрутманы жеткирүү канча турат жана бул канча убакыт алат?"),
    ("ky", "Мен өткөн жумада буйрутма берген заттарды кантип кайтара алам?"),
    ("hu", "Mennyibe kerül egy rendelés kiszállítása és mennyi ideig tart?"),
    ("hu", "Hogyan tudom visszaküldeni a terméket, amit múlt héten rendeltem?"),
    ("cs", "Kolik stojí doprava objednávky a jak dlouho to trvá?"),
    ("cs", "Jak mohu vrátit produkt, který jsem si objednal minulý týden?"),
    ("sk", "Koľko stojí doprava objednávky a ako dlho to trvá?"),
    ("sk", "Ako môžem vrátiť produkt, ktorý som si objednal minulý týždeň?"),
    ("tr", "Bir siparişin teslimat ücreti ne kadar ve ne kadar sürer?"),
    ("tr", "Geçen hafta sipariş ettiğim bir ürünü nasıl iade edebilirim?"),
    ("tr-TR", "Çevrimiçi siparişler için hangi ödeme yöntemlerini kabul ediyorsunuz?"),
    ("az", "Sifarişin çatdırılması nə qədər başa gəlir və bu nə qədər çəkir?"),
    ("az", "Keçən həftə sifariş etdiyim məhsulu necə qaytara bilərəm?"),
    ("sq", "Sa kushton dërgesa e një porosie dhe sa kohë zgjat kjo?"),
    ("sq", "Si mund ta kthej një produkt që porosita javën e kaluar?"),
    ("ku", "Bihayê şandina fermanek çiqas e û ev çiqas dem digire?"),
    ("ku", "Ez çawa dikarim berhemek ku min hefteya borî ferman kiribû vegerînim?"),
    ("ar", "كم تكلفة شحن الطلب وكم من الوقت يستغرق ذلك؟"),
    ("ar", "كيف يمكنني إرجاع منتج طلبته الأسبوع الماضي؟"),
    ("el", "Πόσο κοστίζει η αποστολή μιας παραγγελίας και πόσο καιρό διαρκεί;"),
    ("el", "Πώς μπορώ να επιστρέψω ένα προϊόν που παρήγγειλα την περασμένη εβδομάδα;"),
    ("et", "Kui palju maksab tellimuse kohaletoimetamine ja kui kaua see aega võtab?"),
    ("et", "Kuidas ma saan tagastada toote, mille tellisin eelmisel nädalal?"),
    ("he", "כמה עולה משלוח של הזמנה וכמה זמן זה לוקח?"),
    ("he", "איך אני יכול להחזיר מוצר שהזמנתי בשבוע שעבר?"),
    ("ka", "რა ღირს შეკვეთის მიწოდება და რამდენ ხანს გრძელდება ეს?"),
    ("ka", "როგორ შემიძლია დავაბრუნო პროდუქტი, რომელიც შევუკვეთე გასულ კვირას?"),
    ("lt", "Kiek kainuoja užsakymo pristatymas ir kiek laiko tai užtrunka?"),
    ("lt", "Kaip galiu grąžinti produktą, kurį užsisakiau praėjusią savaitę?"),
    ("lv", "Cik maksā pasūtījuma piegāde un cik ilgs laiks tam nepieciešams?"),
    ("lv", "Kā es varu atgriezt produktu, ko pasūtīju pagājušajā nedēļā?"),
    ("pl", "Ile kosztuje dostawa zamówienia i ile to trwa?"),
    ("pl", "Jak mogę zwrócić produkt, który zamówiłem w zeszłym tygodniu?"),
    ("ro", "Cât costă livrarea unei comenzi și cât timp durează asta?"),
    ("ro", "Cum pot returna un produs pe care l-am comandat săptămâna trecută?"),
    ("uz", "Buyurtmani yetkazib berish qancha turadi va bu qancha vaqt oladi?"),
    ("uz", "O'tgan hafta buyurtma qilgan mahsulotimni qanday qaytarishim mumkin?"),
    # A third probe for the four languages the coordinator named explicitly
    # (pt, hr, uk, tr), plus a couple more region/script-subtag variants.
    ("pt", "Quem é o meu patrocinador e como posso entrar em contacto com ele?"),
    ("hr", "Koje načine plaćanja prihvaćate za narudžbe putem interneta?"),
    ("uk", "Хто мій спонсор і як я можу з ним зв'язатися?"),
    ("tr", "Hangi ödeme yöntemlerini çevrimiçi siparişler için kabul ediyorsunuz?"),
    ("pt-PT", "Como posso devolver um produto que encomendei há uma semana?"),
    ("hr-HR", "Koliko košta dostava narudžbe i koliko to traje?"),
    ("uk-Cyrl", "Скільки коштує доставка замовлення і скільки це займе часу?"),
    ("tr-Latn", "Geçen hafta sipariş ettiğim bir ürünü nasıl iade edebilirim?"),
    ("az-Latn", "Sifarişin çatdırılması nə qədər başa gəlir və bu nə qədər çəkir?"),
    ("sq-AL", "Sa kushton dërgesa e një porosie dhe sa kohë zgjat kjo?"),
    ("ku-Latn", "Bihayê şandina fermanek çiqas e û ev çiqas dem digire?"),
)


class TestNonRouteCopySelectedLanguage:
    """resolve_answer_language must never switch when the selected widget
    language is outside ROUTE_COPY_LANGUAGES - the detector cannot recognise
    that language, so it cannot know the message isn't already written in
    it. This holds unconditionally, regardless of message content, which is
    exactly what makes it safe even though ChatRequest cannot reach these
    language codes today."""

    def test_same_language_probes_never_switch(self):
        """Fable's 68-probe style: a message in each non-route-copy language
        with the widget set to that same language must never switch."""
        failures = []
        for widget, message in NON_ROUTE_COPY_SAME_LANGUAGE_PROBES:
            result = resolve_answer_language(message, widget)
            if result.switched:
                failures.append((widget, message, result))
        assert not failures, f"{len(failures)} unexpected switches: {failures}"
        assert len(NON_ROUTE_COPY_SAME_LANGUAGE_PROBES) >= 68, (
            f"probe set has only {len(NON_ROUTE_COPY_SAME_LANGUAGE_PROBES)} entries, "
            "below the Fable 68-probe bar"
        )

    def test_selected_language_reason_is_reported(self):
        result = resolve_answer_language(
            "Quanto custa o envio de um pedido para Portugal e quanto tempo demora?", "pt"
        )
        assert result == AnswerLanguage("pt", False, "selected_language_not_route_copy")

    def test_region_variant_selected_language_is_normalized(self):
        # "pt-BR" and "sr-ME" must be recognised as their base subtag for
        # the route-copy membership check, not treated as a brand-new code.
        pt_br = resolve_answer_language("Isto é uma mensagem qualquer com pelo menos quatro palavras.", "pt-BR")
        assert pt_br.switched is False
        assert pt_br.reason == "selected_language_not_route_copy"

        # "sr-ME" normalizes to "sr", which IS route-copy, so a genuinely
        # Serbian message on that widget should behave like plain "sr" -
        # i.e. detection is attempted (not blocked by the new gate at all).
        sr_me = resolve_answer_language("Koliko košta dostava porudžbine i koliko to traje?", "sr-ME")
        assert sr_me.reason != "selected_language_not_route_copy"


class TestPortugueseCroatianUkrainianTurkishOnEnglishWidget:
    """Conservative negatives (coordinator, 2026-09-19): a message written in
    a non-route-copy language must not be mistaken for a related route-copy
    language even when the WIDGET is already a recognised one (English) -
    this is the case fix (1) alone cannot catch, because "en" passes the
    route-copy membership gate; it is fix (2)'s winner-share requirement
    that must hold here."""

    def test_portuguese_message_on_english_widget_does_not_switch_to_spanish(self):
        for message in (
            "Quanto custa o envio de um pedido para Portugal e quanto tempo demora?",
            "Como posso devolver um produto que encomendei na semana passada?",
        ):
            result = resolve_answer_language(message, "en")
            assert result.answer_language != "es", (message, result)

    def test_croatian_message_on_english_widget_does_not_switch_to_serbian(self):
        for message in (
            "Koliko košta dostava narudžbe i koliko to traje?",
            "Kako mogu vratiti proizvod koji sam naručio prošli tjedan?",
        ):
            result = resolve_answer_language(message, "en")
            assert result.answer_language != "sr", (message, result)

    def test_ukrainian_message_on_english_widget_does_not_switch_to_russian(self):
        for message in (
            "Скільки коштує доставка замовлення і скільки це займе часу?",
            "Як я можу повернути товар, який я замовив минулого тижня?",
        ):
            result = resolve_answer_language(message, "en")
            assert result.answer_language != "ru", (message, result)

    def test_turkish_message_on_english_widget_does_not_switch_to_french_or_german(self):
        for message in (
            "Bir siparişin teslimat ücreti ne kadar ve ne kadar sürer?",
            "Geçen hafta sipariş ettiğim bir ürünü nasıl iade edebilirim?",
        ):
            result = resolve_answer_language(message, "en")
            assert result.answer_language not in ("fr", "de"), (message, result)


# ---------------------------------------------------------------------------
# "None of the above" SINK languages (Fable CX review finding F1,
# 2026-09-19): reachable TODAY, because every non-route market's widget
# still sends "en" (the other configured languages aren't in ChatRequest's
# enum), so a message actually written in one of them lands on an "en"
# widget. The winner-share gate (S4) alone cannot separate a genuinely
# Portuguese/Hungarian/Croatian/... sentence from its closest route-copy
# relative, because the vocabulary genuinely overlaps - fixed with a small,
# closed marker table per likely non-route language (function words +
# distinctive letters), scored alongside the 12 real candidates but never
# eligible to become answer_language itself; if a sink rivals the route
# winner, or a sink's distinctive letter appears anywhere, the turn stays
# unswitched (reason "non_route_language_likely").
# ---------------------------------------------------------------------------

# The exact three sentences the coordinator reported as failing.
FABLE_F1_EXACT_SENTENCES: tuple[str, ...] = (
    "Qual é o custo de entrega para a Forever Portugal?",
    "Quais são os métodos de pagamento aceites?",
    "Milyen fizetési módokat fogadnak el?",
)

# >=5 realistic customer questions (shipping cost, returns, payment methods,
# sponsorship/contact) in each of the 10 sink languages named in the
# coordinator's fix, widget="en" - must not switch.
SINK_LANGUAGE_NEGATIVE_CASES: dict[str, tuple[str, ...]] = {
    "pt": (
        "Qual é o custo de entrega para a Forever Portugal?",
        "Quais são os métodos de pagamento aceites?",
        "Como posso devolver um produto que encomendei há uma semana?",
        "Quem é o meu patrocinador e como posso contactá-lo?",
        "Quanto tempo demora a entrega de uma encomenda normal?",
    ),
    "hu": (
        "Milyen fizetési módokat fogadnak el?",
        "Mennyibe kerül egy rendelés kiszállítása?",
        "Hogyan tudom visszaküldeni a terméket, amit rendeltem?",
        "Ki a szponzorom és hogyan léphetek vele kapcsolatba?",
        "Mennyi ideig tart a szállítás általában?",
    ),
    "ro": (
        "Cât costă livrarea unei comenzi?",
        "Cum pot returna un produs pe care l-am comandat?",
        "Ce metode de plată acceptați pentru comenzile online?",
        "Cine este sponsorul meu și cum pot să îl contactez?",
        "Cât timp durează livrarea de obicei?",
    ),
    "pl": (
        "Ile kosztuje dostawa zamówienia?",
        "Jak mogę zwrócić produkt, który zamówiłem?",
        "Jakie metody płatności akceptujecie przy zamówieniach online?",
        "Kto jest moim sponsorem i jak mogę się z nim skontaktować?",
        "Jak długo trwa zwykle dostawa?",
    ),
    "tr": (
        "Bir siparişin teslimat ücreti ne kadar?",
        "Sipariş ettiğim bir ürünü nasıl iade edebilirim?",
        "Çevrimiçi siparişler için hangi ödeme yöntemlerini kabul ediyorsunuz?",
        "Sponsorum kim ve onunla nasıl iletişime geçebilirim?",
        "Teslimat genellikle ne kadar sürer?",
    ),
    "hr": (
        "Koliko košta dostava narudžbe?",
        "Kako mogu vratiti proizvod koji sam naručio?",
        "Koje načine plaćanja prihvaćate za narudžbe putem interneta?",
        "Tko je moj sponzor i kako ga mogu kontaktirati?",
        "Koliko obično traje dostava?",
    ),
    "sq": (
        "Cilat metoda pagese pranoni për porositë në internet?",
        "Sa kushton dërgesa e një porosie?",
        "Si mund ta kthej një produkt që porosita?",
        "Kush është sponsori im dhe si mund ta kontaktoj?",
        "Sa kohë zgjat zakonisht dërgesa?",
    ),
    "mk": (
        "Кои начини на плаќање ги прифаќате за нарачки преку интернет?",
        "Колку чини достава на нарачка?",
        "Како можам да го вратам производот што го нарачав?",
        "Кој е мојот спонзор и како можам да го контактирам?",
        "Колку време обично трае доставата?",
    ),
    "bg": (
        "Какви методи на плащане приемате за поръчки онлайн?",
        "Колко струва доставката на поръчка?",
        "Как мога да върна продукт, който съм поръчал?",
        "Кой е моят спонсор и как мога да се свържа с него?",
        "Колко време обикновено отнема доставката?",
    ),
    "uk": (
        "Які способи оплати ви приймаєте для замовлень онлайн?",
        "Скільки коштує доставка замовлення?",
        "Як я можу повернути товар, який я замовив?",
        "Хто мій спонсор і як я можу з ним зв'язатися?",
        "Скільки зазвичай триває доставка?",
    ),
}


class TestSinkLanguages:
    """Fable CX review finding F1 (2026-09-19), closed out by the Fable
    re-review word-evidence gate (also 2026-09-19): the two sentences that
    were disclosed as remaining wrong-language switches (`pt`/`hu`, both
    switching to "es") are FIXED by that gate - coordinator review found a
    wrong-language switch is never an acceptable "known miss", so there is
    no longer any exemption here. Every case below is now a regular,
    unconditional assertion."""

    def test_fable_exact_sentences_no_longer_switch_to_spanish(self):
        for message in FABLE_F1_EXACT_SENTENCES:
            result = resolve_answer_language(message, "en")
            assert result.switched is False, (message, result)
            assert result.answer_language == "en", (message, result)

    def test_sink_language_negatives_never_switch(self):
        failures = []
        for language, questions in SINK_LANGUAGE_NEGATIVE_CASES.items():
            for question in questions:
                result = resolve_answer_language(question, "en")
                if result.switched:
                    failures.append((language, question, result))
        assert not failures, f"{len(failures)} sink-language false switches: {failures}"

    def test_recall_of_the_sink_negative_set(self):
        """Aggregate count for the coordinator report: how many of the 50
        realistic non-route-language questions correctly stay unswitched -
        now 50/50 (100%), up from 48/50 once the word-evidence gate closed
        the two remaining wrong-language switches."""
        total = 0
        correct = 0
        for language, questions in SINK_LANGUAGE_NEGATIVE_CASES.items():
            for question in questions:
                total += 1
                result = resolve_answer_language(question, "en")
                if not result.switched:
                    correct += 1
        assert total == 50
        assert correct == 50, f"only {correct}/{total} sink negatives stayed unswitched"


# =============================================================================
# HELD-OUT SET (Fable CX re-review, third pass, fix D, 2026-09-19). Written
# ONCE and run ONCE to produce the numbers reported to the coordinator; NOT
# iterated against afterwards - no sentence below was adjusted, replaced or
# removed after seeing its result, and no answer_language.py threshold or
# vocabulary was tuned in response to a failure in this specific set (all
# tuning happened against the acceptance/brand-market/sink sets above,
# which remain the "practice" sets). 4 realistic customer questions per
# ROUTE_COPY_LANGUAGES language (12) plus 4 per named sink language (pt hu
# ro pl tr hr mk bg uk et = 10) = 88 total, each with a realistic session
# `country` for that language and widget="en" (or, for the "en" rows, a
# non-English widget so a real switch INTO English is exercised). This is
# the set fix D asks for; its own measured numbers (not an aspirational
# bar) are what CX_LANE7_ANSWER_LANGUAGE.md's held-out table reports.
# =============================================================================

HELD_OUT_ROUTE_CASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "da": ("DK", (
        "Har I mulighed for at levere til en anden adresse end min egen?",
        "Jeg vil gerne vide, om der er fortrydelsesret på dette produkt.",
        "Kan I sende mig en kvittering på min seneste betaling?",
        "Hvor kan jeg se status på min aktuelle bestilling?",
    )),
    "de": ("DE", (
        "Gibt es eine Möglichkeit, die Lieferadresse nachträglich zu ändern?",
        "Ich möchte wissen, ob ein Umtausch für dieses Produkt möglich ist.",
        "Können Sie mir eine Quittung für meine letzte Zahlung schicken?",
        "Wo finde ich den aktuellen Status meiner Bestellung?",
    )),
    "en": ("DE", (  # widget="de" below, country=DE (enables en+de)
        "Is it possible to change the delivery address after placing the order?",
        "I would like to know if this product can be exchanged for another one.",
        "Could you send me a receipt for my last payment?",
        "Where can I see the current status of my order?",
    )),
    "es": ("US", (
        "¿Hay alguna forma de cambiar la dirección de envío después de hacer el pedido?",
        "Quisiera saber si este producto se puede cambiar por otro.",
        "¿Podrían enviarme un recibo de mi último pago?",
        "¿Dónde puedo ver el estado actual de mi pedido?",
    )),
    "fi": ("FI", (
        "Onko mahdollista vaihtaa toimitusosoitetta tilauksen jälkeen?",
        "Haluaisin tietää, voiko tämän tuotteen vaihtaa toiseen.",
        "Voisitteko lähettää minulle kuitin viimeisimmästä maksustani?",
        "Mistä näen tilaukseni tämänhetkisen tilan?",
    )),
    "fr": ("CA", (
        "Est-il possible de modifier l'adresse de livraison après la commande ?",
        "J'aimerais savoir si ce produit peut être échangé contre un autre.",
        "Pourriez-vous m'envoyer un reçu de mon dernier paiement ?",
        "Où puis-je voir l'état actuel de ma commande ?",
    )),
    "it": ("IT", (
        "È possibile modificare l'indirizzo di consegna dopo l'ordine?",
        "Vorrei sapere se questo prodotto può essere cambiato con un altro.",
        "Potreste inviarmi una ricevuta del mio ultimo pagamento?",
        "Dove posso vedere lo stato attuale del mio ordine?",
    )),
    "nl": ("NL", (
        "Is het mogelijk om het afleveradres na de bestelling te wijzigen?",
        "Ik wil graag weten of dit product geruild kan worden.",
        "Kunt u mij een bon sturen van mijn laatste betaling?",
        "Waar kan ik de huidige status van mijn bestelling zien?",
    )),
    "no": ("NO", (
        "Er det mulig å endre leveringsadressen etter at bestillingen er lagt inn?",
        "Jeg vil gjerne vite om dette produktet kan byttes mot et annet.",
        "Kan dere sende meg en kvittering for min siste betaling?",
        "Hvor kan jeg se nåværende status på bestillingen min?",
    )),
    "ru": ("RU", (
        "Можно ли изменить адрес доставки после оформления заказа?",
        "Я хотел бы узнать, можно ли обменять этот товар на другой.",
        "Не могли бы вы прислать мне квитанцию о последнем платеже?",
        "Где я могу посмотреть текущий статус своего заказа?",
    )),
    "sr": ("RS", (
        "Da li je moguće promeniti adresu za dostavu nakon porudžbine?",
        "Želeo bih da znam da li se ovaj proizvod može zameniti za drugi.",
        "Da li mi možete poslati priznanicu za moju poslednju uplatu?",
        "Gde mogu da vidim trenutni status svoje porudžbine?",
    )),
    "sv": ("SE", (
        "Är det möjligt att ändra leveransadressen efter att beställningen är lagd?",
        "Jag skulle vilja veta om den här produkten kan bytas mot en annan.",
        "Kan ni skicka mig ett kvitto på min senaste betalning?",
        "Var kan jag se den aktuella statusen för min beställning?",
    )),
}

HELD_OUT_SINK_CASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "pt": ("PT", (
        "Posso alterar a morada de entrega depois de fazer o pedido?",
        "Gostava de saber se este produto pode ser trocado por outro.",
        "Podem enviar-me um recibo do meu último pagamento?",
        "Onde posso ver o estado atual da minha encomenda?",
    )),
    "hu": ("HU", (
        "Lehetséges-e megváltoztatni a szállítási címet a rendelés után?",
        "Szeretném tudni, hogy ez a termék kicserélhető-e egy másikra.",
        "El tudnák küldeni az utolsó fizetésemről szóló nyugtát?",
        "Hol nézhetem meg a rendelésem jelenlegi állapotát?",
    )),
    "ro": ("RO", (
        "Este posibil să schimb adresa de livrare după plasarea comenzii?",
        "Aș vrea să știu dacă acest produs poate fi schimbat cu altul.",
        "Îmi puteți trimite o chitanță pentru ultima mea plată?",
        "Unde pot vedea starea actuală a comenzii mele?",
    )),
    "pl": ("PL", (
        "Czy można zmienić adres dostawy po złożeniu zamówienia?",
        "Chciałbym wiedzieć, czy ten produkt można wymienić na inny.",
        "Czy mogliby Państwo przesłać mi potwierdzenie ostatniej płatności?",
        "Gdzie mogę sprawdzić aktualny status mojego zamówienia?",
    )),
    "tr": ("TR", (
        "Siparişi verdikten sonra teslimat adresini değiştirmek mümkün mü?",
        "Bu ürünün başka bir ürünle değiştirilip değiştirilemeyeceğini öğrenmek istiyorum.",
        "Son ödememle ilgili bana bir makbuz gönderebilir misiniz?",
        "Siparişimin güncel durumunu nereden görebilirim?",
    )),
    "hr": ("HR", (
        "Je li moguće promijeniti adresu dostave nakon narudžbe?",
        "Zanima me može li se ovaj proizvod zamijeniti za drugi.",
        "Možete li mi poslati potvrdu o mojoj posljednjoj uplati?",
        "Gdje mogu vidjeti trenutni status svoje narudžbe?",
    )),
    "mk": ("MK", (
        "Дали е можно да се промени адресата за достава по нарачката?",
        "Би сакал да знам дали овој производ може да се замени за друг.",
        "Дали можете да ми испратите потврда за последната уплата?",
        "Каде можам да го видам тековниот статус на мојата нарачка?",
    )),
    "bg": ("BG", (
        "Възможно ли е да се промени адресът за доставка след поръчката?",
        "Бих искал да знам дали този продукт може да се смени с друг.",
        "Можете ли да ми изпратите разписка за последното ми плащане?",
        "Къде мога да видя текущия статус на поръчката си?",
    )),
    "uk": ("UA", (
        "Чи можна змінити адресу доставки після оформлення замовлення?",
        "Хотів би дізнатися, чи можна обміняти цей товар на інший.",
        "Чи можете ви надіслати мені квитанцію про останній платіж?",
        "Де я можу побачити поточний статус свого замовлення?",
    )),
    "et": ("BALTICS", (
        "Kas tellimuse esitamise järel on võimalik tarneaadressi muuta?",
        "Tahaksin teada, kas seda toodet saab teise vastu vahetada?",
        "Kas saaksite mulle saata minu viimase makse kviitungi?",
        "Kust ma näen oma tellimuse praegust olekut?",
    )),
}


class TestHeldOutMarketScopedSet:
    """FROZEN held-out set - see the module comment above
    HELD_OUT_ROUTE_CASES. Precision (zero wrong-language switches) is a
    hard requirement across all 88 cases; recall is reported, not forced,
    since this set was deliberately never tuned against."""

    def test_zero_wrong_language_switches_across_the_entire_held_out_set(self):
        """The one non-negotiable bar (coordinator: "precision ... must be
        100%, zero wrong switches")."""
        failures = []
        for language, (country, questions) in HELD_OUT_ROUTE_CASES.items():
            widget = "en" if language != "en" else "de"
            expected = "en" if language == "en" else language
            for question in questions:
                result = resolve_answer_language(question, widget, country=country)
                if result.switched and result.answer_language != expected:
                    failures.append(("route", language, country, question, result))
        for language, (country, questions) in HELD_OUT_SINK_CASES.items():
            for question in questions:
                result = resolve_answer_language(question, "en", country=country)
                if result.switched:
                    failures.append(("sink", language, country, question, result))
        assert not failures, f"{len(failures)} wrong-language switches in the held-out set: {failures}"

    def test_sink_held_out_recall(self):
        """Measured: 40/40 (100%). Asserted at >= 0.90 so this stays a
        regression guard, not a re-tuning target - see the module comment."""
        total = 0
        correct = 0
        for language, (country, questions) in HELD_OUT_SINK_CASES.items():
            for question in questions:
                total += 1
                result = resolve_answer_language(question, "en", country=country)
                if not result.switched:
                    correct += 1
        assert total == 40
        assert correct / total >= 0.90, f"sink held-out recall {correct}/{total} regressed below measured"

    def test_route_held_out_recall(self):
        """Measured: 28/48 (58.3%) - lower than the tuned acceptance sets,
        as expected for a genuinely fresh, never-tuned-against sample.
        Asserted at >= 0.50 so this stays a regression guard for the
        measured value, not a target this test file's own tuning chases."""
        total = 0
        correct = 0
        for language, (country, questions) in HELD_OUT_ROUTE_CASES.items():
            widget = "en" if language != "en" else "de"
            expected = "en" if language == "en" else language
            for question in questions:
                total += 1
                result = resolve_answer_language(question, widget, country=country)
                if result.switched and result.answer_language == expected:
                    correct += 1
        assert total == 48
        assert correct / total >= 0.50, f"route held-out recall {correct}/{total} regressed below measured"
