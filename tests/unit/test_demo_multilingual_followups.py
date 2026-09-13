"""Demo W14: short follow-ups resolve in every conversation language, not only English.

Offline probe 2026-09-12 (all-markets probe, section 1d): after "What is the
delivery cost in Kenya?" phrased in each language, "En voor Uganda?", "Et pour
Uganda?", "Und für Uganda?", "Y para Uganda?", "E para Uganda?", "E per Uganda?",
"Och för Uganda?", "Og for Uganda?", "А для Уганды?" and "A za Ugandu?" never
entered the history path. Retrieval received the bare follow-up and the delivery
topic was lost. English "And for Uganda?" already worked.

The rule is the English one: a short follow-up from THIS session's user turns
carries the anchor topic; a new market replaces the old one; a topic ellipsis
keeps the old market; a full question starting with the same words stays
standalone; assistant text is never an anchor.

Every test here is offline: AWS clients, embeddings, the OpenSearch client and
session/cache writes are stubbed to raise.
"""

from __future__ import annotations

import pytest

from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers


def _no_live_calls(*_: object, **__: object):
    raise AssertionError("W14 tests must never make an AWS, embedding, OpenSearch or model call")


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "embed_text", _no_live_calls)
    monkeypatch.setattr(opensearch_sections, "_client", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "append_session_turn", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "set_cache_value", _no_live_calls)
    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", _no_live_calls)


def _history(*turns: str) -> str:
    lines = []
    for turn in turns:
        lines.extend([f"user: {turn}", "vera: An earlier answer."])
    return "\n".join(lines)


def _resolve(message: str, history: str) -> tuple[str, str]:
    orchestrator = AIOrchestrator()
    retrieval_query = orchestrator._build_retrieval_query(message, history, "cid")
    return retrieval_query, orchestrator._build_request_query(message, retrieval_query, history)


def _targets(query: str) -> set[str]:
    return opensearch_sections._directory_target_country_names(query, "US")


# language -> (anchor, anchor target, topic words, old market spelling, new target, market switches, topic ellipses)
# Russian, Serbian and Finnish decline market names and the alias list holds the base
# form only, so their market cases use names that keep that form (Перу, Чили, Čile, Мароко).
LANGUAGES = {
    "nl": (
        "Wat zijn de verzendkosten naar Kenia?", "Kenya", "verzendkosten", "Kenia", "Uganda",
        ("En voor Oeganda?", "En in Oeganda?", "Wat dan met Oeganda?", "Hoe zit het met Oeganda?"),
        ("En de minimale bestelling?", "Hoe zit het met de minimale bestelling?"),
    ),
    "fr": (
        "Quel est le coût de livraison au Kenya ?", "Kenya", "coût de livraison", "Kenya", "Uganda",
        ("Et pour l'Ouganda ?", "Et en Ouganda ?", "Qu'en est-il de l'Ouganda ?"),
        ("Et la commande minimale ?", "Qu'en est-il de la commande minimale ?"),
    ),
    "de": (
        "Wie hoch sind die Lieferkosten nach Kenia?", "Kenya", "Lieferkosten", "Kenia", "Uganda",
        ("Und für Uganda?", "Und fur Uganda?", "Und in Uganda?", "Und was ist mit Uganda?", "Wie sieht es mit Uganda aus?"),
        ("Und die Mindestbestellung?", "Und was ist mit der Mindestbestellung?"),
    ),
    "es": (
        "¿Cuál es el costo de envío en Kenia?", "Kenya", "costo de envío", "Kenia", "Uganda",
        ("¿Y para Uganda?", "¿Y en Uganda?", "¿Y qué hay de Uganda?", "Y que hay de Uganda?", "¿Y qué pasa con Uganda?"),
        ("¿Y el pedido mínimo?", "¿Y qué pasa con el pedido mínimo?"),
    ),
    "pt": (
        "Qual é o custo de entrega no Quênia?", "Kenya", "custo de entrega", "Quênia", "Uganda",
        ("E para Uganda?", "E em Uganda?", "E quanto à Uganda?"),
        ("E o pedido mínimo?", "E quanto ao pedido mínimo?"),
    ),
    "it": (
        "Qual è il costo di consegna in Kenya?", "Kenya", "costo di consegna", "Kenya", "Uganda",
        ("E per l'Uganda?", "E in Uganda?", "E riguardo all'Uganda?"),
        ("E l'ordine minimo?", "E il minimo d'ordine?"),
    ),
    "sv": (
        "Vad är leveranskostnaden till Kenya?", "Kenya", "leveranskostnaden", "Kenya", "Uganda",
        ("Och för Uganda?", "Och i Uganda?", "Hur är det med Uganda?"),
        ("Och minsta beställningen?", "Hur är det med minsta beställningen?"),
    ),
    "da": (
        "Hvad koster levering til Kenya?", "Kenya", "koster levering", "Kenya", "Uganda",
        ("Og for Uganda?", "Og i Uganda?", "Hvad med Uganda?"),
        ("Hvad med minimumsbestillingen?",),
    ),
    "no": (
        "Hva koster levering til Kenya?", "Kenya", "koster levering", "Kenya", "Uganda",
        ("Og for Uganda?", "Og i Uganda?", "Hva med Uganda?"),
        ("Hva med minstebestillingen?",),
    ),
    "fi": (
        "Mikä on toimitusmaksu Kenia-markkinoilla?", "Kenya", "toimitusmaksu", "Kenia", "Uganda",
        ("Entä Uganda?", "Entäs Uganda?"),
        ("Entä vähimmäistilaus?",),
    ),
    "ru": (
        "Какова стоимость доставки в Перу?", "Peru", "стоимость доставки", "Перу", "Chile",
        ("А для Чили?", "А в Чили?", "И для Чили?", "А что насчёт Чили?", "А что насчет Чили?"),
        ("А что насчёт минимального заказа?",),
    ),
    "ru-latn": (
        "Kakova stoimost dostavki v Kenya?", "Kenya", "stoimost dostavki", "Kenya", "Uganda",
        ("A dlya Uganda?", "A v Uganda?", "A chto naschet Uganda?"),
        ("A chto naschet minimalnogo zakaza?",),
    ),
    "sr": (
        "Kolika je cena dostave za Peru?", "Peru", "cena dostave", "Peru", "Chile",
        ("A za Čile?", "A za Cile?", "I za Čile?"),
        ("A šta je sa minimalnom porudžbinom?", "A sta je sa minimalnom porudzbinom?"),
    ),
    "sr-cyrl": (
        "Колика је цена доставе за Перу?", "Peru", "цена доставе", "Перу", "Morocco",
        ("А за Мароко?", "И за Мароко?", "А шта је са Мароко?"),
        ("А шта је са минималном поруџбином?",),
    ),
}

MARKET_SWITCHES = [
    pytest.param(language, follow_up, id=f"{language}:{follow_up}")
    for language, case in LANGUAGES.items()
    for follow_up in case[5]
]
TOPIC_ELLIPSES = [
    pytest.param(language, follow_up, id=f"{language}:{follow_up}")
    for language, case in LANGUAGES.items()
    for follow_up in case[6]
]


# --- Fail-before: a market switch carries the anchor topic to the new market only ----


@pytest.mark.parametrize("language,follow_up", MARKET_SWITCHES)
def test_market_switch_carries_the_topic_to_the_new_market(language, follow_up) -> None:
    anchor, _, topic, old_market, new_target, _, _ = LANGUAGES[language]
    retrieval, request = _resolve(follow_up, _history(anchor))
    assert retrieval != follow_up, "the follow-up never entered the history path"
    assert topic in retrieval
    assert follow_up in retrieval and request.startswith(retrieval)
    assert old_market not in retrieval.replace(follow_up, "")
    assert _targets(retrieval) == {new_target}


@pytest.mark.parametrize("language,follow_up", TOPIC_ELLIPSES)
def test_topic_ellipsis_keeps_the_anchor_market(language, follow_up) -> None:
    anchor, anchor_target, topic, _, _, _, _ = LANGUAGES[language]
    retrieval, request = _resolve(follow_up, _history(anchor))
    assert retrieval.startswith(anchor)
    assert retrieval.endswith(follow_up)
    assert topic in retrieval and request.startswith(retrieval)
    assert _targets(retrieval) == {anchor_target}


def test_chain_market_switch_then_topic_ellipsis_stays_on_the_new_market() -> None:
    anchor = LANGUAGES["nl"][0]
    retrieval, _ = _resolve("En de minimale bestelling?", _history(anchor, "En voor Oeganda?"))
    assert _targets(retrieval) == {"Uganda"}
    assert "verzendkosten" in retrieval and "Kenia" not in retrieval


@pytest.mark.parametrize(
    "message,shape",
    [
        ("Und fur Uganda?", "market"),
        ("UND FÜR UGANDA?", "market"),
        ("¿Y para Uganda?", "market"),
        ("А что насчет Чили?", "topic_shift"),
        ("Qu’en est-il de l’Ouganda ?", "topic_shift"),
        ("Et la commande minimale ?", "topic"),
        ("And for Uganda?", ""),
        ("What about Uganda?", ""),
    ],
)
def test_localized_shape_is_accent_and_case_insensitive_and_leaves_english_to_english(message, shape) -> None:
    assert AIOrchestrator()._localized_follow_up_shape(message) == shape


# --- Controls: full questions with the same opening words stay standalone --------------

FULL_QUESTIONS = {
    "nl": ("En voor wie is dit product bedoeld?", "Hoe zit het met de verzending als mijn pakket niet aankomt?"),
    "fr": ("Et pour quoi faire ?", "Et pour qui est ce produit ?", "Qu'en est-il de mon remboursement si le colis arrive cassé ?"),
    "de": ("Und für wen gilt das?", "Und für wen gilt das in Uganda?", "Und was ist mit meiner Bestellung passiert?"),
    "es": ("¿Y para qué sirve este producto?", "¿Y qué tal estás?", "¿Y en qué país vive mi patrocinador?", "¿Y qué pasa contigo?"),
    "pt": ("E para que serve este produto?", "E sobre o que é o plano de marketing?"),
    "it": ("E per quanto tempo vale la garanzia?", "E che dire di come funziona il piano di marketing?"),
    "sv": ("Och för vem gäller detta?", "Hur är det med dig?", "Och hur mycket kostar det?"),
    "da": ("Og for hvem gælder det?", "Hvad med dig?", "Og hvornår kommer pakken?"),
    "no": ("Og for hvem gjelder det?", "Hva med deg?", "Og i hvilket land bor sponsoren min?"),
    # "Entä Ugandassa?" names Uganda in a case form the alias list lacks: merging it
    # would keep Kenya as the only recognised market, so it stays standalone.
    "fi": ("Entä sitten?", "Entä jos haluan palauttaa tuotteen ja saada rahani takaisin?", "Entä Ugandassa?"),
    "ru": ("А для чего нужен этот продукт?", "А как насчёт тебя?", "А что насчёт Уганды?"),
    "sr": ("A za šta služi ovaj proizvod?", "A šta je sa tobom?", "A šta je sa Kenijom?"),
    "sr-cyrl": ("А за шта служи овај производ?", "А шта је са тобом?"),
}


@pytest.mark.parametrize(
    "language,question",
    [
        pytest.param(language, question, id=f"{language}:{question}")
        for language, questions in FULL_QUESTIONS.items()
        for question in questions
    ],
)
def test_full_question_with_a_follow_up_opening_is_not_a_follow_up(language, question) -> None:
    anchor = LANGUAGES[language][0]
    assert _resolve(question, _history(anchor)) == (question, question)


@pytest.mark.parametrize("language,follow_up", MARKET_SWITCHES + TOPIC_ELLIPSES)
def test_follow_up_without_a_prior_user_turn_stays_standalone(language, follow_up) -> None:
    assert _resolve(follow_up, "") == (follow_up, follow_up)
    # Assistant prose alone is never an anchor, even when it names a market and topic.
    assistant_only = "vera: Delivery to Kenya costs 10 EUR and the minimum order is 50 EUR."
    retrieval, request = _resolve(follow_up, assistant_only)
    assert retrieval == follow_up and request == follow_up
    assert "Kenya" not in retrieval


# --- W14b, Fable W14 note 1: "And the X?" merges only for a directory field ------------
# English "And the email?" merges and "And the warranty?" does not, so the localized
# topic ellipsis needs a directory field too. Otherwise "En de garantie?" was sent to
# retrieval as the delivery-cost anchor plus a warranty question.

NON_FIELD_TOPIC_ELLIPSES = {
    "nl": ("En de garantie?", "En het marketingplan?", "En de prijs?", "En het leveringsbeleid?"),
    "fr": ("Et la garantie ?", "Et pour les nouveaux clients ?", "Et le prix ?", "Et la politique de livraison ?"),
    "de": ("Und die Preise?", "Und die Garantie?", "Und der Lieferant?"),
    "es": ("Y la empresa?", "¿Y el plan de marketing?", "¿Y los precios?"),
    "pt": ("E o plano de marketing?", "E a empresa?", "E os preços?"),
    "it": ("E la garanzia?", "E i prezzi?", "E l'azienda?"),
    "sv": ("Och priset?", "Och garantin?", "Och marknadsplanen?"),
}
# A capitalised name after a place preposition that is no recognised market: the
# message cannot move the target, so merging it would silently answer for Kenya.
UNRECOGNISED_PLACE_ELLIPSES = {
    "nl": ("En de verzendkosten in Amsterdam?",),
    "fr": ("Et les frais de livraison à Paris ?",),
    "de": ("Und die Lieferkosten in Berlin?",),
    "es": ("¿Y el envío en Madrid?",),
    "pt": ("E a Roma?", "E o frete em Lisboa?"),
    "it": ("E la consegna a Milano?",),
    "sv": ("Och i Stockholm?", "Och e-post i Stockholm?"),
}
# Directory-field ellipses in each topic-ellipsis language keep merging.
FIELD_TOPIC_ELLIPSES = {
    "nl": ("En de verzendkosten?", "En het e-mailadres?", "En de openingstijden?"),
    "fr": ("Et les frais de livraison ?", "Et l'adresse ?", "Et le téléphone ?"),
    "de": ("Und die Lieferkosten?", "Und die E-Mail-Adresse?", "Und die Öffnungszeiten?"),
    "es": ("¿Y el envío?", "¿Y la dirección?", "Y el teléfono?"),
    "pt": ("E o frete?", "E o endereço?", "E o pagamento?"),
    "it": ("E la consegna?", "E l'indirizzo?", "E il pagamento?"),
    "sv": ("Och betalningen?", "Och öppettiderna?", "Och leveranskostnaden?"),
}


def _by_language(cases: dict[str, tuple[str, ...]]) -> list:
    return [
        pytest.param(language, message, id=f"{language}:{message}")
        for language, messages in cases.items()
        for message in messages
    ]


@pytest.mark.parametrize("language,question", _by_language(NON_FIELD_TOPIC_ELLIPSES))
def test_topic_ellipsis_that_names_no_directory_field_stays_standalone(language, question) -> None:
    assert AIOrchestrator()._localized_follow_up_shape(question) == ""
    assert _resolve(question, _history(LANGUAGES[language][0])) == (question, question)


@pytest.mark.parametrize("language,question", _by_language(UNRECOGNISED_PLACE_ELLIPSES))
def test_topic_ellipsis_naming_an_unrecognised_place_stays_standalone(language, question) -> None:
    assert AIOrchestrator()._localized_follow_up_shape(question) == ""
    assert _resolve(question, _history(LANGUAGES[language][0])) == (question, question)


@pytest.mark.parametrize("language,follow_up", _by_language(FIELD_TOPIC_ELLIPSES))
def test_directory_field_topic_ellipsis_keeps_the_anchor_market(language, follow_up) -> None:
    anchor, anchor_target = LANGUAGES[language][:2]
    assert AIOrchestrator()._localized_follow_up_shape(follow_up) == "topic"
    retrieval, request = _resolve(follow_up, _history(anchor))
    assert retrieval.startswith(anchor) and retrieval.endswith(follow_up)
    assert request.startswith(retrieval)
    assert _targets(retrieval) == {anchor_target}


def test_english_topic_ellipsis_is_still_decided_by_the_english_rule() -> None:
    orchestrator = AIOrchestrator()
    for message in ("And the email?", "And the warranty?", "And in Stockholm?"):
        assert orchestrator._localized_follow_up_shape(message) == ""
    anchor = "What is the delivery cost in Kenya?"
    assert _resolve("And the warranty?", _history(anchor))[0] == "And the warranty?"
    assert _resolve("And in Stockholm?", _history(anchor))[0] == "And in Stockholm?"
    assert _resolve("And the email?", _history(anchor))[0] != "And the email?"


# --- W14b, Fable W14 note 3: the first content word decides, not the first word --------


@pytest.mark.parametrize(
    "follow_up,target",
    [
        ("E para os Emirados Árabes Unidos?", "United Arab Emirates"),
        ("E para os Estados Unidos?", "United States"),
    ],
)
def test_portuguese_article_os_is_not_the_danish_pronoun(follow_up, target) -> None:
    assert AIOrchestrator()._localized_follow_up_shape(follow_up) == "market"
    retrieval, _ = _resolve(follow_up, _history(LANGUAGES["pt"][0]))
    assert "custo de entrega" in retrieval and "Quênia" not in retrieval.replace(follow_up, "")
    assert _targets(retrieval) == {target}


@pytest.mark.parametrize(
    "language,question",
    [("da", "Og for os?"), ("nl", "En voor wie?"), ("de", "Und für wen?"), ("pt", "E para os clientes?")],
)
def test_pronoun_or_question_word_after_the_connector_still_stays_standalone(language, question) -> None:
    assert AIOrchestrator()._localized_follow_up_shape(question) == ""
    assert _resolve(question, _history(LANGUAGES[language][0])) == (question, question)


# --- W14b, Fable W14 note 2: governance after a refused anchor --------------------------
# Refused turns stay in history. A localized topic follow-up is judged on its own words,
# exactly like "What about the shipping?"; the market ellipsis keeps the anchor exactly
# like "And for Uganda?"; and the current message is always judged.

INCOME_ANCHOR = "Can you guarantee I will earn 5000 dollars a month in Kenya?"
CURE_ANCHOR = "Does aloe vera cure cancer in Kenya?"
SAFE_ANCHOR = "What is the delivery cost in Kenya?"


def _judged(message: str, anchor: str) -> tuple[str, str, bool]:
    from app.governance import governance_engine

    retrieval, request = _resolve(message, _history(anchor))
    text = AIOrchestrator()._governance_text(message, request)
    allowed = governance_engine.evaluate(text=text, country="US", language="en", correlation_id="cid").allowed
    return retrieval, text, allowed


def test_the_refused_anchors_are_refused_on_their_own() -> None:
    from app.governance import governance_engine

    for anchor in (INCOME_ANCHOR, CURE_ANCHOR):
        assert not governance_engine.evaluate(text=anchor, country="US", language="en", correlation_id="cid").allowed


@pytest.mark.parametrize(
    "anchor,follow_up",
    [
        (INCOME_ANCHOR, "Hoe zit het met de verzendkosten?"),
        (INCOME_ANCHOR, "En de verzendkosten?"),
        (CURE_ANCHOR, "Und die Lieferkosten?"),
        (CURE_ANCHOR, "Und was ist mit Uganda?"),
        (INCOME_ANCHOR, "What about the shipping?"),
    ],
)
def test_localized_topic_follow_up_after_a_refused_anchor_is_judged_on_its_own_words(anchor, follow_up) -> None:
    retrieval, text, allowed = _judged(follow_up, anchor)
    assert retrieval != follow_up, "the follow-up must still resolve against the anchor for retrieval"
    assert text == follow_up
    assert allowed


@pytest.mark.parametrize("follow_up", ["En voor Uganda?", "And for Uganda?", "Und für Uganda?"])
@pytest.mark.parametrize("anchor", [INCOME_ANCHOR, CURE_ANCHOR])
def test_market_ellipsis_after_a_refused_anchor_keeps_the_anchor_like_english(anchor, follow_up) -> None:
    retrieval, text, allowed = _judged(follow_up, anchor)
    assert retrieval != follow_up and text != follow_up
    assert not allowed


@pytest.mark.parametrize("anchor", [SAFE_ANCHOR, INCOME_ANCHOR, CURE_ANCHOR])
@pytest.mark.parametrize(
    "follow_up",
    ["Hoe zit het met guaranteed income?", "Und was ist mit guaranteed income?", "Hoe zit het met cures cancer?"],
)
def test_refused_current_message_is_still_refused_after_any_anchor(anchor, follow_up) -> None:
    _, text, allowed = _judged(follow_up, anchor)
    assert follow_up in text
    assert not allowed


@pytest.mark.parametrize(
    "follow_up",
    ["Und was ist mit garantiertem Einkommen?", "En wat met gegarandeerd inkomen?", "A šta je sa zagarantovanom zaradom?"],
)
def test_localized_guarantee_word_keeps_the_refused_anchor(follow_up) -> None:
    _, text, allowed = _judged(follow_up, INCOME_ANCHOR)
    assert text != follow_up and INCOME_ANCHOR.split(" in ")[0] in text
    assert not allowed


# --- W14c, Fable follow-up B1: "lov" also stems Danish/Norwegian "loven" (the law) -------
# "lov" alone matches "loven"/"lovgivningen" ("the law"/"the legislation"), which is not a
# promise word, so a question about the law after the income anchor was wrongly forced to
# keep the refused anchor. The stem is now inflection-specific ("lova", "lovede", ...) plus
# "løft" (promise/pledge), so "the law" is judged on its own words like "What about the law?".


@pytest.mark.parametrize(
    "follow_up",
    ["Hvad med loven?", "Hva med loven?", "Hvad med lovgivningen?", "Hva med lovgivningen?"],
)
def test_localized_law_word_does_not_keep_the_refused_anchor(follow_up) -> None:
    _, text, allowed = _judged(follow_up, INCOME_ANCHOR)
    assert text == follow_up
    assert allowed


@pytest.mark.parametrize(
    "follow_up",
    ["Hvad med lovede fordele?", "Hvad med løftet?", "Hva med lovet inntekt?"],
)
def test_localized_promise_word_still_keeps_the_refused_anchor(follow_up) -> None:
    _, text, allowed = _judged(follow_up, INCOME_ANCHOR)
    assert text != follow_up and INCOME_ANCHOR.split(" in ")[0] in text
    assert not allowed


# --- W14c, Fable follow-up B2: advertising/testimonial words also keep the anchor --------
# "Hoe zit het met reclame?", "Und was ist mit Werbung?" and their Spanish and French
# equivalents were merged then judged alone, unlike English "What about advertising?"
# (blocked by CONTENT_REQUEST_TERMS). The pattern now also matches these content nouns.


@pytest.mark.parametrize(
    "follow_up",
    [
        "Hoe zit het met reclame?",
        "Und was ist mit Werbung?",
        "Und was ist mit Werbetexten?",
        "¿Y qué hay de la publicidad?",
        "Et concernant les témoignages ?",
    ],
)
def test_localized_advertising_word_keeps_the_refused_anchor(follow_up) -> None:
    _, text, allowed = _judged(follow_up, INCOME_ANCHOR)
    assert text != follow_up and INCOME_ANCHOR.split(" in ")[0] in text
    assert not allowed


@pytest.mark.parametrize(
    "anchor,follow_up",
    [
        (CURE_ANCHOR, "Und was ist mit Uganda?"),
        (CURE_ANCHOR, "Und die Lieferkosten?"),
        (INCOME_ANCHOR, "Hoe zit het met de verzendkosten?"),
    ],
)
def test_advertising_stems_do_not_disturb_other_localized_shapes_after_a_refused_anchor(anchor, follow_up) -> None:
    retrieval, text, allowed = _judged(follow_up, anchor)
    assert retrieval != follow_up
    assert text == follow_up
    assert allowed


def test_advertising_word_after_a_harmless_anchor_behaves_as_before() -> None:
    # The anchor is not refused, so merging the advertising follow-up must not flip the
    # governance outcome: it stays allowed exactly as it did before the B2 stems were added.
    retrieval, text, allowed = _judged("Und was ist mit Werbung?", SAFE_ANCHOR)
    assert retrieval != "Und was ist mit Werbung?"
    assert allowed


# --- W14c, Fable follow-up (d): oblique/possessive pronouns are follow-up stop words -----
# "Und was ist mit mir/uns?", "E quanto a mim?", "E riguardo a me?", "E che dire di noi?",
# "Hoe zit het met jullie/ons?", "Entä minä/me?", "А что насчёт меня/нас?",
# "A šta je sa mnom/nama?" and "¿Y qué hay de nosotros?" were merged as an unrecognised
# topic-shift content word (keeping the anchor market); they are pronouns, like English
# "What about me?", so they now stay standalone.

PRONOUN_STANDALONE_CASES = [
    ("de", "Und was ist mit mir?"),
    ("de", "Und was ist mit uns?"),
    ("pt", "E quanto a mim?"),
    ("it", "E riguardo a me?"),
    ("it", "E che dire di noi?"),
    ("nl", "Hoe zit het met jullie?"),
    ("nl", "Hoe zit het met ons?"),
    ("fi", "Entä minä?"),
    ("fi", "Entäs me?"),
    ("ru", "А что насчёт меня?"),
    ("ru", "А что насчёт нас?"),
    ("sr", "A šta je sa mnom?"),
    ("sr", "A šta je sa nama?"),
    ("es", "¿Y qué hay de nosotros?"),
]


@pytest.mark.parametrize(
    "language,follow_up",
    [pytest.param(language, follow_up, id=f"{language}:{follow_up}") for language, follow_up in PRONOUN_STANDALONE_CASES],
)
def test_localized_pronoun_follow_up_stays_standalone(language, follow_up) -> None:
    anchor = LANGUAGES[language][0]
    assert AIOrchestrator()._localized_follow_up_shape(follow_up) == ""
    assert _resolve(follow_up, _history(anchor)) == (follow_up, follow_up)


@pytest.mark.parametrize("follow_up", ["Und was ist mit mir?", "E quanto a mim?"])
def test_localized_pronoun_follow_up_after_a_refused_anchor_stays_standalone(follow_up) -> None:
    assert _resolve(follow_up, _history(INCOME_ANCHOR)) == (follow_up, follow_up)


@pytest.mark.parametrize(
    "language,follow_up",
    [
        ("de", "Und was ist mit Uganda?"),
        ("nl", "Hoe zit het met de verzendkosten?"),
        ("pt", "E quanto à Uganda?"),
        ("it", "E riguardo all'Uganda?"),
        ("fi", "Entä Uganda?"),
    ],
)
def test_pronoun_stop_words_do_not_disturb_other_localized_follow_ups(language, follow_up) -> None:
    anchor = LANGUAGES[language][0]
    retrieval, request = _resolve(follow_up, _history(anchor))
    assert retrieval != follow_up
    assert request.startswith(retrieval)
