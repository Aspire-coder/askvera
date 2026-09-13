"""Income-claim detection for the non-English conversation languages.

IncomeClaimPolicy only understood English: "Can you guarantee I will earn money
if I join?" was refused in English but allowed in fr, es, de, nl, it, da, no,
sv, fi, sr and ru (offline all-markets probe, 2026-09-12), because nothing in a
translated sentence matched the English words "guarantee" and "earn"/"income".

This module mirrors the English rule for da, de, es, fi, fr, it, nl, no, pt,
ru (Cyrillic and Latin transliteration), sr (Latin and Cyrillic) and sv:

1. an unambiguous income-claim phrase ("revenu garanti", "passives
   Einkommen", "гарантированный доход", ...) is refused on its own, like the
   English DENIED_TOPICS income phrases;
2. a guarantee form together with an earnings or money word anywhere in the
   text is refused, like the English guarantee/earnings pairing;
3. consumer guarantees (money-back, satisfaction, refund, replacement, return,
   warranty) are set aside before that pairing - unless an earnings word
   (earn / income / salary / wage, or an amount per month) is anywhere in the
   text, or a money, profit, bonus, commission or currency word sits in the
   same sentence or within six words of it. This is the English W10/W10b
   carve-out.
4. W16b: a product warranty ("La garantía cubre defectos; el dinero se
   devuelve en 30 días.") is one of those consumer guarantees, and refunded
   money is masked as refund wording unless its clause speaks of a recurring
   or multiplied gain ("cada mes", "doppelt", "с процентами"). See _WARRANTY.

There is no negation exemption, exactly as in English: "there is no guaranteed
income" is refused in every language.

Every language is checked on every text; the message language field is not
consulted (the English policy does not branch on it either), so the word lists
must stay unambiguous across languages. Text is case-folded and accent-folded
first ("garantía"/"garantia", "ё"/"е"); patterns are written in folded form,
except that ä, ö, ü, å, ø also accept their ASCII spellings ("zurück" matches
"zuruck" and "zurueck").
"""

from __future__ import annotations

import re
import unicodedata

# Letters that do not decompose under NFKD, plus dashes, apostrophes and spaces.
_LETTER_FOLDS = str.maketrans({
    "ß": "ss", "ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ł": "l", "ı": "i",
    "’": "'", "‘": "'", "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    " ": " ", " ": " ",
})
# In patterns only: a letter with a mark also accepts its ASCII transcription.
_PATTERN_DIGRAPHS = {"ä": "(?:ae|a)", "ö": "(?:oe|o)", "ü": "(?:ue|u)", "ø": "(?:oe|o)", "å": "(?:aa|a)"}


def fold(text: str) -> str:
    """Case-fold, strip accents and normalise dashes, apostrophes and spaces."""
    folded = unicodedata.normalize("NFKD", (text or "").casefold().translate(_LETTER_FOLDS))
    return "".join(char for char in folded if not unicodedata.combining(char))


def _fold_pattern(pattern: str) -> str:
    """Fold a pattern written with natural spelling; regex syntax is ASCII and unaffected."""
    for letter, alternation in _PATTERN_DIGRAPHS.items():
        pattern = pattern.replace(letter, alternation)
    folded = unicodedata.normalize("NFKD", pattern.translate(_LETTER_FOLDS))
    return "".join(char for char in folded if not unicodedata.combining(char))


# Amount per period ("2 000 € par mois", "20 000 kr i månaden", "100 000 рублей в месяц").
_CURRENCY = (
    r"[€$£]|kr\.?|sek|nok|dkk|eur|usd|rsd|rub|chf|euro\w*|dollar\w*|franc\w*|dinar\w*|kron\w*|reais"
    r"|rubl\w*|evr\w*|евро|руб\w*|долл\w*|динар\w*"
)
_PERIOD = (
    r"mois|mensuel\w*|mensual\w*|mensal\w*|monat\w*|maand\w*|mese|mensil\w*|manad\w*|maned\w*"
    r"|kuukau\w*|kuussa|месяц\w*|ежемесячн\w*|mesec\w*|месец\w*|месечн\w*|semaine|semana|woche\w*|week"
    r"|settimana|vecka|uge|uke|viiko\w*|недел\w*|nedelj\w*|недељ\w*"
)
_AMOUNT = r"\d[\d\s.,']*"
AMOUNT_PER_PERIOD = (
    rf"{_AMOUNT}\s*(?:{_CURRENCY})\s*(?:\S+\s+){{0,2}}(?:{_PERIOD}|(?:al|por|cada|el|un)\s+mes)"
    rf"|{_AMOUNT}\s*(?:par|por|al|pro|per|pr\.?|each|hver|ogni|cada|/)\s*(?:le\s+|el\s+|o\s+|il\s+)?"
    rf"(?:{_PERIOD}|mes)"
)

# A consumer guarantee whose refund wording was masked to " refund " (see REFUND).
_REFUND_GUARANTEE = (
    r"\w*garant\w*|\w*garanz\w*|\w*garand\w*|\w*garanc\w*|\w*takuu\w*|\w*гарант\w*|\w*гаранц\w*"
)
# The words between may not cross punctuation, so one refund never absorbs another clause's guarantee.
_SHARED_CONSUMER = [
    rf"(?:{_REFUND_GUARANTEE})[\s-]+(?:[^\s.!?:;]+[\s-]+){{0,3}}refund",
    rf"refund[\s-]+(?:[^\s.!?:;]+[\s-]+){{0,3}}(?:{_REFUND_GUARANTEE})",
    rf"money[\s-]*back[\s-]*(?:{_REFUND_GUARANTEE})",
]

# Per language:
#   guarantee - guarantee forms (verbs, participles, nouns, compounds);
#   earnings  - earn / income / salary / wage: pair with a guarantee and stop
#               every consumer guarantee in the text from being set aside;
#   money     - money / profit words: pair with a guarantee only;
#   nearby    - single words that keep a consumer guarantee in their sentence
#               (money, profit, bonus, commission);
#   consumer  - consumer-protection guarantee shapes that may be set aside;
#   refund    - "get the money back" wording, masked to " refund " before the
#               consumer check so it is neither a nearby money word nor a
#               barrier between a guarantee and its refund;
#   false_friends - look-alikes blanked before the earnings search;
#   phrases   - unambiguous income-claim phrases, refused on their own.
LANGUAGES: dict[str, dict[str, list[str]]] = {
    "fr": {
        "guarantee": [r"garanti\w*", r"garantiss\w*"],
        "earnings": [
            r"revenus?", r"salaires?", r"gains",
            r"gagn(?:e|es|ent|er|ez|ons|erai|eras|era|erons|erez|eront|erais|erait|eriez|erions|eraient"
            r"|ee|ees|ais|ait|aient|ant|iez|ions)",
        ],
        "money": [r"argent", r"fric", r"profits?", r"benefices?"],
        "nearby": [r"argent", r"fric", r"profits?", r"benefices?", r"commissions?", r"bonus", r"primes?"],
        "consumer": [
            r"satisfaite?s?\s+ou\s+rembourse\w*",
            r"garanti\w*\s+(?:(?:de|d'|la|le|les|une|un|votre|vos|notre|nos|leur|leurs|a|du|des|100|%|totale?|"
            r"complete?|entiere?|etre|d'etre)\s*){0,4}(?:rembours\w*|satisf\w*|echange\w*|remplacement\w*|retour\w*"
            r"|conformite|legale?s?|commerciale?s?|constructeur|fabricant|pieces?)",
            r"(?:rembours\w*|satisf\w*|echange\w*|remplacement\w*|retour\w*)\s+(?:\S+\s+){0,3}garanti\w*",
            r"garantie\s+(?:de\s+|d'\s*)?\d+\s+(?:jours|mois|ans?|annees?)",
            r"(?:sous|hors|periode\s+de|delai\s+de|bon\s+de|carte\s+de|extension\s+de)\s+garantie",
            r"garantie\s+(?:sur\s+(?:les\s+|nos\s+|vos\s+|leurs\s+)?|des\s+|du\s+)produits?",
        ],
        "refund": [
            r"(?:rembours|recuper|rend|restitu|redonn|recev|recoi|renvoy)\w*\s+(?:(?:de|l'|le|la|les|votre|vos|"
            r"leur|leurs|son|sa|ses|mon|ma|mes|notre|nos|tout|integralement|entierement|vous|lui|en)\s*){0,4}"
            r"argent",
            r"argent\s+(?:(?:vous|leur|lui|nous|est|sera|seront|sont|etre|soit|serait|integralement|entierement)\s+)"
            r"{0,3}(?:rembourse\w*|rendu\w*|restitue\w*|retourne\w*|recupere\w*)",
        ],
        "false_friends": [
            r"(?:suis|es|est|sommes|etes|sont|etait|etaient|soit|soient|etre|sera|seront|serait|etais|ete|fut)"
            r"\s+revenue?s?",
        ],
        "phrases": [
            r"(?:revenus?|gains?|salaires?|profits?)\s+(?:mensuels?\s+)?garanti\w*",
            r"garanti\w*\s+(?:de\s+|d'\s*|des\s+|un\s+|une\s+|les\s+|vos\s+|votre\s+)?(?:revenus?|gains|salaires?)",
            r"revenus?\s+passifs?", r"liberte\s+financiere", r"devenir\s+riches?", r"s'enrichir",
            r"gagner\s+(?:beaucoup\s+|vite\s+|rapidement\s+|facilement\s+)*(?:d'|de\s+l')\s*argent\s+"
            r"(?:rapidement|facilement|vite)",
            r"argent\s+facile",
            r"combien\s+(?:est-ce\s+que\s+)?(?:je\s+)?(?:vais|peux|pourrai|pourrais|puis)(?:-je)?\s+gagner",
            r"gagn\w*\s+(?:\S+\s+){0,4}par\s+mois",
            r"remplacer\s+(?:mon|ton|votre)\s+salaire",
        ],
    },
    "es": {
        "guarantee": [r"garantiz\w*", r"garantic\w*", r"garantias?"],
        "earnings": [
            r"ingresos", r"ingreso\s+(?:mensual|fijo|pasivo|garantizado|extra|seguro|estable)", r"rentas?",
            # Fable W16 review, Fix C: singular "ingreso" after an article or possessive ("Te garantizamos un
            # ingreso."), unless it is an admission ("El ingreso a la oficina ...").
            r"(?:un|el|tu|su|mi|nuestro|vuestro|este|ese|algun|ningun|cualquier)\s+ingreso"
            r"(?!\s+(?:a|al|en|de|del|para)(?!\w))",
            r"ganancias?", r"salarios?", r"sueldos?",
            r"gan(?:ar|are|aras|ara|aremos|aran|aria|arias|arian|o|a|an|amos|ado|ados|ando|e|en|emos)",
        ],
        "money": [r"dinero", r"lucros?"],
        "nearby": [r"dinero", r"lucros?", r"comision\w*", r"bono\w*", r"bonificacion\w*"],
        "consumer": [
            r"garanti\w*\s+(?:(?:de|del|la|el|una|un|su|sus|tu|nuestra|100|%|total|completa|al|a)\s*){0,4}"
            r"(?:devolucion\w*|reembolso\w*|satisfaccion\w*|reemplazo\w*|sustitucion\w*|cambio\w*|reposicion\w*"
            r"|legal\w*|comercial\w*|fabricante)",
            r"(?:devolucion\w*|reembolso\w*|satisfaccion\w*|satisfech\w*|reemplazo\w*|sustitucion\w*|cambio\w*)\s+"
            r"(?:\S+\s+){0,3}garantiz\w*",
            r"garantia\s+(?:de\s+)?\d+\s+(?:dias|meses|anos?)",
            r"(?:bajo|en|periodo\s+de|plazo\s+de|certificado\s+de)\s+garantia",
            r"garantia\s+(?:(?:de|en|sobre|para)\s+(?:los\s+|nuestros\s+|sus\s+)?)productos?",
            r"productos?\s+(?:\S+\s+){0,2}garantia",
        ],
        "refund": [
            r"(?:devol|devuelv|reembols|recuper|reintegr|regres|recib)\w*\s+(?:(?:el|la|su|sus|tu|tus|todo|nuestro|"
            r"le|les|se|del|de)\s+){0,3}dinero",
            r"dinero\s+(?:(?:le|les|se|sera|es|seria|integramente|completamente|de)\s+){0,3}"
            r"(?:devuelto\w*|reembolsad\w*|reintegrad\w*|vuelta)",
        ],
        "false_friends": [],
        "phrases": [
            r"(?:ingresos?|ganancias?|salario|sueldo|renta)\s+(?:mensual\w*\s+)?garantizad\w*",
            r"garantia\s+de\s+(?:ingresos?|ganancias?|salario|sueldo)",
            r"ingresos?\s+pasivos?", r"libertad\s+financiera",
            r"(?:hacer|volver)(?:se|me|te|nos)\s+ric[oa]s?", r"(?:me|te|se|nos)\s+(?:hare|haras|hara|volvere)\s+ric[oa]s?",
            r"ganar\s+(?:mucho\s+)?dinero\s+(?:rapido|facil\w*)", r"dinero\s+facil",
            r"cuanto\s+(?:dinero\s+)?(?:puedo|voy\s+a|podria|podre)\s+ganar",
            r"gan\w*\s+(?:\S+\s+){0,4}(?:al|por|cada)\s+mes",
            r"reemplazar\s+mi\s+(?:salario|sueldo)",
        ],
    },
    "pt": {
        "guarantee": [r"garant(?:ir|ido|ida|idos|idas|imos|e|em|o|ia|ias|irei|ira|iria|indo|isse|am)"],
        "earnings": [
            r"rendas?", r"rendimentos?", r"salarios?", r"ganhos?",
            r"ganh(?:ar|arei|aras|ara|aremos|arao|aria|a|as|am|amos|ou|ei|ando|ado)",
        ],
        "money": [r"dinheiro", r"lucros?"],
        "nearby": [r"dinheiro", r"lucros?", r"comiss\w*", r"bonus", r"bonificac\w*"],
        "consumer": [
            r"garanti\w*\s+(?:(?:de|do|da|a|o|sua|seu|nossa|100|%|total|completa)\s*){0,4}"
            r"(?:reembolso\w*|devolucao\w*|satisfacao\w*|substituicao\w*|troca\w*|legal\w*|fabricante)",
            r"(?:reembolso\w*|devolucao\w*|satisfacao\w*|satisfeit\w*|substituicao\w*|troca\w*)\s+(?:\S+\s+){0,3}"
            r"garant\w*",
            r"garantia\s+(?:de\s+)?\d+\s+(?:dias|meses|anos?)",
            r"(?:em|sob|periodo\s+de|prazo\s+de|certificado\s+de)\s+garantia",
            r"garantia\s+(?:(?:dos|nos|sobre\s+os|de|para\s+os)\s+)produtos?",
            r"produtos?\s+(?:\S+\s+){0,2}garantia",
        ],
        "refund": [
            r"(?:devol|reembols|recuper|restitu|receb)\w*\s+(?:(?:o|a|seu|sua|todo|nosso|de|do)\s+){0,3}dinheiro",
            r"dinheiro\s+(?:(?:e|sera|seria|todo|integralmente|de)\s+){0,3}(?:devolvido\w*|reembolsad\w*|volta)",
        ],
        "false_friends": [],
        "phrases": [
            r"(?:renda|rendimentos?|ganhos?|salario|lucros?)\s+(?:mensa\w*\s+)?garantid\w*",
            r"garantia\s+de\s+(?:renda|ganhos?|rendimentos?|salario)",
            r"renda\s+passiva", r"rendimentos?\s+passivos?", r"liberdade\s+financeira",
            r"ficar\s+ric[oa]s?",
            r"ganhar\s+(?:muito\s+)?dinheiro\s+(?:rapido|facil\w*)", r"dinheiro\s+facil",
            r"quanto\s+(?:dinheiro\s+)?(?:posso|vou|poderei|poderia|irei)\s+(?:\w+\s+)?ganhar",
            r"ganh\w*\s+(?:\S+\s+){0,4}(?:por|cada|ao)\s+mes",
            r"substituir\s+(?:o\s+)?meu\s+salario",
        ],
    },
    "it": {
        "guarantee": [r"garanti\w*", r"garanzi\w*"],
        "earnings": [
            r"reddit[oi]", r"stipendi[oi]?", r"salari[oi]?", r"guadagn\w*", r"entrate\s+(?:mensili|garantite|passive)",
        ],
        "money": [r"denaro", r"soldi", r"profitt[oi]"],
        "nearby": [r"denaro", r"soldi", r"profitt[oi]", r"commission\w*", r"bonus", r"provvigion\w*"],
        "consumer": [
            r"soddisfatt[oi]\s+o\s+rimborsat[oi]",
            r"garanzi\w*\s+(?:(?:di|del|della|dei|la|il|una|un|sua|vostra|nostra|100|%|totale|completa|a)\s*){0,4}"
            r"(?:rimbors\w*|soddisfazion\w*|soddisfatt\w*|sostituzion\w*|reso|resi|restituzion\w*|legale|"
            r"convenzionale|commerciale|produttore)",
            r"(?:rimbors\w*|soddisfazion\w*|soddisfatt\w*|sostituzion\w*|reso|restituzion\w*)\s+(?:\S+\s+){0,3}"
            r"garanti\w*",
            r"garanti(?:to|ta|ti|te)\s+(?:\S+\s+){0,3}(?:soddisfazion\w*|rimbors\w*|sostituzion\w*)",
            r"garanzia\s+(?:di\s+)?\d+\s+(?:giorni|mesi|anni)",
            r"(?:in|sotto|periodo\s+di|certificato\s+di)\s+garanzia",
            r"garanzia\s+(?:(?:sui|sul|dei|del|per\s+i)\s+)prodott[oi]",
            r"prodott[oi]\s+(?:\S+\s+){0,2}garanzia",
        ],
        "refund": [
            r"(?:rimbors|restitu|ridare|ridat|recuper|riav|ricev)\w*\s+(?:(?:il|i|tuo|tuoi|suo|suoi|loro|vostro|"
            r"vostri|tutto|tutti|dei|del|di)\s+){0,3}(?:denaro|soldi)",
            r"(?:denaro|soldi)\s+(?:(?:e|sara|saranno|sono|viene|vengono|verra|verranno|tutto|tutti)\s+){0,3}"
            r"(?:rimborsat\w*|restituit\w*|indietro|ridat\w*)",
        ],
        "false_friends": [],
        "phrases": [
            r"(?:reddit[oi]|guadagn[oi]|stipendi[oi]?|profitt[oi]|entrate)\s+(?:mensil\w*\s+)?garantit\w*",
            r"garanzia\s+di\s+(?:reddito|guadagno|stipendio)",
            r"reddit[oi]\s+passiv[oi]", r"entrate\s+passive", r"liberta\s+finanziaria",
            r"diventare\s+ricc\w*", r"arricchir(?:si|mi|ti|ci|vi)",
            r"fare\s+soldi\s+(?:velocemente|facilmente|in\s+fretta)", r"soldi\s+facili",
            r"quanto\s+(?:posso|potro|potrei|riusciro\s+a)\s+guadagnare",
            r"guadagn\w*\s+(?:\S+\s+){0,4}(?:al|ogni|per|a)\s+mese",
            r"sostituire\s+(?:il\s+)?mio\s+stipendio",
        ],
    },
    "de": {
        "guarantee": [r"\w*garant\w*"],
        "earnings": [
            r"\w*einkommen\w*", r"verdien(?:e|en|st|t|te|test|ten|tet)?", r"\w*verdienst\w*",
            r"\w*gehälter\w*", r"(?:monats|jahres|fest|grund|mindest|traum)gehalt\w*", r"gehalts\w*",
            r"(?:mein|dein|ihr|sein|unser|euer)(?:e[mnrs]?)?\s+gehalt", r"\w*lohn(?:es|s)?", r"löhne",
            r"einnahmen",
        ],
        "money": [r"geld(?:es|er|ern|s)?", r"gewinn(?:e|en|s)?", r"profit(?:e|s)?"],
        "nearby": [r"geld(?:es|er|ern|s)?", r"gewinn(?:e|en|s)?", r"profit(?:e|s)?", r"provision\w*", r"bonus\w*",
                   r"boni", r"prämie\w*"],
        "consumer": [
            r"\w*(?:zufriedenheit|rückgabe|umtausch|rückerstattung|erstattung|ersatz|austausch|hersteller|produkt|"
            r"satisfaction)s?[\s-]*garantie\w*",
            r"\w*garantie\w*\s+(?:(?:auf|für|der|die|das|den|dem|des|eine|einen|ihre|ihr|unsere|100|%|volle|voll)\s*)"
            r"{0,4}(?:\w*zufriedenheit|\w*rückgabe|umtausch|\w*erstattung|ersatz|austausch|produkte?|\w*mängel)",
            r"(?:\w*zufriedenheit|zufrieden|\w*rückgabe|umtausch|\w*erstattung|ersatz|austausch)\s+(?:\S+\s+){0,3}"
            r"garantiert",
            r"garantiert\w*\s+(?:\S+\s+){0,3}(?:\w*zufriedenheit|zufrieden\w*|\w*erstattung|umtausch|ersatz)",
            r"\d+\s*-?\s*(?:tage|monate|jahre)s?[\s-]*garantie",
            r"garantie\s+(?:von\s+)?\d+\s+(?:tagen|tage|monaten|monate|jahren|jahre)",
            r"garantie\w*\s+(?:gilt|läuft|beträgt|besteht)\s+(?:\S+\s+){0,2}\d+\s+(?:tage|monate|jahre)",
            r"(?:garantiezeit|garantiefall|garantiebedingungen|garantieanspruch|garantieansprüche|garantieschein)\w*",
            r"gewährleistung\w*\s+(?:(?:und|oder|/)\s*)?garantie\w*|garantie\w*\s+(?:(?:und|oder|/)\s*)gewährleistung",
        ],
        "refund": [
            r"geld[\s-]*zurück\w*",
            r"(?:erstatt|zurückerstatt|zurückgez|zurückbekomm|zurückerh)\w*\s+(?:(?:ihr|sein|dein|das|ihre|sie|"
            r"volles|gesamte|gesamtes|den|als)\s+){0,3}geld",
            r"geld\s+(?:(?:wird|werden|ist|mehr|nicht|voll|vollständig|komplett)\s+){0,3}(?:erstattet|zurückerstattet|"
            r"zurückgezahlt|zurück\w*)",
        ],
        "false_friends": [],
        "phrases": [
            r"garantiert\w*\s+(?:\w+\s+)?(?:einkommen|verdienst\w*|gehalt|gewinn\w*|einnahmen|lohn)",
            r"(?:einkommen|verdienst|gehalt|gewinn|lohn)s?garantie\w*",
            r"passiv\w*\s+einkommen\w*", r"finanziell\w*\s+freiheit", r"finanziell\w*\s+unabhängig\w*",
            r"reich\s+(?:zu\s+)?werden", r"(?:werde|wirst)\s+(?:ich\s+|du\s+)?reich",
            r"schnell\w*\s+geld\s+(?:zu\s+)?verdienen", r"schnelles\s+geld",
            r"wie\s*viel\s+(?:geld\s+)?(?:kann|werde|könnte|würde)\s+ich\s+(?:\w+\s+){0,3}verdienen",
            r"verdien\w*\s+(?:\S+\s+){0,4}(?:pro|im|jeden|je|in\s+der)\s+(?:monat|woche)\w*",
            r"verdien\w*\s+(?:\S+\s+){0,4}monatlich",
            r"(?:mein|dein|ihr)\w*\s+gehalt\s+(?:zu\s+)?ersetzen",
        ],
    },
    "nl": {
        "guarantee": [r"\w*garand\w*", r"\w*garant\w*"],
        "earnings": [
            r"\w*inkomen\w*", r"\w*inkomsten\w*", r"verdien(?:en|t|de|den|d)?", r"\w*verdiensten?",
            r"\w*salaris\w*", r"\w*loon", r"lonen",
        ],
        "money": [r"geld", r"winsten?"],
        "nearby": [r"geld", r"winsten?", r"commissie\w*", r"bonus\w*", r"provisie\w*"],
        "consumer": [
            r"\w*(?:tevredenheid|retour|terugbetaling|vervangings?|omruil|fabrieks|product)s?[\s-]*garantie\w*",
            r"garantie\w*\s+(?:(?:op|voor|van|de|het|een|uw|je|onze|100|%|volledige)\s*){0,4}"
            r"(?:\w*tevredenheid|retour\w*|terugbetaling\w*|vervanging\w*|omruil\w*|producten?)",
            r"(?:tevredenheid|tevreden|retour\w*|terugbetaling\w*|vervanging\w*|omruil\w*)\s+(?:\S+\s+){0,3}"
            r"gegarandeerd\w*",
            r"gegarandeerd\w*\s+(?:\S+\s+){0,3}(?:tevreden\w*|terugbetaling\w*|vervanging\w*|omruil\w*)",
            r"\d+\s*(?:dagen|maanden|jaar)\s*garantie", r"garantie\s+(?:van\s+)?\d+\s+(?:dagen|maanden|jaar)",
            r"(?:garantieperiode|garantietermijn|garantiebewijs|garantievoorwaarden)\w*", r"onder\s+garantie",
        ],
        "refund": [
            r"(?:niet[\s-]*goed[\s-]*)?geld[\s-]*terug\w*",
            r"(?:terugbetaal|terugbetaald|terugkrijg|krijg|krijgt|krijgen|ontvang)\w*\s+"
            r"(?:(?:uw|je|het|hun|zijn|haar|al|volledig)\s+){0,3}geld",
            r"geld\s+(?:(?:wordt|worden|is|volledig)\s+){0,3}(?:terugbetaald|teruggestort)",
        ],
        "false_friends": [],
        "phrases": [
            r"gegarandeerd\w*\s+(?:\w+\s+)?(?:inkomen|inkomsten|salaris|winst|verdiensten|loon)",
            r"(?:inkomens|inkomsten|salaris|winst|verdienste)garantie\w*",
            r"passie\w*\s+inkomen\w*", r"financiele\s+vrijheid", r"financieel\s+onafhankelijk\w*",
            r"rijk\s+(?:te\s+)?worden", r"(?:word|wordt)\s+(?:ik|je|u)\s+rijk",
            r"snel\s+(?:veel\s+)?geld\s+(?:te\s+)?verdienen", r"snel\s+rijk",
            r"hoeveel\s+(?:geld\s+)?(?:kan|zal|ga)\s+ik\s+(?:\w+\s+){0,3}verdienen",
            r"verdien\w*\s+(?:\S+\s+){0,4}(?:per|elke|iedere|in\s+de|p\.?)\s+(?:maand|week)",
            r"verdien\w*\s+(?:\S+\s+){0,4}maandelijks",
            r"mijn\s+salaris\s+(?:te\s+)?vervangen",
        ],
    },
    "sv": {
        "guarantee": [r"\w*garant\w*"],
        "earnings": [
            r"\w*inkomst\w*", r"tjäna(?:r|de|t)?", r"tjänande", r"\w*förtjän\w*",
            r"(?:månads|års|grund|fast|minimi)?lön(?:en|er|erna|ens)?",
        ],
        "money": [r"pengar\w*", r"vinst\w*"],
        "nearby": [r"pengar\w*", r"vinst\w*", r"provision\w*", r"bonus\w*", r"kommission\w*"],
        "consumer": [
            r"\w*(?:nöjd[\s-]*kund|nöjdhets|nöjd|kund|tillfredsställelse|retur|återbetalning|ersättning|byte|ombyte|"
            r"reklamation|produkt)s?[\s-]*garanti\w*",
            r"garanti\w*\s+(?:(?:på|för|av|en|ett|din|er|vår|100|%|full)\s*){0,4}"
            r"(?:\w*nöjd\w*|\w*tillfredsställelse|retur\w*|återbetalning\w*|ersättning\w*|ombyte\w*|byte\w*|"
            r"produkt\w*)",
            r"(?:nöjd\w*|tillfredsställelse|retur\w*|återbetalning\w*|ersättning\w*)\s+(?:\S+\s+){0,3}garanter\w*",
            r"garanter\w*\s+(?:\S+\s+){0,3}(?:nöjd\w*|tillfredsställelse|återbetalning\w*|ersättning\w*)",
            r"\d+\s*(?:dagars|månaders|års)\s*garanti\w*", r"garanti\s+(?:i|på)\s+\d+\s+(?:dagar|månader|år)",
            r"(?:garantitid|garantiperiod|garantibevis|garantivillkor)\w*",
        ],
        "refund": [
            r"pengar(?:na)?[\s-]*tillbaka",
            r"(?:återbetal|få|får|fått)\w*\s+(?:(?:dina|sina|era|hela|alla)\s+){0,2}pengar(?:na)?",
        ],
        "false_friends": [],
        "phrases": [
            r"garanterad\w*\s+(?:\w+\s+)?(?:inkomst\w*|lön\w*|vinst\w*|förtjänst\w*)",
            r"(?:inkomst|löne|vinst)garanti\w*",
            r"passiv\w*\s+inkomst\w*", r"ekonomisk\w*\s+frihet", r"ekonomiskt\s+oberoende",
            r"bli\s+rik(?:are|a)?", r"snabba\s+pengar",
            r"hur\s+mycket\s+(?:pengar\s+)?(?:kan|kommer)\s+jag\s+(?:att\s+)?tjäna",
            r"tjän\w*\s+(?:\S+\s+){0,4}(?:per|i|om|varje|en)\s+(?:månad\w*|vecka)",
            r"ersätta\s+min\s+lön",
        ],
    },
    "da": {
        "guarantee": [r"\w*garant\w*"],
        "earnings": [
            r"\w*indkomst\w*", r"tjen(?:e|er|te|t|ende)", r"\w*fortjeneste\w*", r"\w*indtjening\w*",
            r"(?:måneds|års|grund|fast|minimums?)?løn(?:nen|ninger|ningen)?",
        ],
        "money": [r"penge\w*", r"overskud\w*"],
        "nearby": [r"penge\w*", r"overskud\w*", r"provision\w*", r"bonus\w*", r"kommission\w*"],
        "consumer": [
            r"\w*(?:tilfredsheds?|retur|tilbagebetalings?|ombytnings?|erstatnings?|reklamations?|produkt)"
            r"[\s-]*garanti\w*",
            r"garanti\w*\s+(?:(?:på|for|af|en|et|din|jeres|vores|100|%|fuld)\s*){0,4}"
            r"(?:\w*tilfreds\w*|retur\w*|tilbagebetaling\w*|ombytning\w*|erstatning\w*|produkt\w*)",
            r"(?:tilfreds\w*|retur\w*|tilbagebetaling\w*|ombytning\w*)\s+(?:\S+\s+){0,3}garanter\w*",
            r"garanter\w*\s+(?:\S+\s+){0,3}(?:tilfreds\w*|tilbagebetaling\w*|ombytning\w*|erstatning\w*)",
            r"\d+\s*(?:dages|måneders|års)\s*garanti\w*", r"garanti\s+(?:i|på)\s+\d+\s+(?:dage|måneder|år)",
            r"(?:garantiperiode|garantibevis|garantivilkår|reklamationsret)\w*",
        ],
        "refund": [
            r"penge(?:ne)?[\s-]*tilbage",
            r"(?:tilbagebetal|få|får|fået|refunder)\w*\s+(?:(?:dine|sine|jeres|alle|hele)\s+){0,2}penge(?:ne)?",
            r"penge(?:ne)?\s+(?:\S+\s+){0,2}(?:refunderet|tilbagebetalt)",
        ],
        "false_friends": [],
        "phrases": [
            r"garanteret\s+(?:\w+\s+)?(?:indkomst\w*|løn\w*|fortjeneste\w*|indtjening\w*)",
            r"(?:indkomst|løn|indtjenings)garanti\w*",
            r"passiv\w*\s+indkomst\w*", r"økonomisk\w*\s+frihed", r"økonomisk\s+uafhængig\w*",
            r"blive\s+rig(?:ere|e)?", r"hurtige\s+penge",
            r"hvor\s+(?:mange\s+penge|meget)\s+(?:kan|vil|kommer)\s+jeg\s+(?:til\s+(?:at\s+)?)?tjene",
            r"tjen\w*\s+(?:\S+\s+){0,4}(?:om|pr\.?|per|hver|i|en)\s+(?:måned\w*|uge\w*)",
            r"erstatte\s+min\s+løn",
        ],
    },
    "no": {
        "guarantee": [r"\w*garant\w*"],
        "earnings": [
            r"\w*inntekt\w*", r"tjen(?:e|er|te|t|ende)", r"\w*fortjeneste\w*", r"\w*inntjening\w*",
            r"\w*lønn(?:en|er|ingene|s)?",
        ],
        "money": [r"penger\w*", r"overskudd\w*"],
        "nearby": [r"penger\w*", r"overskudd\w*", r"provisjon\w*", r"bonus\w*", r"kommisjon\w*"],
        "consumer": [
            r"\w*(?:tilfredshets?|retur|tilbakebetalings?|bytte|erstatnings?|reklamasjons?|produkt)[\s-]*garanti\w*",
            r"garanti\w*\s+(?:(?:på|for|av|en|et|din|deres|vår|100|%|full)\s*){0,4}"
            r"(?:\w*tilfreds\w*|retur\w*|tilbakebetaling\w*|bytte\w*|erstatning\w*|produkt\w*)",
            r"(?:tilfreds\w*|retur\w*|tilbakebetaling\w*|bytte\w*)\s+(?:\S+\s+){0,3}garanter\w*",
            r"garanter\w*\s+(?:\S+\s+){0,3}(?:tilfreds\w*|tilbakebetaling\w*|bytte\w*|erstatning\w*)",
            r"\d+\s*(?:dagers|måneders|års)\s*garanti\w*", r"garanti\s+(?:i|på)\s+\d+\s+(?:dager|måneder|år)",
            r"(?:garantiperiode|garantibevis|garantivilkår|reklamasjonsrett)\w*",
        ],
        "refund": [
            r"penge(?:ne|r)?[\s-]*tilbake",
            r"(?:tilbakebetal|få|får|fått|refunder)\w*\s+(?:(?:dine|sine|deres|alle|hele)\s+){0,2}penge(?:ne|r)?",
        ],
        "false_friends": [],
        "phrases": [
            r"garantert\s+(?:\w+\s+)?(?:inntekt\w*|lønn\w*|fortjeneste\w*|inntjening\w*)",
            r"(?:inntekts|lønns|inntjenings)garanti\w*",
            r"passiv\w*\s+inntekt\w*", r"økonomisk\w*\s+frihet", r"økonomisk\s+uavhengig\w*",
            r"bli\s+rik(?:ere|e)?", r"raske\s+penger",
            r"hvor\s+(?:mye|mange\s+penger)\s+(?:kan|vil|kommer)\s+jeg\s+(?:til\s+(?:å\s+)?)?tjene",
            r"tjen\w*\s+(?:\S+\s+){0,4}(?:i|om|per|pr\.?|hver|en)\s+(?:måned\w*|uke\w*)",
            r"erstatte\s+(?:min\s+lønn|lønnen\s+min)",
        ],
    },
    "fi": {
        "guarantee": [
            r"\w*takuu\w*", r"\w*takui\w*", r"taat(?:a|aan|tu\w*|usti|tiin|taisiin)",
            r"taka(?:a|an|at|amme|atte|avat|asi|si|sin|simme|isivat|isi|ama\w*)",
        ],
        "earnings": [
            r"(?:kuukausi|lisä|passiivi|passiivise|vuosi|perus|kuukautise)?tulo(?:t|ni|si|nsa|mme|nne|a|ja|jen|"
            r"ista|ihin|ina|iksi|ksi|tsi|tni|jani|jasi)?",
            r"ansai(?:ta|t\w+)", r"ansio(?:t|ita|iden|ni|si|tulo\w*)", r"tiena\w*",
            r"\w*palk(?:ka|an|kaa|kasi|kani|at|koja|oista)",
        ],
        "money": [r"raha(?:a|t|n|lla|sta|ksi|ni|si|kin|na|nsa)?", r"voitto\w*", r"voitot"],
        "nearby": [r"raha\w{0,4}", r"voito\w*", r"voitto\w*", r"provisio\w*", r"bonus\w*", r"palkkio\w*"],
        "consumer": [
            r"\w*(?:tyytyväisyys|palautus|palautusoikeus|hyvitys|vaihto|valmistaja|tuote)[\s-]*takuu\w*",
            r"(?:takuu\w*|takaa\w*|taat\w*)\s+(?:\S+\s+){0,3}(?:tyytyväisyy\w*|palautu\w*|hyvity\w*|vaihdo\w*|"
            r"vaihto\w*)",
            r"(?:tyytyväisyy\w*|palautu\w*|hyvity\w*|vaihto\w*|tyytyväise\w*)\s+(?:\S+\s+){0,3}"
            r"(?:taat\w*|takaa\w*|takuu\w*)",
            r"\d+\s*(?:päivän|kuukauden|vuoden)\s+takuu\w*", r"takuu(?:aika|aikana|ajan|seen|ehdot|todistus)\w*",
            r"takuun\s+(?:piirissä|voimassa)", r"tuotteill\w*\s+(?:on\s+)?(?:\S+\s+){0,1}takuu\w*",
        ],
        "refund": [
            r"rahat\s+takaisin", r"raha(?:nsa|si|ni|t)?\s+takaisin", r"rahojen\s+palautu\w*",
            r"(?:saa|saat|saavat|saada|palaute\w*|palautta\w*|hyvite\w*)\s+(?:\S+\s+){0,2}raha\w*",
        ],
        "false_friends": [r"\w*ansiosta"],
        "phrases": [
            r"taattu\w*\s+(?:\w+\s+)?(?:tulo\w*|ansio\w*|palk\w*|voitto\w*)",
            r"(?:tulo|ansio|palkka)takuu\w*",
            r"passiivi\w*\s+tulo\w*", r"taloudellinen\s+vapaus", r"taloudellise\w*\s+vapaud\w*",
            r"rikastu\w*", r"rikkaaksi", r"helppo\w*\s+raha\w*", r"nopea\w*\s+raha\w*",
            r"(?:paljonko|kuinka\s+paljon)\s+(?:rahaa\s+)?(?:voin|tulen|voisin)\s+ansaita\w*",
            r"(?:ansai|tiena)\w*\s+(?:\S+\s+){0,4}(?:kuukaudessa|kuussa|viikossa)",
            r"korvata\s+(?:minun\s+)?palk\w*",
        ],
    },
    "ru": {
        "guarantee": [r"\w*гарант\w*"],
        "earnings": [
            r"доход(?:ы|а|ов|у|ом|ами|ах|е|н\w*)?", r"зараб[оа]т\w*", r"зарплат\w*", r"оклад\w*", r"жалован\w*",
        ],
        "money": [r"деньг\w*", r"денег", r"денежн\w*", r"прибыль\w*", r"прибыльн\w*", r"выручк\w*"],
        "nearby": [r"деньг\w*", r"денег", r"денежн\w*", r"прибыл\w*", r"выручк\w*", r"комисси\w*", r"бонус\w*",
                   r"вознагражден\w*"],
        "consumer": [
            r"\w*гаранти\w*\s+(?:(?:на|полного|полной|полную|100|%|вашей|нашей|своей)\s*){0,3}"
            r"(?:возврат\w*|удовлетворен\w*|замен\w*|обмен\w*|качеств\w*|товар\w*|продукци\w*|производител\w*)",
            r"(?:возврат\w*|удовлетворен\w*|замен\w*|обмен\w*)\s+(?:\S+\s+){0,3}\w*гарантир\w*",
            r"гарантийн\w*",
            r"гаранти\w*\s+(?:на\s+)?\d+\s+(?:дн\w*|месяц\w*|год\w*|лет)",
            r"(?:по|на)\s+гаранти\w*",
        ],
        "refund": [
            r"возврат\w*\s+(?:(?:всех|ваших|своих|полной\s+суммы)\s+)?(?:денег|деньг\w*|средств)",
            r"(?:верн\w*|возвращ\w*|возмест\w*|получ\w*)\s+(?:(?:вам|им|ему|ей|свои|ваши|все|назад|обратно)\s+){0,3}"
            r"(?:деньги|денег)",
            r"деньги\s+(?:(?:будут|вам|полностью)\s+){0,3}(?:возвращ\w*|верн\w*|назад|обратно)",
        ],
        "false_friends": [],
        "phrases": [
            r"гарантирован\w*\s+(?:\w+\s+)?(?:доход\w*|заработ\w*|прибыл\w*|зарплат\w*)",
            r"гаранти\w*\s+(?:дохода|заработка|прибыли|зарплаты)",
            r"пассивн\w*\s+доход\w*", r"финансов\w*\s+свобод\w*", r"финансов\w*\s+независимост\w*",
            r"разбогате\w*", r"стать\s+богат\w*", r"легки\w*\s+деньг\w*", r"быстры\w*\s+деньг\w*",
            r"сколько\s+(?:денег\s+)?(?:я\s+)?(?:смогу|могу|буду)\s+(?:\w+\s+)?зараб[оа]т\w*",
            r"сколько\s+(?:денег\s+)?(?:я\s+)?заработа\w*",
            r"зараб[оа]т\w*\s+(?:\S+\s+){0,4}(?:в|за)\s+(?:месяц|неделю)",
            r"заменить\s+(?:мою\s+|свою\s+)?зарплат\w*",
        ],
    },
    "ru-latn": {
        "guarantee": [r"garantir\w*", r"garantiy\w*", r"garantij\w*", r"garantii"],
        "earnings": [r"dokhod\w*", r"dohod\w*", r"zarabot\w*", r"zarabat\w*", r"zarplat\w*"],
        "money": [r"deneg", r"dengi\w*", r"pribyl\w*"],
        "nearby": [r"deneg", r"dengi\w*", r"pribyl\w*"],
        "consumer": [r"garanti\w*\s+(?:\S+\s+){0,2}(?:vozvrat\w*|udovletvor\w*|zamen\w*|obmen\w*)",
                     r"garantiyn\w*"],
        "refund": [r"vozvrat\w*\s+(?:\S+\s+)?(?:deneg|dengi)", r"(?:vern\w*|vozvrashch\w*)\s+(?:\S+\s+)?(?:dengi|deneg)"],
        "false_friends": [],
        "phrases": [
            r"garantirovann\w*\s+(?:dokhod|dohod|zarabot|zarplat|pribyl)\w*", r"passivn\w*\s+(?:dokhod|dohod)\w*",
            r"finansov\w*\s+svobod\w*", r"razbogat\w*",
        ],
    },
    "sr": {
        "guarantee": [r"\w*garant\w*", r"garancij\w*"],
        "earnings": [
            r"prihod(?:a|e|i|u|om|ima)?", r"zarad\w*", r"dohod(?:ak|ka|ku|kom|ci|aka)", r"plat(?:a|u|om)",
        ],
        "money": [r"novac", r"novca", r"novcem", r"novcu", r"profit(?:a|om|u|i)?"],
        "nearby": [r"novac", r"novca", r"novcem", r"novcu", r"pare", r"profit\w*", r"bonus\w*", r"provizij\w*"],
        "consumer": [
            r"garancij\w*\s+(?:(?:na|za|od|100|%|potpunog|pune|vaseg|naseg)\s*){0,3}(?:povra\w*|zadovoljst\w*|"
            r"zamen\w*|zamjen\w*|proizvod\w*|proizvodac\w*|kvalitet\w*)",
            r"(?:povra\w*|zadovoljst\w*|zadovolj\w*|zamen\w*)\s+(?:\S+\s+){0,3}\w*garant\w*",
            r"\w*garantovan\w*\s+(?:\S+\s+){0,3}(?:zadovoljst\w*|povra\w*|zamen\w*)",
            r"garantn\w*\s+(?:rok|list)\w*", r"(?:pod|u)\s+garancij\w*",
            r"garancij\w*\s+(?:od\s+)?\d+\s+(?:dan\w*|mesec\w*|godin\w*)",
            r"proizvod\w*\s+(?:\S+\s+){0,2}garancij\w*",
        ],
        "refund": [
            r"povra\w*\s+(?:(?:celog|punog|vaseg|svog)\s+)?(?:novca|novac|para)",
            r"(?:vrati\w*|vrac\w*|dobi\w*|dobij\w*)\s+(?:(?:vam|im|mu|joj|svoj|vas|ceo|sav)\s+){0,3}"
            r"(?:novac|novca|pare)",
            r"(?:novac|pare)\s+(?:(?:ce|bice|je|biti|vam)\s+){0,3}(?:vracen\w*|nazad)",
        ],
        "false_friends": [],
        "phrases": [
            r"\w*garantovan\w*\s+(?:\w+\s+)?(?:prihod\w*|zarad\w*|dohod\w*|plat[aeu]\w*|profit\w*)",
            r"garancij\w*\s+(?:prihoda|zarade|dohotka|plate)",
            r"pasivn\w*\s+(?:prihod|zarad|dohod)\w*", r"finansijsk\w*\s+slobod\w*", r"finansijsk\w*\s+nezavisnost\w*",
            r"obogat\w*\s+se", r"se\s+obogat\w*", r"postati\s+bogat\w*", r"postanem\s+bogat\w*",
            r"brz\w*\s+(?:zarad\w*|novac|pare)", r"lak\w*\s+(?:zarad\w*|novac|pare)",
            r"koliko\s+(?:novca\s+)?(?:mogu|cu|bih|cemo)\s+(?:da\s+)?zaradi\w*",
            r"zarad\w*\s+(?:\S+\s+){0,4}(?:mesecno|na\s+mesec|po\s+mesecu|mjesecno|nedeljno)",
            r"zameni\w*\s+(?:moju\s+)?plat\w*",
        ],
    },
    "sr-cyrl": {
        "guarantee": [r"\w*гарант\w*", r"\w*гаранц\w*"],
        "earnings": [r"приход(?:а|у|ом|има)?", r"зарад\w*", r"зарађ\w*", r"доход(?:ак|ка|ку|ком|ци|ака)"],
        "money": [r"новац", r"новца", r"новцем", r"новцу", r"профит(?:а|ом|у|и)?"],
        "nearby": [r"новац", r"новца", r"новцем", r"новцу", r"паре", r"профит\w*", r"бонус\w*", r"провизиј\w*"],
        "consumer": [
            r"гаранциј\w*\s+(?:(?:на|за|од|100|%|потпуног|пуне|вашег|нашег)\s*){0,3}(?:поврат\w*|повраћ\w*|"
            r"задовољств\w*|замен\w*|производ\w*|квалитет\w*)",
            r"(?:поврат\w*|повраћ\w*|задовољ\w*|замен\w*)\s+(?:\S+\s+){0,3}\w*гарант\w*",
            r"\w*гарантован\w*\s+(?:\S+\s+){0,3}(?:задовољств\w*|поврат\w*|повраћ\w*|замен\w*)",
            r"гарантн\w*\s+(?:рок|лист)\w*", r"(?:под|у)\s+гаранциј\w*",
            r"гаранциј\w*\s+(?:од\s+)?\d+\s+(?:дан\w*|месец\w*|годин\w*)",
            r"производ\w*\s+(?:\S+\s+){0,2}гаранциј\w*",
        ],
        "refund": [
            r"повра(?:т|ћ)\w*\s+(?:(?:целог|пуног|вашег|свог)\s+)?(?:новца|новац|пара)",
            r"(?:врати\w*|враћ\w*|доби\w*)\s+(?:(?:вам|им|му|јој|свој|ваш|цео|сав)\s+){0,3}(?:новац|новца|паре)",
            r"(?:новац|паре)\s+(?:(?:ће|биће|је|бити|вам)\s+){0,3}(?:враћен\w*|назад)",
        ],
        "false_friends": [],
        "phrases": [
            r"\w*гарантован\w*\s+(?:\w+\s+)?(?:приход\w*|зарад\w*|доход\w*|плат[аеу]\w*|профит\w*)",
            r"гаранциј\w*\s+(?:прихода|зараде|дохотка|плате)",
            r"пасивн\w*\s+(?:приход|зарад|доход)\w*", r"финансијск\w*\s+слобод\w*",
            r"обогат\w*\s+се", r"се\s+обогат\w*", r"постати\s+богат\w*", r"постанем\s+богат\w*",
            r"колико\s+(?:новца\s+)?(?:могу|ћу|бих)\s+(?:да\s+)?заради\w*",
            r"зара(?:д|ђ)\w*\s+(?:\S+\s+){0,4}(?:месечно|на\s+месец|по\s+месецу)",
        ],
    },
}

# W16b (2026-09-12): a product warranty is a consumer guarantee too. In most of
# these languages warranty and guarantee are one word (garantie, garantía,
# Garantie, garanzia, takuu, гарантия, garancija), so "La garantía cubre
# defectos; el dinero se devuelve en 30 días." (and the same in every language)
# was refused: the guarantee paired with the refunded money. As in English
# (income_claim_policy._WARRANTY_GUARANTEE), a guarantee is set aside as a
# warranty only when it covers, applies to or protects against defects, faults
# or damage (or defective products, or their repair or replacement), or products
# are guaranteed free from defects, and that object closes its clause: a
# sentence end, ";", or straight into refund wording ("... y se reembolsa el
# dinero"). It is then judged like every consumer guarantee: an earnings word
# anywhere in the text, or a money word nearby, keeps it.
_WARRANTY_UNIT = (
    r"(?:dias|meses|anos?|jours|mois|ans|annees|tage|tagen|monate|monaten|jahre|jahren|wochen|dagen|maanden|jaar"
    r"|giorni|mesi|anni|dagar|manader|ar|dage|maneder|dager|paivaa|paivan|kuukautta|kuukauden|vuotta|vuoden"
    r"|дней|дня|месяцев|месяца|лет|года|dana|meseci|godina|дана|месеци|година)"
)
_WARRANTY_DURATION = (
    rf"(?:\s+(?:[^\s\d.!?;:,]+\s+){{0,2}}\(?\d+\)?\s+{_WARRANTY_UNIT}(?:\s+(?:ajan|kuluessa|sisalla))?)?"
)
_WARRANTY_CONJUNCTION = (
    r"(?:y|e|et|und|en|och|og|ja|i|a|ou|o|oder|of|eller|tai|ili|и|или|но|mais|ma|men|mutta|pero|aber|maar|ali)"
)
_WARRANTY_END = (
    r"(?=\s*(?:[.!?;](?:\s|$)|$)"
    rf"|[\s,]+(?:{_WARRANTY_CONJUNCTION}\s+)?(?:[^\s.!?;:,]+\s+){{0,2}}refund(?!\w))"
)
_WARRANTY_TAIL = f"{_WARRANTY_DURATION}{_WARRANTY_END}"
_WARRANTY: dict[str, list[str]] = {
    "fr": [
        r"garanti\w*\s+(?:(?:legale|commerciale|constructeur|fabricant)\s+)?(?:couvre|couvrent|couvrira"
        r"|protège\s+contre|s'applique\s+(?:à|aux)|inclut|comprend)\s+(?:(?:les|la|le|l'|tous|toutes|tout|vos|nos|ses"
        r"|leurs|des|éventuels|d'éventuels)\s*){0,2}(?:(?:défauts?|vices?|pannes?|dommages)(?:\s+(?:de\s+fabrication"
        r"|de\s+matériaux|cachés?|de\s+conformité))?(?:\s+(?:et|ou)\s+(?:les\s+)?(?:défauts?|vices?|pannes?|dommages))?"
        r"|produits?\s+(?:défectueux|endommagés?|abîmés?)"
        r"|(?:la\s+|le\s+)?(?:réparation|remplacement)\s+(?:des|du|de)\s+produits?(?:\s+défectueux)?)" + _WARRANTY_TAIL,
        r"garanti(?:e|s|es)?\s+(?:contre|sans)\s+(?:(?:les|tout|tous)\s+)?(?:défauts?|vices?)(?:\s+de\s+fabrication)?"
        + _WARRANTY_TAIL,
    ],
    "es": [
        r"garantía\w*\s+(?:(?:legal|comercial|del\s+fabricante)\s+)?(?:también\s+|solo\s+)?(?:cubre|cubren|cubrirá"
        r"|protege\s+contra|se\s+aplica\s+a|aplica\s+a|incluye|abarca)\s+(?:(?:los|las|el|la|todos|todas|todo"
        r"|cualquier|sus|posibles|eventuales)\s+){0,2}(?:(?:defectos?|fallos?|fallas|averías?|daños)(?:\s+de\s+"
        r"(?:fabricación|materiales?))?(?:\s+(?:y|o)\s+(?:(?:los|las)\s+)?(?:defectos?|fallos?|fallas|averías?|daños))?"
        r"|productos?\s+(?:defectuos\w*|dañad\w*|averiad\w*)"
        r"|(?:la\s+)?(?:reparación|sustitución|reemplazo|reposición)\s+de\s+(?:(?:los|las|el|la)\s+)?productos?"
        r"(?:\s+defectuos\w*)?)" + _WARRANTY_TAIL,
        r"garantizad[oa]s?\s+(?:contra|sin|libres?\s+de)\s+(?:(?:todo|cualquier|los)\s+)?(?:defectos?|fallos?|fallas)"
        r"(?:\s+de\s+fabricación)?" + _WARRANTY_TAIL,
    ],
    "pt": [
        r"garantia\w*\s+(?:(?:legal|do\s+fabricante)\s+)?(?:também\s+)?(?:cobre|cobrem|cobrirá|protege\s+contra"
        r"|se\s+aplica\s+a|aplica-se\s+a|inclui|abrange)\s+(?:(?:os|as|o|a|todos|todas|quaisquer|eventuais|seus|suas)"
        r"\s+){0,2}(?:(?:defeitos?|falhas?|avarias?|danos)(?:\s+de\s+fabrica\w*)?(?:\s+(?:e|ou)\s+(?:os\s+|as\s+)?"
        r"(?:defeitos?|falhas?|avarias?|danos))?"
        r"|produtos?\s+(?:defeituos\w*|danificad\w*|com\s+defeito)"
        r"|(?:o\s+|a\s+)?(?:reparo|reparação|substituição|troca)\s+(?:de\s+|dos\s+|do\s+)?produtos?"
        r"(?:\s+defeituos\w*|\s+com\s+defeito)?)" + _WARRANTY_TAIL,
        r"garantid[oa]s?\s+(?:contra|sem|livres?\s+de)\s+(?:(?:quaisquer|os)\s+)?(?:defeitos?|falhas?)"
        r"(?:\s+de\s+fabrica\w*)?" + _WARRANTY_TAIL,
    ],
    "it": [
        r"garanzi\w*\s+(?:(?:legale|convenzionale|del\s+produttore)\s+)?(?:copre|coprono|coprirà|protegge\s+da"
        r"|si\s+applica\s+(?:a|ai|agli|al|alle)|include|comprende)\s+(?:(?:i|gli|le|il|lo|tutti|tutte|eventuali"
        r"|qualsiasi)\s+){0,2}(?:(?:difetti|difetto|guasti|danni|vizi)(?:\s+di\s+(?:fabbricazione|conformità))?"
        r"(?:\s+(?:e|o)\s+(?:i\s+)?(?:difetti|guasti|danni|vizi))?"
        r"|prodott[oi]\s+(?:difettos\w*|danneggiat\w*|guast[oi])"
        r"|(?:la\s+)?(?:riparazione|sostituzione)\s+(?:dei\s+|del\s+|di\s+)?prodott[oi](?:\s+difettos\w*)?)"
        + _WARRANTY_TAIL,
        r"garantit[oiae]\s+(?:contro|senza|privi?\s+di|esenti?\s+da)\s+(?:(?:i|ogni)\s+)?(?:difetti|vizi)"
        r"(?:\s+di\s+fabbricazione)?" + _WARRANTY_TAIL,
    ],
    "de": [
        r"\w*garantie\w*\s+(?:deckt|umfasst|erfasst|übernimmt|schützt\s+vor|gilt\s+(?:für|bei)|greift\s+bei)\s+"
        r"(?:(?:alle|sämtliche|die|eventuelle|etwaige|jegliche|auch)\s+){0,2}(?:(?:mängel|sachmängel|defekte"
        r"|fehler|herstellungsfehler|fabrikationsfehler|materialfehler|verarbeitungsfehler|schäden)(?:\s+(?:und|oder)"
        r"\s+(?:mängel|defekte|fehler|verarbeitungsfehler|schäden))?"
        r"|(?:defekte|fehlerhafte|beschädigte|mangelhafte)\s+produkte"
        r"|(?:die\s+|den\s+)?(?:reparatur|ersatz|austausch)\s+(?:von\s+|der\s+)?(?:defekten\s+|fehlerhaften\s+)?"
        r"produkte\w*)(?:\s+ab)?" + _WARRANTY_TAIL,
        r"garantiert\s+(?:frei\s+von|ohne)\s+(?:mängel\w*|defekte\w*|fehler\w*)" + _WARRANTY_TAIL,
    ],
    "nl": [
        r"\w*garantie\w*\s+(?:dekt|omvat|beschermt\s+tegen|geldt\s+(?:voor|bij)|is\s+van\s+toepassing\s+op)\s+"
        r"(?:(?:alle|de|het|eventuele)\s+){0,2}(?:(?:defecten|gebreken|fabricagefouten|productiefouten|fouten|schade)"
        r"(?:\s+(?:en|of)\s+(?:defecten|gebreken|fouten|schade))?"
        r"|(?:defecte|gebrekkige|beschadigde|kapotte)\s+producten"
        r"|(?:de\s+)?(?:reparatie|vervanging)\s+(?:van\s+)?(?:defecte\s+)?producten)" + _WARRANTY_TAIL,
        r"gegarandeerd\s+(?:vrij\s+van|zonder)\s+(?:defecten|gebreken|fouten)" + _WARRANTY_TAIL,
    ],
    "sv": [
        r"garanti\w*\s+(?:täcker|omfattar|gäller\s+(?:för|vid)|skyddar\s+mot)\s+(?:(?:alla|eventuella)\s+)?"
        r"(?:(?:defekter|fel|brister|fabrikationsfel|tillverkningsfel|skador)(?:\s+(?:och|eller)\s+(?:defekter|fel"
        r"|brister|skador))?"
        r"|(?:defekta|felaktiga|skadade|trasiga)\s+produkter"
        r"|(?:reparation|utbyte|ersättning|byte)\s+av\s+(?:defekta\s+)?produkter)" + _WARRANTY_TAIL,
        r"garanterat?\s+(?:fria?\s+från|utan)\s+(?:defekter|fel|brister)" + _WARRANTY_TAIL,
    ],
    "da": [
        r"garanti\w*\s+(?:dækker|omfatter|gælder\s+(?:for|ved)|beskytter\s+mod)\s+(?:(?:alle|eventuelle)\s+)?"
        r"(?:(?:fejl|defekter|mangler|fabrikationsfejl|produktionsfejl|skader)(?:\s+(?:og|eller)\s+(?:fejl|defekter"
        r"|mangler|skader))?"
        r"|(?:defekte|fejlbehæftede|beskadigede|ødelagte)\s+produkter"
        r"|(?:reparation|ombytning|udskiftning)\s+af\s+(?:defekte\s+)?produkter)" + _WARRANTY_TAIL,
        r"garanteret\s+(?:fri\s+for|uden)\s+(?:fejl|defekter|mangler)" + _WARRANTY_TAIL,
    ],
    "no": [
        r"garanti\w*\s+(?:dekker|omfatter|gjelder\s+(?:for|ved)|beskytter\s+mot)\s+(?:(?:alle|eventuelle)\s+)?"
        r"(?:(?:feil|defekter|mangler|produksjonsfeil|fabrikasjonsfeil|skader)(?:\s+(?:og|eller)\s+(?:feil|defekter"
        r"|mangler|skader))?"
        r"|(?:defekte|feilaktige|skadde|ødelagte)\s+produkter"
        r"|(?:reparasjon|bytte|utskifting)\s+av\s+(?:defekte\s+)?produkter)" + _WARRANTY_TAIL,
        r"garantert\s+(?:fri\s+for|uten)\s+(?:feil|defekter|mangler)" + _WARRANTY_TAIL,
    ],
    "fi": [
        r"takuu\w*\s+(?:kattaa|koskee|suojaa)\s+(?:(?:kaikki|mahdolliset)\s+)?(?:(?:viat|vikoja|virheet|virheitä"
        r"|valmistusviat|valmistusvirheet|vauriot)(?:\s+(?:ja|tai)\s+(?:viat|virheet|vauriot))?"
        r"|vialliset\s+tuotteet|viallisia\s+tuotteita"
        r"|(?:viallisten\s+)?tuotteiden\s+(?:korjauksen|vaihdon|korjaamisen|vaihtamisen))" + _WARRANTY_TAIL,
    ],
    "ru": [
        r"гаранти\w*\s+(?:распространяется\s+на|покрывает|охватывает|действует\s+на)\s+(?:(?:все|любые|возможные)"
        r"\s+)?(?:(?:дефекты|брак|неисправности|поломки|повреждения|производственные\s+(?:дефекты|брак))"
        r"(?:\s+(?:и|или)\s+(?:дефекты|брак|неисправности|поломки|повреждения))?"
        r"|(?:бракованн|неисправн|дефектн)\w*\s+(?:товар|продукт|продукци)\w*"
        r"|(?:ремонт|замену)\s+(?:бракованн\w*\s+|неисправн\w*\s+)?(?:товар|продукт|продукци)\w*)" + _WARRANTY_TAIL,
    ],
    "sr": [
        r"garancij\w*\s+(?:pokriva|obuhvata|važi\s+za|se\s+odnosi\s+na|štiti\s+od)\s+(?:(?:sve|eventualne)\s+)?"
        r"(?:(?:nedostatke|nedostatak|kvarove|kvar|greške|oštećenja|fabričke\s+(?:greške|nedostatke))"
        r"(?:\s+(?:i|ili)\s+(?:nedostatke|kvarove|greške|oštećenja))?"
        r"|neispravn\w*\s+proizvod\w*"
        r"|(?:popravku|zamenu|zamjenu)\s+(?:neispravn\w*\s+)?proizvod\w*)" + _WARRANTY_TAIL,
    ],
    "sr-cyrl": [
        r"гаранциј\w*\s+(?:покрива|обухвата|важи\s+за|се\s+односи\s+на|штити\s+од)\s+(?:(?:све|евентуалне)\s+)?"
        r"(?:(?:недостатке|недостатак|кварове|квар|грешке|оштећења|фабричке\s+(?:грешке|недостатке))"
        r"(?:\s+(?:и|или)\s+(?:недостатке|кварове|грешке|оштећења))?"
        r"|неисправн\w*\s+производ\w*"
        r"|(?:поправку|замену)\s+(?:неисправн\w*\s+)?производ\w*)" + _WARRANTY_TAIL,
    ],
}
# Refunded-money wording the per-language "refund" lists above did not reach ("das Geld wird innerhalb von 30
# Tagen erstattet", "pengarna återbetalas", "rahat palautetaan", "novac se vraća").
_REFUND_EXTRA: dict[str, list[str]] = {
    "es": [r"dinero\s+(?:(?:le|les|se|te|nos|será|es|sería|íntegramente|completamente)\s+){0,3}"
           r"(?:devuelv\w*|devolverá\w*|reembolsa\w*|reintegra\w*)"],
    "de": [r"geld\s+(?:(?:wird|werden|wurde|ist|ihnen|dir|euch|voll|vollständig|komplett|sofort|umgehend|innerhalb"
           r"|binnen|von|\d+|tagen|wochen)\s+){0,6}(?:erstattet|zurückerstattet|zurückgezahlt|rückerstattet"
           r"|zurückgegeben)"],
    "nl": [r"geld\s+(?:(?:wordt|worden|is|zal|zullen|u|je|jullie|direct|meteen|volledig|binnen|\d+|dagen|weken)\s+)"
           r"{0,5}(?:terugbetaald|teruggestort|vergoed)"],
    "it": [r"(?:denaro|soldi)\s+(?:(?:è|sarà|saranno|sono|viene|vengono|verrà|verranno|ti|vi|gli|le|interamente"
           r"|completamente|entro|\d+|giorni)\s+){0,5}(?:rimborsat\w*|restituit\w*)"],
    "pt": [r"dinheiro\s+(?:(?:é|será|seria|lhe|lhes|te|integralmente|em|até|\d+|dias)\s+){0,5}"
           r"(?:devolvid\w*|reembolsad\w*|restituíd\w*)"],
    "sv": [r"pengar(?:na)?\s+(?:(?:du|ni|dig|er|kunden|direkt|inom|\d+|dagar|kommer|att|ska|kan|blir|fullt|helt)\s+)"
           r"{0,5}(?:återbetalas|återbetalade?|återförs|betalas\s+tillbaka)"],
    "da": [r"penge(?:ne)?\s+(?:(?:du|i|dig|jer|kunden|straks|inden|for|\d+|dage|vil|blive|bliver|kan|fuldt)\s+){0,5}"
           r"(?:tilbagebetales|tilbagebetalt|refunderes|betales\s+tilbage)"],
    "no": [r"penge(?:ne|r)?\s+(?:(?:du|dere|deg|kunden|straks|innen|\d+|dager|vil|bli|blir|kan|fullt)\s+){0,5}"
           r"(?:tilbakebetales|tilbakebetalt|refunderes|refundert|betales\s+tilbake)"],
    "fi": [r"raha(?:t|si|nne|nsa|mme)?\s+(?:(?:sinulle|teille|asiakkaalle|heti|täysimääräisesti|kokonaan|\d+|päivän"
           r"|kuluessa|sisällä)\s+){0,4}(?:palautetaan|palautuvat|palautuu|hyvitetään|maksetaan\s+takaisin)"],
    "sr": [r"(?:novac|pare)\s+(?:(?:se|će|biće|je|biti|vam|ti|im|odmah|u|potpunosti)\s+){0,3}"
           r"(?:vraća\w*|vrati\w*|refundira\w*)"],
    "sr-cyrl": [r"(?:новац|паре)\s+(?:(?:се|ће|биће|је|бити|вам|ти|им|одмах|у|потпуности)\s+){0,3}"
                r"(?:враћа\w*|врати\w*)"],
}
# Refunded money that comes back again and again, multiplied or with interest, is a return, not a refund
# ("el dinero se devuelve cada mes", "das Geld wird doppelt erstattet", "деньги возвращаются с процентами").
# Refund wording with one of these words anywhere in its clause is not masked, so the money still counts.
_RECURRING: dict[str, list[str]] = {
    "fr": [r"chaque\s+(?:jour|semaine|mois|année)", r"par\s+(?:jour|semaine|mois|an|année)",
           r"tous\s+les\s+(?:jours|mois|ans)", r"toutes\s+les\s+semaines", r"mensuel\w*", r"hebdomadaire\w*",
           r"annuel\w*", r"quotidien\w*", r"doubl\w*", r"tripl\w*", r"(?:deux|trois|dix|\d+)\s+fois", r"intérêts?",
           r"rendement\w*", r"bénéfices?", r"profits?", r"gains?"],
    "es": [r"cada\s+(?:día|semana|mes|año)", r"(?:al|por)\s+(?:día|semana|mes|año)", r"todos\s+los\s+(?:días|meses|años)",
           r"mensual\w*", r"semanal\w*", r"anual\w*", r"diari\w*", r"dobl\w*", r"duplic\w*", r"tripl\w*",
           r"(?:dos|tres|diez|\d+)\s+veces", r"interés\w*", r"intereses", r"rendimiento\w*", r"ganancia\w*",
           r"beneficio\w*"],
    "pt": [r"cada\s+(?:dia|semana|mês|ano)", r"por\s+(?:dia|semana|mês|ano)", r"todos\s+os\s+(?:dias|meses|anos)",
           r"mensal\w*", r"semanal\w*", r"anual\w*", r"diári\w*", r"dobr\w*", r"tripl\w*",
           r"(?:duas|três|dez|\d+)\s+vezes", r"juros", r"rendimento\w*", r"lucro\w*"],
    "it": [r"ogni\s+(?:giorno|settimana|mese|anno)", r"al\s+(?:giorno|mese|anno)", r"a\s+settimana",
           r"tutti\s+i\s+(?:giorni|mesi)", r"mensil\w*", r"settimanal\w*", r"annual\w*", r"giornalier\w*",
           r"raddoppi\w*", r"doppi\w*", r"tripl\w*", r"(?:due|tre|dieci|\d+)\s+volte", r"interess\w*",
           r"rendiment\w*", r"profitt\w*", r"guadagn\w*"],
    "de": [r"jede[nrs]?\s+(?:tag|woche|monat|jahr)", r"(?:pro|im|je)\s+(?:tag|woche|monat|jahr)", r"monatlich\w*",
           r"wöchentlich\w*", r"jährlich\w*", r"täglich\w*", r"doppelt\w*", r"verdoppel\w*",
           r"(?:zwei|drei|vier|zehn|mehr|viel)fach\w*", r"(?:zwei|drei|vier|zehn)mal", r"zinse?n?", r"rendite\w*",
           r"gewinn\w*"],
    "nl": [r"(?:elke|iedere)\s+(?:dag|week|maand)", r"elk\s+jaar", r"per\s+(?:dag|week|maand|jaar)", r"maandelijks",
           r"wekelijks", r"jaarlijks", r"dagelijks", r"verdubbel\w*", r"dubbel\w*", r"driedubbel\w*",
           r"(?:twee|drie|tien|\d+)\s+keer", r"rente", r"rendement\w*", r"winst\w*"],
    "sv": [r"varje\s+(?:dag|vecka|månad|år)", r"(?:per|i|om)\s+(?:dagen|veckan|månaden|året)", r"månatlig\w*",
           r"veckovis", r"årlig\w*", r"dagligen", r"dubbl\w*", r"fördubbl\w*", r"tredubbl\w*",
           r"(?:två|tre|tio|\d+)\s+gånger", r"ränt\w*", r"avkastning\w*", r"vinst\w*"],
    "da": [r"hver\s+(?:dag|uge|måned|år)", r"(?:om|pr\.?|per|i)\s+(?:dagen|ugen|måneden|året)", r"månedlig\w*",
           r"ugentlig\w*", r"årlig\w*", r"dagligt?", r"dobbelt\w*", r"fordobl\w*", r"tredobl\w*",
           r"(?:to|tre|ti|\d+)\s+gange", r"rente\w*", r"afkast\w*", r"overskud\w*"],
    "no": [r"hver\s+(?:dag|uke|måned|år)", r"(?:om|pr\.?|per|i)\s+(?:dagen|uka|uken|måneden|året)", r"månedlig\w*",
           r"ukentlig\w*", r"årlig\w*", r"daglig\w*", r"dobbelt\w*", r"fordobl\w*", r"tredobl\w*",
           r"(?:to|tre|ti|\d+)\s+ganger", r"rente\w*", r"avkastning\w*", r"overskudd\w*"],
    "fi": [r"joka\s+(?:päivä|viikko|kuukausi|vuosi)", r"päivässä", r"viikossa", r"kuukaudessa", r"kuussa",
           r"vuodessa", r"kuukausittain", r"viikoittain", r"vuosittain", r"päivittäin", r"kaksinkertai\w*",
           r"kolminkertai\w*", r"tuplat\w*", r"(?:kaksi|kolme|kymmenen|\d+)\s+kertaa", r"kor(?:ko|on|koa|koj)\w*",
           r"tuot(?:to|on|toa|toj)\w*", r"voit(?:to|on|toa|toj)\w*"],
    "ru": [r"кажд\w*\s+(?:день|недел\w*|месяц|год)", r"в\s+(?:месяц|неделю|день|год)", r"ежемесячн\w*",
           r"еженедельн\w*", r"ежегодн\w*", r"ежедневн\w*", r"вдвое", r"вдвойне", r"втрое", r"удво\w*", r"утроен\w*",
           r"(?:два|три|десять|\d+)\s+раза?", r"процент\w*", r"прибыл\w*", r"доходност\w*"],
    "ru-latn": [r"kazhd\w*\s+(?:den|mesyac|nedel\w*)", r"ezhemesyachn\w*", r"procent\w*", r"pribyl\w*", r"vdvoe"],
    "sr": [r"svak\w*\s+(?:dan|nedelj\w*|mesec\w*|godin\w*)", r"mesečno", r"mjesečno", r"nedeljno", r"godišnje",
           r"dnevno", r"(?:na|po)\s+mesec\w*", r"dupl\w*", r"udvostru\w*", r"trostru\w*",
           r"(?:dva|tri|deset|\d+)\s+puta", r"kamat\w*", r"profit\w*"],
    # Not "dobit" (profit): "dobiti" is also "to get" ("mogu dobiti povraćaj novca").
    "sr-cyrl": [r"свак\w*\s+(?:дан|недељ\w*|месец\w*|годин\w*)", r"месечно", r"недељно", r"годишње", r"дневно",
                r"(?:на|по)\s+месец\w*", r"дупл\w*", r"удвостру\w*", r"(?:два|три|десет|\d+)\s+пута", r"камат\w*",
                r"профит\w*"],
}
for _language, _patterns in _WARRANTY.items():
    LANGUAGES[_language]["consumer"].extend(_patterns)
for _language, _patterns in _REFUND_EXTRA.items():
    LANGUAGES[_language]["refund"].extend(_patterns)
for _language in LANGUAGES:
    LANGUAGES[_language]["recurring"] = _RECURRING.get(_language, [])
# Nearby money is matched per token: "l'argent" is one token, and Finnish inflects "bonus" as "bonuksen".
# Without these, "La garantie couvre les défauts ; l'argent vous est rendu chaque mois." set the warranty aside.
LANGUAGES["fr"]["nearby"].append(r"\w+'(?:argent|fric|profits?|bénéfices?|commissions?|bonus|primes?)")
LANGUAGES["fi"]["nearby"].append(r"bonuk\w*")

# English earnings words also pair with a translated guarantee ("garantiertes income").
_ENGLISH_EARNINGS = [r"earn(?:ed|ing|ings|s)?", r"incomes?", r"salar(?:y|ies)", r"wages?"]
_ENGLISH_MONEY = [r"money", r"profits?", r"revenues?"]
_SHARED_NEARBY = [_CURRENCY, r"cash", r"payouts?", r"commissions?", r"bonus(?:es)?"] + _ENGLISH_MONEY


def _union(key: str, extra: list[str] | None = None) -> re.Pattern[str]:
    parts = [_fold_pattern(p) for language in LANGUAGES.values() for p in language[key]] + list(extra or [])
    if not parts:
        return re.compile(r"(?!x)x")
    body = "|".join(f"(?:{part})" for part in parts)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


GUARANTEE_RE = _union("guarantee")
EARNINGS_RE = _union("earnings", _ENGLISH_EARNINGS + [AMOUNT_PER_PERIOD])
MONEY_RE = _union("money", _ENGLISH_MONEY)
CONSUMER_RE = _union("consumer", _SHARED_CONSUMER)
WARRANTY_RE = re.compile("|".join(f"(?:{_fold_pattern(p)})" for patterns in _WARRANTY.values() for p in patterns))
REFUND_RE = _union("refund")
RECURRING_RE = _union("recurring", [
    r"twice", r"double\w*", r"tripl\w*", r"interest", r"profits?", r"monthly", r"weekly",
    r"(?:every|each|per)\s+(?:day|week|month|year)",
])
# Fable W16 review, Fix A (2026-09-12): refunded money next to a prize, premium, payout, lifestyle word, an addition
# ("plus une voiture neuve", "und ein neues Auto obendrauf", unless it is shipping costs) or an amount of 1,000 or more
# (not a duration or percentage) is not a refund either: "La garantie couvre les défauts ; l'argent vous est rendu,
# plus une voiture neuve." was allowed. Patterns below are written in folded form (see fold()).
_ENGLISH_UNITS = r"(?:business|working|calendar|day|week|month|year|hour)s?"
_GAIN_UNITS = (
    _WARRANTY_UNIT + "|" + _ENGLISH_UNITS
    + r"|jours?|dias?|dage|dagar|dager|paivaa|paivan|tagen?|giorni|semaines?|semanas?|wochen?|weken|veckor|uger|uker"
    r"|viikkoa|mois|meses|mesi|monate|maanden|manader|maneder|kuukautta|ans?|anos|anni|jahre|jaar|ar|vuotta|дн\w*"
    r"|недел\w*|месяц\w*|лет|год\w*|dana|nedelj\w*|meseci|godin\w*|дана|недељ\w*|месеци|годин\w*|arbeitstag\w*"
    r"|werkdag\w*|arkipaiv\w*|jours\s+ouvr\w*|dias\s+(?:habiles|uteis|laborables)|giorni\s+lavorativi|рабочих"
)
_GAIN_AMOUNT_GUARD = (
    rf"(?<![\d.,])(?:\d{{1,3}}(?:[.,]\d{{3}})++|\d{{4,}}+)"
    rf"(?![\d.,]*+\s*+(?:{_GAIN_UNITS}|%|percent|por\s+ciento|pour\s+cent|prozent|procent|per\s+cento|процент\w*|posto"
    rf"|odsto)(?!\w))"
)
_GAIN_SHIPPING = (
    r"(?:frais|port|livraison|expedition|gastos|envio|portes|entrega|spese|spedizione|consegna|versand\w*|liefer\w*"
    r"|verzend\w*|bezorg\w*|frakt\w*|fragt\w*|levering\w*|leverans\w*|toimitus\w*|postikulut|доставк\w*|стоимост\w*"
    r"|troskov\w*|dostav\w*|postarin\w*|трошков\w*|достав\w*|поштарин\w*|shipping|postage|delivery|handling|taxes|vat"
    r"|duties|costs?|fees?|charges?)"
)
_GAIN_PLUS = rf"(?:plus|mas|piu|plys|плюс|obendrauf|bovenop)(?!\s+(?:\S+\s+){{0,2}}{_GAIN_SHIPPING}(?!\w))"
_GAIN_WORDS = [
    # English words also seen in folded text
    r"premiums?", r"uplift", r"extra", r"multipl\w*", r"x\s*\d+", r"\d+\s*x", r"again,?\s+and\s+again", r"then\s+some",
    r"grand", r"\d+k", r"thousands?", r"millions?", r"jackpots?", r"prizes?", r"gifts?", r"rewards?", r"royalt\w*",
    r"upside", r"wealth\w*", r"rich(?:es|er)?", r"millionaires?", r"retire\w*", r"lifestyle", r"freedom",
    r"cars?", r"holidays?", r"vacations?", r"villas?", r"cruises?", r"yachts?", r"rolex", r"mercedes", r"tesla", r"bmw",
    r"bitcoin", r"crypto\w*", r"pay(?:s|ing|out|outs|check|checks)?", r"paid", _GAIN_PLUS,
    # fr
    r"primes?", r"supplements?", r"trimestriel\w*", r"semestriel\w*", r"versements?", r"voitures?", r"maisons?",
    r"riches?", r"millionnaires?", r"retraite", r"encore\s+et\s+encore", r"cinq\s+mille", r"mille", r"milliers",
    # es
    r"primas?", r"premios?", r"adicional\w*", r"trimestral\w*", r"semestral\w*", r"coches?", r"autos?", r"casas?",
    r"ricos?", r"ricas?", r"millonari\w*", r"jubil\w*", r"una\s+y\s+otra\s+vez", r"mil", r"miles", r"millon\w*",
    r"ademas\s+(?:un|una|de\s+un|de\s+una)",
    # pt
    r"adicionais", r"carros?", r"milionari\w*", r"aposentad\w*", r"vez\s+apos\s+vez", r"milhares", r"milh\w*",
    # it
    r"premi", r"premio", r"auto", r"case", r"casa", r"ricc\w*", r"milionari\w*", r"pensione", r"cinquemila", r"mila",
    r"migliaia", r"milion\w*",
    # de
    r"aufschlag\w*", r"pramie\w*", r"zusatzlich\w*", r"vierteljahrlich\w*", r"halbjahrlich\w*", r"auszahlung\w*",
    r"autos?", r"wagen", r"haus", r"hauser", r"reich\w*", r"millionar\w*", r"rente", r"ruhestand",
    r"wieder\s+und\s+wieder", r"tausend\w*", r"\w+tausend", r"million\w*",
    # nl
    r"premie\w*", r"toeslag\w*", r"driemaandelijks\w*", r"maandelijks\w*", r"wekelijks\w*", r"jaarlijks\w*",
    r"uitkering\w*", r"auto'?s?", r"huis", r"huizen", r"rijk\w*", r"miljonair\w*", r"pensioen",
    r"opnieuw\s+en\s+opnieuw", r"duizend", r"\w+duizend", r"miljoen\w*",
    # sv / da / no
    r"tillagg\w*", r"kvartalsvis", r"manatlig\w*", r"utbetalning\w*", r"bil", r"bilar", r"hus", r"rik\w*",
    r"miljonar\w*", r"pension\w*", r"igen\s+och\s+igen", r"igjen\s+og\s+igjen", r"igen\s+og\s+igen", r"tusen",
    r"\w+tusen", r"miljon\w*", r"tillaeg\w*", r"manedlig\w*", r"udbetaling\w*", r"utbetaling\w*", r"biler", r"rig\w*",
    r"millionaer\w*", r"tusind", r"\w+tusind", r"million\w*",
    # fi
    r"lisa\w*", r"palkkio\w*", r"neljannesvuosittain", r"kuukausittain", r"viikoittain", r"vuosittain", r"auto\w*",
    r"talo\w*", r"rika\w*", r"rikas", r"miljonaar\w*", r"elake\w*", r"yha\s+uudelleen", r"tuhat\w*", r"\w+tuhatta",
    r"miljoon\w*",
    # ru (Cyrillic)
    r"надбавк\w*", r"преми\w*", r"дополнительн\w*", r"ежеквартальн\w*", r"выплат\w*", r"машин\w*", r"автомобил\w*",
    r"дом\w*", r"богат\w*", r"миллионер\w*", r"пенси\w*", r"снова\s+и\s+снова", r"тысяч\w*", r"миллион\w*",
    r"удва\w*", r"удво\w*",
    # sr (Latin + Cyrillic)
    r"premij\w*", r"dodat\w*", r"tromesecn\w*", r"mesecn\w*", r"nedeljn\w*", r"godisnj\w*", r"isplat\w*", r"auto",
    r"kola", r"kuc\w*", r"bogat\w*", r"milioner\w*", r"penzij\w*", r"iznova\s+i\s+iznova", r"hiljad\w*", r"milion\w*",
    r"премиј\w*", r"додат\w*", r"тромесечн\w*", r"месечн\w*", r"недељн\w*", r"годишњ\w*", r"исплат\w*", r"ауто",
    r"кола", r"кућ\w*", r"богат\w*", r"милионер\w*", r"пензиј\w*", r"изнова\s+и\s+изнова", r"хиљад\w*", r"милион\w*",
]
GAIN_RE = re.compile(
    RECURRING_RE.pattern + "|(?<!\\w)(?:" + "|".join(f"(?:{_fold_pattern(p)})" for p in _GAIN_WORDS) + ")(?!\\w)"
    + f"|{_GAIN_AMOUNT_GUARD}"
)
PHRASE_RE = _union("phrases")
FALSE_FRIEND_RE = _union("false_friends")
NEARBY_TOKEN_RE = re.compile(
    "|".join(f"(?:{_fold_pattern(p)})" for language in LANGUAGES.values() for p in language["nearby"])
    + "|" + "|".join(f"(?:{p})" for p in _SHARED_NEARBY)
)

# A consumer guarantee is kept when a nearby money word sits in its sentence,
# or within this many words across a sentence end - as in English.
CONSUMER_GUARANTEE_WINDOW = 6
_TOKEN_RE = re.compile(r"(?P<end>[.!?]+(?=\s|$))|[$€£¥]|\d+(?:[.,']\d+)*|\w+(?:'\w+)*")


def _tokens(segment: str) -> list[str | None]:
    return [None if token.group("end") else token.group(0) for token in _TOKEN_RE.finditer(segment)]


def _money_nearby(tokens: list[str | int | None], at: int, step: int) -> bool:
    """Scan one direction: the whole sentence, then only the window beyond it."""
    words = 0
    crossed_sentence_end = False
    index = at + step
    while 0 <= index < len(tokens):
        token = tokens[index]
        index += step
        if token is None:
            crossed_sentence_end = True
            continue
        if crossed_sentence_end and words >= CONSUMER_GUARANTEE_WINDOW:
            return False
        if isinstance(token, str) and NEARBY_TOKEN_RE.fullmatch(token):
            return True
        words += 1
    return False


_CLAUSE_END_RE = re.compile(r"[.!?;:]")


def _mask_refunds(text: str) -> str:
    """Replace refund wording with " refund ", unless its clause speaks of a recurring gain, a prize or a payout."""
    def replace(match: re.Match[str]) -> str:
        # Fable W16 Fix A: only the clause around the refund wording is searched, not the wording itself.
        before = _CLAUSE_END_RE.split(text[:match.start()])[-1]
        after = _CLAUSE_END_RE.split(text[match.end():], maxsplit=1)[0]
        return match.group(0) if GAIN_RE.search(before) or GAIN_RE.search(after) else " refund "

    return REFUND_RE.sub(replace, text)


def _without_consumer_guarantees(text: str) -> str:
    """Blank consumer guarantees that no money word sits next to."""
    masked = _mask_refunds(text)
    matches = list(CONSUMER_RE.finditer(masked))
    if not matches:
        return masked
    tokens: list[str | int | None] = []
    position = 0
    for index, match in enumerate(matches):
        tokens.extend(_tokens(masked[position:match.start()]))
        tokens.append(index)
        position = match.end()
    tokens.extend(_tokens(masked[position:]))
    kept = {
        token for at, token in enumerate(tokens)
        if isinstance(token, int) and (_money_nearby(tokens, at, -1) or _money_nearby(tokens, at, 1))
    }
    # W16b: a warranty is set aside only when every money word in the whole text is refund wording, as in English.
    if any(isinstance(token, str) and NEARBY_TOKEN_RE.fullmatch(token) for token in tokens):
        for index, match in enumerate(matches):
            warranty = WARRANTY_RE.match(masked, match.start())
            if warranty and warranty.end() == match.end():
                kept.add(index)
    parts: list[str] = []
    position = 0
    for index, match in enumerate(matches):
        parts.append(masked[position:match.start()])
        parts.append(match.group(0) if index in kept else " ")
        position = match.end()
    parts.append(masked[position:])
    return "".join(parts)


def contains_translated_income_claim(message: str) -> bool:
    """True when a non-English text makes or asks for an income claim."""
    text = fold(message)
    if PHRASE_RE.search(text):
        return True
    if not GUARANTEE_RE.search(text):
        return False
    searchable = FALSE_FRIEND_RE.sub(" ", text)
    earnings = EARNINGS_RE.search(searchable)
    guarantee_text = text if earnings else _without_consumer_guarantees(text)
    if not GUARANTEE_RE.search(guarantee_text):
        return False
    return bool(earnings or MONEY_RE.search(searchable))
