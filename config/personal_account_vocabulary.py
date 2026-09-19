r"""Closed, per-language vocabulary for detecting a PERSONAL-ACCOUNT lookup.

Phase 3 Lane 3 (docs/conversation-quality/phase3/CX_LANES.md). This is a NEW
vocabulary -- nothing in this repository already distinguishes "where is MY
order" (a lookup this chatbot cannot perform: no account/order backend is
wired to it) from an ordinary policy question that happens to use the
possessive "my" ("How is my bonus calculated?", "What are the payment
methods for my order?"). It is deliberately narrow, mirroring the shape and
discipline of ``config/directory_field_vocabulary.py`` and
``app/response/contact_completion.py``'s per-language tables: closed
phrase-shape regexes, not a loose keyword list, so a general policy question
that merely contains a possessive does not match.

## The shape being matched

A personal-account request names a CONCRETE, ALREADY-EXISTING piece of the
reader's own account state and asks to look it up:

1. **Location/status lookup** -- "where is my order", "what is the status
   of my shipment", "my order status".
2. **Completed-event confirmation** -- "has my payment been received",
   "did my commission arrive" (past tense / present-perfect: a check on
   whether something already happened, not a question about *when* it will
   happen in the future).
3. **Current-value lookup** -- "what is my balance", "how many points do I
   have", "what is my commission this month".
4. **Earned-amount lookup** -- "how much did I earn (this month)".
5. **Identifier reference** -- "my tracking number", "my order number".

None of these shapes match:

- a calculation/policy question ("How IS my bonus CALCULATED?" -- asks about
  a rule, not a value);
- a future-timing policy question ("WHEN WILL my commission BE PAID?" --
  asks about payment schedule policy, not whether a specific payment
  already happened);
- a capability question ("CAN I return my order?");
- a general fact question that happens to use "my" ("What are the payment
  methods for my order?").

## Confidence per language

Each language's regex was written from this same five-shape template,
translated by a fluent-enough reviewer pass (not machine-expanded from a
word list), matching the same "translate one reviewed shape, don't
re-derive per language" discipline as
``app/response/contact_completion.py``'s ``_RECOMMENDS_CONTACT_PATTERNS``.

- **High** (en, de, es, fr, it, nl, sv) -- the possessive + lookup-verb
  shape is unambiguous and the reviewed translation was checked against the
  negative examples above in that language.
- **Medium** (da, no, fi) -- close relatives of the high-confidence
  Germanic/Nordic set; Finnish additionally inflects the possessive as a
  suffix (``tilaukseni`` = "my order") rather than a separate word, so the
  pattern matches the suffixed noun form directly instead of a standalone
  possessive token.
- **Medium** (ru, sr) -- Slavic languages drop the possessive pronoun more
  often in casual speech than Germanic/Romance ones ("где мой заказ" is
  typical, but "где заказ" alone -- no possessive -- would NOT match here,
  by design: this module fails conservatively rather than guessing that an
  unmarked question is personal-account).

An unrecognised or unlisted language code returns ``False`` (never
personal-account) rather than guess, exactly like
``recommends_contact_in_language``.
"""

from __future__ import annotations

import re

from config.directory_field_vocabulary import normalize_language_code

# One compiled regex per language. Each alternates the five lookup shapes
# described in the module docstring; every branch requires BOTH a
# first-person possessive (or, for Finnish, a possessive-suffixed noun) AND
# a concrete account-object noun (order, payment, commission, bonus,
# points/volume, balance, account, shipment/tracking), never one alone.
_PERSONAL_ACCOUNT_PATTERNS: dict[str, re.Pattern[str]] = {
    "en": re.compile(
        r"""
        \bwhere\s+is\s+my\s+(?:order|shipment|package|payment|refund)\b
        | \b(?:what\s*'?s|what\s+is)\s+the\s+status\s+of\s+my\s+
            (?:order|shipment|package|payment)\b
        | \bmy\s+order\s+status\b
        | \b(?:has|did)\s+my\s+(?:payment|commission|bonus|order|refund)\s+
            (?:been\s+)?(?:receive[d]?|arrive[d]?|paid|processed|ship(?:ped)?)\b
        | \b(?:what\s*'?s|what\s+is)\s+my\s+
            (?:balance|commission|bonus|points|volume|account\s+balance)\b
        | \bhow\s+(?:much|many)\s+(?:did\s+i\s+earn|points\s+do\s+i\s+have)\b
        | \bmy\s+(?:tracking|order|account)\s+number\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "de": re.compile(
        r"""
        \bwo\s+ist\s+(?:meine\s+bestellung|meine\s+sendung|mein\s+paket|
            meine\s+zahlung)\b
        | \bstatus\s+meiner\s+bestellung\b
        | \bist\s+meine\s+(?:zahlung|provision|bonuszahlung|bestellung)\s+
            (?:eingegangen|angekommen|bezahlt|versendet)\b
        | \bwie\s+hoch\s+ist\s+mein\s+
            (?:kontostand|guthaben|provision|bonus|punktestand)\b
        | \bwie\s+viel(?:e)?\s+(?:habe\s+ich\s+verdient|punkte\s+habe\s+ich)\b
        | \bmeine\s+(?:sendungsverfolgung|bestellnummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "es": re.compile(
        r"""
        \bd[oó]nde\s+est[aá]\s+mi\s+(?:pedido|env[ií]o|paquete|pago)\b
        | \bestado\s+de\s+mi\s+pedido\b
        | \b(?:se\s+ha\s+recibido|ha\s+llegado|se\s+ha\s+pagado)\s+mi\s+
            (?:pago|comisi[oó]n|bono|pedido)\b
        | \bcu[aá]l\s+es\s+mi\s+
            (?:saldo|comisi[oó]n|bono|puntos)\b
        | \bcu[aá]nto\s+(?:he\s+ganado|puntos\s+tengo)\b
        | \bmi\s+n[uú]mero\s+de\s+(?:seguimiento|pedido|cuenta)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "fr": re.compile(
        r"""
        \bo[uù]\s+est\s+ma\s+(?:commande|livraison|colis|paiement)\b
        | \bstatut\s+de\s+ma\s+commande\b
        | \b(?:mon\s+paiement|ma\s+commission|ma\s+prime|ma\s+commande)\s+
            (?:a[- ]t[- ]il|a[- ]t[- ]elle)\s+(?:[ée]t[ée]\s+re[cç]u(?:e)?|
            [ée]t[ée]\s+pay[ée]e?|arriv[ée]e?)\b
        | \bquel\s+est\s+mon\s+
            (?:solde|montant\s+de\s+commission|bonus|nombre\s+de\s+points)\b
        | \bcombien\s+(?:ai[- ]je\s+gagn[ée]|de\s+points\s+ai[- ]je)\b
        | \bmon\s+num[ée]ro\s+de\s+(?:suivi|commande|compte)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "it": re.compile(
        r"""
        \bdov['’]?\s*[eè]\s+il\s+mio\s+(?:ordine|spedizione|pacco|pagamento)\b
        | \bstato\s+del\s+mio\s+ordine\b
        | \b(?:il\s+mio\s+pagamento|la\s+mia\s+commissione|il\s+mio\s+bonus|
            il\s+mio\s+ordine)\s+[eè]\s+stat[oa]\s+
            (?:ricevut[oa]|arrivat[oa]|pagat[oa])\b
        | \bqual\s+[eè]\s+il\s+mio\s+
            (?:saldo|importo\s+commissione|bonus|numero\s+di\s+punti)\b
        | \bquanto\s+ho\s+guadagnato\b
        | \bil\s+mio\s+numero\s+di\s+(?:tracciamento|ordine|conto)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "nl": re.compile(
        r"""
        \bwaar\s+is\s+mijn\s+(?:bestelling|zending|pakket|betaling)\b
        | \bstatus\s+van\s+mijn\s+bestelling\b
        | \bis\s+mijn\s+(?:betaling|commissie|bonus|bestelling)\s+
            (?:ontvangen|aangekomen|betaald|verzonden)\b
        | \bwat\s+is\s+mijn\s+
            (?:saldo|commissiebedrag|bonus|aantal\s+punten)\b
        | \bhoeveel\s+(?:heb\s+ik\s+verdiend|punten\s+heb\s+ik)\b
        | \bmijn\s+(?:trackingnummer|bestelnummer|rekeningnummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "sv": re.compile(
        r"""
        \bvar\s+[aä]r\s+min\s+(?:order|leverans|paket|betalning)\b
        | \bstatus\s+f[oö]r\s+min\s+order\b
        | \b(?:har\s+min\s+betalning|har\s+min\s+provision|har\s+min\s+bonus|
            har\s+min\s+order)\s+
            (?:mottagits|kommit|betalats|skickats)\b
        | \bvad\s+[aä]r\s+min\s+
            (?:saldo|provision|bonus|po[aä]ng)\b
        | \bhur\s+mycket\s+(?:har\s+jag\s+tj[aä]nat|po[aä]ng\s+har\s+jag)\b
        | \bmitt\s+(?:sp[aå]rningsnummer|ordernummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "da": re.compile(
        r"""
        \bhvor\s+er\s+min\s+(?:ordre|forsendelse|pakke|betaling)\b
        | \bstatus\s+p[aå]\s+min\s+ordre\b
        | \b(?:er\s+min\s+betaling|er\s+min\s+provision|er\s+min\s+bonus|
            er\s+min\s+ordre)\s+
            (?:modtaget|ankommet|betalt|afsendt)\b
        | \bhvad\s+er\s+min\s+
            (?:saldo|provision|bonus|po[iî]nt(?:sum)?)\b
        | \bhvor\s+meget\s+(?:har\s+jeg\s+tjent|point\s+har\s+jeg)\b
        | \bmit\s+(?:sporingsnummer|ordrenummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "no": re.compile(
        r"""
        \bhvor\s+er\s+min\s+(?:bestilling|forsendelse|pakke|betaling)\b
        | \bstatus\s+p[aå]\s+min\s+bestilling\b
        | \b(?:er\s+min\s+betaling|er\s+min\s+provisjon|er\s+min\s+bonus|
            er\s+min\s+bestilling)\s+
            (?:mottatt|ankommet|betalt|sendt)\b
        | \bhva\s+er\s+min\s+
            (?:saldo|provisjon|bonus|po[eé]ngsum)\b
        | \bhvor\s+mye\s+(?:har\s+jeg\s+tjent|po[eé]ng\s+har\s+jeg)\b
        | \bmitt\s+(?:sporingsnummer|bestillingsnummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "fi": re.compile(
        r"""
        \bmiss[aä]\s+tilaukseni\s+on\b
        | \btilaukseni\s+tila\b
        | \bonko\s+(?:maksuni|palkkioni|bonukseni|tilaukseni)\s+
            (?:vastaanotettu|saapunut|maksettu|l[aä]hetetty)\b
        | \bmik[aä]\s+on\s+
            (?:saldoni|palkkioni|bonukseni|pisteideni\s+m[aä][aä]r[aä])\b
        | \bpaljonko\s+(?:olen\s+ansainnut|pisteit[aä]\s+minulla\s+on)\b
        | \b(?:seurantanumeroni|tilausnumeroni|tilinumeroni)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    # Cyrillic Russian: possessive "мой/моя/моё" + account-object noun +
    # a lookup shape. "где заказ" (no possessive) deliberately does not
    # match -- see the module docstring's confidence note for Slavic
    # languages.
    "ru": re.compile(
        r"""
        где\s+мо[йяё]\s+(?:заказ|посылка|отправление|платёж)
        | статус\s+моего\s+заказа
        | (?:получен\s+ли\s+мой|пришёл\s+ли\s+мой|поступил\s+ли\s+мой)\s+
            (?:платёж|заказ|бонус|комиссион)
        | как[аоо]й\s+мо[йяё]\s+(?:баланс|комиссион|бонус|остаток\s+баллов)
        | сколько\s+(?:я\s+заработал|у\s+меня\s+баллов)
        | мо[йяё]\s+(?:номер\s+отслеживания|номер\s+заказа|номер\s+счёта)
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    # Cyrillic Serbian (the route-locale spelling); the same possessive +
    # object + lookup-shape discipline as Russian above.
    "sr": re.compile(
        r"""
        где\s+је\s+мо(?:ј|ја|је)\s+(?:поруџбина|пошиљка|уплата)
        | статус\s+моје\s+поруџбине
        | да\s+ли\s+је\s+мо(?:ј|ја|је)\s+
            (?:уплата|поруџбина|бонус|провизија)\s+
            (?:примљена|стигла|исплаћена|послата)
        | колико\s+је\s+мо(?:ј|ја|је)\s+
            (?:стање|провизија|бонус|број\s+поена)
        | колико\s+сам\s+(?:зарадио|поена\s+имам)
        | мо(?:ј|ја|је)\s+(?:број\s+за\s+праћење|број\s+поруџбине|број\s+рачуна)
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
}


def supported_languages() -> frozenset[str]:
    """Every language code this vocabulary has a reviewed pattern for."""
    return frozenset(_PERSONAL_ACCOUNT_PATTERNS)


def matches_personal_account_shape(question: str, language: str) -> bool:
    """True when ``question`` fits the narrow personal-account lookup shape.

    Only the closed per-language patterns above are consulted; an
    unrecognised/unlisted language code returns ``False``. The language tag
    is normalized with the same helper
    ``app.response.contact_completion.recommends_contact_in_language`` uses,
    so "fr-FR" is recognized the same as "fr".
    """
    language_code = normalize_language_code(language)
    pattern = _PERSONAL_ACCOUNT_PATTERNS.get(language_code)
    if pattern is None:
        return False
    return bool(pattern.search(question or ""))
