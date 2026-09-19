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
        PHONE: ("reach",),
        PAYMENT_METHODS: (r"credit\s+cards?", r"debit\s+cards?"),
    },
}
# R05/N6 second follow-up (2026-09-18): "contact" was removed from the
# ``PHONE`` synonym above. It is redundant with
# ``app/retrieval/opensearch_sections.py``'s ``_DIRECTORY_DETAIL_RE``
# (``\b(?:address|business\s+hours?|email|office|phone|telephone|website|
# contact)\b``), which already feeds ``_directory_guard_topic_match`` ->
# ``directory_topic_route`` -> ``deterministic_directory_route`` in
# ``app/retrieval/providers.py._planned_retrieval_plan`` independently of
# this module - "How do I contact Forever Ghana?" still resolves to
# "directory" through that route (see
# ``tests/unit/test_r05_directory_protection_intent.py::
# test_contact_question_still_routes_to_directory_without_the_synonym``).
# Also fixed here: ``utils.directory_fields._DIRECTORY_INTENT_SYNONYM_PATTERNS``
# used to compile every term in this dict with a leading word-start
# (``(?<!\w)``) only, no trailing boundary - correct for the compound-stem
# terms in ``LANGUAGE_FIELD_TERMS`` above (deliberately, see this module's
# "Whole-word / inflection handling" section), but wrong for "reach", a bare
# verb with no useful inflection to catch this way: it let "reach**es**"
# ("...when it reaches Manager level?") match too. A trailing boundary
# (``(?!\w)``) was added to that compilation so only the literal word
# "reach" itself matches now; "credit/debit card(s)" already carried their
# own explicit, bounded ``s?`` and are unaffected.

# --- R05/N6 second follow-up (2026-09-18): multilingual POLICY-wording -----
#
# Symmetric counterpart to ``DIRECTORY_INTENT_SYNONYM_TERMS`` above and to
# ``LANGUAGE_FIELD_TERMS``: an independent review found that
# ``app/retrieval/providers.py``'s policy-wording suppression check
# (``DIRECTORY_POLICY_WORDING_RE``, plus
# ``services.guardrails.is_policy_safety_question``) is English-only, while
# the field-intent RECOGNITION check added by the first R05/N6 follow-up
# (``directory_field_intent_present``, via ``LANGUAGE_FIELD_TERMS``) is
# 13-language. That asymmetry meant a non-English POLICY question that also
# names a directory field (e.g. Spanish "¿Cual es la politica de Forever
# Norway sobre los metodos de pago?" - "politica" = policy, "metodos de
# pago" = payment methods) fell through the English-only policy check,
# matched the field-intent disjunct instead, and was wrongly promoted to
# "directory" with the full country bonus - reopening the N6 class of bug
# for non-English policy questions. The English equivalent already
# correctly resolves to "policy"/0.0 via ``DIRECTORY_POLICY_WORDING_RE``.
#
# What is actually covered (fixed by the fourth R05/N6 follow-up,
# 2026-09-18, coordinator review finding S1 - the original docstring here
# claimed "policy/rules/regulations/terms" coverage that did not exist yet;
# this now states exactly what each language's tuple below contains):
#
# - **"policy" sense** (a company policy/rulebook): es politica/normas/
#   reglas/reglamento; fr politique/regles/reglement; de Richtlinie/Regel/
#   Regelung/Vorschrift/Bestimmung; nl beleid/regel/reglement; it politica/
#   regola/regolamento; pt politica/regra/regulamento; fi kaytanto/saanto/
#   maarays; no/da retningslinje/regel; sv riktlinje/regel; ru politika/
#   pravilo; sr politika/pravilo (Latin and Cyrillic).
# - **"regulation(s)" sense** as a distinct synonym, where the language has
#   one: de Vorschrift(en)/Bestimmung(en) (both added alongside Regelung,
#   which already covered this sense); fi maarays/maaraykset.
# - **"guideline(s)" sense**: fr directive(s); it "linea guida"/"linee
#   guida" (multi-word, matched as a literal phrase); pt diretriz(es); fi
#   ohje/ohjeet; nl richtlijn(en) (already present for "guideline", not new
#   here); es directriz/directrices; no/da retningslinje(r) and its
#   definite forms retningslinjene/retningslinjerne (already present); sv
#   riktlinje(r) and riktlinjerna (already present).
# - **"condition(s)"/"terms" sense** (as in "terms and conditions"): es
#   condicion/condiciones; fr condition(s); de Bedingung(en); nl
#   voorwaarde(n); it condizione/condizioni; pt condicao/condicoes; fi
#   ehto/ehdot; no/da/sv vilkar/villkor (invariant singular=plural in all
#   three); ru uslovie/uslovija/uslovijah (nominative + locative); sr
#   uslov/uslovi/uslova/uslovima (Latin and Cyrillic).
# - **Oblique/definite grammatical forms**, where the review's own repros
#   needed them: ru political/pravila's dative/accusative/instrumental
#   cases (politike/politiku/politikoj, pravilam/pravilami/pravilah); sr
#   the equivalent oblique forms of politika/pravila (politici/politiku/
#   politikom, pravilima), Latin and Cyrillic; no/da/sv definite plural
#   forms of regel/retningslinje/riktlinje (reglene/retningslinjene,
#   reglerne/retningslinjerne, reglerna/riktlinjerna).
#
# Deliberately narrow and closed, exactly like ``DIRECTORY_INTENT_SYNONYM_TERMS``:
# spelled out as explicit inflected forms (not open stems, except where a
# language's own grammar makes an explicit list impractical - see below),
# so every entry is auditable and matched as a whole word
# (``utils.directory_fields._POLICY_WORDING_PATTERNS`` wraps each with both
# a leading and a trailing boundary, and folds accents - see
# ``utils.directory_fields._fold_diacritics`` - so one accented spelling
# also matches its accentless and NFD-decomposed variants without a
# separate entry) rather than approximated the way the field-request stems
# above are. Covers every language ``LANGUAGE_FIELD_TERMS`` already covers
# except English itself (English's own ``DIRECTORY_POLICY_WORDING_RE``
# stays the sole English source, unchanged, exactly as
# ``LANGUAGE_FIELD_TERMS`` leaves English to
# ``utils.directory_fields._FIELD_REQUEST_PATTERNS``).
#
# **Not covered, on purpose:** every other inflected case a language's
# grammar can produce beyond the forms listed above (e.g. Finnish's
# remaining oblique cases of "kaytanto"/"saanto"/"ehto"/"maarays"/"ohje"
# beyond the ones spelled out; German/Dutch/Romance-language genitive or
# other compound-forming inflections). A form not in this list is treated
# the same as before this task existed - "ambiguous", not "policy" - which
# only risks losing directory *protection* for that specific unlisted
# spelling, never wrongly granting it (this table is read only by the
# suppression side, never by anything that recognizes directory intent).
#
# **Accepted idiom trade-off (coordinator review note N1):** "regel"/
# "regler" (no/da) and "riktlinje"/"regel" family forms also match inside
# the idiom "som regel" ("as a rule", not a reference to a policy
# document), so a genuinely directory-intentioned Norwegian/Danish/Swedish
# question that happens to use that idiom would be wrongly suppressed to
# "policy". This is deliberately accepted, not fixed, for the same reason
# English's own widened ``DIRECTORY_POLICY_WORDING_RE`` accepts "terms of"
# firing inside the unrelated "in terms of X" idiom (see that regex's own
# comment in ``app/retrieval/providers.py``): the genuine policy-document
# sense dominates real usage, and narrowing either pattern to dodge its own
# idiom risks missing the genuine sense it exists to catch. Over-suppression
# here only costs the country-match *bonus* on a country-named row, never
# retrieval inclusion (the row can still be found and returned).
#
# Confidence: reuses the same high/medium split as ``LANGUAGE_FIELD_TERMS``'s
# own docstring - French/German/Dutch/Spanish/Italian/Swedish forms
# (including this follow-up's regulation/condition/guideline additions to
# them) are ordinary, unambiguous dictionary words (high confidence);
# Portuguese/Finnish/Norwegian/Danish/Russian/Serbian forms remain this
# module's own first pass (medium confidence, same caveat as the
# payment/delivery-cost-vs-time split above - a native reviewer should
# check these before they gate anything destructive in production). The
# Finnish "ehto"/"ehdot" pair is explicitly flagged medium-to-low: Finnish
# consonant gradation (t/d) is captured for this one pair by listing both
# the nominative and the gradated plural explicitly, but no further oblique
# case of it is covered.
POLICY_WORDING_TERMS: dict[str, tuple[str, ...]] = {
    "es": (
        "política", "políticas", "norma", "normas", "regla", "reglas",
        "reglamento", "reglamentos", "condición", "condiciones",
        "directriz", "directrices",
    ),
    "fr": (
        "politique", "politiques", "règle", "règles", "règlement", "règlements",
        "condition", "conditions", "directive", "directives",
    ),
    "de": (
        "richtlinie", "richtlinien", "regel", "regeln", "regelung", "regelungen",
        "vorschrift", "vorschriften", "bestimmung", "bestimmungen",
        "bedingung", "bedingungen",
    ),
    "nl": (
        "beleid", "regel", "regels", "voorwaarde", "voorwaarden",
        "richtlijn", "richtlijnen", "reglement",
    ),
    "it": (
        "politica", "politiche", "regola", "regole", "regolamento", "regolamenti",
        "condizione", "condizioni", "linea guida", "linee guida",
    ),
    "pt": (
        "política", "políticas", "regra", "regras", "regulamento", "regulamentos",
        "condição", "condições", "diretriz", "diretrizes",
    ),
    "fi": (
        "käytäntö", "käytännön", "käytäntöä", "sääntö", "säännöt", "säännön",
        "ehto", "ehdot", "määräys", "määräykset", "ohje", "ohjeet",
    ),
    "no": (
        "retningslinje", "retningslinjer", "retningslinjene",
        "regel", "regler", "reglene", "vilkår",
    ),
    "da": (
        "retningslinje", "retningslinjer", "retningslinjerne",
        "regel", "regler", "reglerne", "vilkår",
    ),
    "sv": (
        "riktlinje", "riktlinjer", "riktlinjerna",
        "regel", "regler", "reglerna", "villkor",
    ),
    "ru": (
        "политика", "политики", "политике", "политику", "политикой",
        "правило", "правила", "правилам", "правилами", "правилах",
        "условие", "условия", "условиях",
    ),
    "sr": (
        "politika", "politike", "politici", "politiku", "politikom",
        "pravilo", "pravila", "pravilima",
        "uslov", "uslovi", "uslova", "uslovima",
        "политика", "политике", "политици", "политику", "политиком",
        "правило", "правила", "правилима",
        "услов", "услови", "услова", "условима",
    ),
}
