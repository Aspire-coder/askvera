"""Earnings-projection detector for GENERATED answers only.

Ported from the offline prototype (income_design/proto2_final.py +
income_design/proto2_vocab_final.py). A projection is an earnings
representation attributed to people (you, FBOs, a role, "most", "the
average"):

  P1  strong earn verb (earn / make / take home / bring in / net ...) + a
      money quantity (currency amount, or a magnitude such as "several
      thousand dollars", "a lot of money")
  P2  weak receive verb (receive / get / be paid / collect ...) + money
      quantity + an ESTIMATE marker (roughly, around, typically, on average,
      most, a range "400 to 800") + an earner subject
  P3  estimate + income noun (average income, typical earnings, monthly
      bonus checks) + money quantity
  P4  unquantified promise phrase with no amount (full-time income, replace
      your salary, quit your job ...) -- "financial freedom" / "financial
      independence" phrasing is deliberately NOT included here; it is
      already covered by a different, existing mechanism
  P5  a role label mapped to an estimated amount per period
      ("Supervisor: about $1,500 a month", "| Manager | ~$3,000/mo |")
  P6  verb-free estimate ("FBOs in their second year usually clear $1,000 a
      month")

It is set aside when the earn verb sits in a condition or relative clause
("if an FBO earns EUR 20 ..., EUR 3 is deducted", "FBOs who earn $600
receive a 1099"), or is negated / reported inside a prohibition ("FBOs may
not claim that you will earn $500").

Every language's vocabulary is applied to every text (like
income_claim_translations), on fold()ed text. This vocabulary is
deliberately NOT merged into income_claim_translations.LANGUAGES: _union()
there expects every key to exist in every language, and this module's key
shapes (strong/weak/earner/estimate/noun/rel/conj/refund/...) do not match
that contract, so it stays fully separate. fold(), _fold_pattern() and
_PERIOD (as _TR_PERIOD) are imported from income_claim_translations rather
than duplicated, per the port's design.

Public entry point: detect_earnings_projection(text, language) -> match | None.
"""

from __future__ import annotations

import bisect
import re

from app.risk.policies.income_claim_translations import _PERIOD as _TR_PERIOD
from app.risk.policies.income_claim_translations import _fold_pattern, fold

# ---------------------------------------------------------------------------------------------------------------
# Shared: money quantities
# ---------------------------------------------------------------------------------------------------------------
_NUM = r"\d{1,3}(?:[ .,' ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CUR_WORD = (
    r"dollars?|dolares|dollari|dollaria|dollarin|dollar|usd|us\$|eur|euros?|euro[an]?|evra|evro|evru|евро|евра|евру|chf|gbp|pounds?"
    r"|sterling|kr\.?|kronor|kroner|kronur|sek|nok|dkk|rsd|dinara|dinar[ai]?|динар\w*|rub|рубл\w*|руб\.?|сом\w*|kgs"
    r"|долл\w*|франк\w*|francs?|zl|pln|ron|mdl|dzd|cad|aud|nzd|franken|frank"
)
_CUR_SYM = r"[$€£]|us\$|c\$|a\$"
AMOUNT = (
    rf"(?:\d+(?:[.,]\d)?\s?k(?=\s*(?:a|per|each|every|/)\s*(?:month|week|year|mo)(?!\w))|(?:{_CUR_SYM})\s?(?:{_NUM})(?:\s?(?:k|000))?"
    rf"|(?:{_NUM})\s?(?:k\s?)?(?:{_CUR_SYM}|(?:{_CUR_WORD})(?!\w))"
    rf"|(?:{_NUM})\s?:-"
    rf"|(?:usd|eur|chf|gbp|sek|nok|dkk|rsd|rub|kgs)\s?(?:{_NUM}))"
)
# magnitudes that stand for money without a figure (folded)
_MAGNITUDE = [
    # en
    r"(?:several|a\s+few|many|tens\s+of|hundreds\s+of|thousands\s+of)\s+(?:thousand|hundred)?\s*(?:dollars|euros|pounds|kronor|kroner)",
    r"(?:thousands|hundreds)\s+(?:of\s+)?(?:dollars|euros|pounds|kronor|kroner)?\s*(?:a|per|each|every)\s+(?:month|week|year)",
    r"(?:six|seven|five)[\s-]figures?(?:\s+(?:income|salary|sum))?",
    r"(?:a\s+lot\s+of|lots\s+of|good|big|serious|real|decent|great|huge|significant|substantial)\s+(?:money|cash)",
    r"(?:a|an)\s+(?:good|decent|solid|comfortable|nice|substantial|significant|steady|full[\s-]?time|life[\s-]?changing|great|healthy|generous)\s+(?:income|living|salary|wage|paycheck|pay)",
    r"(?:a\s+)?full[\s-]?time\s+(?:income|salary|wage)", r"a\s+fortune",
    # fr
    r"(?:plusieurs|quelques)\s+milliers\s+d'?\s*(?:euros|dollars|francs)", r"des\s+milliers\s+d'?\s*(?:euros|dollars|francs)",
    r"beaucoup\s+d'argent", r"(?:un\s+)?revenu\s+(?:confortable|important|substantiel|a\s+temps\s+plein|complet|eleve)",
    r"un\s+(?:bon|gros)\s+salaire",
    # es
    r"(?:varios|unos)\s+miles\s+de\s+(?:dolares|euros)", r"miles\s+de\s+(?:dolares|euros)", r"mucho\s+dinero",
    r"(?:un\s+)?(?:ingreso|sueldo|salario)\s+(?:a\s+tiempo\s+completo|considerable|importante|alto|comodo)",
    r"un\s+buen\s+(?:sueldo|salario|ingreso)",
    # it
    r"(?:diverse|alcune|parecchie)\s+migliaia\s+di\s+(?:euro|dollari|franchi)", r"migliaia\s+di\s+(?:euro|dollari)",
    r"(?:molti|tanti)\s+soldi", r"molto\s+denaro", r"un\s+(?:buon|ottimo)\s+(?:reddito|stipendio|guadagno)",
    r"(?:un\s+)?(?:reddito|stipendio)\s+(?:a\s+tempo\s+pieno|pieno|elevato|consistente)",
    # de
    r"(?:mehrere|einige\s+)?tausend(?:e)?\s+(?:euro|dollar|franken)", r"viel\s+geld",
    r"ein\s+(?:gutes|hohes|solides|volles|ordentliches)\s+(?:einkommen|gehalt)", r"(?:ein\s+)?vollzeiteinkommen",
    # nl
    r"(?:enkele|een\s+paar|duizenden)\s+(?:duizend\s+)?(?:euro|dollar)", r"veel\s+geld",
    r"een\s+(?:goed|hoog|fatsoenlijk|volledig)\s+(?:inkomen|salaris)", r"(?:een\s+)?voltijds\s+inkomen",
    # sv / da / no
    r"(?:flera|några|tusentals)\s+(?:tusen\s+)?(?:kronor|euro|dollar)", r"mycket\s+pengar",
    r"en\s+(?:bra|god|hög|heltids)\s*(?:inkomst|lön)", r"(?:flere|nogle|tusindvis\s+af)\s+(?:tusind\s+)?(?:kroner|euro|dollars?)",
    r"mange\s+penge", r"en\s+(?:god|høj|fuldtids)\s*(?:indkomst|løn)", r"(?:flere|noen|tusenvis\s+av)\s+(?:tusen\s+)?(?:kroner|euro|dollar)",
    r"mye\s+penger", r"en\s+(?:god|høy|heltids)\s*(?:inntekt|lønn)",
    # fi
    r"(?:useita|muutamia|tuhansia)\s+(?:tuhansia\s+)?(?:euroja|dollareita)", r"paljon\s+rahaa",
    r"(?:hyvat|hyvia|korkeat)\s+tulot", r"kokopaivaiset\s+tulot",
    # ru
    r"(?:несколько|тысячи)\s+(?:тысяч\s+)?(?:долларов|евро|рублей|сомов)", r"много\s+денег", r"большие\s+деньги",
    r"(?:хороший|высокий|стабильный)\s+доход",
    # sr
    r"(?:nekoliko|hiljade)\s+(?:hiljada\s+)?(?:evra|dolara|dinara)", r"mnogo\s+novca", r"(?:dobar|visok)\s+(?:prihod|zaradu|platu)",
    r"(?:неколико|хиљаде)\s+(?:хиљада\s+)?(?:евра|долара|динара)", r"много\s+новца",
]
MONEY_RE = re.compile(
    r"(?<!\w)(?:" + AMOUNT + "|" + "|".join(_fold_pattern(p) for p in _MAGNITUDE) + r")(?!\w)"
)
_PERCENT_OR_CC = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|percent|prosent|procent|prozent|pour\s*cent|por\s*ciento|per\s*cento|cc\b)")

# ---------------------------------------------------------------------------------------------------------------
# Per language vocabulary (natural spelling; folded at compile time)
#   strong   - finite forms of "earn / make money / take home" whose object is money
#   weak     - receive / get / be paid: count only with an estimate marker and an earner subject
#   earner   - people or roles the earnings are attributed to (subject)
#   estimate - approximation / typicality / population / potential markers
#   noun     - income nouns for the "average income is ..." shape
#   cond     - words opening a condition or relative clause
#   neg      - negations that govern the verb (checked in a 3-token window before it)
#   report   - prohibition / reporting context that makes the clause a quotation of a banned claim
#   modal    - auxiliaries that mark a main clause after an unpunctuated condition
#   promise  - unquantified income promises
# ---------------------------------------------------------------------------------------------------------------
L: dict[str, dict[str, list[str]]] = {}
L["en"] = dict(
    strong=[r"earns?", r"earning(?=\s)", r"(?:make|makes|making)(?=\s+(?:\w+\s+){0,3}?(?:[$€£\d]|a\s+lot|lots|good|big|serious|real|decent|great|huge|significant|substantial|several|thousands|hundreds|six|five|seven|a\s+(?:good|decent|solid|comfortable|nice|full)|money|a\s+fortune))", r"takes?\s+home", r"taking\s+home", r"took\s+home",
            r"brings?\s+(?:in|home)", r"bringing\s+(?:in|home)", r"brought\s+(?:in|home)", r"nets", r"netting", r"pockets?", r"pocketing",
            r"(?:have|has|had|'ve)\s+(?:\w+\s+)?(?:earned|made)", r"(?:be|are|is|'re|would\s+be|'d\s+be)\s+looking\s+at", r"earn", r"earned(?=\s+(?:about|around|roughly|over|more|up|nearly|almost|close|some|an?\s+average|[$€£\d]))",
            r"made(?=\s+(?:about|around|roughly|over|more|nearly|almost|close|some|[$€£\d]))"],
    weak=[r"receives?", r"receiving", r"received", r"gets?", r"getting", r"got", r"collects?", r"(?:are|is|be|being|get|gets|got|were|was)\s+paid", r"draws?"],
    earner=[r"you", r"you'll", r"you're", r"your", r"they", r"we", r"i", r"he", r"she", r"people", r"someone", r"anyone",
            r"everyone", r"everybody", r"members?", r"fbos?", r"fbo's", r"distributors?", r"(?:business\s+)?owners?", r"partners?",
            r"sellers?", r"supervisors?", r"managers?", r"leaders?", r"recruits?", r"newcomers?", r"beginners?", r"earners?",
            r"consultants?", r"reps?", r"representatives?", r"associates?", r"most", r"many", r"participants?", r"families",
            r"mums?", r"moms?", r"students?", r"retirees?"],
    estimate=[r"about", r"around", r"roughly", r"approximately", r"approx", r"nearly", r"almost", r"close\s+to", r"typically",
              r"typical", r"usually", r"usual", r"normally", r"generally", r"commonly", r"on\s+average", r"average", r"averages?",
              r"median", r"most", r"majority", r"many", r"can\s+expect", r"could", r"might", r"potentially", r"potential",
              r"realistic(?:ally)?", r"expected?", r"expect(?:s|ing)?", r"as\s+much\s+as", r"several", r"often", r"regularly", r"easily", r"some"],
    noun=[r"incomes?", r"earnings", r"pay(?:checks?|cheques?)", r"salar(?:y|ies)", r"wages?", r"bonus\s+checks?",
          r"bonus\s+cheques?", r"take[\s-]home"],
    cond=[r"if", r"when", r"whenever", r"once", r"unless", r"until", r"who", r"that", r"which", r"whose", r"where",
          r"whether", r"how\s+much", r"what"],
    neg=[r"not", r"never", r"no", r"cannot", r"can't", r"can't", r"don't", r"doesn't", r"won't", r"didn't", r"nobody",
         r"none", r"neither", r"nor", r"without"],
    report=[r"prohibit\w*", r"forbid\w*", r"banned?", r"not\s+(?:allowed|permitted)", r"may\s+not", r"must\s+not",
            r"must\s+never", r"should\s+not", r"shouldn't", r"never\s+(?:say|claim|tell|promise|state|suggest|imply)",
            r"(?:do|does)\s+not\s+(?:say|claim|tell|promise|state|suggest|imply|represent)",
            r"(?:don't|doesn't)\s+(?:say|claim|tell|promise|state|suggest|imply|represent)",
            r"(?:cannot|can't|can't)\s+(?:say|claim|tell|promise|state|suggest|imply|represent|predict|guarantee)",
            r"misleading", r"deceptive", r"false", r"illegal", r"unlawful", r"(?:such\s+as|like)\s*[\"'“‘]",
            r"claims?\s+(?:like|such\s+as|that)", r"representations?\s+(?:of|about|regarding)\s+(?:income|earnings)", r"(?:income|earnings)\s+(?:claims?|representations?)", r"implied", r"such\s+representations", r"representations?\s+and/?\s*or\s+images", r"images\s+used\s+to\s+show", r"statements?\s+(?:like|such\s+as|that)", r"examples?\s+(?:of|include)"],
    modal=[r"will", r"'ll", r"can", r"could", r"would", r"should", r"may", r"might", r"then"],
    promise=[r"full[\s-]?time\s+income", r"replac(?:e|es|ed|ing)\s+(?:your|my|their|his|her|a|the)\s+(?:(?:full[\s-]?time|day)\s+jobs?|jobs?|salar(?:y|ies)|incomes?|paychecks?|wages?)", r"(?:income|earnings|pay|success)\s+(?:is|are|will\s+be)\s+(?:\w+\s+)?(?:assured|certain|secured?)", r"make\s+(?:you|them|people|anyone|everyone)\s+(?:financially\s+(?:independent|free)|rich|wealthy)", r"(?:income|earnings|money)\s+(?:\w+\s+){0,2}life[\s-]?changing", r"(?:double|triple)s?\s+(?:your|their|his|her|my)\s+(?:money|investment|income)", r"(?:anyone|everyone|whoever)\s+(?:who\s+)?(?:\w+\s+){0,4}(?:does|do)\s+(?:very\s+|really\s+|extremely\s+)?well",
             r"quit\s+(?:your|my|their|his|her)\s+(?:day\s+)?jobs?", r"retire\s+(?:early|young|rich|in\s+\d+)",
             r"passive\s+income", r"residual\s+income",
             r"life[\s-]?changing\s+(?:income|money)", r"unlimited\s+(?:income|earnings|earning\s+potential)",
             r"six[\s-]figure\s+(?:income|salary|earner)", r"never\s+(?:have\s+to\s+)?work\s+again", r"(?:get|become)\s+rich",
             r"(?:enjoy\w*|liv(?:e|es|ing)|lead\w*|ha(?:ve|s)|afford\w*|achiev\w*|gives?|offers?|provides?|brings?)\s+(?:\w+\s+){0,3}(?:luxury|lavish|luxurious|dream)\s+(?:lifestyle|life|cars?|house|home|holidays?|vacations?)",
             r"make\s+a\s+(?:good\s+|full\s+|comfortable\s+)?living", r"(?:support|provide\s+for)\s+(?:your|my|their)\s+family",
             r"live\s+off\s+(?:this|it|your\s+(?:bonuses|business))", r"be\s+your\s+own\s+boss\s+and\s+(?:earn|make)"],
)
L["fr"] = dict(
    strong=[r"gagn(?:e|es|ent|ez|ons|era|eras|erez|erons|eront|erait|eraient|eriez|ait|aient|iez|ions)",
            r"(?:a|ont|avez|avons|as)\s+(?:\w+\s+)?gagne_pp", r"gagner", r"toucher", r"touch(?:e|es|ent|ez|era|erez|eront|erait|eraient)", r"empoch\w+"],
    weak=[r"recoi(?:s|t|vent)", r"recevez", r"recevons", r"recevr\w+", r"percoi(?:s|t|vent)", r"percevez", r"percevr\w+",
          r"(?:est|sont|etes|serez|seront|sera)\s+payes?"],
    earner=[r"vous", r"tu", r"ils", r"elles", r"nous", r"je", r"on", r"fbo", r"distributeurs?", r"membres?",
            r"superviseurs?", r"managers?", r"la\s+plupart", r"beaucoup", r"gens", r"personnes", r"partenaires?",
            r"vendeurs?", r"entrepreneurs?", r"conseillers?"],
    estimate=[r"environ", r"a\s+peu\s+pres", r"approximativement", r"en\s+moyenne", r"moyenne", r"moyen", r"typiquement",
              r"generalement", r"habituellement", r"normalement", r"la\s+plupart", r"pres\s+de", r"quelque", r"pouvez",
              r"pourrez", r"pourriez", r"peut", r"peuvent", r"pourra", r"pourraient", r"souvent", r"facilement",
              r"typique", r"plusieurs", r"autour\s+de", r"dans\s+les"],
    noun=[r"revenus?", r"gains", r"salaires?", r"remuneration"],
    cond=[r"si", r"s'", r"quand", r"lorsque", r"lorsqu'", r"des\s+que", r"une\s+fois\s+que", r"qui", r"que", r"qu'",
          r"combien", r"dont"],
    neg=[r"ne", r"n'", r"jamais", r"aucun\w*", r"pas", r"sans", r"personne", r"nul\w*"],
    report=[r"interdi\w*", r"prohib\w*", r"pas\s+(?:le\s+)?droit", r"trompeu\w*", r"fausses?", r"faux", r"illega\w*",
            r"ne\s+(?:doit|doivent|devez|peut|peuvent|pouvez)\s+(?:pas|jamais)", r"n'?\s*affirm\w*\s+(?:pas|jamais)",
            r"telles?\s+que\s*[\"«]", r"comme\s+[\"«]", r"par\s+exemple\s+[\"«]", r"(?:affirmations?|declarations?)\s+(?:comme|telles|selon)"],
    modal=[r"allez", r"va", r"vont", r"pouvez", r"pourrez", r"pourriez", r"peut", r"peuvent", r"pourra", r"alors"],
    promise=[r"revenus?\s+a\s+temps\s+plein", r"remplacer\s+(?:votre|ton|son|leur|mon)\s+(?:salaire|emploi|travail|revenu)",
             r"quitter\s+(?:votre|ton|son|leur|mon)\s+(?:emploi|travail|job)", r"prendre\s+(?:votre|ta|sa)\s+retraite\s+(?:tot|anticipee|jeune)",
             r"revenus?\s+passifs?", r"revenus?\s+residuels?",
             r"revenus?\s+illimites?", r"(?:devenir|etre)\s+riches?", r"(?:style|train)\s+de\s+vie\s+(?:de\s+luxe|luxueux|de\s+reve)",
             r"gagner\s+(?:votre|ta|sa|leur)\s+vie", r"ne\s+plus\s+jamais\s+travailler"],
)
L["es"] = dict(
    strong=[r"gan(?:a|as|an|amos|ais|ara|aras|aran|aremos|aria|arias|arian|o|aste|aron)", r"(?:ha|han|has|hemos)\s+ganado", r"ganar", r"(?:se|te|me|nos)\s+lleva(?:n|s|mos|ra|ran|ras)?", r"llevarse", r"llevarte",
            r"embols\w+"],
    weak=[r"recib(?:e|es|en|imos|ira|iras|iran|iria|irian|io|ieron)", r"percib(?:e|es|en|ira|iran|iria)",
          r"cobr(?:a|as|an|ara|aran|aria)", r"(?:se\s+les?\s+)?paga(?:n|ra|ran)?"],
    earner=[r"usted(?:es)?", r"tu", r"ellos", r"ellas", r"nosotros", r"yo", r"la\s+mayoria", r"fbo", r"distribuidor(?:es)?",
            r"miembros?", r"supervisor(?:es)?", r"gerentes?", r"personas", r"gente", r"socios?", r"vendedor(?:es)?",
            r"muchos", r"emprendedor(?:es)?"],
    estimate=[r"aproximadamente", r"alrededor\s+de", r"unos", r"unas", r"cerca\s+de", r"en\s+promedio", r"promedio",
              r"normalmente", r"generalmente", r"tipicamente", r"habitualmente", r"la\s+mayoria", r"puede", r"pueden",
              r"podra", r"podran", r"podria", r"podrian", r"a\s+menudo", r"facilmente", r"tipico", r"varios", r"media"],
    noun=[r"ingresos?", r"ganancias", r"salarios?", r"sueldos?"],
    cond=[r"si", r"cuando", r"una\s+vez\s+que", r"que", r"quien(?:es)?", r"cuanto", r"cuyo"],
    neg=[r"no", r"nunca", r"jamas", r"ningun\w*", r"nadie", r"sin", r"ni"],
    report=[r"prohib\w*", r"no\s+(?:se\s+)?(?:permite|permiten|puede|pueden|debe|deben)", r"engano\w*", r"falsa?s?",
            r"ilegal\w*", r"como\s+[\"«]", r"tales\s+como\s*[\"«]", r"(?:afirmaciones|declaraciones)\s+(?:como|de\s+que)"],
    modal=[r"va", r"vas", r"van", r"puede", r"pueden", r"podra", r"podran", r"podria", r"entonces"],
    promise=[r"ingresos?\s+(?:a|de)\s+tiempo\s+completo", r"reemplazar\s+(?:tu|su|mi)\s+(?:salario|sueldo|trabajo|empleo)",
             r"dejar\s+(?:tu|su|mi)\s+(?:trabajo|empleo)", r"jubilarte\s+(?:joven|pronto|antes)", r"jubilarse\s+(?:joven|pronto|antes)",
             r"ingresos?\s+pasivos?", r"ingresos?\s+residual\w*",
             r"ingresos?\s+ilimitados?", r"hacerte\s+rico", r"(?:volverte|hacerse)\s+rico", r"estilo\s+de\s+vida\s+(?:de\s+lujo|lujoso)",
             r"ganarte\s+la\s+vida", r"ganarse\s+la\s+vida", r"nunca\s+mas\s+trabajar"],
)
L["it"] = dict(
    strong=[r"guadagn(?:a|i|ano|iamo|ate|era|erai|eranno|erete|eremo|erebbe|erebbero|avano|ava)", r"(?:ha|hanno|hai|abbiamo)\s+guadagnato", r"guadagnare",
            r"intasc\w+", r"port(?:a|ano|i)\s+a\s+casa"],
    weak=[r"ricev(?:e|i|ono|iamo|ete|era|erai|eranno|erebbe|erebbero)", r"percepi\w+", r"percepisc\w+",
          r"(?:viene|vengono|verra|verranno|sono|e)\s+pagat[oi]"],
    earner=[r"tu", r"voi", r"lei", r"loro", r"noi", r"io", r"la\s+maggior\s+parte", r"fbo", r"distributori?", r"membri",
            r"supervisori?", r"manager", r"persone", r"gente", r"incaricati", r"molti", r"venditori?", r"imprenditori?"],
    estimate=[r"circa", r"intorno\s+a[i]?", r"all'incirca", r"approssimativamente", r"in\s+media", r"media", r"medio",
              r"tipicamente", r"generalmente", r"di\s+solito", r"normalmente", r"solitamente", r"la\s+maggior\s+parte",
              r"puo", r"possono", r"potra", r"potranno", r"potrebbe", r"potrebbero", r"spesso", r"facilmente", r"tipico",
              r"diverse", r"quasi"],
    noun=[r"reddit[oi]", r"guadagni", r"stipendi[oi]?", r"entrate"],
    cond=[r"se", r"quando", r"una\s+volta\s+che", r"che", r"chi", r"quanto", r"il\s+cui"],
    neg=[r"non", r"mai", r"nessun\w*", r"senza", r"ne"],
    report=[r"vietat\w*", r"proibit\w*", r"non\s+(?:e|sono)\s+(?:consentit|permess)\w*", r"non\s+(?:puo|possono|deve|devono)",
            r"ingannevol\w*", r"fals[aei]", r"illegal\w*", r"come\s+[\"«]", r"(?:affermazioni|dichiarazioni)\s+(?:come|del\s+tipo)"],
    modal=[r"puoi", r"potrai", r"potresti", r"puo", r"possono", r"potra", r"potranno", r"allora"],
    promise=[r"reddito\s+a\s+tempo\s+pieno", r"sostituire\s+(?:il\s+)?(?:tuo|suo|mio)\s+(?:stipendio|lavoro|reddito)",
             r"lasciare\s+(?:il\s+)?(?:tuo|suo|mio)\s+lavoro", r"andare\s+in\s+pensione\s+(?:presto|giovane)",
             r"reddito\s+passivo", r"rendita\s+passiva",
             r"reddito\s+residuale", r"guadagni\s+illimitati", r"diventare\s+ricc[oih]", r"stile\s+di\s+vita\s+(?:di\s+lusso|lussuoso)",
             r"non\s+lavorare\s+mai\s+piu"],
)
L["de"] = dict(
    strong=[r"verdien(?:e|en|st|t)", r"verdient(?:e|en|est|et)(?=\s+(?:\w+\s+){0,2}(?:[€$£]|\d|eur|usd|chf))", r"(?:hat|haben|hast|habt)\s+(?:\w+\s+){0,4}verdient", r"nimmt\s+(?:\w+\s+){0,4}ein",
            r"nehmen\s+(?:\w+\s+){0,4}ein", r"einnehmen", r"mit\s+nach\s+hause"],
    weak=[r"rechnen", r"erh(?:a|ä)lt", r"erhalten", r"erhaltst", r"bekomm(?:e|en|st|t)", r"bekommt", r"ausgezahlt"],
    earner=[r"sie", r"du", r"ihr", r"wir", r"ich", r"man", r"die\s+meisten", r"viele", r"fbos?", r"vertriebspartner\w*",
            r"berater\w*", r"supervisor(?:en|s)?", r"manager", r"mitglieder\w*", r"leute", r"menschen", r"geschaftspartner\w*",
            r"unternehmer\w*"],
    estimate=[r"etwa", r"ungef(?:a|ä)hr", r"rund", r"circa", r"ca", r"durchschnittlich", r"im\s+durchschnitt", r"im\s+schnitt",
              r"typischerweise", r"normalerweise", r"gew(?:o|ö)hnlich", r"meist\w*", r"in\s+der\s+regel", r"k(?:o|ö)nnen",
              r"kannst", r"kann", r"k(?:o|ö)nnten", r"oft", r"leicht", r"typisch\w*", r"mehrere", r"fast", r"knapp"],
    noun=[r"\w*einkommen", r"\w*verdienst\w*", r"gehalt", r"geh(?:a|ä)lter", r"einnahmen"],
    cond=[r"wenn", r"falls", r"sobald", r"sofern", r"der", r"die", r"das", r"welche[rsn]?", r"wer", r"wie\s*viel", r"was"],
    neg=[r"nicht", r"kein\w*", r"nie", r"niemals", r"niemand", r"ohne"],
    report=[r"verboten", r"untersagt", r"nicht\s+(?:erlaubt|gestattet|zul(?:a|ä)ssig)", r"d(?:u|ü)rfen\s+(?:\w+\s+){0,3}(?:nicht|keine)",
            r"irref(?:u|ü)hrend\w*", r"falsch\w*", r"unzul(?:a|ä)ssig\w*", r"rechtswidrig\w*", r"wie\s+[\"„»]", r"etwa\s+[\"„»]",
            r"(?:aussagen|behauptungen)\s+wie"],
    modal=[r"werden", r"wirst", r"wird", r"k(?:o|ö)nnen", r"kannst", r"kann", r"k(?:o|ö)nnten", r"dann"],
    promise=[r"vollzeiteinkommen", r"(?:ihr|dein|sein)\s+gehalt\s+ersetzen", r"(?:ihren|deinen|seinen)\s+job\s+(?:kundigen|aufgeben|an\s+den\s+nagel)",
             r"fr(?:u|ü)h\s+in\s+rente", r"passives?\s+einkommen",
             r"residualeinkommen", r"unbegrenzte\w*\s+(?:einkommen|verdienst\w*)", r"reich\s+werden", r"luxus(?:leben|lebensstil)",
             r"nie\s+wieder\s+arbeiten"],
)
L["nl"] = dict(
    strong=[r"verdien(?:t|en)?", r"verdiende(?:n)?(?=\s+(?:\w+\s+){0,2}(?:[€$£]|\d|eur|usd))", r"(?:heeft|hebben|heb|hebt)\s+(?:\w+\s+){0,4}verdiend", r"(?:houdt|houden|hou)\s+(?:\S+\s+){0,6}?over"],
    weak=[r"ontvang(?:t|en|st)?", r"ontving(?:en)?", r"krijg(?:t|en)?", r"kreeg(?:en)?", r"(?:wordt|worden)\s+(?:\w+\s+){0,3}uitbetaald"],
    earner=[r"u", r"je", r"jij", r"jullie", r"ze", r"zij", r"we", r"wij", r"ik", r"men", r"de\s+meeste", r"veel", r"fbo'?s?",
            r"distributeurs?", r"leden", r"supervisors?", r"managers?", r"mensen", r"verkopers?", r"ondernemers?", r"partners?"],
    estimate=[r"ongeveer", r"rond(?:om)?", r"circa", r"ca", r"gemiddeld", r"doorgaans", r"normaal\s+gesproken", r"meestal",
              r"gewoonlijk", r"typisch", r"de\s+meeste", r"kan", r"kunnen", r"kunt", r"zou", r"zouden", r"vaak",
              r"makkelijk", r"gemakkelijk", r"enkele", r"bijna", r"zo'?n"],
    noun=[r"\w*inkomen\w*", r"\w*inkomsten", r"salaris", r"verdiensten?"],
    cond=[r"als", r"wanneer", r"indien", r"zodra", r"die", r"dat", r"wie", r"hoeveel", r"wat"],
    neg=[r"niet", r"geen", r"nooit", r"niemand", r"zonder"],
    report=[r"verboden", r"niet\s+(?:toegestaan|toegelaten)", r"mogen\s+(?:\w+\s+){0,3}(?:niet|geen)", r"misleidend\w*",
            r"onjuist\w*", r"vals\w*", r"onwettig\w*", r"zoals\s+[\"„']", r"(?:uitspraken|beweringen|claims)\s+(?:zoals|als)"],
    modal=[r"zal", r"zult", r"zullen", r"gaat", r"gaan", r"kan", r"kunt", r"kunnen", r"zou", r"dan"],
    promise=[r"voltijds\s+inkomen", r"fulltime\s+inkomen", r"(?:je|uw|zijn|haar)\s+(?:salaris|baan)\s+(?:vervangen|opzeggen)",
             r"(?:je|uw)\s+baan\s+(?:op\s+te\s+zeggen|opzeggen)", r"vroeg\s+met\s+pensioen", r"passie\w*\s+inkomen", r"residueel\s+inkomen", r"onbeperkt\w*\s+inkomen",
             r"rijk\s+worden", r"luxe\s+levensstijl", r"nooit\s+meer\s+(?:hoeven\s+)?(?:te\s+)?werken"],
)
L["sv"] = dict(
    strong=[r"tj(?:a|ä)nar", r"tj(?:a|ä)na", r"tj(?:a|ä)nade", r"(?:har|hade)\s+(?:\w+\s+){0,3}tj(?:a|ä)nat", r"drar\s+in"],
    weak=[r"f(?:a|å)r", r"fick", r"erh(?:a|å)ller", r"erh(?:o|ö)ll", r"(?:utbetalas|betalas\s+ut)"],
    earner=[r"du", r"ni", r"de", r"vi", r"jag", r"man", r"de\s+flesta", r"m(?:a|å)nga", r"fbo:?\w*", r"distribut(?:o|ö)rer",
            r"medlemmar", r"supervisors?", r"managers?", r"personer", r"folk", r"f(?:o|ö)rs(?:a|ä)ljare"],
    estimate=[r"ungef(?:a|ä)r", r"runt", r"cirka", r"ca", r"omkring", r"i\s+genomsnitt", r"genomsnitt\w*", r"vanligtvis",
              r"normalt", r"oftast", r"typiskt", r"de\s+flesta", r"kan", r"kunna", r"skulle", r"ofta", r"l(?:a|ä)tt",
              r"flera", r"n(?:a|ä)stan"],
    noun=[r"\w*inkomst\w*", r"l(?:o|ö)n(?:en)?", r"f(?:o|ö)rtj(?:a|ä)nst\w*"],
    cond=[r"om", r"n(?:a|ä)r", r"s(?:a|å)\s+snart", r"som", r"vem", r"hur\s+mycket", r"vad"],
    neg=[r"inte", r"ej", r"aldrig", r"ingen", r"inget", r"inga", r"utan"],
    report=[r"f(?:o|ö)rbjud\w*", r"inte\s+till(?:a|å)tet", r"f(?:a|å)r\s+(?:\w+\s+){0,2}(?:inte|aldrig)", r"vilseledande",
            r"falsk\w*", r"olagli\w*", r"s(?:a|å)som\s+[\"”']", r"(?:p(?:a|å)st(?:a|å)enden|uttalanden)\s+som"],
    modal=[r"kommer", r"kan", r"kunna", r"skulle", r"ska", r"s(?:a|å)"],
    promise=[r"heltidsinkomst", r"ers(?:a|ä)tta\s+(?:din|er|sin)\s+(?:l(?:o|ö)n|inkomst|jobb)", r"s(?:a|ä)ga\s+upp\s+(?:dig|er)",
             r"sluta\s+(?:ditt|ert|sitt)\s+jobb", r"g(?:a|å)\s+i\s+pension\s+tidigt", r"passiv\w*\s+inkomst\w*", r"obegr(?:a|ä)nsad\w*\s+inkomst\w*", r"bli\s+rik",
             r"lyxliv\w*", r"aldrig\s+mer\s+jobba"],
)
L["da"] = dict(
    strong=[r"tjen(?:er|te)", r"tjene", r"(?:har|havde)\s+(?:\w+\s+){0,3}tjent", r"tjent"],
    weak=[r"f(?:a|å)r", r"fik", r"modtag(?:er)?", r"modtog", r"(?:udbetales|bliver\s+udbetalt)"],
    earner=[r"du", r"i", r"de", r"vi", r"jeg", r"man", r"de\s+fleste", r"mange", r"fbo'?\w*", r"distribut(?:o|ø)rer",
            r"medlemmer", r"supervisors?", r"managers?", r"personer", r"folk", r"s(?:a|æ)lgere"],
    estimate=[r"cirka", r"ca", r"omkring", r"ca\.", r"i\s+gennemsnit", r"gennemsnitlig\w*", r"typisk", r"normalt",
              r"s(?:a|æ)dvanligvis", r"oftest", r"de\s+fleste", r"kan", r"kunne", r"vil\s+kunne", r"ofte", r"let", r"nemt",
              r"flere", r"n(?:a|æ)sten", r"rundt\s+regnet"],
    noun=[r"\w*indkomst\w*", r"l(?:o|ø)n(?:nen)?", r"\w*indtjening\w*", r"fortjeneste"],
    cond=[r"hvis", r"n(?:a|å)r", r"s(?:a|å)\s+snart", r"som", r"der", r"hvem", r"hvor\s+meget", r"hvad"],
    neg=[r"ikke", r"aldrig", r"ingen", r"intet", r"uden"],
    report=[r"forbud\w*", r"forbudt", r"ikke\s+tilladt", r"m(?:a|å)\s+(?:\w+\s+){0,2}(?:ikke|aldrig)", r"vildledende",
            r"falsk\w*", r"ulovli\w*", r"s(?:a|å)som\s+[\"”']", r"(?:p(?:a|å)stande|udsagn)\s+som"],
    modal=[r"vil", r"kan", r"kunne", r"skal", r"s(?:a|å)"],
    promise=[r"fuldtidsindkomst", r"erstatte\s+(?:din|jeres|sin)\s+(?:l(?:o|ø)n|indkomst|job)", r"sige\s+(?:dit|jeres|sit)\s+job\s+op",
             r"g(?:a|å)\s+tidligt\s+p(?:a|å)\s+pension", r"passiv\w*\s+indkomst\w*", r"ubegr(?:a|æ)nset\w*\s+indkomst\w*", r"blive\s+rig", r"luksusliv\w*",
             r"aldrig\s+mere\s+arbejde"],
)
L["no"] = dict(
    strong=[r"tjen(?:er|te)", r"tjene", r"(?:har|hadde)\s+(?:\w+\s+){0,3}tjent", r"tjent"],
    weak=[r"f(?:a|å)r", r"fikk", r"mottar", r"mottok", r"(?:utbetales|blir\s+utbetalt)"],
    earner=[r"du", r"dere", r"de", r"vi", r"jeg", r"man", r"de\s+fleste", r"mange", r"fbo'?\w*", r"distribut(?:o|ø)rer",
            r"medlemmer", r"supervisorer", r"managere?", r"personer", r"folk", r"selgere"],
    estimate=[r"cirka", r"ca", r"omtrent", r"rundt", r"i\s+gjennomsnitt", r"gjennomsnittlig\w*", r"typisk", r"normalt",
              r"vanligvis", r"oftest", r"de\s+fleste", r"kan", r"kunne", r"vil\s+kunne", r"ofte", r"lett", r"enkelt",
              r"flere", r"nesten"],
    noun=[r"\w*inntekt\w*", r"l(?:o|ø)nn(?:en)?", r"\w*inntjening\w*", r"fortjeneste"],
    cond=[r"hvis", r"dersom", r"n(?:a|å)r", r"s(?:a|å)\s+snart", r"som", r"hvem", r"hvor\s+mye", r"hva"],
    neg=[r"ikke", r"aldri", r"ingen", r"intet", r"uten"],
    report=[r"forbud\w*", r"forbudt", r"ikke\s+tillatt", r"m(?:a|å)\s+(?:\w+\s+){0,2}(?:ikke|aldri)", r"villedende",
            r"falsk\w*", r"ulovli\w*", r"slik\s+som\s+[\"”']", r"(?:p(?:a|å)stander|utsagn)\s+som"],
    modal=[r"vil", r"kan", r"kunne", r"skal", r"s(?:a|å)"],
    promise=[r"heltidsinntekt", r"erstatte\s+(?:din|deres|sin)\s+(?:l(?:o|ø)nn|inntekt|jobb)", r"si\s+opp\s+(?:jobben|deg)",
             r"g(?:a|å)\s+av\s+med\s+pensjon\s+tidlig", r"passiv\w*\s+inntekt\w*", r"ubegrenset\w*\s+inntekt\w*", r"bli\s+rik", r"luksusliv\w*", r"aldri\s+mer\s+jobbe"],
)
L["fi"] = dict(
    strong=[r"ansaits(?:e|et|ee|emme|ette|evat)", r"ansaitsi(?:t|mme|tte|vat)?", r"ansaitsisi\w*", r"ansaita",
            r"tienaa\w*", r"ansaitsemaan", r"tienasi\w*", r"(?:on|ovat|olet)\s+ansainnut\w*"],
    weak=[r"saa(?:t|mme|tte|vat)?", r"sai(?:t|vat)?", r"saisi\w*", r"(?:maksetaan|maksettaisiin)"],
    earner=[r"sina", r"sa", r"te", r"he", r"me", r"mina", r"useimmat", r"monet", r"fbo:?\w*", r"jakelij\w+", r"jasen\w*",
            r"supervisor\w*", r"manager\w*", r"ihmiset", r"myyj\w+", r"yrittaj\w+"],
    estimate=[r"noin", r"suunnilleen", r"arviolta", r"keskimaarin", r"keskimaarainen", r"tyypillisesti", r"yleensa",
              r"tavallisesti", r"useimmat", r"voi", r"voit", r"voivat", r"voisi\w*", r"usein", r"helposti", r"tyypillinen",
              r"useita", r"lahes", r"jopa"],
    noun=[r"tulo(?:t|ja|nsa)?", r"ansio(?:t|ita)?", r"palkka", r"kuukausitulo\w*", r"tienesti\w*"],
    cond=[r"jos", r"kun", r"kunhan", r"heti\s+kun", r"joka", r"jotka", r"kuka", r"paljonko", r"kuinka\s+paljon", r"mita"],
    neg=[r"ei", r"en", r"et", r"emme", r"ette", r"eivat", r"koskaan", r"ilman", r"kukaan"],
    report=[r"kielle\w*", r"ei\s+(?:ole\s+)?sallit\w*", r"ei\s+saa", r"eivat\s+saa", r"harhaanjohtav\w*", r"vaar\w*", r"laiton\w*",
            r"kuten\s+[\"”]", r"(?:vaitteet|lausunnot)\s+kuten"],
    modal=[r"tulet", r"tulevat", r"voit", r"voivat", r"voi", r"voisit", r"silloin", r"niin"],
    promise=[r"kokopaivai\w*\s+tulo\w*", r"korvata\s+(?:palkkasi|tyosi|tulosi)", r"irtisanoutua", r"jaada\s+(?:aikaisin\s+)?elakkeelle\s+aikaisin",
             r"passiivi\w*\s+tulo\w*",
             r"rajattoma\w*\s+tulo\w*", r"rikastu\w*", r"luksuselama\w*", r"ei\s+koskaan\s+enaa\s+toita"],
)
L["ru"] = dict(
    strong=[r"зарабатыва\w+", r"заработа\w+", r"получает\s+доход\w*", r"имеет\s+доход\w*"],
    weak=[r"получа(?:ет|ют|ете|ешь|ем)", r"получит\w*", r"получ(?:ил|или|ила)", r"выплачива\w+"],
    earner=[r"вы", r"ты", r"они", r"мы", r"я", r"большинство", r"многие", r"fbo", r"дистрибьютор\w*", r"партнер\w*",
            r"участник\w*", r"супервайзер\w*", r"менеджер\w*", r"люди", r"человек", r"консультант\w*", r"продавц\w*"],
    estimate=[r"около", r"примерно", r"приблизительно", r"порядка", r"в\s+среднем", r"средн\w*", r"обычно", r"как\s+правило",
              r"типичн\w*", r"большинство", r"может", r"можете", r"могут", r"сможете", r"смогут", r"часто", r"легко",
              r"несколько", r"почти", r"до"],
    noun=[r"доход\w*", r"заработ(?:ок|ка|ки)", r"зарплат\w*"],
    cond=[r"если", r"когда", r"как\s+только", r"который", r"которые", r"которая", r"кто", r"сколько", r"что"],
    neg=[r"не", r"никогда", r"ни", r"никто", r"нет", r"без"],
    report=[r"запрещ\w*", r"не\s+разреш\w*", r"не\s+(?:допускается|допускаются|могут|может|должны|должен)", r"вводящ\w*\s+в\s+заблуждение",
            r"ложн\w*", r"незаконн\w*", r"такие\s+как\s*[\"«]", r"например\s*[\"«]", r"(?:заявления|утверждения)\s+(?:вроде|типа|о\s+том)"],
    modal=[r"будете", r"будут", r"будешь", r"сможете", r"смогут", r"можете", r"могут", r"может", r"тогда"],
    promise=[r"доход\w*\s+(?:на\s+)?полн\w*\s+(?:рабоч\w*\s+)?(?:день|ставк\w*)", r"замени\w*\s+(?:вашу|свою|твою)\s+(?:зарплату|работу)",
             r"уволит\w*\s+с\s+работы", r"бросит\w*\s+(?:вашу|свою|твою)?\s*работу", r"рано\s+(?:выйти|уйти)\s+на\s+пенсию",
             r"пассивн\w*\s+доход\w*", r"резидуальн\w*\s+доход\w*",
             r"неограниченн\w*\s+доход\w*", r"разбогатет\w*", r"роскошн\w*\s+(?:жизн\w*|образ\w*)", r"больше\s+никогда\s+не\s+работать"],
)
L["sr"] = dict(
    strong=[r"zaradiva\w+", r"zaradjiva\w+", r"зарађива\w+", r"zaradjuj\w+", r"zaraduj\w+", r"zaradi(?:s|te|mo|ce|cete|cemo|ti|o|la|li)?", r"zaradice\w*",
            r"зарађуј\w+", r"зарађу\w+", r"заради(?:ш|те|мо|ће|ћете)?"],
    weak=[r"dobij(?:a|as|ate|aju|es|ete|u)", r"dobice(?:te|s)?", r"prima(?:s|te|ju)?", r"isplacuje\s+se", r"добиј\w+",
          r"прима(?:ш|те|ју)?", r"исплаћује\s+се"],
    earner=[r"vi", r"ti", r"oni", r"mi", r"ja", r"vecina", r"mnogi", r"fbo", r"distributer\w*", r"clanovi", r"supervizor\w*",
            r"menadzer\w*", r"ljudi", r"prodavc\w*", r"ви", r"ти", r"они", r"већина", r"многи", r"дистрибутер\w*", r"људи",
            r"чланови"],
    estimate=[r"oko", r"otprilike", r"priblizno", r"u\s+proseku", r"prosecn\w*", r"obicno", r"uglavnom", r"tipicno", r"vecina",
              r"mozete", r"mogu", r"moze", r"cesto", r"lako", r"nekoliko", r"skoro", r"око", r"отприлике", r"у\s+просеку",
              r"просечн\w*", r"обично", r"углавном", r"већина", r"можете", r"могу", r"може"],
    noun=[r"prihod\w*", r"zarad[aeu]", r"plat[aeu]", r"приход\w*", r"зарад[аеу]", r"плат[аеу]"],
    cond=[r"ako", r"kada", r"kad", r"cim", r"koji", r"koja", r"koje", r"ko", r"koliko", r"sta", r"ако", r"када", r"који",
          r"која", r"које", r"колико"],
    neg=[r"ne", r"nikada", r"nikad", r"nijedan", r"niko", r"bez", r"не", r"никада", r"нико", r"без"],
    report=[r"zabranjen\w*", r"nije\s+dozvoljen\w*", r"ne\s+smeju", r"ne\s+sme", r"obmanjujuc\w*", r"lazn\w*", r"nezakonit\w*",
            r"kao\s+sto\s+je\s+[\"„]", r"забрањен\w*", r"није\s+дозвољен\w*", r"не\s+смеју", r"обмањујућ\w*", r"лажн\w*"],
    modal=[r"cete", r"ce", r"mozete", r"mogu", r"moze", r"tada", r"ћете", r"ће", r"можете", r"могу"],
    promise=[r"prihod\w*\s+(?:za|kao\s+za)\s+puno\s+radno\s+vreme", r"zamenit\w*\s+(?:vasu|svoju)\s+platu", r"dati\s+otkaz",
             r"napustit\w*\s+(?:vas|svoj)\s+posao", r"rano\s+u\s+penziju", r"pasivn\w*\s+prihod\w*", r"neogranicen\w*\s+prihod\w*", r"obogatit\w*", r"luksuzn\w*\s+zivot\w*",
             r"пасивн\w*\s+приход\w*"],
)

# ---------------------------------------------------------------------------------------------------------------
# Detector (ported from income_design/proto2_final.py)
# ---------------------------------------------------------------------------------------------------------------
PERIOD = re.compile(r"(?<!\w)(?:month\w*|week\w*|year\w*|annual\w*|/\s?(?:mo|month|wk|yr|year)|" + _TR_PERIOD
                    + r"|mes|meses|mese|mesi|an|ans|annee\w*|ano|anos|anno|anni|jahr\w*|jaar|ar|aret|vuo\w*|год\w*|godin\w*|годин\w*)(?!\w)")
# Forever rank names (shared across languages) and FBO words: the label of a "role: amount" line.
ROLE = re.compile(_fold_pattern(
    r"(?<!\w)(?:(?:new|active|aktive?|actifs?|activos?|attivi|aktiivise\w*|активн\w*|aktivn\w*)\s+)?"
    r"(?:fbo'?s?|fbo:\w*|fbo-\w*|(?:assistant\s+)?supervisor\w*|superviseur\w*|supervizor\w*|супервайзер\w*|(?:senior\s+|soaring\s+|sapphire\s+|diamond[\s-]+sapphire\s+|diamond\s+|double\s+diamond\s+|triple\s+diamond\s+|eagle\s+)?manager\w*|менеджер\w*|menadzer\w*|gerentes?)(?!\w)"))
_POST_THRESHOLD = re.compile(_fold_pattern(
    r"\s*(?:or|and|ou|o|oder|of|eller|tai|или|ili)\s+(?:more|above|higher|over|plus|mas|piu|mehr|meer|mer|mere|enemman|более|vise|dariber|daruber|au-dessus|superiore)"))

REL = {
    "en": [r"who", r"that", r"which", r"whose"],
    "fr": [r"qui", r"que", r"qu'", r"dont"],
    "es": [r"que", r"quien(?:es)?", r"cuyos?"],
    "it": [r"che", r"chi", r"il\s+cui"],
    "de": [r"der", r"die", r"das", r"welche[rsn]?", r"wer"],
    "nl": [r"die", r"dat", r"wie"],
    "sv": [r"som", r"vem"],
    "da": [r"som", r"der", r"hvem"],
    "no": [r"som", r"hvem"],
    "fi": [r"joka", r"jotka", r"kuka"],
    "ru": [r"который", r"которые", r"которая", r"кто"],
    "sr": [r"koji", r"koja", r"koje", r"ko", r"који", r"која", r"које"],
}
CONJ = {
    "en": [r"if", r"when", r"whenever", r"once", r"unless", r"until", r"whether", r"how\s+much"],
    "fr": [r"si", r"s'", r"quand", r"lorsque", r"lorsqu'", r"des\s+que", r"une\s+fois\s+que", r"combien"],
    "es": [r"si", r"cuando", r"una\s+vez\s+que", r"cuanto"],
    "it": [r"se", r"quando", r"una\s+volta\s+che", r"quanto"],
    "de": [r"wenn", r"falls", r"sobald", r"sofern", r"wie\s*viel", r"ob"],
    "nl": [r"als", r"wanneer", r"indien", r"zodra", r"hoeveel", r"of"],
    "sv": [r"om", r"n(?:a|ä)r", r"s(?:a|å)\s+snart", r"hur\s+mycket"],
    "da": [r"hvis", r"n(?:a|å)r", r"s(?:a|å)\s+snart", r"hvor\s+meget"],
    "no": [r"hvis", r"dersom", r"n(?:a|å)r", r"s(?:a|å)\s+snart", r"hvor\s+mye"],
    "fi": [r"jos", r"kun", r"kunhan", r"heti\s+kun", r"paljonko", r"kuinka\s+paljon"],
    "ru": [r"если", r"когда", r"как\s+только", r"сколько"],
    "sr": [r"ako", r"kada", r"kad", r"cim", r"koliko", r"da\s+li", r"ако", r"када", r"колико"],
}
# The object of a receive verb that is a refund, not earnings (per language, folded)
REFUND = {
    "en": r"(?:a|an|the|your|their|any|full)?\s*(?:refunds?|reimbursements?|credits?|discounts?|rebates?|replacements?|invoices?|bills?|statements?|forms?|receipts?)",
    "fr": r"(?:un|une|le|la|votre)?\s*(?:rembourse\w*|avoir|remise|facture|credit)",
    "es": r"(?:un|una|el|la|su)?\s*(?:reembols\w*|devolucion|factura|credito|descuento)",
    "it": r"(?:un|una|il|lo|la)?\s*(?:rimbors\w*|fattura|credito|sconto)",
    "de": r"(?:eine|einen|die|den|ihre|ihren)?\s*(?:\w*erstattung|gutschrift|rechnung|rabatt)",
    "nl": r"(?:een|de|het|uw|je)?\s*(?:terugbetaling|restitutie|factuur|creditnota|korting)",
    "sv": r"(?:en|ett|din)?\s*(?:aterbetalning|kreditering|faktura|rabatt)",
    "da": r"(?:en|et|din)?\s*(?:refusion|tilbagebetaling|kreditnota|faktura|rabat)",
    "no": r"(?:en|et|din)?\s*(?:refusjon|tilbakebetaling|kreditnota|faktura|rabatt)",
    "fi": r"(?:hyvity\w*|palautu\w*|lasku\w*|alennu\w*)",
    "ru": r"(?:возврат\w*|счет\w*|скидк\w*|компенсаци\w*)",
    "sr": r"(?:povracaj\w*|refundacij\w*|racun\w*|popust\w*|поврацај\w*|рачун\w*)",
}
_NOUN_NOT = re.compile(r"\s+(?:tax\w*|statements?|disclosure|brackets?|thresholds?|levels?|requirements?|verification|skatt\w*|steuer\w*|impot\w*|impuest\w*|impost\w*|belasting\w*|vero\w*|налог\w*|porez\w*)")
_AFTER_NEG = {
    "fr": r"\s+(?:pas|jamais|rien)(?!\w)", "de": r"\s+(?:\w+\s+)?(?:nicht|nie|niemals|kein\w*)(?!\w)",
    "nl": r"\s+(?:\w+\s+)?(?:niet|nooit|geen)(?!\w)", "sv": r"\s+(?:inte|aldrig|ej)(?!\w)", "da": r"\s+(?:ikke|aldrig)(?!\w)",
    "no": r"\s+(?:ikke|aldri)(?!\w)",
}
_NO_SUBJ = {
    "en": r"(?:no|none\s+of\s+(?:the|our))", "fr": r"(?:aucun\w*|nul\w*)", "es": r"(?:ningun\w*)", "it": r"(?:nessun\w*)",
    "de": r"(?:kein\w*)", "nl": r"(?:geen)", "sv": r"(?:ingen|inga)", "da": r"(?:ingen)", "no": r"(?:ingen)",
    "fi": r"(?:kukaan|mikaan)", "ru": r"(?:ни\s+один\w*|никто)", "sr": r"(?:nijedan|niko|нијед\w*|нико)",
}
_RANGE_SEP = r"(?:-|–|—|to|a|à|y|e|bis|tot|till|til|до|do|и|i|et|und|och|og|en|ja|ou|or|and)"
RANGE = re.compile(
    rf"(?<!\w)(?:{AMOUNT}|\d[\d .,]*)\s*{_RANGE_SEP}\s*(?:{AMOUNT}|\d[\d .,]*\s*(?:{_CUR_WORD}))"
)
FUTURE = {
    "fr": re.compile(r"gagner(?:a|as|ez|ons|ont|ai|ais|ait|aient|iez|ions)|toucher(?:a|as|ez|ont)"),
    "es": re.compile(r"ganar(?:a|as|an|emos|ia|ias|ian)"),
    "it": re.compile(r"guadagner\w+"),
    "sr": re.compile(r"zaradic\w*|zaradi(?:ce|cete)"),
}
# P6 (verb-free): an earner, a FIRM estimate marker (not a bare modal), a currency amount and a period in one clause,
# with no rule-context word (cost, fee, price, order, pay-as-payer, tax, refund, deduction, minimum, threshold).
EST6 = {
    "en": r"about|around|roughly|approximately|approx|nearly|almost|close\s+to|typically|typical|usually|normally|generally|on\s+average|average|median|most|likely|probably|realistic(?:ally)?|expect\w*|~|somewhere",
    "fr": r"environ|a\s+peu\s+pres|approximativement|en\s+moyenne|moyenne|typiquement|generalement|habituellement|normalement|la\s+plupart|pres\s+de|autour\s+de|probablement|tournera|~",
    "es": r"aproximadamente|alrededor\s+de|unos|unas|cerca\s+de|en\s+promedio|promedio|normalmente|generalmente|tipicamente|habitualmente|la\s+mayoria|probablemente|rondar\w*|~",
    "it": r"circa|intorno\s+a\w*|all'incirca|approssimativamente|in\s+media|media|tipicamente|generalmente|di\s+solito|normalmente|solitamente|la\s+maggior\s+parte|probabilmente|aggirer\w*|~",
    "de": r"etwa|ungefahr|rund|circa|ca|durchschnittlich|im\s+durchschnitt|im\s+schnitt|typischerweise|normalerweise|gewohnlich|meist\w*|in\s+der\s+regel|wahrscheinlich|~",
    "nl": r"ongeveer|rond(?:om)?|circa|ca|gemiddeld|doorgaans|meestal|gewoonlijk|typisch|de\s+meeste|waarschijnlijk|zo'?n|~",
    "sv": r"ungefar|runt|cirka|ca|omkring|i\s+genomsnitt|genomsnitt\w*|vanligtvis|normalt|oftast|typiskt|de\s+flesta|troligen|~",
    "da": r"cirka|ca|omkring|i\s+gennemsnit|gennemsnitlig\w*|typisk|normalt|sadvanligvis|oftest|de\s+fleste|sandsynligvis|~",
    "no": r"cirka|ca|omtrent|rundt|i\s+gjennomsnitt|gjennomsnittlig\w*|typisk|normalt|vanligvis|oftest|de\s+fleste|sannsynligvis|~",
    "fi": r"noin|suunnilleen|arviolta|keskimaarin|keskimaarai\w*|tyypillisesti|yleensa|tavallisesti|useimmat|todennakoisesti|~",
    "ru": r"около|примерно|приблизительно|порядка|в\s+среднем|средн\w*|обычно|как\s+правило|типичн\w*|большинство|скорее\s+всего|~",
    "sr": r"oko|otprilike|priblizno|u\s+proseku|prosecn\w*|obicno|uglavnom|tipicno|vecina|verovatno|око|отприлике|у\s+просеку|обично|већина|~",
}
RULECTX = {
    "en": r"pay|pays|paid|spend\w*|cost\w*|fees?|price\w*|order\w*|purchas\w*|buy\w*|tax\w*|refund\w*|deduct\w*|charg\w*|minimum|maximum|threshold|shipping|delivery|postage|discount\w*|withheld|held|accumulat\w*|invoice\w*|vat",
    "fr": r"pai\w*|pay\w*|depens\w*|cout\w*|frais|prix|commande\w*|achat\w*|achet\w*|impot\w*|taxe\w*|rembours\w*|dedui\w*|deduct\w*|minimum|maximum|seuil|livraison|remise\w*|facture\w*|tva",
    "es": r"pag\w*|gast\w*|cost\w*|cuota\w*|tarifa\w*|precio\w*|pedido\w*|compra\w*|impuest\w*|reembols\w*|descont\w*|deduc\w*|minimo|maximo|umbral|envio|entrega|factura\w*|iva",
    "it": r"pag\w*|spes\w*|cost\w*|quota\w*|prezz\w*|ordin\w*|acquist\w*|impost\w*|tass\w*|rimbors\w*|detratt\w*|trattenut\w*|minimo|massimo|soglia|spedizion\w*|consegna|fattur\w*|iva",
    "de": r"zahl\w*|bezahl\w*|ausgeb\w*|kost\w*|gebuhr\w*|preis\w*|bestell\w*|kauf\w*|steuer\w*|erstatt\w*|abgezogen|einbehalten|mindest\w*|hochst\w*|maximal\w*|schwelle|versand\w*|liefer\w*|rechnung\w*|mwst",
    "nl": r"betal\w*|uitgeven|kost\w*|vergoeding\w*|prijs\w*|bestel\w*|aankoop\w*|koop\w*|belasting\w*|terugbetal\w*|ingehouden|afgetrokken|minimum|maximum|minimaal|maximaal|drempel|verzend\w*|lever\w*|factuur\w*|btw",
    "sv": r"betal\w*|kostar|kostnad\w*|avgift\w*|pris\w*|bestall\w*|kop\w*|skatt\w*|aterbetal\w*|dras|avdrag\w*|minst|minimum|max\w*|frakt\w*|leverans\w*|faktur\w*|moms",
    "da": r"betal\w*|koster|omkostning\w*|gebyr\w*|pris\w*|bestil\w*|kob\w*|skat\w*|refusion|fratrak\w*|traekkes|minimum|maks\w*|fragt\w*|levering\w*|faktur\w*|moms",
    "no": r"betal\w*|koster|kostnad\w*|gebyr\w*|pris\w*|bestill\w*|kjop\w*|skatt\w*|refusjon|trekkes|fratrekk\w*|minimum|maks\w*|frakt\w*|levering\w*|faktur\w*|mva",
    "fi": r"maks\w*|kulu\w*|hinta\w*|hinnan|tilau\w*|ostos\w*|osta\w*|vero\w*|hyvity\w*|vahenn\w*|vahimm\w*|enimm\w*|toimitus\w*|lasku\w*|alv",
    "ru": r"плат\w*|оплат\w*|трат\w*|стоим\w*|сбор\w*|цен\w*|заказ\w*|покуп\w*|налог\w*|возврат\w*|удерж\w*|вычет\w*|миним\w*|максим\w*|порог\w*|доставк\w*|счет\w*|ндс",
    "sr": r"plac\w*|plat\w*|trosk\w*|kost\w*|naknad\w*|cen\w*|porudzb\w*|narudzb\w*|naruc\w*|poruc\w*|kupov\w*|porez\w*|povrac\w*|odbij\w*|minim\w*|maksim\w*|prag\w*|dostav\w*|racun\w*|pdv|плаћ\w*|трошк\w*|накнад\w*|цен\w*|порез\w*",
}
EST6_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)|~") for k, v in EST6.items()}
RULECTX_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in RULECTX.items()}
_CLAUSE_BREAK = re.compile(r",(?!\d)|\s[-–—]\s|:\s|\(|\)|\"|“|”|«|»")


def _comp(patterns):
    return re.compile(r"(?<!\w)(?:" + "|".join(f"(?:{_fold_pattern(p)})" for p in patterns) + r")(?!\w)")


V: dict[str, dict] = {}
for _lang, _voc in L.items():
    V[_lang] = {k: _comp(v) for k, v in _voc.items() if k != "cond"}
    V[_lang]["rel"] = _comp(REL[_lang])
    V[_lang]["conj"] = _comp(CONJ[_lang])
    V[_lang]["refund"] = re.compile(r"\s*" + _fold_pattern(REFUND[_lang]) + r"(?!\w)")
    V[_lang]["after_neg"] = re.compile(_AFTER_NEG[_lang]) if _lang in _AFTER_NEG else None
    V[_lang]["no_subj"] = re.compile(r"(?<!\w)" + _fold_pattern(_NO_SUBJ[_lang]) + r"\s+(?:\w+\s+){0,2}$")
LANGS = list(V)

# Sentence split on ORIGINAL text: terminal punctuation followed by space and an upper-case letter / digit / quote /
# markdown, line breaks, bullets and semicolons. Abbreviations such as "kr." "ca." "approx." do not split.
_SPLIT = re.compile(
    r"(?<=[.!?])[\"”»'*)]*\s+(?=[\"“«'*(\[]*[A-ZÀ-ÖØ-ÞА-ЯЁЂ-Џ0-9•])|\n+|\s+[•·]\s+|;\s+|\s+-\s+(?=[\\*A-ZÀ-ÖØ-ÞА-ЯЁЂ-Џ])|\s*#{1,6}\s+"
)


def sentences(text):
    return [s for s in _SPLIT.split(text or "") if s and s.strip()]


class _ClauseIndex:
    """Precomputed clause-break offsets for one sentence.

    _seg_start/_seg_end originally rescanned the sentence from position 0 for
    every call (_seg_start) or re-searched from `pos` (_seg_end). Called once
    per money match, that made a sentence with N unpunctuated money amounts
    O(N) per lookup and O(N^2) overall -- one 2,000-amount sentence took
    several seconds. This precomputes every clause-break span once per
    sentence (O(len(s))) and answers each _seg_start/_seg_end query with a
    bisect lookup (O(log N)), for the identical result: `ends` and `starts`
    are the clause breaks' end and start offsets, in the order _CLAUSE_BREAK
    finds them (left to right, non-overlapping, so both lists are already
    sorted ascending -- no explicit sort needed).
    """

    __slots__ = ("ends", "starts")

    def __init__(self, s: str) -> None:
        starts = []
        ends = []
        for m in _CLAUSE_BREAK.finditer(s):
            starts.append(m.start())
            ends.append(m.end())
        self.starts = starts
        self.ends = ends

    def seg_start(self, pos: int) -> int:
        """End offset of the last clause break that ends at or before `pos`, or 0."""
        idx = bisect.bisect_right(self.ends, pos) - 1
        return self.ends[idx] if idx >= 0 else 0

    def seg_end(self, pos: int, length: int) -> int:
        """Start offset of the first clause break at or after `pos`, or `length`."""
        idx = bisect.bisect_left(self.starts, pos)
        return self.starts[idx] if idx < len(self.starts) else length


def _seg_start(s, pos, idx: "_ClauseIndex | None" = None):
    if idx is not None:
        return idx.seg_start(pos)
    start = 0
    for m in _CLAUSE_BREAK.finditer(s, 0, pos):
        start = m.end()
    return start


def _seg_end(s, pos, idx: "_ClauseIndex | None" = None):
    if idx is not None:
        return idx.seg_end(pos, len(s))
    m = _CLAUSE_BREAK.search(s, pos)
    return m.start() if m else len(s)


def _words(t):
    return re.findall(r"[\w'’]+", t)


WIN_BEFORE, WIN_AFTER = 60, 80  # money must sit near the verb (chars)
V2_LANGS = {"de", "nl", "sv", "da", "no"}
# Prohibition stated AFTER the claim in the same sentence ("... promising a luxury lifestyle is prohibited").
POST_BAN = {
    "en": r"(?:is|are)\s+(?:strictly\s+)?(?:prohibited|forbidden|not\s+(?:allowed|permitted))|(?:is|are)\s+banned",
    "fr": r"(?:est|sont)\s+(?:strictement\s+)?(?:interdit\w*|prohib\w*)|(?:n'est|ne\s+sont)\s+pas\s+(?:autoris\w*|permis\w*)",
    "es": r"(?:esta|estan)\s+(?:estrictamente\s+)?prohibid\w*|no\s+(?:esta|estan)\s+permitid\w*",
    "it": r"(?:e|sono)\s+(?:severamente\s+|rigorosamente\s+)?(?:vietat\w*|proibit\w*)|non\s+(?:e|sono)\s+(?:consentit|permess)\w*",
    "de": r"(?:ist|sind)\s+(?:streng\s+)?(?:verboten|untersagt|nicht\s+(?:erlaubt|gestattet|zulassig))",
    "nl": r"(?:is|zijn)\s+(?:strikt\s+)?(?:verboden|niet\s+toegestaan)",
    "sv": r"(?:ar)\s+(?:strangt\s+)?(?:forbjud\w*|inte\s+tillat\w*)",
    "da": r"(?:er)\s+(?:strengt\s+)?(?:forbudt|ikke\s+tilladt)",
    "no": r"(?:er)\s+(?:strengt\s+)?(?:forbudt|ikke\s+tillatt)",
    "fi": r"(?:on|ovat)\s+(?:ehdottomasti\s+)?kiellet\w*|ei\s+ole\s+sallittu",
    "ru": r"запрещ\w*|не\s+допуска\w*",
    "sr": r"(?:je|su)\s+(?:strogo\s+)?zabranjen\w*|nije\s+dozvoljen\w*",
}
POST_BAN_RE = {k: re.compile(_fold_pattern(v)) for k, v in POST_BAN.items()}


def _reported(s, pos, end, lang):
    return bool(V[lang]["report"].search(s, 0, pos) or POST_BAN_RE[lang].search(s, end))


def _subordinate(s, v, lang, idx=None):
    lo = _seg_start(s, v.start(), idx)
    lead = s[lo:v.start()]
    voc = V[lang]
    if lang in V2_LANGS and not _words(lead) and not s[:lo].rstrip().endswith(","):
        return True  # verb-first: conditional or question ("Verdient ein FBO EUR 1 an Bonus, wird ...")
    # relative pronoun directly before the verb ("FBOs who earn", "qui gagnent", "som tjanar"), allowing one adverb
    for r in voc["rel"].finditer(lead):
        between = lead[r.end():]
        if len(_words(between)) <= 1 and not voc["modal"].search(between):
            return True
        # verb-final relative clause opened right after a comma: ", die mehr als 450 EUR verdienen"
        if lo > 0 and not lead[:r.start()].strip() and not voc["modal"].search(between):
            return True
    for c in voc["conj"].finditer(lead):
        between = lead[c.end():]
        if voc["modal"].search(between):
            continue
        if len(voc["earner"].findall(between)) >= 2:
            continue  # "If you work hard you earn ..." - a second subject opens the main clause
        if lang in FUTURE and FUTURE[lang].fullmatch(v.group(0)) and len(_words(between)) >= 2:
            continue  # pro-drop future after a condition: "Se sponsorizzi tre persone guadagnerai ..."
        return True
    return False


def _negated(s, v, lang, idx=None):
    voc = V[lang]
    lo = _seg_start(s, v.start(), idx)
    before = s[lo:v.start()]
    w = list(re.finditer(r"[\w'’]+", before))
    near = before[w[-3].start():] if len(w) >= 3 else before
    if voc["neg"].search(near):
        return True
    if voc["after_neg"] is not None and voc["after_neg"].match(s, v.end()):
        return True
    if voc["no_subj"].search(before):
        return True
    return False


def _money(s, lo, hi, verb=None, lang=None):
    for m in MONEY_RE.finditer(s, lo, hi):
        if _PERCENT_OR_CC.match(s, m.start()):
            continue
        if verb is not None and m.start() > verb.end():
            gap = s[verb.end():m.start()]
            c = V[lang]["conj"].search(gap)
            if c and not V[lang]["modal"].search(gap, c.end()):
                continue  # "could get their bonuses ... only if the bonus amount is less than 250 RON"
        return m
    return None


# Accent-significant forms that fold() would merge with a finite verb: French past participle "gagné(e)(s)" /
# "touché" becomes "gagne" / "touche" (present tense) once accents are stripped ("le montant gagné basé sur 2,66 euros").
_PRE_FOLD = [(re.compile(r"(?i)\b(gagn|touch)(?:é|É|é)(e?s?)\b"), r"\1e_pp")]


def _fold(raw):
    for pattern, repl in _PRE_FOLD:
        raw = pattern.sub(repl, raw)
    return fold(raw)


# Negation words inside idioms that negate nothing (the guardrails _FALSE_NEGATION_RE idea, per language):
# "Sin embargo, el ingreso tipico ... ronda los 750 dolares" was read as negated by "sin".
NEG_IDIOM = {
    "en": r"not\s+only|no\s+doubt|without\s+(?:a\s+)?(?:doubt|question)|no\s+matter",
    "fr": r"non\s+seulement|sans\s+doute|sans\s+aucun\s+doute",
    "es": r"sin\s+embargo|no\s+obstante|no\s+solo|sin\s+duda",
    "it": r"non\s+solo|senza\s+dubbio",
    "de": r"nicht\s+nur|ohne\s+zweifel",
    "nl": r"niet\s+alleen|zonder\s+twijfel",
    "sv": r"inte\s+bara|utan\s+tvekan",
    "da": r"ikke\s+kun|ikke\s+bare|uden\s+tvivl",
    "no": r"ikke\s+bare|ikke\s+bare|uten\s+tvil",
    "fi": r"ei\s+vain|ei\s+ainoastaan",
    "ru": r"не\s+только|без\s+сомнения",
    "sr": r"ne\s+samo|bez\s+sumnje",
}
NEG_IDIOM_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in NEG_IDIOM.items()}


def _mask_idioms(s, lang):
    return NEG_IDIOM_RE[lang].sub(lambda m: re.sub(r"\w", "x", m.group(0)), s)


def _detect_p1(s, lang, raw, idx=None):
    voc = V[lang]
    for v in voc["strong"].finditer(s):
        lo, hi = _seg_start(s, v.start(), idx), _seg_end(s, v.end(), idx)
        lo, hi = max(lo, v.start() - WIN_BEFORE), min(hi, v.end() + WIN_AFTER)
        m = _money(s, lo, hi, v, lang)
        if not m:
            continue
        if _subordinate(s, v, lang, idx) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang):
            continue
        return ("P1", lang, raw)
    return None


def _detect_p2(s, lang, raw, idx=None):
    voc = V[lang]
    for v in voc["weak"].finditer(s):
        lo, hi = _seg_start(s, v.start(), idx), _seg_end(s, v.end(), idx)
        if voc["refund"].match(s, v.end()):
            continue
        hi = min(hi, v.end() + WIN_AFTER)
        m = _money(s, max(lo, v.start() - WIN_BEFORE), hi, v, lang)
        if not m or not voc["earner"].search(s, lo, v.start()):
            continue
        span = s[lo:hi]
        if not (voc["estimate"].search(span) or RANGE.search(span)):
            continue
        if _POST_THRESHOLD.match(s, m.end()) and not PERIOD.search(s, m.end(), hi):
            continue  # "Most FBOs receive their bonus of $100 or more by bank transfer" - a payment threshold
        if _subordinate(s, v, lang, idx) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang):
            continue
        return ("P2", lang, raw)
    return None


def _detect_p3(s, lang, raw):
    voc = V[lang]
    for n in voc["noun"].finditer(s):
        if _NOUN_NOT.match(s, n.end()):
            continue
        m = _money(s, n.end(), min(len(s), n.end() + 60)) or _money(s, max(0, n.start() - 40), n.start())
        if not m:
            continue
        around = s[max(0, n.start() - 40):min(len(s), n.end() + 60)]
        if not (voc["estimate"].search(around) or RANGE.search(around)):
            continue
        w = list(re.finditer(r"[\w'’]+", s[:n.start()]))
        near = s[w[-3].start():n.start()] if len(w) >= 3 else s[:n.start()]
        if _reported(s, n.start(), n.end(), lang) or voc["neg"].search(near):
            continue
        return ("P3", lang, raw)
    return None


def _detect_p5(s, lang, raw):
    voc = V[lang]
    for r in ROLE.finditer(s):
        sep = re.match(r"\s*(?:\*\*)?\s*(?:[:|=–—](?=\s)|\s-\s)", s[r.end():])
        if not sep:
            continue
        tail = s[r.end() + sep.end():r.end() + sep.end() + 70]
        m = _money(tail, 0, len(tail))
        if not m or not PERIOD.search(tail, m.end()):
            continue
        if not (voc["estimate"].search(tail) or RANGE.search(tail) or "~" in tail[:m.start() + 1]):
            continue
        if _reported(s, r.start(), r.end(), lang) or RULECTX_RE[lang].search(tail):
            continue
        return ("P5", lang, raw)
    return None


def _detect_p6(s, lang, raw, idx=None):
    voc = V[lang]
    for m in MONEY_RE.finditer(s):
        if _PERCENT_OR_CC.match(s, m.start()):
            continue
        lo, hi = _seg_start(s, m.start(), idx), _seg_end(s, m.end(), idx)
        clause = s[lo:hi]
        if not PERIOD.search(s, m.end(), min(hi, m.end() + 40)) and not PERIOD.search(s, max(lo, m.start() - 30), m.start()):
            continue
        if not voc["earner"].search(clause) or not EST6_RE[lang].search(clause):
            continue
        if RULECTX_RE[lang].search(clause) or voc["neg"].search(clause) or _reported(s, m.start(), m.end(), lang):
            continue
        if any(not PERIOD.match(clause, c.end() + 1) for c in voc["conj"].finditer(clause)) \
                or voc["rel"].search(s, lo, m.start()):
            continue
        return ("P6", lang, raw)
    return None


def _detect_p4(s, lang, raw, idx=None):
    voc = V[lang]
    for p in voc["promise"].finditer(s):
        lo = _seg_start(s, p.start(), idx)
        if _reported(s, p.start(), p.end(), lang) or voc["neg"].search(s, lo, p.start()):
            continue
        return ("P4", lang, raw)
    return None


def detect_lang(text, lang):
    for raw in sentences(text):
        s = _mask_idioms(_fold(raw), lang)
        # Precomputed once per sentence so P1/P2/P4/P6 (which look up a clause
        # span per verb/amount match) are each O(log n) per lookup instead of
        # O(n), keeping the whole sentence O(n log n) instead of O(n^2).
        idx = _ClauseIndex(s)
        hit = (
            _detect_p1(s, lang, raw, idx)
            or _detect_p2(s, lang, raw, idx)
            or _detect_p3(s, lang, raw)
            or _detect_p5(s, lang, raw)
            or _detect_p6(s, lang, raw, idx)
            or _detect_p4(s, lang, raw, idx)
        )
        if hit:
            return hit
    return None


_STOP = {
    "en": "the and of to is are you your for with that this will be a an in on it they per month most can".split(),
    "fr": "le la les et des est vous pour une un avec que dans du au par mois ils sont".split(),
    "es": "el la los y de que es para con una un por del las al mes su".split(),
    "de": "der die das und ist sie fur mit ein eine einem einen nicht werden den im pro monat sind".split(),
    "nl": "de het en van een is voor met niet worden zijn je u per maand ze die".split(),
    "it": "il la di che e per con una un non sono gli del le al mese degli".split(),
    "sv": "och att det ar for som med en ett av pa inte har du i manaden kronor".split(),
    "da": "og at det er for som med en et af pa ikke har du om maneden til".split(),
    "no": "og at det er for som med en et av pa ikke har du i maneden til".split(),
    "fi": "ja on etta ei tai se kun voi myos ovat jos sinun noin kuukaudessa".split(),
    "ru": "и в не на что с по для это как вы или около месяц".split(),
    "sr": "i u je da se na za od ne su sa ili oko mesecno".split(),
}


def sentence_langs(folded, hint=None):
    """Languages whose function words appear in the sentence (within 60% of the best), plus the request language.
    With no function-word evidence at all, every language is tried."""
    words = re.findall(r"\w+", folded)
    scores = {lang: sum(1 for w in words if w in set(ws)) for lang, ws in _STOP.items()}
    best = max(scores.values())
    if best <= 1:
        return LANGS
    chosen = [lang for lang in LANGS if scores[lang] >= max(1, 0.6 * best)]
    if hint in V and hint not in chosen:
        chosen.append(hint)
    return chosen


def detect(text, hint=None):
    for raw in sentences(text):
        folded = _fold(raw)
        for lang in sentence_langs(folded, hint):
            hit = detect_lang(raw, lang)
            if hit:
                return hit
    return None


def detect_earnings_projection(text: str, language: str | None = None):
    """Return the first earnings-projection match in `text`, or None.

    `language` is used as a hint (the request/answer language); every
    language's vocabulary is still tried against every sentence, exactly as
    income_claim_translations does, so a mismatched hint never suppresses a
    real match. The return value is (rule, lang, sentence) or None.
    """
    return detect(text, hint=language)
