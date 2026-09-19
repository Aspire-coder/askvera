r"""Closed, multilingual vocabulary for Lane 5 (conversation repair + typo
clarification), scoped to `app/orchestrator/conversation_repair.py` only.

Per the CX lane contract (docs/conversation-quality/phase3/CX_LANES.md), a
new closed vocabulary is allowed only where none already exists, must live in
`config/`, and must be documented with its confidence per language. Everything
below is new to this module: it is a presentation-layer word list (what a
reader recognizes as "shipping" vs "shopping", and what a correction like "no,
I meant X" looks like in each language), not a second copy of any existing
retrieval-matching vocabulary. Two things ARE reused rather than duplicated,
per the "no duplicated vocabularies" rule:

- Market resolution never appears here at all. `app/orchestrator/
  conversation_repair.py` resolves a market/country repair only through
  `services.market_config.find_market_mentions` / `market_display_name` -
  the same resolvers `app/orchestrator/reference_resolution.py` already
  trusts - never a locally invented alias list.
- The typo shape/distance helpers used to detect a "shipping"/"shopping"
  collision are imported (read-only) from `app/retrieval/typo_safety.py`
  (Codex-owned), not reimplemented here.

## Language coverage

Exactly the 12 route locales `config/conversation_routes.json` configures
(da, de, en, es, fi, fr, it, nl, no, ru, sr, sv) - the same set
`app/retrieval/typo_safety.py`'s collision pair and
`config/directory_field_vocabulary.py`'s field terms are built for.

## Confidence

- **High** (a direct literal translation of a fixed, unambiguous English
  phrase, not an idiom): the `MEANT_CUE_PHRASES` / `NOT_CUE_WORDS` correction
  markers for en/es/fr/de/fi/sv - these are the six languages this lane's
  tests exercise directly and were checked against the task's own examples
  ("no, quise decir...", "non, je voulais dire...", "nein, ich meinte...",
  "ei, tarkoitin...").
  - MEANT_CUE_PHRASES["ru"] and MEANT_CUE_PHRASES["sr"] used the ASCII
    Latin script by mistake for a script whose ordinary written form is
    Cyrillic; corrected here to the Cyrillic "я имел(а) в виду" / "мислио
    сам на" / "мислила сам на" (Latin "mislio/mislila sam na" is also a
    real, ordinary Serbian spelling, so Serbian keeps both scripts; Russian
    keeps only Cyrillic, its ordinary written form).
- **Medium** (first pass, same discipline as the six above, but not
  independently checked against a worked example in this task): nl, it, pt,
  no, da, ru, sr correction markers, and every language's
  `SHIPPING_OPTION_LABEL` / `SHOPPING_OPTION_LABEL` pair.
- **Low** (a deliberately small, closed set of extra bare words that make a
  typo'd "shipping"/"shopping" collision resolve to a topic repair - see
  `TOPIC_REPLACEMENT_WORDS`): every language. A missing word here only ever
  makes `detect_repair` fail to resolve a topic repair it could have
  (the safe, conservative direction - see `conversation_repair.py`'s own
  module docstring for the same "under-covering is safe, over-covering is
  not" reasoning `config/reference_vocabulary.py` already documents).
- **Low, English-only** (`CONTEXT_DISAMBIGUATION_WORDS`): the localized
  entries for the other 11 languages are a first-pass, non-native-reviewed
  translation of the same small English set (courier/delivery-leaning and
  purchase/cart-leaning words), following the source module's own
  "under-covering is safe" principle - a missing disambiguating word only
  ever causes one extra clarifying question, never a silently wrong answer.
"""

from __future__ import annotations

# --- Correction cues ("no, I meant X" / "not Y, X") -------------------------
#
# `conversation_repair.detect_repair` builds one case-insensitive regex per
# language from each of the two tables below. Neither table is itself a
# regex: values are plain literal phrases, escaped by the caller.

# "I meant X" / "I actually meant X" style, with an optional leading
# "no,"/"sorry," (or that language's equivalent) handled by the caller's
# regex template, not spelled out per-phrase here.
MEANT_CUE_PHRASES: dict[str, tuple[str, ...]] = {
    "en": ("i meant", "i actually meant"),
    "es": ("quise decir", "queria decir"),
    "fr": ("je voulais dire",),
    "de": ("ich meinte", "ich meine"),
    "fi": ("tarkoitin",),
    "sv": ("jag menade",),
    "nl": ("ik bedoelde",),
    "it": ("intendevo",),
    "pt": ("quis dizer",),
    "no": ("jeg mente",),
    "da": ("jeg mente",),
    "ru": ("я имел в виду", "я имела в виду"),
    "sr": ("mislio sam na", "mislila sam na", "мислио сам на", "мислила сам на"),
}

# The single word that opens a "not Y, X" contrast ("not Kenya, Uganda").
NOT_CUE_WORDS: dict[str, str] = {
    "en": "not",
    "es": "no",
    "fr": "pas",
    "de": "nicht",
    "fi": "ei",
    "sv": "inte",
    "nl": "niet",
    "it": "non",
    "pt": "nao",
    "no": "ikke",
    "da": "ikke",
    "ru": "ne",
    "sr": "ne",
}

# --- Field-typo collision (shipping/shopping) -------------------------------
#
# `app/retrieval/typo_safety.py` (Codex-owned, read-only) defines exactly one
# semantic-collision pair, in English: {"shipping", "shopping"}. These two
# words are one QWERTY-adjacent letter apart ("i" -> "o"), so a typo'd form
# near either one is, by construction, plausibly a typo of the other too.
# `conversation_repair.typo_clarification` looks for that English collision
# regardless of the message's declared language (a support question in any
# of the 12 route languages may still contain the borrowed English word
# "shipping"/"shopping", exactly as the task's own worked examples show:
# "shoping cost", "shippng cost", "shopping cost" are all bare English
# tokens). What IS localized is the readable clarifying question built
# around that collision: the two options a reader sees, and the words that
# make the question unnecessary because the sentence already disambiguates.
#
# A genuinely native-language typo collision pair (e.g. two French words one
# edit apart that mean different things) is out of scope for this module:
# `typo_safety._SEMANTIC_COLLISION_PAIRS` is Codex-owned and English-only,
# and extending it to other languages needs that module's own review, not a
# second, unreviewed collision table invented here.

# The two readable option labels `clarify_field`'s {options} placeholder is
# filled with, already localized (Lane 4's renderer fills the template
# around them, but does not translate them further). Deliberately a plain
# readable phrase, not a regex-matching stem, which is why this is a new,
# presentation-layer pair distinct from `config/directory_field_vocabulary`'s
# `DELIVERY_COST` matching stems (that module answers "does this question
# name the delivery-cost field", a different question from "what should the
# reader see as the two options").
SHIPPING_OPTION_LABEL: dict[str, str] = {
    "en": "shipping cost",
    "es": "coste de envio",
    "fr": "frais de livraison",
    "de": "Versandkosten",
    "fi": "toimituskulut",
    "sv": "fraktkostnad",
    "nl": "verzendkosten",
    "it": "costi di spedizione",
    "pt": "custo de envio",
    "no": "fraktkostnad",
    "da": "fragtomkostning",
    "ru": "стоимость доставки",
    "sr": "trosak dostave",
}
SHOPPING_OPTION_LABEL: dict[str, str] = {
    "en": "shopping cost",
    "es": "coste de compra",
    "fr": "frais d'achat",
    "de": "Einkaufskosten",
    "fi": "ostoskulut",
    "sv": "shoppingkostnad",
    "nl": "aankoopkosten",
    "it": "costi di acquisto",
    "pt": "custo de compra",
    "no": "handlekostnad",
    "da": "indkobsomkostning",
    "ru": "стоимость покупки",
    "sr": "trosak kupovine",
}

# Words that already disambiguate a "shipping"/"shopping" collision, so no
# question is asked. Two directions: a courier/delivery-leaning word settles
# the collision toward "shipping"; a purchase/cart-leaning word settles it
# toward "shopping". Either direction is sufficient by itself - the point is
# only that the sentence is no longer ambiguous, not which side it lands on.
CONTEXT_DISAMBIGUATION_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset({
        "delivery", "courier", "postage", "parcel", "shipment", "ship", "shipped",
        "purchase", "purchasing", "buy", "buying", "cart", "checkout", "order",
    }),
    "es": frozenset({
        "entrega", "envio", "paquete", "mensajeria",
        "compra", "comprar", "carrito", "pedido",
    }),
    "fr": frozenset({
        "livraison", "colis", "transporteur",
        "achat", "acheter", "panier", "commande",
    }),
    "de": frozenset({
        "lieferung", "versand", "paket", "kurier",
        "einkauf", "kaufen", "warenkorb", "bestellung",
    }),
    "fi": frozenset({
        "toimitus", "paketti", "kuljetus",
        "ostos", "ostaa", "ostoskori", "tilaus",
    }),
    "sv": frozenset({
        "leverans", "paket", "frakt",
        "kop", "kopa", "varukorg", "bestallning",
    }),
    "nl": frozenset({
        "levering", "bezorging", "pakket",
        "aankoop", "kopen", "winkelwagen", "bestelling",
    }),
    "it": frozenset({
        "consegna", "pacco", "corriere",
        "acquisto", "comprare", "carrello", "ordine",
    }),
    "pt": frozenset({
        "entrega", "pacote", "transportadora",
        "compra", "comprar", "carrinho", "pedido",
    }),
    "no": frozenset({
        "levering", "pakke", "frakt",
        "kjop", "kjope", "handlekurv", "bestilling",
    }),
    "da": frozenset({
        "levering", "pakke", "fragt",
        "kob", "kobe", "indkobskurv", "bestilling",
    }),
    "ru": frozenset({
        "доставка", "посылка", "курьер",
        "покупка", "купить", "корзина", "заказ",
    }),
    "sr": frozenset({
        "dostava", "paket", "kurir",
        "kupovina", "kupiti", "korpa", "porudzbina",
    }),
}

# --- Topic repairs beyond the shipping/shopping collision -------------------
#
# A deliberately small, closed set: folded (casefolded, accent-stripped)
# token -> the canonical, already-localized label the topic repair replaces
# it with. `conversation_repair._resolve_market_or_topic` and
# `_find_replaced_span` are the only readers. Every language's set always
# includes its own words for "shipping"/"delivery" (mapping to
# SHIPPING_OPTION_LABEL) and "shopping"/"purchase" (mapping to
# SHOPPING_OPTION_LABEL), so "no, I meant shipping" and its equivalents in
# the other 11 languages resolve as a topic repair even outside the typo
# collision path (an exact, correctly spelled word still needs to be
# recognized as a valid repair target).
TOPIC_REPLACEMENT_WORDS: dict[str, dict[str, str]] = {
    "en": {"shipping": "shipping", "shopping": "shopping", "delivery": "shipping"},
    "es": {"envio": "shipping", "entrega": "shipping", "compra": "shopping"},
    "fr": {"livraison": "shipping", "expedition": "shipping", "achat": "shopping"},
    "de": {"versand": "shipping", "lieferung": "shipping", "einkauf": "shopping"},
    "fi": {"toimitus": "shipping", "ostos": "shopping"},
    "sv": {"frakt": "shipping", "leverans": "shipping", "kop": "shopping"},
    "nl": {"verzending": "shipping", "levering": "shipping", "aankoop": "shopping"},
    "it": {"spedizione": "shipping", "consegna": "shipping", "acquisto": "shopping"},
    "pt": {"envio": "shipping", "entrega": "shipping", "compra": "shopping"},
    "no": {"frakt": "shipping", "levering": "shipping", "kjop": "shopping"},
    "da": {"fragt": "shipping", "levering": "shipping", "kob": "shopping"},
    "ru": {
        "доставка": "shipping",
        "покупка": "shopping",
    },
    "sr": {"dostava": "shipping", "kupovina": "shopping"},
}

# Bare, single-word canonical form of each collision-pair side, used only for
# `detect_repair`'s TOKEN-level swap (replacing one bare word in the
# previous question with another bare word keeps the rest of that question's
# own wording - "cost", "fee", whatever it already said - untouched, unlike
# swapping in the multi-word `SHIPPING_OPTION_LABEL`/`SHOPPING_OPTION_LABEL`
# phrase above, which is written for `typo_clarification`'s standalone
# ``clarify_field`` question and would duplicate a word already in the
# sentence, e.g. "the shipping cost cost"). Each is simply the first,
# most-common stem already listed in `TOPIC_REPLACEMENT_WORDS` for that side.
SHIPPING_BARE_WORD: dict[str, str] = {
    "en": "shipping",
    "es": "envio",
    "fr": "livraison",
    "de": "Versand",
    "fi": "toimitus",
    "sv": "frakt",
    "nl": "verzending",
    "it": "spedizione",
    "pt": "envio",
    "no": "frakt",
    "da": "fragt",
    "ru": "доставка",
    "sr": "dostava",
}
SHOPPING_BARE_WORD: dict[str, str] = {
    "en": "shopping",
    "es": "compra",
    "fr": "achat",
    "de": "Einkauf",
    "fi": "ostos",
    "sv": "kop",
    "nl": "aankoop",
    "it": "acquisto",
    "pt": "compra",
    "no": "kjop",
    "da": "kob",
    "ru": "покупка",
    "sr": "kupovina",
}

SUPPORTED_REPAIR_LANGUAGES = frozenset(MEANT_CUE_PHRASES)

assert set(MEANT_CUE_PHRASES) == set(SHIPPING_BARE_WORD)
assert set(MEANT_CUE_PHRASES) == set(SHOPPING_BARE_WORD)

assert set(MEANT_CUE_PHRASES) == set(NOT_CUE_WORDS)
assert set(MEANT_CUE_PHRASES) == set(SHIPPING_OPTION_LABEL)
assert set(MEANT_CUE_PHRASES) == set(SHOPPING_OPTION_LABEL)
assert set(MEANT_CUE_PHRASES) == set(CONTEXT_DISAMBIGUATION_WORDS)
assert set(MEANT_CUE_PHRASES) == set(TOPIC_REPLACEMENT_WORDS)
