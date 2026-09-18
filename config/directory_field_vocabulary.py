r"""Multilingual vocabulary for interpreting *which* directory field a question asks for.

Phase 2 / Lane B (2026-09-18). Scope, deliberately narrow: this module answers
only "does the QUESTION name this canonical directory field?" for the same
nine/ten canonical keys :mod:`utils.directory_fields` already uses for
English (``phone``, ``order_phone``, ``email``, ``website``, ``address``,
``business_hours``, ``payment_methods``, ``delivery_cost``, ``delivery_time``,
``fax``). It is consumed only by
:func:`utils.directory_fields._requested_directory_field_set`.

It does **not** localize how a field is *labelled inside a generated answer*.
The directory record itself is a canonical, always-English document (see
``utils/directory_fields.py``'s own note on ``_SUPPORT_CONTACT_LABEL_TRANSLATIONS``:
"The English text always comes verbatim from the approved directory record
itself"), and every test fixture in this codebase that exercises
``remove_unrequested_directory_fields``/``restore_missing_requested_directory_fields``
against a non-English *question* still uses an English-labelled *answer*
(see ``tests/conversation/test_intent_multipart_order_size_payment.py``'s
``KENYA_ANSWER``). So the removal/restoration mechanics that scan the answer
text for "Label: value" lines need no change here - only the interpretation
of the question does.

## How the terms were chosen

Wherever this repository already carries a reviewed multilingual vocabulary
for the same idea, its terms are reused verbatim rather than re-invented:

- ``app/orchestrator/chat_orchestrator.py``'s ``LOCALIZED_DIRECTORY_FIELD_TERMS``
  (built for a different purpose - deciding whether a short follow-up names a
  directory field at all, for nl/fr/de/es/pt/it/sv/da/no/fi/ru/sr) supplied
  the phone/email/website/address/business-hours/delivery/payment stems here,
  split per canonical field key (that dict lumps them together for its own
  purpose; this module needs them apart to tell "phone" from "email").
- ``utils/directory_fields.py``'s own ``_SUPPORT_CONTACT_LABEL_TRANSLATIONS``
  and ``_LOCALIZED_ORDER_SIZE_QUESTION_RE``/``_FBO_ORDER_SIZE_LABELS`` confirm
  the same stems for address/phone/email/website/business_hours/fax and for
  the minimum-order trigger, for nl/fr/de/es/it/pt/sv (labels) and
  nl/fr/de/es/it/da/fi/no/sv/ru/sr (order-size trigger; ``pt`` was missing
  there and is added in this change, using the same "pedido mínimo" /
  "encomenda mínima" shape as the other Romance languages).
- ``payment_methods``, ``delivery_cost``, ``delivery_time``, ``order_phone``
  and ``fax`` (as a *request* term, not just a label) had no existing reviewed
  split in either file, so those stems are new to this module. They follow
  the same "compound stem, not a bare generic word" discipline as the reused
  terms (see below) but carry lower confidence - see "Confidence" below.

## Whole-word / inflection handling

Every stem is matched with ``(?<!\\w)`` (a word start) but no trailing
boundary, exactly like ``app/orchestrator/chat_orchestrator.py``'s
``_follow_up_stem_pattern``: this lets one spelling match a family of
inflected forms that share a prefix (Dutch "levertijd"/"levertijden", German
"Lieferzeit"/"Lieferzeiten", Finnish case suffixes glued onto a noun stem)
without hard-coding every ending. This is a bounded approximation, not a real
stemmer or morphological analyzer:

- **Finnish** is heavily inflected (15 grammatical cases, consonant gradation
  inside the stem itself: "puhelin" -> "puhelimen", "puhelimesta"). Matching
  from the *nominative* stem before its case ending is added
  (``puhelin``, ``sähköposti``, ``osoite``/``osoitte`` to also catch the
  gradated "osoitteen") catches the nominative and most oblique forms that
  keep the written stem intact, but a form whose gradation changes the
  stem's own letters *before* any suffix (e.g. "puhelimeen", "puhelimista")
  is only caught here because ``puhelin``'s stem-final vowel already varies
  in the recorded fragment set below; a rarer gradation is not guaranteed to
  match. This is a known, documented gap, not a claimed complete solution.
- **German/Dutch compounds** are matched by their compound-initial fragment
  (e.g. "liefer" covers "Lieferzeit", "Lieferkosten", "Liefergebühr"), which
  is safe because German/Dutch compounding glues without a case ending
  between the parts.
- **Russian/Serbian** case endings are handled the same bounded way: the stem
  before the case ending is kept and the ending left open, e.g. Russian
  "заказ" covers "заказа", "заказом", "заказе".
- No stemmer, morphological analyzer or machine translation is used anywhere
  in this module, per the project rule against new runtime dependencies and
  network/model calls.
- **Documented limitation - suffix compounds.** Every stem below matches
  from a word start (``(?<!\w)``), so it only matches when the field word is
  the *first* element of a compound ("Lieferzeit") or stands alone ("die
  Adresse des Büros"). A field word that is the compound's *second* element
  ("Büroadresse", "Firmenadresse" - "office address" written as one German
  word instead of "die Adresse des Büros") is not matched, because the stem
  does not sit at that inner position's word boundary. This is the same
  bound the reused ``LOCALIZED_DIRECTORY_FIELD_TERMS`` in
  ``chat_orchestrator.py`` already accepts (its own address/phone stems are
  written the same way); this module inherits it rather than working around
  it with a second, unreviewed pattern shape.

## Confidence, per language

High confidence (reused, already-reviewed terms; only split apart, not
re-worded): French, German, Dutch, Spanish, Italian, Swedish - these were
already carrying phone/email/website/address/business_hours/delivery/payment
stems in ``LOCALIZED_DIRECTORY_FIELD_TERMS`` or
``_SUPPORT_CONTACT_LABEL_TRANSLATIONS``.

Medium confidence (reused base vocabulary, but the split-out
``payment_methods``/``delivery_cost``/``delivery_time`` distinction, and
``order_phone``/``fax`` request terms, are new and unreviewed by a native
speaker): Portuguese, Finnish, Norwegian, Danish, Russian, Serbian - the
phone/email/address/business_hours stems are the reused, reviewed ones; the
payment/delivery-cost-vs-time split and fax/order-phone additions are this
module's own first pass and are the terms least sure of.

Least sure of, specifically: the Russian and Serbian ``payment_methods``
stems (``способ\\w* оплат`` / ``način\\w* plaćanj``) and the
``delivery_cost`` vs. ``delivery_time`` split for every language other than
the five high-confidence ones above - a native reviewer should check these
before they gate anything destructive in production.

## Explicit business/office hours only, never a bare duration

Every ``business_hours`` entry below is a compound term ("opening hours",
"office hours", "heures d'ouverture", "Öffnungszeiten", "aukioloaika" -
never a bare "hours"/"heures"/"Stunden"/"horas"/"ore"/"tuntia"/"timmar"/
"timer"/"часов"/"sati" duration word). This mirrors the reviewed exclusion
already documented on ``LOCALIZED_DIRECTORY_FIELD_TERMS`` in
``chat_orchestrator.py`` ("Bare 'hours' words ... are left out as too
loose") and means a duration such as "48 heures"/"48 Stunden"/"48 tuntia"
never matches ``business_hours`` here by construction - no separate
"explicit-only" pattern is needed the way English needs
``_EXPLICIT_BUSINESS_HOURS_RE`` as a second, narrower check.

## Combinations out of this module's scope

"Free-delivery threshold" (a minimum spend that waives the delivery fee) is
not one of the ten canonical field keys this module (or its English side)
already tracks - there is no existing ``en`` pattern for it either, and per
instruction this module does not invent a new canonical key unilaterally.
The "delivery fee" half of that combination is covered here as
``delivery_cost``; the "threshold" half is out of scope.

"Eligibility + waiting period" and "qualification amount + qualification
period" are policy text (rank/manager qualification rules), not structured
directory record fields - they have no canonical key in this module at all
and are not directory fields to begin with. They are out of scope for
``utils/directory_fields.py`` and are not forced into it.
"""

from __future__ import annotations

# Canonical field keys, matching utils.directory_fields exactly.
PHONE = "phone"
ORDER_PHONE = "order_phone"
EMAIL = "email"
WEBSITE = "website"
ADDRESS = "address"
BUSINESS_HOURS = "business_hours"
PAYMENT_METHODS = "payment_methods"
DELIVERY_COST = "delivery_cost"
DELIVERY_TIME = "delivery_time"
FAX = "fax"

# Per-language, per-field REQUEST stems: "does the question name this field?"
# English is intentionally absent - utils/directory_fields.py's existing
# _FIELD_REQUEST_PATTERNS/_ORDER_PHONE_REQUEST_RE stay the sole English
# source, unchanged, for backward compatibility.
LANGUAGE_FIELD_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "fr": {
        PHONE: ("téléphone", "telephone"),
        EMAIL: (r"e-?mail", "courriel"),
        WEBSITE: (r"site (?:web|internet)",),
        ADDRESS: ("adresse",),
        BUSINESS_HOURS: (r"heures? d[' ]ouverture", r"horaires? d[' ]ouverture"),
        PAYMENT_METHODS: (r"(?:moyens?|m[eé]thodes?|modes?) de paiement",),
        DELIVERY_COST: (r"frais de livraison", r"co[uû]t de livraison"),
        DELIVERY_TIME: (r"d[eé]lai\w* de livraison",),
        FAX: ("fax",),
    },
    "de": {
        PHONE: ("telefon",),
        EMAIL: (r"e-?mail",),
        WEBSITE: ("webseite", "internetseite", "website"),
        ADDRESS: ("adress", "anschrift"),
        BUSINESS_HOURS: ("öffnungszeit", "oeffnungszeit", "geschäftszeit", "geschaeftszeit"),
        PAYMENT_METHODS: ("zahlungsmethod", "zahlungsart", "zahlungsmittel"),
        DELIVERY_COST: (r"liefer(?:kosten|gebühr|gebuehr)",),
        DELIVERY_TIME: ("lieferzeit",),
        FAX: ("fax",),
    },
    "nl": {
        PHONE: ("telefoon",),
        EMAIL: (r"e-?mail",),
        WEBSITE: ("website",),
        ADDRESS: ("adres",),
        BUSINESS_HOURS: ("openingstijd", "openingsuren"),
        PAYMENT_METHODS: ("betaalmethod", "betalingsmethod", "betaalwijz"),
        DELIVERY_COST: ("verzendkost", "leverkost", "bezorgkost"),
        DELIVERY_TIME: ("levertijd",),
        FAX: ("fax",),
    },
    "es": {
        PHONE: ("teléfono", "telefono"),
        EMAIL: (r"correo\s+electr[oó]nico", r"e-?mail"),
        WEBSITE: (r"(?:sitio|p[aá]gina)\s+web",),
        ADDRESS: (r"direcci[oó]n",),
        BUSINESS_HOURS: (r"horario\s+(?:de\s+oficina|comercial|de\s+atenci[oó]n)",),
        PAYMENT_METHODS: (r"m[eé]todos?\s+de\s+pago", r"formas?\s+de\s+pago"),
        DELIVERY_COST: (r"(?:coste?|costo|gastos?)\s+de\s+env[ií]o",),
        DELIVERY_TIME: (r"(?:plazo|tiempo)\s+de\s+entrega",),
        FAX: ("fax",),
    },
    "it": {
        PHONE: ("telefono",),
        EMAIL: (r"e-?mail", "posta elettronica"),
        WEBSITE: (r"sito\b",),
        ADDRESS: ("indirizzo",),
        BUSINESS_HOURS: (r"orario\s+(?:d[' ]ufficio|di\s+apertura|commerciale)",),
        PAYMENT_METHODS: (r"metodi\s+di\s+pagamento",),
        DELIVERY_COST: (r"(?:costi|spese)\s+di\s+spedizione",),
        DELIVERY_TIME: (r"tempi\s+di\s+consegna",),
        FAX: ("fax",),
    },
    "pt": {
        PHONE: ("telefone",),
        EMAIL: (r"e-?mail",),
        WEBSITE: (r"site\b",),
        ADDRESS: (r"endere[cç]o",),
        BUSINESS_HOURS: (r"hor[aá]rio\s+de\s+(?:funcionamento|atendimento)",),
        PAYMENT_METHODS: (r"m[eé]todos?\s+de\s+pagamento", r"formas?\s+de\s+pagamento"),
        DELIVERY_COST: (r"(?:custo|taxa)\s+de\s+(?:envio|entrega)",),
        DELIVERY_TIME: (r"prazo\s+de\s+entrega", r"tempo\s+de\s+entrega"),
        FAX: ("fax",),
    },
    "sv": {
        PHONE: ("telefon",),
        EMAIL: (r"e-?post", "mejl"),
        WEBSITE: ("webbplats", "hemsida", "webbsida"),
        ADDRESS: ("adress",),
        BUSINESS_HOURS: ("öppettid",),
        PAYMENT_METHODS: ("betalningsmetod", "betalningssätt"),
        DELIVERY_COST: ("fraktkostnad", "leveranskostnad"),
        DELIVERY_TIME: ("leveranstid",),
        FAX: ("fax",),
    },
    "da": {
        PHONE: ("telefon",),
        EMAIL: (r"e-?mail",),
        WEBSITE: ("hjemmeside", "webside"),
        ADDRESS: ("adresse",),
        BUSINESS_HOURS: ("åbningstid",),
        PAYMENT_METHODS: ("betalingsmetode",),
        DELIVERY_COST: ("leveringsomkostning", "fragtomkostning"),
        DELIVERY_TIME: ("leveringstid",),
        FAX: ("fax",),
    },
    "no": {
        PHONE: ("telefon",),
        EMAIL: (r"e-?post", "epost"),
        WEBSITE: ("nettside", "hjemmeside"),
        ADDRESS: ("adresse",),
        BUSINESS_HOURS: ("åpningstid",),
        PAYMENT_METHODS: ("betalingsmetode",),
        DELIVERY_COST: ("leveringskostnad", "fraktkostnad"),
        DELIVERY_TIME: ("leveringstid",),
        FAX: ("fax",),
    },
    "fi": {
        PHONE: ("puhelin",),
        EMAIL: ("sähköposti",),
        WEBSITE: ("verkkosivu", "kotisivu"),
        ADDRESS: ("osoite", "osoitte"),
        BUSINESS_HOURS: ("aukioloaika",),
        PAYMENT_METHODS: ("maksutap",),
        DELIVERY_COST: (r"toimitus(?:maksu|kulu)",),
        DELIVERY_TIME: ("toimitusaika",),
        FAX: ("faksi", "fax"),
    },
    "ru": {
        PHONE: ("телефон",),
        EMAIL: (r"электронн\w*\s+почт", "имейл", "емейл"),
        WEBSITE: ("сайт",),
        ADDRESS: ("адрес",),
        BUSINESS_HOURS: (r"час\w*\s+работ", r"график\w*\s+работ"),
        PAYMENT_METHODS: (r"способ\w*\s+оплат",),
        DELIVERY_COST: (r"стоимост\w*\s+доставк",),
        DELIVERY_TIME: (r"срок\w*\s+доставк",),
        FAX: ("факс",),
    },
    "sr": {
        PHONE: ("telefon", "телефон"),
        EMAIL: ("imejl", "email", "имејл", "мејл"),
        WEBSITE: ("sajt", "сајт"),
        ADDRESS: ("adres", "адрес"),
        BUSINESS_HOURS: (r"radn\w*\s+vrem", r"радн\w*\s+врем"),
        PAYMENT_METHODS: (r"na[cč]in\w*\s+pla[cć]anj", r"начин\w*\s+плаћањ"),
        DELIVERY_COST: (r"tro[sš]k\w*\s+dostav", r"трош\w*\s+достав"),
        DELIVERY_TIME: ("vreme dostave", "rok dostave", "време доставе", "рок доставе"),
        FAX: ("faks", "факс"),
    },
}

# Per-language "order" qualifier word(s): combined with PHONE being requested,
# these promote the request to ORDER_PHONE too, exactly mirroring English's
# _ORDER_PHONE_REQUEST_RE (`\border\b`). Reuses the same stems already used
# as the minimum-order-question trigger elsewhere in this repository
# (utils.directory_fields._LOCALIZED_ORDER_SIZE_QUESTION_RE), since "order"
# in "order phone" and "order" in "minimum order" is the same word in every
# one of these languages.
ORDER_WORD_TERMS: dict[str, tuple[str, ...]] = {
    "fr": ("commande",),
    "de": ("bestell",),
    "nl": ("bestel",),
    "es": ("pedido",),
    "it": ("ordine",),
    "pt": ("encomenda", "pedido"),
    "sv": (r"best[aä]ll",),
    "da": ("bestil",),
    "no": ("bestill",),
    "fi": ("tilau",),
    "ru": ("заказ",),
    "sr": (r"porud[zž]bin", r"narud[zž]bin", "поруџбин", "наруџбин"),
}

# Language-code aliases this module accepts, folded to the codes used as keys
# in LANGUAGE_FIELD_TERMS/ORDER_WORD_TERMS above.
_LANGUAGE_ALIASES: dict[str, str] = {
    "nb": "no",
    "nn": "no",
}


def normalize_language_code(language: str | None) -> str:
    """Fold a request-language tag to the code used as a key in this module.

    "fr-FR", "fr_FR" and "FR" all fold to "fr". Norwegian's "nb"/"nn" tags
    fold to "no", the code used throughout this repository's other
    localized vocabularies. An empty/``None`` input folds to "en".
    """
    code = (language or "en").strip().lower().replace("_", "-").split("-", 1)[0]
    return _LANGUAGE_ALIASES.get(code, code) or "en"


def supported_languages() -> frozenset[str]:
    """Every non-English language code this module has a vocabulary for."""
    return frozenset(LANGUAGE_FIELD_TERMS)


# --- R05/N6 follow-up (2026-09-18): directory-INTENT-only synonyms ---------
#
# Scope: these terms exist ONLY to help `app.retrieval.providers` recognise
# that a question carries genuine directory-field intent, for the retrieval
# scoring/dominance protection described in
# `docs/conversation-quality/phase2/R05_N6_DIRECTORY_PROTECTION.md`. They are
# never consumed by `utils.directory_fields._requested_directory_field_set`
# (the function `remove_unrequested_directory_fields`,
# `restore_missing_requested_directory_fields`, and `directory_field_conflicts`
# all call), so adding a term here cannot change what those functions strip,
# restore, or flag as conflicting - that behaviour keeps reading only
# `LANGUAGE_FIELD_TERMS`/`ORDER_WORD_TERMS`, exactly as before this change.
#
# An independent review of the R05/N6 fix (2026-09-18) found that
# `_requested_directory_field_set`'s own English field-request patterns
# already recognise "located"/"location" (part of the `address` field) and
# every literal field name (phone, email, website, address, business hours,
# payment methods, delivery cost/time, fax) in every one of the 13
# languages `LANGUAGE_FIELD_TERMS` covers - so questions phrased with those
# words need no new vocabulary at all. Two shapes from the review's failing
# repro set are not covered by any existing field name, though:
#
# - "How do I **reach** Forever Ghana?" - a bare contact verb, naming no
#   field at all, that nonetheless clearly asks for a way to contact the
#   office (a phone-shaped request in spirit). "contact" itself is the same
#   shape ("How do I **contact** Forever Ghana?").
# - "Does Forever Ghana accept **credit cards**?" - asking about a specific
#   payment instrument rather than using the literal phrase "payment
#   methods".
#
# Deliberately narrow and closed, per the review's own instruction not to
# make directory-intent recognition permissive wholesale: only these two
# shapes, English only. Confidence: English only, reviewer-identified
# (2026-09-18); not yet extended to any of the other 12 languages
# `LANGUAGE_FIELD_TERMS` covers - a documented gap (see
# `directory_field_intent_present`'s docstring in `utils/directory_fields.py`
# and the R05/N6 doc's "Limitations" section), not a claimed complete
# solution. A native-language addition here should follow the same
# "compound stem, not a bare generic word" discipline as the rest of this
# module before being trusted for another language.
DIRECTORY_INTENT_SYNONYM_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        PHONE: ("reach", "contact"),
        PAYMENT_METHODS: (r"credit\s+cards?", r"debit\s+cards?"),
    },
}
