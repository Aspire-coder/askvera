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
_CODES = r"usd|eur|chf|gbp|sek|nok|dkk|rsd|rub|kgs"
# 1b/currency: currencies of non-route markets (names, ISO codes, symbols, slang). ISO codes that are also common
# words or product words are deliberately left out: all, try, top, cup, mop, pen, cop, bob, ils, mur, gel ("Aloe Vera Gel 1").
_CUR_WORD_1B = (
    r"rand|naira|rupees?|rupias?|roupies?|rupien|pesos?|shillings?|schilling\w*|dirhams?|dirhames|dirham|baht|bucks|quid"
    r"|yen|yuan|renminbi|ringgit|rupiah|cedis?|kwacha|pula|fcfa|f\s?cfa|francs?\s+cfa|cfa|leones|birr|taka|lempiras?"
    r"|quetzal(?:es)?|soles|bolivianos?|guaranies|colones|reais|forints?|zlot(?:y|ys|ych|ys)|korun[ay]?|hryvni?as?|гривн\w*"
    r"|tenge|тенге|manats?|somoni|riyals?|rials?|lira|lire|liras|leva|денар\w*|рупи\w*|песо|ранд\w*|найр\w*|шиллинг\w*"
    # Fable item 9: "5 grand prizes"/"the grand total"/"grand opening"/"the grand final" -- "grand" is not a
    # money-slang word for 1,000 when the very next word is a common "grand X" collocation, not a currency use.
    r"|grand(?!\s+(?:prizes?|totals?|openings?|finals?|prix|jury|slam))"
)
_CODES_1B = (
    r"zar|ngn|inr|kes|php|aed|thb|mxn|brl|jpy|cny|rmb|myr|idr|ghs|ugx|tzs|egp|mad|pkr|bdt|lkr|ars|clp|hkd|sgd"
    r"|twd|krw|huf|czk|bgn|uah|kzt|xof|xaf|sar|qar|kwd|omr|bhd|jod|vnd|npr|zmw|bwp|mwk|etb|rwf|xcd|ttd|jmd|dop|gtq"
    r"|hnl|crc|pyg|uyu|isk|bam|mkd|azn|byn|uzs|mnt|lak|khr|mmk|ksh|rs\.?"
)
_CUR_SYM_1B = r"[₹₦₱¥₩₺₴₽₸₵₡₲₭₫฿৳₨]|r\$|💰|💵|💸|💶|💷"
_CUR_WORD = _CUR_WORD + "|" + _CUR_WORD_1B + "|" + _CODES_1B
_CUR_SYM = _CUR_SYM + "|" + _CUR_SYM_1B
_CODES = _CODES + "|" + _CODES_1B
AMOUNT = (
    rf"(?:\d+(?:[.,]\d)?\s?k(?=\s*(?:a|per|each|every|/)\s*(?:month|week|year|mo)(?!\w))|(?:{_CUR_SYM})\s?(?:{_NUM})(?:\s?(?:k|000))?"
    rf"|(?:{_NUM})\s?(?:k\s?)?(?:{_CUR_SYM}|(?:{_CUR_WORD})(?!\w))"
    rf"|(?:{_NUM})\s?:-"
    rf"|(?=[a-z]{{2,3}}\.?\s?\d)(?:{_CODES})\s?(?:{_NUM}))"
)
# 1b/spelled: a money amount written in words ("nine hundred dollars", "three grand", "neuf cents euros",
# "novecientos dólares", "neunhundert Euro", "девятисот долларов"). One number-word token list per language (folded);
# compounding languages (de/nl/sv/it/fi) match a run of glued tokens. A single article-like or ambiguous short token
# ("a", "un", "en", "to", "sei", ...) never starts an amount on its own, so "converted to euros" is not money.
_NUMW = {
    "en": r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen"
          r"|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand",
    "fr": r"deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|vingts?|trente"
          r"|quarante|cinquante|soixante|cents?|mille",
    "es": r"dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieci\w+|veinte|veinti\w+"
          r"|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|doscient[oa]s|trescient[oa]s"
          r"|cuatrocient[oa]s|quinient[oa]s|seiscient[oa]s|setecient[oa]s|ochocient[oa]s|novecient[oa]s|mil",
    "it": r"(?:due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici"
          r"|diciassette|diciotto|diciannove|venti?|trenta?|quaranta?|cinquanta?|sessanta?|settanta?|ottanta?|novanta?"
          r"|cento|mille|mila|uno|un)+",
    # Fable item 5: "und" is only a JOIN token ("hundertundfünfzig"), never the first token of a glued run --
    # otherwise "Dollar und Euro" (a bare coordinating "and") started a spelled amount on its own.
    "de": r"(?:ein|zwei|drei|vier|funf|sechs|sieben|sieb|acht|neun|zehn|elf|zwolf|zwanzig|dreissig|vierzig|funfzig"
          r"|sechzig|siebzig|achtzig|neunzig|hundert|tausend)"
          r"(?:und|ein|zwei|drei|vier|funf|sechs|sieben|sieb|acht|neun|zehn|elf|zwolf|zwanzig|dreissig|vierzig|funfzig"
          r"|sechzig|siebzig|achtzig|neunzig|hundert|tausend)*",
    "nl": r"(?:een|twee|drie|vier|vijf|zes|zeven|acht|negen|tien|elf|twaalf|twintig|dertig|veertig|vijftig|zestig"
          r"|zeventig|tachtig|negentig|en|honderd|duizend)+",
    "sv": r"(?:en|ett|tva|tre|fyra|fem|sex|sju|atta|nio|tio|elva|tolv|tjugo|trettio|fyrtio|femtio|sextio|sjuttio"
          r"|attio|nittio|hundra|tusen)+",
    "da": r"to|tre|fire|fem|seks|syv|otte|ni|ti|tyve|tredive|fyrre|halvtreds|tres|halvfjerds|firs|halvfems|hundrede"
          r"|tusind",
    "no": r"to|tre|fire|fem|seks|sju|syv|atte|ni|ti|tjue|tretti|forti|femti|seksti|sytti|atti|nitti|hundre|tusen",
    "fi": r"(?:yksi|kaksi|kolme|nelja|viisi|kuusi|seitseman|kahdeksan|yhdeksan|kymmenen|kymmenta|toista|sata|sataa"
          r"|tuhat|tuhatta)+",
    "ru": r"два|две|двух|три|трех|четыре|четырех|пять|пяти|шесть|шести|семь|семи|восемь|восьми|девять|девяти|десять"
          r"|десяти|\w+надцат\w*|двадцат\w*|тридцат\w*|сорок\w*|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяносто"
          r"|сто|ста|сот|двест\w*|двухсот\w*|трист\w*|трехсот\w*|четырест\w*|четырехсот\w*|\w+сот|тысяч\w*",
    "sr": r"dva|dve|tri|cetiri|pet|sest|sedam|osam|devet|deset|\w+naest|dvadeset|trideset|cetrdeset|pedeset|sezdeset"
          r"|sedamdeset|osamdeset|devedeset|sto|stotin\w*|dvesta|trista|cetiristo|petsto|sesto|sedamsto|osamsto"
          r"|devetsto|hiljad\w*",
}
# Words that may JOIN number words ("fifteen hundred AND fifty", "mille ET un", "veinte Y cinco") but never start one.
_NUMW_JOIN = r"and|et|y|e|und|en|og|och|i|и"
# Tokens that are also common function words: allowed inside an amount, never as its only / first token.
_NUMW_NOSTART = r"to|en|ni|ti|sei|sex|fem|pet|tre|tres|once|ett|un|uno|ein|een"
_NUMW_TOKEN = "|".join(f"(?:{v})" for v in _NUMW.values())
_SPELLED_NUM = (
    rf"(?:(?:a|an|un|une|ein|eine|een)\s+(?:hundred|thousand|cent|mille|hundert|tausend|honderd|duizend)(?!\w)"
    rf"|(?!(?:{_NUMW_NOSTART})\s)(?:{_NUMW_TOKEN})(?!\w))"
    rf"(?:[\s-]+(?:(?:{_NUMW_JOIN})[\s-]+)?(?:{_NUMW_TOKEN})(?!\w))*"
)
_SPELLED_MONEY = (
    rf"(?:{_SPELLED_NUM})\s+(?:(?:{_CUR_WORD})|grand)(?!\w)"
    r"|\d+\s?grand(?!\w)"
)
# Spelled amounts are rewritten to a figure ("$100") once per sentence in _fold(), rather than added to MONEY_RE:
# MONEY_RE is scanned many times per sentence (per verb, per noun, per language) and the number-word alternation is
# the costliest branch; one substitution pass per sentence keeps the detector's cost flat and lets every rule
# (P1..P8, RANGE, the "make ..." lookahead) see a spelled amount exactly as it sees a figure.
_SPELLED_RE = re.compile(r"(?<!\w)(?:" + _SPELLED_MONEY + r")")
# cheap gate: a currency word (or "grand") right after a word -- only then is the number-word pass run
_SPELLED_GATE = re.compile(r"[^\W\d_]\s+(?:" + _CUR_WORD + r"|grand)(?!\w)")
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
    # 1b/hedge: "report" is the PROHIBITION class (explaining/quoting a banned claim -- reported regardless of a
    # later contrast word). "hedge" is the HEDGE class (a personal disclaimer: "I cannot promise/guarantee/predict
    # ..." or "no guarantee(s)") -- a hedge earlier in the sentence does not extend across a genuine contrast word
    # to swallow a real claim that follows it, but a PROHIBITION does (see _report_lo). "promise"/"guarantee"/
    # "predict" were removed from this list's cannot/can't/don't/doesn't alternations and moved to "hedge" below.
    report=[r"prohibit\w*", r"forbid\w*", r"banned?", r"not\s+(?:allowed|permitted)", r"may\s+not", r"must\s+not",
            r"must\s+never", r"should\s+not", r"shouldn't", r"never\s+(?:say|claim|tell|state|suggest|imply)",
            r"(?:do|does)\s+not\s+(?:say|claim|tell|state|suggest|imply|represent)",
            r"(?:don't|doesn't)\s+(?:say|claim|tell|state|suggest|imply|represent)",
            r"(?:cannot|can't|can't)\s+(?:say|claim|tell|state|suggest|imply|represent)",
            r"misleading", r"deceptive", r"false", r"illegal", r"unlawful", r"(?:such\s+as|like)\s*[\"'“‘]",
            r"claims?\s+(?:like|such\s+as|that)", r"representations?\s+(?:of|about|regarding)\s+(?:income|earnings)", r"(?:income|earnings)\s+(?:claims?|representations?)", r"implied", r"such\s+representations", r"representations?\s+and/?\s*or\s+images", r"images\s+used\s+to\s+show", r"statements?\s+(?:like|such\s+as|that)", r"examples?\s+(?:of|include)"],
    hedge=[r"(?:cannot|can't|can't|do\s+not|does\s+not|don't|doesn't)\s+(?:promise|guarantee|predict)"],
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
# 1b: the "make/made/earned" lookaheads also accept a spelled amount or a non-route currency symbol
_LA_1B = ""
_LA_1B += r"|[₹₦₱¥₩₺₴₽₸₵₡₲₭₫฿৳₨💰💵💸]|(?:zar|ngn|inr|kes|php|aed|thb|mxn|rs\.?|ksh)\s?\d"
if _LA_1B:
    L["en"]["strong"] = [x.replace(r"(?:[$€£\d]|", r"(?:[$€£\d]" + _LA_1B + "|", 1) if "(?=" in x else x for x in L["en"]["strong"]]
# "Managers make more than a full-time teacher": make/made followed by a comparative
L["en"]["strong"] = [x.replace(r"(?:[$€£\d]|", r"(?:[$€£\d]|(?:far\s+|much\s+|way\s+)?more\s+than|as\s+much\s+as|twice|double|triple|\w+\s+times\s+(?:the|a|what)|", 1) if x.startswith("(?:make|makes|making)") or x.startswith("made") else x for x in L["en"]["strong"]]

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
    hedge=[r"ne\s+(?:peux|peut|pouvez|pouvons|peuvent)\s+(?:pas|rien)\s+(?:promettre|garantir|predire)"],
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
    hedge=[r"no\s+(?:puedo|puede|podemos|pueden)\s+(?:prometer|garantizar|predecir)"],
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
    hedge=[r"non\s+(?:posso|puo|possiamo|possono)\s+(?:promettere|garantire|prevedere)"],
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
    hedge=[r"(?:kann|kannst|k(?:o|ö)nnen|k(?:o|ö)nnt)\s+(?:\w+\s+){0,2}nichts?\s+(?:versprechen|garantieren|vorhersagen)"],
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
    hedge=[r"kan\s+(?:\w+\s+){0,2}niets?\s+(?:beloven|garanderen|voorspellen)"],
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
    hedge=[r"kan\s+inte\s+(?:lova|garantera|f(?:o|ö)rutsaga)"],
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
    hedge=[r"kan\s+ikke\s+(?:love|garantere|forudsige)"],
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
    hedge=[r"kan\s+ikke\s+(?:love|garantere|forutsi)"],
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
    hedge=[r"ei\s+voi\s+(?:luvata|taata|ennustaa)"],
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
    hedge=[r"не\s+(?:могу|может|можем|могут)\s+(?:обещать|гарантировать|предсказать)"],
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
    hedge=[r"ne\s+(?:mogu|moze|mozemo)\s+(?:obecati|garantovati)", r"не\s+(?:могу|може|можемо)\s+(?:обећати|гарантовати)"],
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
# 1b/period: "$1,500/mo", "$200/month" -- the slash form glued to the amount had no (?<!\w) boundary to satisfy.
PERIOD = re.compile(r"(?:(?<!\w)(?:month\w*|week\w*|year\w*|annual\w*|/\s?(?:mo|month|wk|yr|year)|" + _TR_PERIOD
                    + r"|mes|meses|mese|mesi|an|ans|annee\w*|ano|anos|anno|anni|jahr\w*|jaar|ar|aret|vuo\w*|год\w*|godin\w*|годин\w*)"
                    + r"|/\s?(?:mo|month|wk|week|yr|year|an|mois|mes|monat|maand|mese))(?!\w)")
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
_NOUN_NOT = re.compile(r"\s+(?:tax\w*|statements?|disclosure|brackets?|thresholds?|levels?|requirements?|verification|summar\w*|overview\w*|skatt\w*|steuer\w*|impot\w*|impuest\w*|impost\w*|belasting\w*|vero\w*|налог\w*|porez\w*)")
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
    # Fable item 6: a "save/discount" word ("Expect to save about $10 a month as a Preferred Customer", "Espere
    # un descuento de 15 dolares al mes") describes a CONSUMER saving, not an earnings projection; add
    # sav\w*/spar\w*/econom\w*/ahorr\w* (and each locale's equivalent) to rule context. es "descont\w*" also
    # missed its own noun/verb stem "descuent\w*" (descuento/descontar both fold to "descuent*" or "descont*"
    # depending on conjugation -- keep both).
    # "mail\w*" is NOT here (see _P3BC_MAIL below): RULECTX is shared by P5/P6/P8/P9/_report_lo too, and "mailed"
    # is a normal word in a real projection's own delivery clause ("Supervisor: about $1,500 a month, mailed on
    # the 15th." is P5 on step 1) -- adding it here silently turned those into misses. A P3bc-local exclusion
    # keeps the "Bonus checks of $100 or more are mailed to Supervisors every month" fix scoped to P3bc only.
    "en": r"pay|pays|paid|spend\w*|cost\w*|fees?|price\w*|order\w*|purchas\w*|buy\w*|tax\w*|refund\w*|deduct\w*|charg\w*|minimum|maximum|threshold|shipping|delivery|postage|discount\w*|withheld|held|accumulat\w*|invoice\w*|vat|sav\w*",
    "fr": r"pai\w*|pay\w*|depens\w*|cout\w*|frais|prix|commande\w*|achat\w*|achet\w*|impot\w*|taxe\w*|rembours\w*|dedui\w*|deduct\w*|minimum|maximum|seuil|livraison|remise\w*|facture\w*|tva|econom\w*",
    "es": r"pag\w*|gast\w*|cost\w*|cuota\w*|tarifa\w*|precio\w*|pedido\w*|compra\w*|impuest\w*|reembols\w*|descuent\w*|descont\w*|deduc\w*|minimo|maximo|umbral|envio|entrega|factura\w*|iva|ahorr\w*",
    "it": r"pag\w*|spes\w*|cost\w*|quota\w*|prezz\w*|ordin\w*|acquist\w*|impost\w*|tass\w*|rimbors\w*|detratt\w*|trattenut\w*|minimo|massimo|soglia|spedizion\w*|consegna|fattur\w*|iva|risparm\w*",
    "de": r"zahl\w*|bezahl\w*|ausgeb\w*|kost\w*|gebuhr\w*|preis\w*|bestell\w*|kauf\w*|steuer\w*|erstatt\w*|abgezogen|einbehalten|mindest\w*|hochst\w*|maximal\w*|schwelle|versand\w*|liefer\w*|rechnung\w*|mwst|spar\w*",
    "nl": r"betal\w*|uitgeven|kost\w*|vergoeding\w*|prijs\w*|bestel\w*|aankoop\w*|koop\w*|belasting\w*|terugbetal\w*|ingehouden|afgetrokken|minimum|maximum|minimaal|maximaal|drempel|verzend\w*|lever\w*|factuur\w*|btw|bespaar\w*|besparing\w*",
    "sv": r"betal\w*|kostar|kostnad\w*|avgift\w*|pris\w*|bestall\w*|kop\w*|skatt\w*|aterbetal\w*|dras|avdrag\w*|minst|minimum|max\w*|frakt\w*|leverans\w*|faktur\w*|moms|spar\w*",
    "da": r"betal\w*|koster|omkostning\w*|gebyr\w*|pris\w*|bestil\w*|kob\w*|skat\w*|refusion|fratrak\w*|traekkes|minimum|maks\w*|fragt\w*|levering\w*|faktur\w*|moms|spar\w*",
    "no": r"betal\w*|koster|kostnad\w*|gebyr\w*|pris\w*|bestill\w*|kjop\w*|skatt\w*|refusjon|trekkes|fratrekk\w*|minimum|maks\w*|frakt\w*|levering\w*|faktur\w*|mva|spar\w*",
    "fi": r"maks\w*|kulu\w*|hinta\w*|hinnan|tilau\w*|ostos\w*|osta\w*|vero\w*|hyvity\w*|vahenn\w*|vahimm\w*|enimm\w*|toimitus\w*|lasku\w*|alv|saast\w*",
    "ru": r"плат\w*|оплат\w*|трат\w*|стоим\w*|сбор\w*|цен\w*|заказ\w*|покуп\w*|налог\w*|возврат\w*|удерж\w*|вычет\w*|миним\w*|максим\w*|порог\w*|доставк\w*|счет\w*|ндс|сэконом\w*|эконом\w*",
    "sr": r"plac\w*|plat\w*|trosk\w*|kost\w*|naknad\w*|cen\w*|porudzb\w*|narudzb\w*|naruc\w*|poruc\w*|kupov\w*|porez\w*|povrac\w*|odbij\w*|minim\w*|maksim\w*|prag\w*|dostav\w*|racun\w*|pdv|плаћ\w*|трошк\w*|накнад\w*|цен\w*|порез\w*|ustede\w*|usteda\w*",
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
# 1b/currency: "Rs. 30,000" -- the rupee abbreviation's period is not a sentence end
_SPLIT = re.compile(_SPLIT.pattern.replace("(?<=[.!?])", r"(?<=[.!?])(?<!(?<!\w)[Rr]s\.)", 1))


def sentences(text):
    return [s for s in _SPLIT.split(text or "") if s and s.strip()]


def _clause_initial(s: str, start: int) -> bool:
    """Whether position `start` opens a clause: the very start of the sentence, or right after a "," or ";"
    (only whitespace in between). A bare mid-clause adverb ("... still earn ...", "... teacher and ...") is not
    a genuine contrastive conjunction splitting the sentence into two independent clauses (Fable B1)."""
    if start == 0:
        return True
    j = start
    while j > 0 and s[j - 1].isspace():
        j -= 1
    return j > 0 and s[j - 1] in ",;"


class _ClauseIndex:
    """Precomputed clause-break (and 1b hedge-scan) offsets for one sentence.

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

    1b's hedge scope (`_report_lo`) added the same shape of per-call rescan:
    `CONTRAST_RE[lang].finditer(s, 0, pos)` and `_QUOTE.search(s, 0, pos)`
    were each re-run from 0 for every verb/noun/rank/amount match in the
    sentence, i.e. the same O(N)-per-lookup / O(N^2)-overall pattern this
    class already exists to avoid. `contrast_starts`/`contrast_ends` and
    `quote_starts` precompute those matches once per (sentence, lang) so
    `contrast_lo`/`quote_before` answer in O(log N) too. Only a CLAUSE-
    INITIAL contrast word (sentence start, or right after a "," or ";") is
    kept: a bare adverb like "still"/"yet"/"though" used mid-clause ("... still
    earn $500 ...", "... teacher and ...") is not a genuine contrastive
    conjunction splitting the sentence into two independent clauses, and
    treating it as one let an earlier PROHIBITION get skipped over (Fable
    B1: "FBOs are prohibited from claiming that new members still earn $500
    a month ..." wrongly fired because "still" was treated as if it opened a
    new, unreported clause).

    `_reported` itself has the identical pre-existing shape: `V[lang]["report"].search(s, lo, pos)` (whole-clause/
    whole-sentence scope by design -- a "prohibited"/"misleading" earlier in the sentence marks everything after it
    as reported, however far away) and `POST_BAN_RE[lang].search(s, end)` are each called once per verb/noun/rank/
    amount match too. `report_starts`, `hedge_starts` and `post_ban_starts` precompute those matches once per
    (sentence, lang) so `report_between`/`hedge_between`/`post_ban_after` answer in O(log N) as well, with the
    identical result (the scope itself is unchanged -- only how fast repeated queries over it are answered).

    `report` is the PROHIBITION vocabulary and `hedge` is the HEDGE vocabulary (see the `L[lang]["hedge"]`
    docstring): `_report_lo` uses `report_starts` alone to decide whether a PROHIBITION word before a contrast word
    forces the whole-sentence scope back on (a prohibition dominates a later contrast; only a HEDGE may be
    re-scoped past), while `_reported`'s own reported-claim search uses `report_starts` UNION `hedge_starts` (the
    combined vocabulary), exactly like the single pre-split `report` list used to.
    """

    __slots__ = (
        "ends", "starts", "contrast_starts", "contrast_ends", "quote_starts", "report_starts", "hedge_starts",
        "post_ban_starts",
    )

    def __init__(self, s: str, lang: str) -> None:
        starts = []
        ends = []
        for m in _CLAUSE_BREAK.finditer(s):
            starts.append(m.start())
            ends.append(m.end())
        self.starts = starts
        self.ends = ends
        contrast_starts = []
        contrast_ends = []
        for c in CONTRAST_RE[lang].finditer(s):
            if _clause_initial(s, c.start()):
                contrast_starts.append(c.start())
                contrast_ends.append(c.end())
        self.contrast_starts = contrast_starts
        self.contrast_ends = contrast_ends
        self.quote_starts = [m.start() for m in _QUOTE.finditer(s)]
        self.report_starts = [m.start() for m in V[lang]["report"].finditer(s)]
        self.hedge_starts = [m.start() for m in V[lang]["hedge"].finditer(s)]
        self.post_ban_starts = [m.start() for m in POST_BAN_RE[lang].finditer(s)]

    def seg_start(self, pos: int) -> int:
        """End offset of the last clause break that ends at or before `pos`, or 0."""
        idx = bisect.bisect_right(self.ends, pos) - 1
        return self.ends[idx] if idx >= 0 else 0

    def seg_end(self, pos: int, length: int) -> int:
        """Start offset of the first clause break at or after `pos`, or `length`."""
        idx = bisect.bisect_left(self.starts, pos)
        return self.starts[idx] if idx < len(self.starts) else length

    def contrast_lo(self, pos: int) -> tuple[int, int]:
        """(start, end) of the last CLAUSE-INITIAL CONTRAST match before `pos`, or (0, 0) if none -- `end` is the
        identical result to the pre-1b-review `for c in CONTRAST_RE[lang].finditer(s, 0, pos): lo = c.end()`
        (restricted to clause-initial matches; see the class docstring); `start` lets `_report_lo` check whether a
        PROHIBITION word precedes the contrast word itself, not just the verb."""
        idx = bisect.bisect_left(self.contrast_starts, pos) - 1
        return (self.contrast_starts[idx], self.contrast_ends[idx]) if idx >= 0 else (0, 0)

    def quote_before(self, pos: int) -> bool:
        """Whether a quotation mark occurs before `pos` -- identical result to `_QUOTE.search(s, 0, pos)`."""
        return bisect.bisect_left(self.quote_starts, pos) > 0

    def report_between(self, lo: int, pos: int) -> bool:
        """Whether a "report" (PROHIBITION) vocabulary match starts in [lo, pos) -- identical result to
        `V[lang]["report"].search(s, lo, pos)`."""
        i = bisect.bisect_left(self.report_starts, lo)
        return i < len(self.report_starts) and self.report_starts[i] < pos

    def hedge_between(self, lo: int, pos: int) -> bool:
        """Whether a "hedge" vocabulary match starts in [lo, pos) -- identical result to
        `V[lang]["hedge"].search(s, lo, pos)`."""
        i = bisect.bisect_left(self.hedge_starts, lo)
        return i < len(self.hedge_starts) and self.hedge_starts[i] < pos

    def post_ban_after(self, end: int) -> bool:
        """Whether a POST_BAN match starts at or after `end` -- identical result to `POST_BAN_RE[lang].search(s, end)`."""
        i = bisect.bisect_left(self.post_ban_starts, end)
        return i < len(self.post_ban_starts)


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


CONTRAST = {
    "en": r"but|however|yet|although|though|still|nevertheless|nonetheless|that\s+said|even\s+so",
    "fr": r"mais|cependant|toutefois|pourtant|neanmoins",
    "es": r"pero|sin\s+embargo|no\s+obstante|aunque|xxx\s+xxxxxxx|xx\s+xxxxxxxx",
    "it": r"ma|pero|tuttavia|comunque",
    "de": r"aber|jedoch|doch|allerdings|trotzdem",
    "nl": r"maar|echter|toch",
    "sv": r"men|dock|anda",
    "da": r"men|dog|alligevel",
    "no": r"men|likevel|dog",
    "fi": r"mutta|kuitenkin|silti",
    "ru": r"но|однако",
    "sr": r"ali|medjutim|medutim|ipak|али|међутим|ипак",
}
CONTRAST_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in CONTRAST.items()}
_QUOTE = re.compile(r"[\"“”«»„]")


def _report_lo(s, pos, lang, idx: "_ClauseIndex | None" = None):
    """1b/hedge: a HEDGE in an EARLIER contrast clause ("I cannot promise anything, BUT most FBOs earn $900") does
    not turn the projection after the contrast word into a reported claim. Never applied when a quotation mark
    precedes the verb (a quoted banned claim may itself contain "but"), and never applied when a PROHIBITION word
    (see `L[lang]["hedge"]`'s docstring) precedes the contrast word: a prohibition explanation dominates the whole
    sentence regardless of a later "but" ("Statements that you will earn $5,000 a month are banned, but so is
    saying that most FBOs earn $900 a month" must stay reported past "but" too -- Fable B1). Only a genuine
    CLAUSE-INITIAL contrast word re-scopes at all (see `_clause_initial`/the `_ClauseIndex` docstring).

    `idx.quote_before`/`idx.contrast_lo`/`idx.report_between` (when a precomputed `_ClauseIndex` is passed) answer
    this in O(log n) instead of rescanning s[0:pos] for `_QUOTE`/`CONTRAST_RE`/`V[lang]["report"]` on every call.
    The four post-contrast scans (EST6_RE/_PROGRAM/_RULE1B/RULECTX_RE) are bounded to
    `min(_seg_end(s, pos, idx), pos + WIN_AFTER + 40)` instead of running unbounded to the end of the sentence --
    Fable verified identical verdicts with that bound (item B2)."""
    if idx is not None:
        if idx.quote_before(pos):
            return 0
        c_start, c_end = idx.contrast_lo(pos)
    else:
        if _QUOTE.search(s, 0, pos):
            return 0
        c_start = c_end = 0
        for c in CONTRAST_RE[lang].finditer(s, 0, pos):
            if _clause_initial(s, c.start()):
                c_start, c_end = c.start(), c.end()
    if not c_end:
        return 0
    reported_before_contrast = (
        idx.report_between(0, c_start) if idx is not None else bool(V[lang]["report"].search(s, 0, c_start))
    )
    if reported_before_contrast:
        return 0
    lo = c_end
    # Fable perf addendum: bounding only the upper end left the window (`lo` to `rhi`) as wide as `pos - lo`,
    # which stays huge for the WHOLE rest of a long unpunctuated sentence when `lo` is pinned at one EARLY
    # clause-initial contrast that never recurs ("but prohibited you earn $900 a month and " * N, no comma to
    # open a later contrast) -- O(n) per call again, O(n^2) overall. `rlo` bounds the window's WIDTH the same way
    # P1/P2 already bound theirs (WIN_BEFORE before the verb, plus the same +40 margin as `rhi`); the re-scope
    # point returned below (`lo` = c_end) is unchanged -- only this existence-check's search window is windowed.
    rlo = max(lo, pos - WIN_BEFORE - 40)
    rhi = min(_seg_end(s, pos, idx), pos + WIN_AFTER + 40)
    if not EST6_RE[lang].search(s, rlo, rhi) and (
            _PROGRAM.search(s, rlo, rhi) or _RULE1B.search(s, rlo, rhi) or RULECTX_RE[lang].search(s, rlo, rhi)):
        # "..., but qualifying Managers can earn up to $400 under Forever2Drive": a rule clause after the contrast
        # word, with no estimate marker -- keep the whole-sentence scope
        return 0
    return lo


def _reported(s, pos, end, lang, idx: "_ClauseIndex | None" = None):
    """`report_between`/`hedge_between`/`post_ban_after` (when a precomputed `_ClauseIndex` is passed) answer in
    O(log n) instead of rescanning s[lo:pos]/s[end:] for `V[lang]["report"]`/`V[lang]["hedge"]`/`POST_BAN_RE` on
    every call -- otherwise identical results. The PROHIBITION (`report`) and HEDGE (`hedge`) vocabularies are
    searched together here, exactly like the single pre-split `report` list used to be: the split only matters to
    `_report_lo`'s decision about whether a preceding word may be re-scoped past a contrast word."""
    lo = _report_lo(s, pos, lang, idx)
    if idx is not None:
        return idx.report_between(lo, pos) or idx.hedge_between(lo, pos) or idx.post_ban_after(end)
    return bool(
        V[lang]["report"].search(s, lo, pos) or V[lang]["hedge"].search(s, lo, pos)
        or POST_BAN_RE[lang].search(s, end)
    )


def _subordinate(s, v, lang, idx=None):
    lo = _seg_start(s, v.start(), idx)
    # Fable B2: `lead` was unbounded (s[lo:v.start()]), so a long unpunctuated clause with many verb matches (no
    # comma/clause-break to advance `lo`) made every scan below O(len(lead)) per call and O(n^2) overall. Capping
    # to the last ~400 chars bounds each call while preserving identical verdicts (Fable verified this on the full
    # battery): a genuine relative/subordinating clause marker sits close to the verb it governs, well inside 400
    # chars, in every real (and every synthetic battery) sentence.
    lead = s[max(lo, v.start() - 400):v.start()]
    voc = V[lang]
    if lang in V2_LANGS and not _words(lead) and not s[:lo].rstrip().endswith(","):
        return True  # verb-first: conditional or question ("Verdient ein FBO EUR 1 an Bonus, wird ...")
    # relative pronoun directly before the verb ("FBOs who earn", "qui gagnent", "som tjanar"), allowing one adverb.
    # `between` (lead[r.end():]) shrinks as r moves later, so only the LAST match can have <= 1 word before the
    # verb, and only the FIRST match can sit directly after the clause-opening comma (lead[:r.start()] grows as r
    # moves later) -- checking every match for both conditions was redundant and, for a sentence with many "rel"
    # matches before `lo` advances, the same O(n^2) shape as the unbounded `lead` above (Fable B2).
    rel_matches = list(voc["rel"].finditer(lead))
    if rel_matches:
        r = rel_matches[-1]
        between = lead[r.end():]
        if len(_words(between)) <= 1 and not voc["modal"].search(between):
            return True
        r = rel_matches[0]
        # verb-final relative clause opened right after a comma: ", die mehr als 450 EUR verdienen"
        if lo > 0 and not lead[:r.start()].strip() and not voc["modal"].search(lead[r.end():]):
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
    # Fable perf addendum: `before` was unbounded (s[lo:v.start()]), the same O(len)-per-call / O(n^2)-overall
    # shape as the pre-existing P3 bug and _subordinate's `lead` above -- an unpunctuated sentence with many verb
    # matches (no comma/clause-break to advance `lo`) made this and the following `re.finditer` + two more
    # `.search()` calls (all over the same growing `before`) cost O(n) each. Capped to the same ~400 chars as
    # `_subordinate`'s `lead`, for the identical result (`neg`/`no_subj` only ever look a few words back; `near`
    # is explicitly the last 3 words).
    before = s[max(lo, v.start() - 400):v.start()]
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
    s = fold(raw)
    if _SPELLED_GATE.search(s):
        s = _SPELLED_RE.sub("$100", s)
    return s


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
        if _subordinate(s, v, lang, idx) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang, idx):
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
        if _subordinate(s, v, lang, idx) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang, idx):
            continue
        return ("P2", lang, raw)
    return None


def _detect_p3(s, lang, raw, idx: "_ClauseIndex | None" = None):
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
        # Pre-existing quadratic path: `re.finditer(..., s[:n.start()])` rescanned from 0 for every income-noun
        # match, so a sentence with N unpunctuated nouns was O(N) per lookup / O(N^2) overall (~5.2s for 2,000).
        # `near` only ever needs the last 3 word-tokens before the noun, so bound the rescan to WIN_BEFORE chars --
        # comfortably more than 3 tokens except in pathological cases with no word shorter than ~20 chars, which
        # `_NOUN_NOT`/`voc["noun"]` never produce -- for the identical `near` value.
        wlo = max(0, n.start() - WIN_BEFORE)
        w = list(re.finditer(r"[\w'’]+", s[wlo:n.start()]))
        near = s[wlo + w[-3].start():n.start()] if len(w) >= 3 else s[wlo:n.start()]
        if _reported(s, n.start(), n.end(), lang, idx) or voc["neg"].search(near):
            continue
        return ("P3", lang, raw)
    return None


def _detect_p5(s, lang, raw, idx: "_ClauseIndex | None" = None):
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
        if _reported(s, r.start(), r.end(), lang, idx) or RULECTX_RE[lang].search(tail):
            continue
        return ("P5", lang, raw)
    return None


def _detect_p6(s, lang, raw, idx=None):
    voc = V[lang]
    for m in MONEY_RE.finditer(s):
        if _PERCENT_OR_CC.match(s, m.start()):
            continue
        lo, hi = _seg_start(s, m.start(), idx), _seg_end(s, m.end(), idx)
        # Fable perf addendum: `clause = s[lo:hi]` (and `voc["rel"].search(s, lo, ...)` below) was unbounded --
        # pre-existing in step 1, not new to 1b, but the same O(len)-per-call / O(n^2)-overall shape as the other
        # fixes above: an unpunctuated sentence with many money matches (no comma/clause-break to advance lo/hi)
        # made every scan here O(n). Windowed to a generous 400 chars each side (P6 is clause-scoped, not
        # verb-distance-scoped like P1/P2, so this stays much wider than WIN_BEFORE/WIN_AFTER) for the identical
        # result on real and battery text -- Fable verified this on the full battery.
        wlo, whi = max(lo, m.start() - 400), min(hi, m.end() + 400)
        clause = s[wlo:whi]
        if not PERIOD.search(s, m.end(), min(hi, m.end() + 40)) and not PERIOD.search(s, max(lo, m.start() - 30), m.start()):
            continue
        if not voc["earner"].search(clause) or not EST6_RE[lang].search(clause):
            continue
        if RULECTX_RE[lang].search(clause) or voc["neg"].search(clause) or _reported(s, m.start(), m.end(), lang, idx):
            continue
        if any(not PERIOD.match(clause, c.end() + 1) for c in voc["conj"].finditer(clause)) \
                or voc["rel"].search(s, wlo, m.start()):
            continue
        return ("P6", lang, raw)
    return None


def _detect_p4(s, lang, raw, idx=None):
    voc = V[lang]
    for p in voc["promise"].finditer(s):
        lo = _seg_start(s, p.start(), idx)
        if _reported(s, p.start(), p.end(), lang, idx) or voc["neg"].search(s, lo, p.start()):
            continue
        return ("P4", lang, raw)
    return None


# >>> 1b block
# ---------------------------------------------------------------------------------------------------------------
# STEP 1b extensions
# ---------------------------------------------------------------------------------------------------------------
# P7 (compare): an earn verb, or an income noun as subject, compared with an OUTSIDE pay benchmark -- a profession or
# a salary/wage -- instead of an amount ("Managers earn more than a teacher's salary", "twice the minimum wage",
# "Les Managers gagnent plus qu'un enseignant"). Ranks are never a benchmark ("Managers earn more than Supervisors").
_PROF = {
    "en": r"teachers?|nurses?|doctors?|lawyers?|engineers?|accountants?|police\s*(?:officers?|m[ae]n)|surgeons?|dentists?|pilots?|ceos?|bankers?|professors?|civil\s+servants?|most\s+(?:people|professionals|workers|employees|doctors|lawyers)|(?:the\s+)?average\s+(?:worker|employee|person|household)",
    "fr": r"enseignants?|professeurs?|instituteurs?|institutrices?|infirmier\w*|medecins?|docteurs?|avocats?|ingenieurs?|comptables?|policiers?|fonctionnaires?|la\s+plupart\s+des\s+(?:gens|salaries|travailleurs)",
    "es": r"maestr[oa]s?|profesor\w*|enfermer[oa]s?|medic[oa]s?|doctor\w*|abogad[oa]s?|ingenier[oa]s?|contador\w*|policias?|funcionari[oa]s?|la\s+mayoria\s+de\s+(?:la\s+gente|los\s+trabajadores)",
    "it": r"insegnant[ei]|professor\w*|infermier[eia]|medic[oi]|dottor\w*|avvocat[oi]|ingegner[ei]|commercialist[ai]|poliziott[oi]|impiegat[oi]|la\s+maggior\s+parte\s+(?:della\s+gente|dei\s+lavoratori)",
    "de": r"lehrer\w*|krankenschwester\w*|krankenpfleger\w*|arzt|arzte\w*|aerzte\w*|anwalt|anwalte\w*|ingenieur\w*|polizist\w*|beamte\w*|die\s+meisten\s+(?:menschen|angestellten|arbeitnehmer)",
    "nl": r"leraren|leraar|docent\w*|verpleegkundigen?|artsen?|dokters?|advocaten?|ingenieurs?|politieagent\w*|ambtenaren?|de\s+meeste\s+(?:mensen|werknemers)",
    "sv": r"larare|lararen|sjukskoterska\w*|lakare\w*|advokat\w*|ingenjor\w*|polis\w*|de\s+flesta\s+(?:manniskor|anstallda)",
    "da": r"laerer\w*|larer\w*|sygeplejersk\w*|laege\w*|lage\w*|advokat\w*|ingenior\w*|politibetjent\w*|de\s+fleste\s+(?:mennesker|ansatte)",
    "no": r"laerer\w*|larer\w*|sykepleier\w*|lege\w*|advokat\w*|ingenior\w*|politi\w*|de\s+fleste\s+(?:mennesker|ansatte)",
    "fi": r"opettaj\w*|sairaanhoitaj\w*|laakari\w*|lakimie\w*|insinoor\w*|poliisi\w*|useimmat\s+(?:ihmiset|palkansaajat)",
    "ru": r"учител\w*|медсестр\w*|врач\w*|юрист\w*|адвокат\w*|инженер\w*|полицейск\w*|чиновник\w*|большинство\s+(?:людей|работников)",
    "sr": r"nastavni\w*|uciteljic\w*|ucitelj\w*|medicinsk\w+\s+sestr\w*|lekar\w*|doktor\w*|advokat\w*|inzenjer\w*|policaj\w*|vecina\s+(?:ljudi|zaposlenih)",
}
_PAYBENCH = {
    "en": r"(?:(?:a|an|the|your|their|his|her|my|most|many)\s+)?(?:\w+(?:'s|s')\s+)?(?:(?:current|average|typical|regular|normal|monthly|annual|yearly|full[\s-]?time|part[\s-]?time|minimum|national|living|median|corporate|professional)\s+){0,2}(?:salar(?:y|ies)|wages?|paychecks?|pay\s?cheques?|day\s+jobs?)",
    "fr": r"(?:(?:un|une|le|la|votre|leur|ton|son|mon)\s+)?(?:(?:bon|gros|vrai)\s+)?(?:salaire|smic)(?:\s+(?:minimum|moyen|mensuel|a\s+temps\s+plein|actuel|d'\w+|de\s+\w+))*",
    "es": r"(?:(?:un|el|su|tu|mi)\s+)?(?:salario|sueldo)(?:\s+(?:minimo|medio|promedio|mensual|a\s+tiempo\s+completo|actual|de\s+\w+))*",
    "it": r"(?:(?:uno|lo|il|un|tuo|suo)\s+)?(?:stipendio|salario)(?:\s+(?:minimo|medio|mensile|a\s+tempo\s+pieno|attuale|di\s+\w+))*",
    "de": r"(?:(?:ein|eine|einem|einer|das|den|dem|ihr|ihren|dein|deinen|sein)\s+)?(?:\w*gehalt|\w*lohn)",
    "nl": r"(?:(?:een|het|je|uw|jouw)\s+)?(?:\w*salaris|\w*loon|modaal\s+inkomen)",
    "sv": r"(?:(?:en|din|ett)\s+)?(?:\w*lon)",
    "da": r"(?:(?:en|din|et)\s+)?(?:\w*lon(?:nen)?)",
    "no": r"(?:(?:en|din|et)\s+)?(?:\w*lonn(?:en)?)",
    "fi": r"(?:\w*palkka\w*)",
    "ru": r"(?:\w*зарплат\w*|\w*оклад\w*)",
    "sr": r"(?:\w*plat[aeu])",
}
_CMP = {
    "en": r"(?:(?:far|much|way|a\s+lot|easily|often)\s+)?(?:\d+(?:[.,]\d+)?\s*(?:%|percent|per\s+cent|pour\s*cent|por\s*ciento|prozent|per\s*cento)\s+(?:on\s+top\s+of|of)|more\s+than|as\s+much\s+as|higher\s+than|twice|double|triple|(?:two|three|four|five|ten|several|many)\s+times)\s+(?:what\s+)?",
    "fr": r"(?:bien\s+|beaucoup\s+)?(?:\d+(?:[.,]\d+)?\s*(?:%|percent|per\s+cent|pour\s*cent|por\s*ciento|prozent|per\s*cento)\s+(?:de|du|en\s+plus\s+de)\s*|plus\s+qu[e']\s*|autant\s+qu[e']\s*|davantage\s+qu[e']\s*|(?:deux|trois|quatre|cinq|dix|plusieurs)\s+fois\s+(?:plus\s+qu[e']\s*)?|le\s+double\s+(?:d[eu']\s*)?)",
    "es": r"(?:mucho\s+)?(?:\d+(?:[.,]\d+)?\s*(?:%|percent|per\s+cent|pour\s*cent|por\s*ciento|prozent|per\s*cento)\s+(?:de|del)\s+|mas\s+que\s+|tanto\s+como\s+|el\s+doble\s+(?:de\s*l?\s*|que\s+)|(?:dos|tres|cuatro|cinco|diez|varias)\s+veces\s+(?:mas\s+que\s+)?)",
    "it": r"(?:molto\s+)?(?:\d+(?:[.,]\d+)?\s*(?:%|percent|per\s+cent|pour\s*cent|por\s*ciento|prozent|per\s*cento)\s+(?:di|del\w*)\s*|piu\s+di\s*|piu\s+che\s+|quanto\s+|il\s+doppio\s+(?:di\s*|del\w*\s*)|(?:due|tre|quattro|cinque|dieci)\s+volte\s+(?:piu\s+di\s*)?)",
    "de": r"(?:viel\s+|deutlich\s+)?(?:\d+(?:[.,]\d+)?\s*(?:%|percent|per\s+cent|pour\s*cent|por\s*ciento|prozent|per\s*cento)\s+(?:von|des|ihres|deines|seines)\s+|mehr\s+als\s+|so\s+viel\s+wie\s+|das\s+doppelte\s+(?:von\s+|eines?\s+|des\s+)?|(?:zwei|drei|vier|funf|zehn)mal\s+so\s+viel\s+wie\s+)",
    "nl": r"(?:veel\s+)?(?:meer\s+dan\s+|evenveel\s+als\s+|net\s+zoveel\s+als\s+|het\s+dubbele\s+van\s+|(?:twee|drie|vier|vijf|tien)\s+keer\s+(?:zoveel\s+als\s+|meer\s+dan\s+)?)",
    "sv": r"(?:mycket\s+)?(?:mer\s+an\s+|lika\s+mycket\s+som\s+|dubbelt\s+sa\s+mycket\s+som\s+)",
    "da": r"(?:meget\s+)?(?:mere\s+end\s+|lige\s+sa\s+meget\s+som\s+|dobbelt\s+sa\s+meget\s+som\s+)",
    "no": r"(?:mye\s+)?(?:mer\s+enn\s+|like\s+mye\s+som\s+|dobbelt\s+sa\s+mye\s+som\s+)",
    "fi": r"(?:paljon\s+)?(?:enemman\s+kuin\s+|yhta\s+paljon\s+kuin\s+|kaksi\s+kertaa\s+enemman\s+kuin\s+)",
    "ru": r"(?:гораздо\s+|намного\s+)?(?:больше,?\s+(?:чем\s+)?|столько\s+же,?\s+сколько\s+|вдвое\s+больше,?\s+(?:чем\s+)?)",
    "sr": r"(?:mnogo\s+)?(?:vise\s+od\s+|koliko\s+i\s+|duplo\s+vise\s+od\s+)",
}
_CMP_DET = r"(?:(?:a|an|the|un|une|uno|una|un'|ein|eine|einen|einem|einer|een|en|ett|et|de|des|du|le|la|el|il|lo|los|gli|die|der|den|dem)\s+)?"
_CMP_NOUN_SUBJ = {
    "en": r"(?:bonus(?:es)?|income|earnings|commissions?|pay\s?checks?|bonus\s+checks?)\s+(?:alone\s+)?(?:(?:is|are|can|could|will|would|be|often|easily|typically|usually|quickly|soon)\s+){1,3}",
}
# literal keys every _CMP phrase contains (cheap pre-check before the full comparison pattern)
_CMP_KEY = re.compile(_fold_pattern(r"%|percent|cent|prozent|more|much|higher|twice|double|triple|times|plus|autant|davantage|fois|mas|tanto|doble|veces|piu|quanto|doppio|volte|mehr|viel|doppelte|mal|meer|evenveel|zoveel|dubbele|keer|mer|mycket|dubbelt|mere|meget|mye|enemman|paljon|kertaa|больше|столько|вдвое|vise|koliko|duplo"))
_CMP_ADJ = r"(?:(?:most|many|some|typical|average|qualified|experienced|senior|junior|full[\s-]?time|part[\s-]?time|la\s+plupart\s+des|la\s+mayoria\s+de\s+los|die\s+meisten|de\s+meeste|la\s+maggior\s+parte\s+degli)\s+){0,2}"
_CMP_RE = {}
for _k in L:
    _bench = "(?:" + _PROF[_k] + "|" + _PAYBENCH[_k] + ")"
    _CMP_RE[_k] = re.compile(r"(?<!\w)" + _fold_pattern(_CMP[_k]) + _CMP_DET + _CMP_ADJ + _fold_pattern(_bench) + r"(?!\w)")
_CMP_NOUN_SUBJ_RE = {k: re.compile(r"(?<!\w)" + _fold_pattern(v)) for k, v in _CMP_NOUN_SUBJ.items()}


def _detect_p7(s, lang, raw, idx=None):
    voc = V[lang]
    cre = _CMP_RE[lang]
    if not _CMP_KEY.search(s) or not cre.search(s):
        return None  # one scan: no comparison with an outside pay benchmark anywhere in the sentence
    for v in voc["strong"].finditer(s):
        hi = min(_seg_end(s, v.end(), idx), v.end() + 60)
        c = cre.search(s, v.end(), hi)
        if not c or re.search(r"[\d$€£]", s[v.end():c.start()]):
            continue
        if _subordinate(s, v, lang, idx) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang, idx):
            continue
        return ("P7", lang, raw)
    if lang in _CMP_NOUN_SUBJ_RE:
        for n in _CMP_NOUN_SUBJ_RE[lang].finditer(s):
            c = cre.match(s, n.end())
            if not c:
                continue
            lo = max(_seg_start(s, n.start(), idx), n.start() - WIN_BEFORE)
            if voc["neg"].search(s, lo, c.start()) or _reported(s, n.start(), n.end(), lang, idx):
                continue
            return ("P7", lang, raw)
    return None


# P8 (expect): an expectation verb -- expect / count on / plan on / look forward to -- with an amount per period,
# either subject-less ("Expect roughly EUR500 a month once you have three active legs") or with an earner subject
# ("You can count on $500 a month"). Rule context in the clause (pay, order, fee, shipping ...) sets it aside.
EXPECT = {
    "en": r"expect(?:s|ing|ed)?|count(?:s|ing)?\s+on|plan(?:s|ning)?\s+(?:on|for)|anticipat(?:e|es|ing)|look(?:s|ing)?\s+forward\s+to|bank(?:s|ing)?\s+on|reckon\s+on",
    "fr": r"comptez\s+sur|compter\s+sur|compte\s+sur|attendez[\s-]vous\s+a|attends[\s-]toi\s+a|s'attendre\s+a|tablez\s+sur|misez\s+sur",
    "es": r"cuent[ae]\s+con|contar\s+con|esper[ae]|esperar|esperad",
    "it": r"aspettat[ie]|aspettarsi|aspettarti|si\s+aspetti|conta(?:te)?\s+su|contare\s+su",
    "de": r"rechne(?:n|t)?\s+(?:sie\s+|du\s+)?mit|erwarte(?:n|t)?|stell(?:en)?\s+(?:dich|sie\s+sich)\s+auf",
    "nl": r"reken\s+(?:maar\s+)?op|verwacht",
    "sv": r"rakna\s+med|forvanta\s+dig|forvantas",
    "da": r"regn\s+med|forvent",
    "no": r"regn\s+med|forvent",
    "fi": r"odota|odottaa",
    "ru": r"рассчитывайте\s+на|рассчитывай\s+на|рассчитывать\s+на|ожидайте|ожидай|ожидать",
    "sr": r"racunajte\s+na|racunaj\s+na|ocekujte|ocekuj|ocekivati",
}
EXPECT_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in EXPECT.items()}
# Fable B3: `^` never matches at pos > 0 with `.match(s, lo, ...)` (only Python's re.MULTILINE makes `^` match
# after a newline; there is no way to make it match at an arbitrary `pos`), so with the leading `^` this pattern
# was DEAD whenever lo > 0 -- i.e. whenever the clause-initial "expect"/"count on" was not at the true start of
# the sentence (after a leading clause + comma: "Once you have three active legs, expect ..."; "Realistically,
# expect ..."). `.match(s, lo, v.start())` already anchors the search at `lo`; only the trailing `$` (anchored to
# `v.start()` via `endpos`) is needed.
_LEAD_FILLER = re.compile(r"[\s*_>#•·\-\d.)]*(?:(?:so|and|then|just|realistically|honestly|initially|typically|generally|usually|et|alors|y|entonces|e|quindi|und|dann|en|dus|och|sa|og|ja|и|i)\s+)*$")


def _detect_p8(s, lang, raw, idx=None):
    voc = V[lang]
    for v in EXPECT_RE[lang].finditer(s):
        lo, hi = _seg_start(s, v.start(), idx), _seg_end(s, v.end(), idx)
        wlo, whi = max(lo, v.start() - WIN_BEFORE), min(hi, v.end() + WIN_AFTER)
        initial = v.start() - lo <= WIN_BEFORE and _LEAD_FILLER.match(s, lo, v.start())
        if not (initial or voc["earner"].search(s, wlo, v.start())):
            continue
        m = _money(s, v.end(), whi, v, lang)
        if not m or _PERCENT_OR_CC.match(s, m.start()):
            continue
        if not PERIOD.search(s, m.end(), min(hi, m.end() + 40)) and not PERIOD.search(s, v.end(), m.start()):
            continue
        rhi = min(hi, m.end() + 40)
        # Fable item 7: searching from `wlo` (before the verb) let the EXPECT verb match itself trip this guard --
        # ru "рассчитывайте" contains the "рассчит*" stem _RULE1B uses for "calculated"; sr "racunajte" contains
        # the "racun*" stem RULECTX uses for "invoice/bill" -- so the guard fired on every ru/sr "count on"
        # projection regardless of actual context. Starting from `v.end()` excludes the verb's own span.
        if RULECTX_RE[lang].search(s, v.end(), rhi) or _PROGRAM.search(s, v.end(), rhi) or _RULE1B.search(s, v.end(), rhi):
            continue
        # V2 languages read a sentence-initial verb as a conditional ("Verdient ein FBO ..., wird ..."); an imperative
        # ("Rechne mit etwa 500 EUR im Monat", "Reken op ...") is verb-first too, so that reading needs a main clause
        # after a comma before it can set the expectation aside.
        v2_imperative = lang in V2_LANGS and v.start() == lo and s.find(",", v.end()) < 0
        if (not v2_imperative and _subordinate(s, v, lang, idx)) or _negated(s, v, lang, idx) or _reported(s, v.start(), v.end(), lang, idx):
            continue
        return ("P8", lang, raw)
    return None


# P3b (noun): an income noun tied to a rank or earner and an amount per period, with no verb and no estimate
# ("Manager income: $3,000/month", "Managers receive bonus checks of $3,000 or more every month");
# P3c: "bonus" as the income noun, only with an estimate marker ("A typical monthly bonus at Manager level is $3,000").
NOUN_B = {
    "en": r"incomes?|earnings|salar(?:y|ies)|pay\s?checks?|pay\s?cheques?|bonus\s+checks?|bonus\s+cheques?|take[\s-]home(?:\s+pay)?",
    "fr": r"revenus?|gains|salaires?|remuneration",
    "es": r"ingresos?|ganancias|salarios?|sueldos?",
    "it": r"reddit[oi]|guadagn[oi]|stipendi[oi]?",
    # bare "verdienst" is also the verb ("Verdienst du ... EUR 1 an Bonus, werden ..."): only compounds or after a determiner
    "de": r"\w*einkommen|\w+verdienst|(?:der|den|dem|des|ihr\w*|dein\w*|sein\w*|monatlich\w*|durchschnittlich\w*)\s+verdienst|gehalt|geh(?:a|ä)lter",
    "nl": r"\w*inkomen|inkomsten|salaris|verdiensten",
    "sv": r"\w*inkomst(?:er)?|lon(?:en)?|fortjanst",
    "da": r"\w*indkomst|lon(?:nen)?|indtjening",
    "no": r"\w*inntekt|lonn(?:en)?|inntjening",
    "fi": r"tulot|ansiot|palkka|kuukausitulo\w*",
    "ru": r"доход\w*|заработ(?:ок|ка)|зарплат\w*",
    "sr": r"prihod\w*|zarad[aeu]|plat[aeu]",
}
NOUN_C = {
    "en": r"bonus(?:es)?|commissions?|payouts?", "fr": r"bonus|primes?|commissions?", "es": r"bonos?|bonificacion\w*|comision\w*",
    "it": r"bonus|provvigion[ei]", "de": r"bonus|boni|provision\w*", "nl": r"bonus\w*|provisie\w*", "sv": r"bonus\w*|provision\w*",
    "da": r"bonus\w*|provision\w*", "no": r"bonus\w*|provisjon\w*", "fi": r"bonus\w*|palkkio\w*", "ru": r"бонус\w*|комисси\w*",
    "sr": r"bonus\w*|provizij\w*",
}
NOUN_B_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in NOUN_B.items()}
NOUN_C_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in NOUN_C.items()}
# program / cap words that make an amount a published rule, not earnings (Forever2Drive, travel allowance, "up to")
# 1b: threshold / condition / worked-example wording around an income noun or an expected amount: a published rule
# ("bonus income BELOW $10 a month is carried forward", "FBOs WITH income of $600 or more a year receive a 1099",
# "Manager income is CALCULATED monthly: 13% Volume Bonus on $5,000 of group VOLUME is $650", "about 4 CC a month")
_RULE1B = re.compile(_fold_pattern(
    r"(?<!\w)(?:below|under|less\s+than|at\s+least|exceed\w*|above|reach\w*\s+(?:a\s+|the\s+)?(?:total\s+of\s+|minimum\s+of\s+)?(?:[$€£]|\d)|calculat\w*|computed|volume|case\s+credits?|cc"
    r"|(?:of|in|de|di|an|van|av|af|из)\s+(?:products?|produits?|productos?|prodotti|produkte?n?|producten|продукци\w*)|dépass\w*|excède\w*|excede\w*|supera\w*|übersteig\w*|überschreit\w*|overschrijd\w*|overstijg\w*"
    r"|overskrid\w*|ylittä\w*|превыша\w*|prelaz\w*|premaš\w*|moins\s+de|menos\s+de|meno\s+di|weniger\s+als|minder\s+dan"
    r"|mindre\s+än|mindre\s+end|mindre\s+enn|calcul\w*|berechn\w*|calcol\w*|berekend|beräkn\w*|beregn\w*|lasket\w*|рассчит\w*"
    r"|obračun\w*|volum\w*|umsatz\w*|omzet)(?!\w)"))
_WITH_NOUN = re.compile(r"(?:with|whose|having|avec|con|mit|met|med|joilla|с|sa)\s+(?:\w+\s+){0,2}$")
_PROGRAM = re.compile(r"forever\s?2\s?drive|f2d|chairman|allowance|incentive\s+trip|up\s+to|jusqu'a|hasta|fino\s+a|bis\s+zu|tot\s+(?:wel\s+)?\d|upp\s+till|op\s+til|inntil|jopa|до\s+\d|do\s+\d")


# Fable review round 2: "mailed to <rank>" is a P3bc-LOCAL exclusion (not RULECTX -- RULECTX is shared by
# P5/P6/P8/P9/_report_lo, and "mailed" is an ordinary word in a real projection's own delivery clause,
# e.g. "Supervisor: about $1,500 a month, mailed on the 15th." must stay P5). It exists only to catch the
# passive payout-processing shape "Bonus checks of $100 or more are mailed to Supervisors every month.".
_P3BC_MAIL = re.compile(r"mailed\s+to\s+(?:\w+\s+){0,2}" + ROLE.pattern)


def _p3bc_money(s, n, lo, hi):
    """The noun's money match, or None if it is a percent/CC figure, a payment/mailing THRESHOLD, or a "mailed to
    <rank>" payout-processing clause (see `_P3BC_MAIL`).

    Fable item 8: a payment/mailing THRESHOLD ("Bonus checks of $100 or more are mailed to Supervisors every
    month") is a payout-processing rule, not a projection -- apply the same "or more/above" guard P2 already has.
    P2's own PERIOD exception is bounded to WIN_AFTER of the verb, not the whole clause (P2 itself narrows `hi` to
    `v.end() + WIN_AFTER` before this check) -- reuse that same bound here, so a period marker anywhere later in a
    long clause ("... every month") doesn't defeat the threshold guard the way an unbounded clause-`hi` would.
    Split out of `_detect_p3bc` to keep that function's branching (flake8 C901) within bounds.
    """
    m = _money(s, n.end(), min(hi, n.end() + 60)) or _money(s, max(lo, n.start() - 40), n.start())
    if not m or _PERCENT_OR_CC.match(s, m.start()):
        return None
    rhi = min(hi, m.end() + WIN_AFTER)
    if _POST_THRESHOLD.match(s, m.end()) and not PERIOD.search(s, m.end(), rhi):
        return None
    if _P3BC_MAIL.search(s, m.end(), rhi):
        return None
    return m


def _detect_p3bc(s, lang, raw, idx=None):
    voc = V[lang]
    if not (NOUN_B_RE[lang].search(s) or NOUN_C_RE[lang].search(s)) or not PERIOD.search(s) or not MONEY_RE.search(s):
        return None
    for kind, rx in (("B", NOUN_B_RE[lang]), ("C", NOUN_C_RE[lang])):
        for n in rx.finditer(s):
            if _NOUN_NOT.match(s, n.end()):
                continue
            lo, hi = _seg_start(s, n.start(), idx), _seg_end(s, n.end(), idx)
            if s.startswith(": ", hi):
                hi = _seg_end(s, hi + 2, idx)  # "Manager income: $3,000/month" -- the amount follows the label's colon
            m = _p3bc_money(s, n, lo, hi)
            if not m:
                continue
            # the noun's own window, as P1/P2 bound theirs, so a long unpunctuated clause stays linear
            wlo, whi = max(lo, n.start() - WIN_BEFORE), min(hi, n.end() + WIN_AFTER)
            clause = s[wlo:whi]
            if not (ROLE.search(clause) or voc["earner"].search(clause)):
                continue
            if not PERIOD.search(clause):
                continue
            if kind == "C" and not (voc["estimate"].search(clause) or RANGE.search(clause)):
                continue
            if RULECTX_RE[lang].search(clause) or _PROGRAM.search(clause) or _RULE1B.search(clause):
                continue
            if _WITH_NOUN.search(s, wlo, n.start()):
                continue
            w = list(re.finditer(r"[\w'’]+", s[wlo:n.start()]))
            near = s[wlo + w[-3].start():n.start()] if len(w) >= 3 else s[wlo:n.start()]
            if voc["neg"].search(near) or voc["neg"].search(s, min(n.end(), m.start()), max(n.end(), m.start())):
                continue
            if _reported(s, n.start(), n.end(), lang, idx):
                continue
            if voc["rel"].search(s, wlo, max(m.start(), n.start())) or voc["conj"].search(s, wlo, max(m.start(), n.start())):
                continue
            return ("P3", lang, raw)
    return None


# Header-scoped role rows (markdown tables and "Heading:" lists): an income header ("Typical monthly income",
# "Revenu mensuel typique", "Monatseinkommen") over rows whose first cell / label is a Forever rank and whose cell in
# that column is an amount ("| Supervisor | $1,500 |").
_HEAD_NOUN = re.compile(r"(?<!\w)(?:" + "|".join(_fold_pattern(NOUN_B[k]) for k in NOUN_B) + r")(?!\w)")
_HEAD_VERB = re.compile("|".join(V[k]["strong"].pattern for k in V))
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_ALL_RULECTX = re.compile(r"(?<!\w)(?:" + "|".join(_fold_pattern(v) for v in RULECTX.values()) + r")(?!\w)")
_ROLE_CELL = re.compile(r"^[\s*_]*" + ROLE.pattern + r"[\s*_:]*(?:\([^)]*\))?[\s*_]*$")
_LIST_ROW = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+(.*)$")
# Fable B4: a worked-example/calculation header ("Income calculation", "Bonus income example on 4 CC", "Income
# disclosure statement") is a compliant explanation of how a figure is derived, not an income projection; add its
# own header exclusion rather than stretch RULECTX/_RULE1B (which stay scoped to the sentence-level rules).
_HEAD_EXCL = (
    r"example\w*|illustration\w*|sample\w*|calculation\w*|disclosure\w*|statements?"
    r"|exemples?|illustrations?|echantillons?|calculs?|divulgations?|declarations?"
    r"|ejemplos?|ilustracion\w*|muestras?|calculo\w*|divulgacion\w*|declaracion\w*"
    r"|beispiele?|veranschaulichung\w*|musters?|berechnung\w*|offenlegung\w*|erklarung\w*"
    r"|esempi?|illustrazion\w*|campion\w*|calcol\w*|divulgazion\w*|dichiarazion\w*"
    r"|voorbeeld\w*|illustraties?|steekproe\w*|berekening\w*|openbaarmaking\w*|verklaring\w*"
)
_HEAD_EXCL_RE = re.compile(r"(?<!\w)(?:" + _fold_pattern(_HEAD_EXCL) + r")(?!\w)")
# Union of every language's ESTIMATE vocabulary, for the table/list period-or-estimate requirement below (P5's
# own sentence-level rule already requires one; _detect_tables has no single `lang` to key V[lang]["estimate"]
# with, so this reuses each language's already-anchored compiled pattern, exactly as `_HEAD_VERB` does above).
_ALL_ESTIMATE = re.compile("|".join(V[k]["estimate"].pattern for k in V))
# Fable review round 2: a header/heading whose only content -- besides the income noun itself -- is rank/role/
# level filler ("Income", "Earnings by rank:") satisfies the period-or-estimate requirement below too, since it
# already passed every OTHER exclusion (RULECTX/_PROGRAM/_RULE1B/_PERCENT_OR_CC/_HEAD_EXCL) and there is nothing
# left it could be qualified BY. A worked-example header that happens to also lack a period/estimate word
# ("Retail earnings on one $28.60 product") is NOT bare -- it has substantial other content -- so it still needs
# one, same as before.
_HEAD_BARE_FILLER = re.compile(
    r"^[\s*_:|]*(?:(?:by|per|for|of|each|a|the|par|pour|de|por|del|van|voor|av|fur)\s+)*"
    r"(?:ranks?|roles?|levels?|niveau\w*|nivel(?:es)?|livell[oi]|ebene\w*|rangs?)?[\s*_:|]*$"
)


def _bare_noun_head(h):
    """Whether `h` is a bare income-noun header/heading (see `_HEAD_BARE_FILLER`)."""
    m = _HEAD_NOUN.search(h)
    return bool(m and _HEAD_BARE_FILLER.match(h[:m.start()] + h[m.end():]))


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


_LEAD_APPROX = re.compile(r"^[\s*_~≈]*(?:(?:about|around|approx\.?|approximately|roughly|typically|avg\.?|average|environ|env\.|unos|aprox\.?|etwa|ca\.?|circa|rund|ongeveer|ungefar|omkring|omtrent|noin|около|примерно|oko)\s+)?")


def _row_money(cell):
    """An amount that LEADS the cell ("$1,500", "~ $1,500/mo", "about 1 500 EUR"), not one inside a description
    ("Leadership Bonus from $0 upward")."""
    lead = _LEAD_APPROX.match(cell)
    m = MONEY_RE.match(cell, lead.end())
    return m if m and not _PERCENT_OR_CC.match(cell, m.start()) else None


def _detect_tables(text):
    if not text or ("|" not in text and ":" not in text):
        return None
    lines = text.split("\n")
    if len(lines) < 2:
        return None
    folded = [_fold(x) for x in lines]
    i, n = 0, len(lines)
    while i < n:
        f = folded[i]
        # markdown table: header row, separator row, data rows
        if "|" in f and i + 1 < n and _TABLE_SEP.match(folded[i + 1]):
            head = _cells(f[f.index("|"):])  # a header glued to preceding prose ("... success. | Level | Income |")
            # Fable B4: a header naming a worked example/calculation ("Income calculation", "Bonus income example
            # on 4 CC") is a compliant walk-through of how a figure is derived, not a projection; and a program
            # threshold (_RULE1B: "on 1 CC", "at least") or a bare percentage/case-credit figure (_PERCENT_OR_CC)
            # anywhere in the header (not just via RULECTX/_PROGRAM) rules the column out too.
            cols = [
                k for k, h in enumerate(head)
                if (_HEAD_NOUN.search(h) or _HEAD_VERB.search(h))
                and not _ALL_RULECTX.search(h) and not _PROGRAM.search(h)
                and not _RULE1B.search(h) and not _PERCENT_OR_CC.search(h) and not _HEAD_EXCL_RE.search(h)
            ]
            j = i + 2
            has_period_or_estimate = PERIOD.search(f) or _ALL_ESTIMATE.search(f)
            while j < n and folded[j].lstrip().startswith("|"):
                if cols:
                    row = _cells(folded[j])
                    if row and _ROLE_CELL.match(row[0]):
                        row_period_or_estimate = has_period_or_estimate or PERIOD.search(folded[j]) or _ALL_ESTIMATE.search(folded[j])
                        for k in cols:
                            # Fable review round 2: a header whose only content is an unqualified income noun
                            # ("Income", "Rank | Income |") satisfies this too -- it already passed every OTHER
                            # exclusion above (RULECTX/_PROGRAM/_RULE1B/_PERCENT_OR_CC/_HEAD_EXCL), so lacking a
                            # period/estimate word besides the bare noun itself is not evidence of anything;
                            # requiring one dropped "| Rank | Income |\n|---|---|\n| Supervisor | $1,500 |", which
                            # the pre-review 1b caught. Checked per column (not the whole header line) so a
                            # worked-example column elsewhere in the same row ("Retail earnings on one $28.60
                            # product") doesn't launder a genuinely bare column's neighbor -- and vice versa.
                            row_ok = row_period_or_estimate or _bare_noun_head(head[k])
                            if (
                                k < len(row) and row_ok and _row_money(row[k])
                                and not _ALL_RULECTX.search(row[k]) and not _PROGRAM.search(row[k])
                                and not _RULE1B.search(row[k]) and not _PERCENT_OR_CC.search(row[k])
                            ):
                                return ("P5", "table", lines[i] + " / " + lines[j])
                j += 1
            i = j
            continue
        # "Heading:" line (income noun, ends with a colon) followed by "- Rank: amount" list rows
        if (
            f.rstrip().rstrip("*").endswith(":") and _HEAD_NOUN.search(f)
            and not _ALL_RULECTX.search(f) and not _PROGRAM.search(f)
            and not _RULE1B.search(f) and not _PERCENT_OR_CC.search(f) and not _HEAD_EXCL_RE.search(f)
        ):
            j = i + 1
            # Fable review round 2: same as the table case above -- a bare "Earnings by rank:" heading (no
            # period/estimate word besides the income noun itself and rank/role/level filler, already past every
            # other exclusion) satisfies this too; a worked-example heading that merely lacks a period/estimate
            # word too ("Earnings example on one $28.60 product:") is not bare, so it still needs one.
            head_ok = PERIOD.search(f) or _ALL_ESTIMATE.search(f) or _bare_noun_head(f)
            while j < n and _LIST_ROW.match(folded[j]):
                body = _LIST_ROW.match(folded[j]).group(1)
                r = ROLE.search(body)
                if r and r.start() <= 4:
                    sep = re.match(r"(?:\*\*)?\s*(?::|\s-|\|)\s*(?:\*\*)?\s", body[r.end():])
                    tail = body[r.end() + sep.end():] if sep else ""
                    m = _row_money(tail)
                    row_ok = head_ok or PERIOD.search(body) or _ALL_ESTIMATE.search(body)
                    if (
                        sep and m and row_ok
                        and not _ALL_RULECTX.search(tail) and not _PROGRAM.search(tail)
                        and not _RULE1B.search(tail) and not _PERCENT_OR_CC.search(tail)
                    ):
                        return ("P5", "list", lines[i] + " / " + lines[j])
                j += 1
            i = max(j, i + 1)
            continue
        i += 1
    return None


# P9 (worth): the reader's business / team / downline is "worth" an amount per period
# ("Your business will be worth $5,000 a month within a year").
WORTH = {
    "en": r"(?:your|their|his|her|the|a|an|this|my)\s+(?:forever\s+)?(?:business|team|downline|organi[sz]ation|network|group)\s+(?:(?:will|could|can|would|may|might|should|is|are|soon|quickly|easily)\s+){0,2}(?:(?:be|become|grow\s+to\s+be)\s+)?worth",
    "fr": r"(?:votre|ton|leur|son|mon)\s+(?:activite|entreprise|business|equipe|reseau|groupe)\s+(?:(?:va|pourra|peut|pourrait)\s+)?(?:vaut|vaudra|valoir|valait)",
    "es": r"(?:tu|su|mi)\s+(?:negocio|equipo|red|grupo)\s+(?:(?:va\s+a|podra|puede|podria)\s+)?(?:vale|valdra|valer)",
    "it": r"(?:la\s+tua|la\s+sua|il\s+tuo|il\s+suo)\s+(?:attivita|business|squadra|rete|gruppo)\s+(?:(?:potra|puo|potrebbe)\s+)?(?:vale|varra|valere)",
    "de": r"(?:ihr|dein|sein)\s+(?:geschaft|business|unternehmen|team|netzwerk)\s+(?:(?:wird|kann|konnte|ist)\s+)?(?:\S+\s+){0,4}wert",
}
WORTH_RE = {k: re.compile(r"(?<!\w)(?:" + _fold_pattern(v) + r")(?!\w)") for k, v in WORTH.items()}


def _detect_p9(s, lang, raw, idx=None):
    rx = WORTH_RE.get(lang)
    if rx is None:
        return None
    for w in rx.finditer(s):
        lo, hi = _seg_start(s, w.start(), idx), _seg_end(s, w.end(), idx)
        wlo, whi = max(lo, w.start() - WIN_BEFORE), min(hi, w.end() + WIN_AFTER)
        m = _money(s, wlo, whi)
        if not m or not PERIOD.search(s, wlo, whi):
            continue
        if RULECTX_RE[lang].search(s, wlo, whi) or _RULE1B.search(s, wlo, whi) or V[lang]["neg"].search(s, wlo, w.end()) or _reported(s, w.start(), w.end(), lang, idx):
            continue
        if V[lang]["conj"].search(s, wlo, w.start()):
            continue
        return ("P9", lang, raw)
    return None

# <<< 1b block


def detect_lang(text, lang):
    for raw in sentences(text):
        s = _mask_idioms(_fold(raw), lang)
        # Precomputed once per sentence so P1/P2/P3/P4/P5/P6 and the hedge scope (which look up a clause span, or a
        # contrast/quote offset, per verb/noun/rank/amount match) are each O(log n) per lookup instead of O(n),
        # keeping the whole sentence O(n log n) instead of O(n^2).
        idx = _ClauseIndex(s, lang)
        hit = (
            _detect_p1(s, lang, raw, idx)
            or _detect_p2(s, lang, raw, idx)
            or _detect_p3(s, lang, raw, idx)
            or _detect_p5(s, lang, raw, idx)
            or _detect_p6(s, lang, raw, idx)
            or _detect_p4(s, lang, raw, idx)
            or _detect_p7(s, lang, raw, idx)
            or _detect_p8(s, lang, raw, idx)
            or _detect_p3bc(s, lang, raw, idx)
            or _detect_p9(s, lang, raw, idx)
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
    hit = _detect_tables(text)
    if hit:
        return hit
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
