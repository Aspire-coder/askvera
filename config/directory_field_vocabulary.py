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
# R05/N6 sixth follow-up (2026-09-18, coordinator review of 99ec438,
# MEDIUM finding): a Fable review ran 35 idiom/subordinate-clause probes
# against the fourth/fifth follow-ups' widened vocabulary and found 27
# newly, wrongly suppressed from "directory"/8.0 to "policy"/0.0. The root
# cause: several of the words added by the fourth follow-up are NOT
# dominantly policy-document words in ordinary usage - their dominant sense
# is something else entirely, and the fourth follow-up's own docstring
# claims about some of them ("richtlijn(en) already present for
# 'guideline'", "no/da retningslinje(r) ... already present", "sv
# riktlinje(r) ... already present") were themselves imprecise about what
# "already present" (in the reviewed second-follow-up F1 set) actually
# meant. Confirmed false positives from the review's probe set:
#
# - es "buenas condiciones" (office in good CONDITION, plural is the
#   normal Spanish idiom - the fifth follow-up's claim that only the
#   singular was ambiguous in Spanish/Italian/Portuguese was wrong)
# - it "in buone condizioni", pt "em boas condições" - same idiom, plural
# - en "road conditions"/"weather conditions" - same idiom, English
# - ru "в условиях пандемии" ("under pandemic conditions" - "условия" as a
#   circumstance/setting, not a policy document)
# - no/da/sv "uansett vilkår"/"under alla villkor" ("regardless of
#   terms"/"under all conditions" as a general expression, not "terms and
#   conditions" the document)
# - nl "onder voorwaarde dat" ("on condition that", a conjunction, not a
#   policy document)
# - de "unter der Bedingung" ("under the condition [that]", same
#   conjunction sense), "die Bestimmung meiner Sendung" (Bestimmung here
#   means "destination", not "provision/regulation" - a genuine directory/
#   logistics question)
# - fr "dans ces conditions" ("under these circumstances", not a policy
#   document), "directives de mon médecin" (a doctor's instructions, not a
#   Forever policy document)
# - it "linee guida del mio medico" (same - a doctor's guidelines)
# - es "directrices" (bare, same guideline-instruction ambiguity)
#
# **Coordinator decision (implemented exactly): keep only words whose
# dominant sense is a policy document.** Three categories survive per
# language:
#
# 1. **The original, second-follow-up F1 set** (``policy``/``rules``
#    equivalents already reviewed then - including German "Richtlinie",
#    which stays because it was part of that original reviewed set, not a
#    new addition; see the justification comment directly above
#    ``POLICY_WORDING_TERMS`` below).
# 2. **A distinct "regulation(s)" synonym**, where the language has one
#    whose dominant sense is unambiguously a policy/regulatory document:
#    es reglamento(s); fr règlement(s) (already in the F1 set); de
#    Vorschrift(en); nl reglement; it regolamento/regolamenti; pt
#    regulamento/regulamentos; fi määräykset (medium confidence, PLURAL
#    ONLY - the coordinator's decision names only the plural; the singular
#    "määräys" is dropped along with everything else not explicitly kept).
# 3. **The COMPOUND "terms and conditions" phrase**, matched as a whole
#    multi-word phrase (so it cannot fire on any word inside it appearing
#    alone elsewhere) - added new in this follow-up: en "terms and
#    conditions" (already present)/"terms of" (with the lookbehind, already
#    present); es "terminos y condiciones"; fr "conditions generales"; de
#    "Geschaftsbedingungen"/"AGB"/"Nutzungsbedingungen"; nl "algemene
#    voorwaarden"; it "termini e condizioni"; pt "termos e condicoes";
#    no/da "vilkar og betingelser"/"salgsbetingelser"; sv "allmanna
#    villkor"; fi "kayttoehdot"/"toimitusehdot"; ru "usloviya
#    ispol'zovaniya"/"usloviya prodazhi" (условия использования/условия
#    продажи).
#
# **Everything else the fourth/fifth follow-ups added is DROPPED**, per
# the coordinator's explicit instruction, because its dominant real-world
# sense is not a policy document:
#
# - every BARE condition-family form: es condiciones, fr conditions, de
#   Bedingung(en), nl voorwaarde(n), it condizioni, pt condicoes, fi
#   ehto/ehdot, no/da/sv vilkar/villkor, ru uslovie/uslovija/uslovijah,
#   sr uslov/uslovi/uslova/uslovima (Latin and Cyrillic) - the bare form
#   (singular or plural) is dominated in ordinary usage by a circumstance/
#   setting/conjunction sense ("in good condition(s)", "under the
#   condition that", "under pandemic conditions"), not a policy document.
# - every BARE guideline-family form: es directriz/directrices, fr
#   directive(s), it "linea guida"/"linee guida", pt diretriz/diretrizes,
#   fi ohje/ohjeet, nl richtlijn(en), no/da retningslinje/retningslinjer/
#   retningslinjene, sv riktlinje/riktlinjer/riktlinjerna - "guideline" in
#   ordinary usage very often refers to someone's personal or professional
#   guidance (a doctor's, a trainer's), not a company policy document, and
#   the fourth follow-up's claim that the nl/no/da/sv forms were "already
#   present" (in the original F1 set) was imprecise: nl "richtlijn" was
#   never in the original F1 set at all, and no/da "retningslinje(r)"/sv
#   "riktlinje(r)" WERE technically present in the original F1 set (see
#   ``POLICY_WORDING_TERMS``'s history), but the coordinator's explicit,
#   later instruction is to drop them regardless, alongside every other
#   guideline-family word, keeping only German "Richtlinie" from that
#   semantic family (justified below).
# - de Bestimmung(en) specifically: its dominant sense in ordinary usage
#   ("Bestimmung meiner Sendung" = "destination of my shipment") is a
#   genuine directory/logistics question, not "provision/regulation".
# - Serbian's oblique-case additions (politici/politiku/politikom,
#   pravilima, and their Cyrillic equivalents) were reverted here at first:
#   the coordinator's explicit KEEP list named only "the ru oblique cases
#   of политика/правила", not Serbian's - so, to implement the decision
#   exactly rather than extrapolate an unstated equivalence, Serbian
#   reverted to precisely its original F1 set. A follow-up coordinator
#   review then restored "pravilima"/"правилима" specifically (it is
#   rules-family - the oblique plural of "pravila" = rules - not
#   guideline/condition-family): see the seventh follow-up's own comment
#   directly above the "sr" entry in ``POLICY_WORDING_TERMS`` below.
#   politika's own oblique forms (politici/politiku/politikom, Cyrillic
#   equivalents) remain reverted; only pravilima's were restored.
#
# A form dropped here is treated the same as before this whole task
# existed - "ambiguous", not "policy" - which only risks losing directory
# *protection* for that specific spelling, never wrongly granting it (this
# table is read only by the suppression side, never by anything that
# recognizes directory intent). Reopened limitation, stated honestly: a
# genuine policy question using bare "conditions" ("What are the
# conditions of Forever Norway on the delivery address?", or the identical
# shape in any covered language) once again resolves to "directory"/8.0
# instead of "policy"/0.0, exactly as before the fourth follow-up - see
# ``docs/conversation-quality/phase2/R05_N6_DIRECTORY_PROTECTION.md``'s
# "Sixth follow-up" section.
#
# Matching mechanics are unchanged: every term below is still matched as a
# whole word/phrase (leading AND trailing boundary -
# ``utils.directory_fields._POLICY_WORDING_PATTERNS``) with accents folded
# (``utils.directory_fields._fold_diacritics``), so one accented spelling
# also matches its accentless and NFD-decomposed variants. A multi-word
# compound phrase (e.g. "terminos y condiciones") matches only that exact
# phrase, never a bare word inside it appearing alone elsewhere in the
# question.
#
# Confidence: the original F1 set and the regulation-equivalent additions
# keep the high/medium split already documented in ``LANGUAGE_FIELD_TERMS``'s
# own docstring (fr/de/nl/es/it/sv high; pt/fi/no/da/ru/sr medium). The new
# compound "terms and conditions" phrases are high confidence: each is the
# standard, unambiguous name for that legal document type in its language
# (e.g. German "AGB"/"Allgemeine Geschaftsbedingungen" and Norwegian/Danish
# "salgsbetingelser" have no other common meaning), so a multi-word phrase
# match carries far less ambiguity risk than any single bare word did.
POLICY_WORDING_TERMS: dict[str, tuple[str, ...]] = {
    "es": (
        "política", "políticas", "norma", "normas", "regla", "reglas",  # original F1 set
        "reglamento", "reglamentos",  # regulation(s) equivalent
        "términos y condiciones",  # compound "terms and conditions" phrase
    ),
    "fr": (
        "politique", "politiques", "règle", "règles", "règlement", "règlements",  # original F1 set (règlement(s) already the regulation(s) equivalent)
        "conditions générales",  # compound "terms and conditions" phrase
    ),
    # German "Richtlinie"/"Richtlinien" stays: it was part of the original,
    # second-follow-up F1 set (already reviewed then), not a new addition
    # this follow-up is introducing - unlike the guideline-family words
    # dropped from every other language above/below, which either were
    # never reviewed at all (nl "richtlijn") or are dropped regardless of
    # their own review history per the coordinator's explicit instruction
    # (no/da/sv). "Richtlinie" in German ordinary usage overwhelmingly
    # means an official/company directive or policy (a "Richtlinie" is
    # what a company or authority issues), unlike "guideline" in English
    # or "richtlijn" in Dutch, which lean more readily toward informal
    # personal/professional guidance.
    "de": (
        "richtlinie", "richtlinien", "regel", "regeln", "regelung", "regelungen",  # original F1 set
        "vorschrift", "vorschriften",  # regulation(s) equivalent
        "geschäftsbedingungen", "agb", "nutzungsbedingungen",  # compound "terms and conditions" phrases
    ),
    "nl": (
        "beleid", "regel", "regels",  # original F1 set
        "reglement",  # regulation(s) equivalent
        "algemene voorwaarden",  # compound "terms and conditions" phrase
    ),
    "it": (
        "politica", "politiche", "regola", "regole",  # original F1 set
        "regolamento", "regolamenti",  # regulation(s) equivalent
        "termini e condizioni",  # compound "terms and conditions" phrase
    ),
    "pt": (
        "política", "políticas", "regra", "regras",  # original F1 set
        "regulamento", "regulamentos",  # regulation(s) equivalent
        "termos e condições",  # compound "terms and conditions" phrase
    ),
    "fi": (
        "käytäntö", "käytännön", "käytäntöä", "sääntö", "säännöt", "säännön",  # original F1 set
        "määräykset",  # regulation(s) equivalent, medium confidence, plural only (coordinator's exact wording)
        "käyttöehdot", "toimitusehdot",  # compound "terms and conditions" phrases (single Finnish compound words)
    ),
    # R05/N6 seventh follow-up (2026-09-18, coordinator review of 52cee7b):
    # the sixth follow-up over-corrected by dropping "reglene"/"reglerne"/
    # "reglerna" - the definite PLURAL of "regel"/"regel"/"regel" ("rule"),
    # not a guideline-family word at all. They are the ordinary way to
    # write "the rules" in Norwegian/Danish/Swedish ("Hva er reglene til
    # Forever Norge for leveringsadressen?" = "What are the RULES of
    # Forever Norge for the delivery address?"), squarely inside the KEEP
    # list's "policy/RULES family" - the sixth follow-up's blanket "not
    # explicitly named, so drop it" reasoning wrongly swept up a rules-
    # family inflection alongside the (correctly dropped)
    # retningslinjene/riktlinjerna guideline-family definite forms.
    # Restored here, narrowly: only the definite plural of "regel" itself,
    # not the guideline-family "retningslinje"/"riktlinje" family, which
    # stays dropped.
    "no": (
        "regel", "regler", "reglene",  # original F1 set + restored rules-family definite plural (retningslinje/retningslinjer/retningslinjene stay dropped - guideline family)
        "vilkår og betingelser", "salgsbetingelser",  # compound "terms and conditions" phrases
    ),
    "da": (
        "regel", "regler", "reglerne",  # original F1 set + restored rules-family definite plural (retningslinje/retningslinjer/retningslinjerne stay dropped - guideline family)
        "vilkår og betingelser", "salgsbetingelser",  # compound "terms and conditions" phrases
    ),
    "sv": (
        "regel", "regler", "reglerna",  # original F1 set + restored rules-family definite plural (riktlinje/riktlinjer/riktlinjerna stay dropped - guideline family)
        "allmänna villkor",  # compound "terms and conditions" phrase
    ),
    "ru": (
        "политика", "политики", "правило", "правила",  # original F1 set
        "политике", "политику", "политикой",  # kept: oblique cases of политика (coordinator's explicit exception)
        "правилам", "правилами", "правилах",  # kept: oblique cases of правила (coordinator's explicit exception)
        "условия использования", "условия продажи",  # compound "terms and conditions" phrases
    ),
    # Seventh follow-up: "pravilima"/"правилима" (dative/instrumental
    # plural of "pravila" = rules) restored, narrowly, for the same
    # rules-family reason as no/da/sv "reglene" above - the coordinator's
    # instruction was to restore only the pravila/правила oblique forms if
    # they were rules-family, leaving everything else (politika/политика's
    # own oblique forms, the uslov/услова condition-family forms) dropped.
    "sr": (
        "politika", "politike", "pravilo", "pravila", "политика", "правило", "правила",  # original F1 set
        "pravilima", "правилима",  # restored: rules-family oblique plural (Latin and Cyrillic)
    ),
}
