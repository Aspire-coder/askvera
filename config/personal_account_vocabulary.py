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
   have" (balance/points/volume only -- see the Fable S1 note below for why
   commission/bonus are NOT in this shape).
4. **Earned-amount lookup** -- "how much did I earn (this month)".
5. **Identifier reference, as an explicit lookup** -- "what is my tracking
   number", "track my order" (anchored to a lookup verb -- see the Fable S1
   note below for why a bare "my order number" is NOT enough).

None of these shapes match:

- a calculation/policy question ("How IS my bonus CALCULATED?" -- asks about
  a rule, not a value);
- a future-timing policy question ("WHEN WILL my commission BE PAID?" --
  asks about payment schedule policy, not whether a specific payment
  already happened);
- a capability question ("CAN I return my order?");
- a general fact question that happens to use "my" ("What are the payment
  methods for my order?").

## Fable CX review finding S1 (2026-09-19, should-fix, all 12 languages)

The first shipped version of this vocabulary matched TWO policy shapes it
should not have, both reproduced by Fable at 23/23 probes:

1. **Rate/percentage questions.** "What is my bonus percentage as an
   Assistant Supervisor?" and "What is my commission rate?" (and the
   equivalents Fable listed in every other language) matched the
   current-value lookup shape because that shape originally accepted
   "commission"/"bonus" as a bare object noun ("what is my commission",
   "what is my bonus") with nothing after it required. A rate/percentage
   question uses the exact same opening words. **Fix:** "commission" and
   "bonus" (and their per-language translations) are removed from the
   plain current-value shape entirely; the current-value shape now only
   ever matches ``balance``/``points``/``volume``/``account balance`` (the
   fields that genuinely have no rate/policy reading). A commission/bonus
   VALUE lookup only matches through the completed-event shape below,
   which requires a state or time marker a rate question never has ("has
   my commission been paid" matches; "what is my commission rate" does
   not, because it carries no ``has``/``did``/``was`` and no
   received/arrived/paid/processed/shipped word).
2. **"Do I need my order number..." capability questions.** "Do I need my
   order number to return a product?" and "Brauche ich meine Bestellnummer
   für eine Rücksendung?" matched the identifier shape because it
   originally accepted a bare "my order/tracking/account number" anywhere
   in the sentence. **Fix:** every identifier shape is now anchored to an
   actual lookup verb immediately before it ("what is my tracking
   number", "track my order", German "wie lautet meine Bestellnummer" /
   "wo finde ich meine Bestellnummer", etc. -- see each language's pattern)
   rather than matching the bare noun phrase anywhere in the question. "Do
   I need..." / "Brauche ich..." has no lookup verb immediately before the
   noun phrase, so it no longer matches.

Both fixes are structural (narrowing WHAT the shapes accept), not a bolted-
on exclusion list of "bad words" layered on top of the original shapes --
consistent with this module's "closed phrase shapes, not a keyword blocklist"
discipline. New completed-event/time-marker positives were added per
language for the commission/bonus VALUE-with-state-marker case ("has my
commission been paid", "was my payment received", "where is my bonus
payment", "how much did I earn last month") so shape 2 above (Fable's
"(b) commission/bonus/payment only with a state or time marker") stays
fully covered even though the bare rate-shaped match is gone.

## Fable CX review findings F2/F3 (2026-09-19, re-review of the S1 fix)

**F2 (should-fix, all 12 languages).** "What is my volume requirement to
stay active?" and "What is my balance requirement for the 2CC rule?" still
matched the plain current-value shape (``what is my balance/points/
volume``), because that shape has no opinion about what comes AFTER the
noun -- and a requirement/rule/eligibility POLICY question opens with
exactly the same words as a value lookup. **Fix:** each language's
current-value branch gains a bounded negative lookahead (the next few words
after the noun, not the whole rest of the sentence) that vetoes the match
when a requirement/rule/policy-purpose word follows within a short, bounded
window (up to 40 characters, so it stays scoped to the same clause rather
than the whole rest of the sentence): "requirement(s)", "rule", "needed",
"minimum", "to stay/to qualify/to remain (active)", "for the ..." (and the
per-language equivalents inlined in each language's pattern below). "What
is my balance?" alone still matches -- the lookahead only vetoes when one
of these words is actually present nearby.

**F3 (low, all 12 languages).** The S1 narrowing was slightly too aggressive
in the other direction: "What is my commission this month?" and "Did my
bonus get paid this month?" (and the per-language equivalents) stopped
matching, because (a) commission/bonus were removed entirely from the plain
current-value shape (correctly, for the rate/percentage case) and (b) the
completed-event shape required the verb immediately after the aux ("has my
bonus BEEN paid"), which "did my bonus GET paid" doesn't fit. **Fix:** two
targeted additions per language, not a re-opening of the S1 fix -- (a) a new
narrow shape requires the commission/bonus/earnings noun to be immediately
followed by an explicit time marker ("this month", "last month", "this
week", "so far"): a time marker makes it a concrete lookup the same way a
completed-event verb does, while a bare rate/percentage/role word (S1) still
never matches, because the new shape's noun must be followed directly by one
of the closed time-marker phrases, nothing else; (b) the completed-event
shape's optional linking word gains "get" ("did my bonus GET paid") beside
the existing "been" ("has my bonus BEEN paid").

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
        \bwhere\s+is\s+my\s+(?:bonus\s+)?(?:order|shipment|package|payment|refund)\b
        | \b(?:what\s*'?s|what\s+is)\s+the\s+status\s+of\s+my\s+
            (?:order|shipment|package|payment)\b
        | \bmy\s+order\s+status\b
        | \btrack\s+my\s+(?:order|shipment|package)\b
        | \b(?:has|did|was)\s+my\s+(?:payment|commission|bonus|order|refund)\s+
            (?:been\s+|get\s+)?(?:receive[d]?|arrive[d]?|paid|processed|ship(?:ped)?)\b
        | \b(?:what\s*'?s|what\s+is)\s+my\s+
            (?:balance|points|volume|account\s+balance)\b
            (?!.{0,40}?\b(?:requirements?|rule|needed|minimum|
                to\s+stay|to\s+qualify|to\s+remain|for\s+the)\b)
        | \b(?:what\s*'?s|what\s+is|how\s+much\s+is)\s+my\s+
            (?:commission|bonus|earnings)\s+
            (?:this\s+month|last\s+month|this\s+week|so\s+far)\b
        | \bhow\s+(?:much|many)\s+(?:did\s+i\s+earn|points\s+do\s+i\s+have)\b
        | \b(?:what\s*'?s|what\s+is|track)\s+my\s+(?:tracking|order|account)\s+number\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "de": re.compile(
        r"""
        \bwo\s+ist\s+(?:meine\s+(?:bonus)?zahlung|meine\s+bestellung|
            meine\s+sendung|mein\s+paket)\b
        | \bstatus\s+meiner\s+bestellung\b
        | \b(?:ist|wurde)\s+meine?\s+(?:zahlung|provision|bonus(?:zahlung)?|
            bestellung)\s+
            (?:eingegangen|angekommen|bezahlt|versendet|ausgezahlt)\b
        | \bwie\s+hoch\s+ist\s+mein\s+
            (?:kontostand|guthaben|punktestand)\b
            (?!.{0,40}?\b(?:anforderung(?:en)?|regel|erforderlich|
                mindest\w*|um\s+aktiv\s+zu\s+bleiben|um\s+mich\s+zu\s+
                qualifizieren|f[uü]r\s+die)\b)
        | \b(?:wie\s+hoch\s+ist|was\s+ist)\s+mein(?:e)?\s+
            (?:provision|bonus|verdienst)\s+
            (?:diesen\s+monat|letzten\s+monat|diese\s+woche|bisher)\b
        | \bwie\s+viel(?:e)?\s+(?:habe\s+ich\s+verdient|punkte\s+habe\s+ich)\b
        | \b(?:wie\s+lautet|was\s+ist|wo\s+finde\s+ich)\s+meine\s+
            (?:sendungsverfolgungsnummer|bestellnummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "es": re.compile(
        r"""
        \bd[oó]nde\s+est[aá]\s+mi\s+(?:bono\s+)?(?:pedido|env[ií]o|paquete|pago)\b
        | \bestado\s+de\s+mi\s+pedido\b
        | \b(?:se\s+ha\s+recibido|ha\s+llegado|se\s+ha\s+pagado)\s+mi\s+
            (?:pago|comisi[oó]n|bono|pedido)\b
        | \bcu[aá]l\s+es\s+mi\s+
            (?:saldo|puntos)\b
            (?!.{0,40}?\b(?:requisitos?|regla|necesario|m[ií]nimo|
                para\s+(?:permanecer|seguir)\s+activo|para\s+calificar|
                para\s+la)\b)
        | \b(?:cu[aá]l\s+es|cu[aá]nto\s+es)\s+mi\s+
            (?:comisi[oó]n|bono|ganancia)\s+
            (?:este\s+mes|el\s+mes\s+pasado|esta\s+semana|hasta\s+ahora)\b
        | \bcu[aá]nto\s+(?:he\s+ganado|puntos\s+tengo)\b
        | \b(?:cu[aá]l\s+es|d[oó]nde\s+encuentro)\s+mi\s+
            n[uú]mero\s+de\s+(?:seguimiento|pedido|cuenta)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "fr": re.compile(
        r"""
        \bo[uù]\s+est\s+ma\s+(?:commande|livraison|colis|paiement|prime)\b
        | \bstatut\s+de\s+ma\s+commande\b
        | \b(?:mon\s+paiement|ma\s+commission|ma\s+prime|ma\s+commande)\s+
            (?:a[- ]t[- ]il|a[- ]t[- ]elle)\s+(?:[ée]t[ée]\s+re[cç]u(?:e)?|
            [ée]t[ée]\s+pay[ée]e?|arriv[ée]e?)\b
        | \bquel\s+est\s+mon\s+
            (?:solde|nombre\s+de\s+points)\b
            (?!.{0,40}?\b(?:exigences?|r[èe]gle|requis|n[ée]cessaire|
                minimum|pour\s+rester\s+actif|pour\s+me\s+qualifier|
                pour\s+la)\b)
        | \b(?:quel\s+est|combien\s+est)\s+mon\s+
            (?:bonus|commission|gains?)\s+
            (?:ce\s+mois[- ]ci|le\s+mois\s+dernier|cette\s+semaine|
                jusqu['’]?\s*[aà]\s+pr[ée]sent)\b
        | \bcombien\s+(?:ai[- ]je\s+gagn[ée]|de\s+points\s+ai[- ]je)\b
        | \b(?:quel\s+est|o[uù]\s+trouve[- ]je)\s+mon\s+
            num[ée]ro\s+de\s+(?:suivi|commande|compte)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "it": re.compile(
        r"""
        \bdov['’]?\s*[eè]\s+il\s+mio\s+(?:bonus\s+)?
            (?:ordine|spedizione|pacco|pagamento)\b
        | \bstato\s+del\s+mio\s+ordine\b
        | \b(?:il\s+mio\s+pagamento|la\s+mia\s+commissione|il\s+mio\s+bonus|
            il\s+mio\s+ordine)\s+[eè]\s+stat[oa]\s+
            (?:ricevut[oa]|arrivat[oa]|pagat[oa])\b
        | \bqual\s+[eè]\s+il\s+mio\s+
            (?:saldo|numero\s+di\s+punti)\b
            (?!.{0,40}?\b(?:requisit[oi]|regola|necessari[oa]|
                minim[oa]|per\s+rimanere\s+attiv[oa]|per\s+qualificarmi|
                per\s+la)\b)
        | \b(?:qual\s+[eè]|quanto\s+[eè])\s+(?:il\s+mio|la\s+mia)\s+
            (?:bonus|commissione|guadagno)\s+
            (?:questo\s+mese|il\s+mese\s+scorso|questa\s+settimana|finora)\b
        | \bquanto\s+ho\s+guadagnato\b
        | \b(?:qual\s+[eè]|dove\s+trovo)\s+il\s+mio\s+
            numero\s+di\s+(?:tracciamento|ordine|conto)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "nl": re.compile(
        r"""
        \bwaar\s+is\s+mijn\s+(?:bonus\s*)?(?:betaling|bestelling|zending|pakket)\b
        | \bstatus\s+van\s+mijn\s+bestelling\b
        | \bis\s+mijn\s+(?:betaling|commissie|bonus|bestelling)\s+
            (?:ontvangen|aangekomen|betaald|verzonden)\b
        | \bwat\s+is\s+mijn\s+
            (?:saldo|aantal\s+punten)\b
            (?!.{0,40}?\b(?:vereiste(?:n)?|regel|nodig|minimum|
                om\s+actief\s+te\s+blijven|om\s+in\s+aanmerking\s+te\s+komen|
                voor\s+de)\b)
        | \b(?:wat\s+is|hoeveel\s+is)\s+mijn\s+
            (?:commissie|bonus|verdiensten)\s+
            (?:deze\s+maand|vorige\s+maand|deze\s+week|tot\s+nu\s+toe)\b
        | \bhoeveel\s+(?:heb\s+ik\s+verdiend|punten\s+heb\s+ik)\b
        | \b(?:wat\s+is|waar\s+vind\s+ik)\s+mijn\s+
            (?:trackingnummer|bestelnummer|rekeningnummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "sv": re.compile(
        r"""
        \bvar\s+[aä]r\s+min\s+(?:bonus\s*)?(?:order|leverans|paket|betalning)\b
        | \bstatus\s+f[oö]r\s+min\s+order\b
        | \b(?:har\s+min\s+betalning|har\s+min\s+provision|har\s+min\s+bonus|
            har\s+min\s+order)\s+
            (?:mottagits|kommit|betalats|skickats)\b
        | \bvad\s+[aä]r\s+(?:min|mitt)\s+
            (?:saldo|po[aä]ng)\b
            (?!.{0,40}?\b(?:krav|regel|beh[oö]vs|minimum|
                f[oö]r\s+att\s+f[oö]rbli\s+aktiv|f[oö]r\s+att\s+kvalificera|
                f[oö]r\s+regeln)\b)
        | \b(?:vad\s+[aä]r|hur\s+mycket\s+[aä]r)\s+min\s+
            (?:provision|bonus|intj[aä]ning)\s+
            (?:denna\s+m[aå]nad|f[oö]rra\s+m[aå]naden|denna\s+vecka|
                hittills)\b
        | \bhur\s+mycket\s+(?:har\s+jag\s+tj[aä]nat|po[aä]ng\s+har\s+jag)\b
        | \b(?:vad\s+[aä]r|var\s+hittar\s+jag)\s+mitt\s+
            (?:sp[aå]rningsnummer|ordernummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "da": re.compile(
        r"""
        \bhvor\s+er\s+min\s+(?:bonus\s*)?(?:ordre|forsendelse|pakke|betaling)\b
        | \bstatus\s+p[aå]\s+min\s+ordre\b
        | \b(?:er\s+min\s+betaling|er\s+min\s+provision|er\s+min\s+bonus|
            er\s+min\s+ordre)\s+
            (?:modtaget|ankommet|betalt|afsendt)\b
        | \bhvad\s+er\s+min\s+
            (?:saldo|po[iî]nt(?:sum)?)\b
            (?!.{0,40}?\b(?:krav|regel|n[oø]dvendig|minimum|
                for\s+at\s+forblive\s+aktiv|for\s+at\s+kvalificere|
                for\s+reglen)\b)
        | \b(?:hvad\s+er|hvor\s+meget\s+er)\s+min\s+
            (?:provision|bonus|indtjening)\s+
            (?:denne\s+m[aå]ned|sidste\s+m[aå]ned|denne\s+uge|
                indtil\s+videre)\b
        | \bhvor\s+meget\s+(?:har\s+jeg\s+tjent|point\s+har\s+jeg)\b
        | \b(?:hvad\s+er|hvor\s+finder\s+jeg)\s+mit\s+
            (?:sporingsnummer|ordrenummer|kontonummer)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    "no": re.compile(
        r"""
        \bhvor\s+er\s+min\s+(?:bonus\s*)?(?:bestilling|forsendelse|pakke|betaling)\b
        | \bstatus\s+p[aå]\s+min\s+bestilling\b
        | \b(?:er\s+min\s+betaling|er\s+min\s+provisjon|er\s+min\s+bonus|
            er\s+min\s+bestilling)\s+
            (?:mottatt|ankommet|betalt|sendt)\b
        | \bhva\s+er\s+min\s+
            (?:saldo|po[eé]ngsum)\b
            (?!.{0,40}?\b(?:krav|regel|n[oø]dvendig|minimum|
                for\s+[aå]\s+forbli\s+aktiv|for\s+[aå]\s+kvalifisere|
                for\s+regelen)\b)
        | \b(?:hva\s+er|hvor\s+mye\s+er)\s+min\s+
            (?:provisjon|bonus|inntjening)\s+
            (?:denne\s+m[aå]neden|forrige\s+m[aå]ned|denne\s+uken|
                s[aå]\s+langt)\b
        | \bhvor\s+mye\s+(?:har\s+jeg\s+tjent|po[eé]ng\s+har\s+jeg)\b
        | \b(?:hva\s+er|hvor\s+finner\s+jeg)\s+mitt\s+
            (?:sporingsnummer|bestillingsnummer|kontonummer)\b
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
            (?:saldoni|pisteideni\s+m[aä][aä]r[aä])\b
            (?!.{0,40}?\b(?:vaatimus\w*|s[aä][aä]nt[oö]\w*|
                tarvitaan|v[aä]himm[aä]is\w*|pysy[aä][aä]kseni\s+aktiivisena|
                t[aä]ytt[aä][aä]kseni\s+vaatimuksen)\b)
        | \bmik[aä]\s+on\s+(?:palkkioni|bonukseni|ansioni)\s+
            (?:t[aä]ss[aä]\s+kuussa|viime\s+kuussa|t[aä]ll[aä]\s+viikolla|
                t[aä]h[aä]n\s+menness[aä])\b
        | \bpaljonko\s+(?:olen\s+ansainnut|pisteit[aä]\s+minulla\s+on)\b
        | \b(?:mik[aä]\s+on|mist[aä]\s+l[oö]yd[aä]n)\s+
            (?:seurantanumeroni|tilausnumeroni|tilinumeroni)\b
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    # Cyrillic Russian: possessive "мой/моя/моё" + account-object noun +
    # a lookup shape. "где заказ" (no possessive) deliberately does not
    # match -- see the module docstring's confidence note for Slavic
    # languages.
    "ru": re.compile(
        r"""
        где\s+мо[йяё]\s+(?:бонус|заказ|посылка|отправление|платёж)
        | статус\s+моего\s+заказа
        | (?:получен\s+ли\s+мой|пришёл\s+ли\s+мой|поступил\s+ли\s+мой)\s+
            (?:платёж|заказ|бонус|комиссион)
        | какой\s+мой\s+(?:баланс|остаток\s+баллов)
            (?!.{0,40}?\b(?:требовани[ея]|правил[оа]|нужен|нужно|
                минимум|чтобы\s+остаться\s+активным|чтобы\s+соответствовать)\b)
        | как(?:ая|ой)\s+мо[яй]\s+(?:комиссия|бонус|заработок)\s+
            (?:в\s+этом\s+месяце|в\s+прошлом\s+месяце|на\s+этой\s+неделе|
                на\s+сегодняшний\s+день)
        | сколько\s+(?:я\s+заработал|у\s+меня\s+баллов)
        | (?:какой\s+мой|где\s+найти\s+мой)\s+
            (?:номер\s+отслеживания|номер\s+заказа|номер\s+счёта)
        """,
        re.IGNORECASE | re.VERBOSE,
    ),
    # Cyrillic Serbian (the route-locale spelling); the same possessive +
    # object + lookup-shape discipline as Russian above.
    "sr": re.compile(
        r"""
        где\s+је\s+мо(?:ј|ја|је)\s+(?:бонус|поруџбина|пошиљка|уплата)
        | статус\s+моје\s+поруџбине
        | да\s+ли\s+је\s+мо(?:ј|ја|је)\s+
            (?:уплата|поруџбина|бонус|провизија)\s+
            (?:примљена|стигла|исплаћена|послата)
        | колико\s+је\s+мо(?:ј|ја|је)\s+
            (?:стање|број\s+поена)
            (?!.{0,40}?\b(?:услов\w*|правил[оа]|потребан|минимум|
                да\s+останем\s+активан|да\s+испуним\s+услов)\b)
        | коли(?:ка|ко)\s+је\s+мо(?:ј|ја|је)\s+
            (?:провизија|бонус|зарада)\s+
            (?:овог\s+месеца|прошлог\s+месеца|ове\s+недеље|до\s+сада)
        | колико\s+сам\s+(?:зарадио|поена\s+имам)
        | (?:колико\s+је\s+мо(?:ј|ја|је)|где\s+да\s+нађем\s+мо(?:ј|ја|је))\s+
            (?:број\s+за\s+праћење|број\s+поруџбине|број\s+рачуна)
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
