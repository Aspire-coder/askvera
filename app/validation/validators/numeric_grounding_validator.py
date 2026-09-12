"""Validate that numeric claims are grounded in retrieved source text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity
from services.market_config import find_market_mentions, market_adjective_codes
from utils.redaction import PHONE_RE


# Numbers are universal. Claim extraction deliberately does not depend on unit
# words such as "months" or document terms such as "Case Credits": every figure
# is a claim, whatever follows it. Unit words are read only afterwards, by
# _measure, to compare what an answer figure and a source figure count. That
# lexicon is per measure (hour, day, week, month, year, Case Credits, currency,
# percent) in the corpus languages, never per market, and a figure whose unit it
# does not recognise is compared exactly as before. The only abbreviations it
# expands are CC <-> Case Credits and FBO <-> Forever Business Owner, and only
# for subject matching (_with_unit_equivalents).
# A thousands group belongs to the number in front of it. Without this,
# "7 800DZD" was read as the claim "7", which then matched nothing once the
# source had been canonicalised to "7800dzd", and the sentence stating
# Algeria's minimum order was deleted.
_GROUPED_NUMBER = r"\d+(?:[ \u00a0\u202f]\d{3}(?!\d))*(?:[.,]\d+)?"
NUMERIC_CLAIM_PATTERN = re.compile(
    rf"(?<![\w.])(?P<number>{_GROUPED_NUMBER}"
    rf"(?:\s*(?:-|\u2013|\u2014)\s*{_GROUPED_NUMBER})?)(?!\d|\.\d)",
    re.UNICODE,
)


@dataclass(frozen=True)
class MeasurableClaim:
    """One numeric claim extracted from an answer."""

    text: str
    number: str
    start: int
    end: int
    sentence: str
    context: str
    prefix: str


# A space between digits followed by exactly three more, and no fourth: a
# thousands group, so "7 800" becomes "7800" on both the source and the claim.
#
# The sponsoring directory writes amounts in space-grouped and continental
# notation -- Algeria states "7 800DZD" and "0,200CC" -- and a model asked in
# English writes "7,800" and "0.200". Neither was found in the source, so the
# sentence stating the minimum order was deleted, and with nothing left the
# answer fell back to "the approved policy documents do not contain enough
# information". Observed live on 2026-09-08; four of six natural renderings of
# that record produced an empty answer.
#
# Only a SPACE is stripped, never a comma or a point. A space is never a
# decimal separator, so "7 800" can only be 7800. A comma or point before
# three digits is genuinely ambiguous -- "1,000" and "1.000" are one thousand
# and one, depending on locale -- and this corpus states Case Credit
# thresholds, where guessing wrong is a 1000x error in a number a distributor
# acts on. test_numeric_grounding_does_not_treat_thousands_separator_as_decimal
# holds that line and is right to.
_DIGIT_GROUP_RE = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")


def _normalize(text: str) -> str:
    """Normalize text for tolerant, Unicode-safe source matching."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*(?:-|\u2013|\u2014)\s*", "-", normalized)
    normalized = _DIGIT_GROUP_RE.sub("", normalized)
    return normalized.strip()


def _number_variants(number: str) -> set[str]:
    """Return safe decimal notation variants without changing numeric value."""
    normalized = _normalize(number)
    variants = {normalized}
    # A one- or two-digit fractional part is unambiguously decimal in the
    # policy data we validate. Treat comma and point notation as equivalent so
    # an English answer can cite a source that uses continental formatting.
    decimal_match = re.fullmatch(r"(?P<whole>\d+)(?P<separator>[.,])(?P<fraction>\d{1,2})", normalized)
    if decimal_match:
        other_separator = "," if decimal_match.group("separator") == "." else "."
        variants.add(
            f"{decimal_match.group('whole')}{other_separator}{decimal_match.group('fraction')}"
        )

    # A leading zero settles the ambiguity a three-digit tail otherwise carries.
    # "0,200" cannot be a thousands group -- that would just be "200" -- so it
    # is a decimal and "0.200" is the same figure. Algeria's minimum order is
    # written "0,200CC" and a model asked in English renders it "0.200".
    # "1,000" against "1.000" stays ambiguous and is deliberately not covered.
    leading_zero = re.fullmatch(r"0(?P<separator>[.,])(?P<fraction>\d{3,})", normalized)
    if leading_zero:
        other_separator = "," if leading_zero.group("separator") == "." else "."
        variants.add(f"0{other_separator}{leading_zero.group('fraction')}")

    # A grouped thousand also appears ungrouped: a source writing "7 800"
    # normalises to "7800", and an answer writing "7,800" has to be able to
    # reach it. Offered as an alternative to try, never as a replacement, so
    # "1.000" still fails to find "1,000" and the 1000x confusion stays caught.
    grouped = re.fullmatch(r"(?P<whole>\d{1,3})(?P<separator>[.,])(?P<group>\d{3})", normalized)
    if grouped and grouped.group("whole") != "0":
        variants.add(f"{grouped.group('whole')}{grouped.group('group')}")

    # A trailing zero is presentation, not value. Measured on the first live
    # benchmark run: the Algeria record states a delivery cost of "900 DZD
    # ($7.5)", the model wrote "$7.50", and the answer was discarded whole as
    # an ungrounded numeric claim. The figure was right, the source was right,
    # and the retrieval was right; only the formatting differed.
    #
    # The last fractional digit is never removed, so "1.000" reaches "1.0" and
    # stops. Reducing it to "1" would let a claim meaning one thousand match a
    # source saying one, which is the 1000x confusion the grouped rule above
    # is careful to avoid.
    for variant in list(variants):
        decimal = re.fullmatch(r"(?P<whole>\d+)(?P<separator>[.,])(?P<fraction>\d+)", variant)
        if not decimal:
            continue
        whole, separator, fraction = decimal.group("whole", "separator", "fraction")
        trimmed = fraction.rstrip("0") or "0"
        variants.add(f"{whole}{separator}{trimmed}")
        # The mirror case: the answer writes "7.5" where the record writes
        # "7.50", or "0.2" where it writes "0,200". Padding stops at three
        # decimal places, which is as precise as this corpus gets.
        for width in range(len(fraction) + 1, 4):
            variants.add(f"{whole}{separator}{fraction.ljust(width, '0')}")

    # A whole amount is the same amount when the record adds zero cents. Hong
    # Kong states free delivery "for minimum purchase of HK$3,000.00" and a
    # model writes "HK$3,000"; a decimal tail is rightly not a match boundary,
    # so the threshold was removed and the answer kept an empty "Free Delivery:"
    # heading. Exactly two zeros are added, after the padding above, so "24"
    # reaches "24.00" but never "24.000", and a point group keeps a comma for
    # its cents so "3.000" still cannot reach "3,000.00".
    for variant in list(variants):
        if re.fullmatch(r"\d+", variant):
            variants |= {f"{variant}.00", f"{variant},00"}
    if grouped and grouped.group("whole") != "0":
        cents = "," if grouped.group("separator") == "." else "."
        variants.add(f"{normalized}{cents}00")
    return variants


def _word_tokens(text: str) -> set[str]:
    """Return Unicode word tokens for local subject comparison."""
    return set(re.findall(r"[^\W\d_]{2,}", _normalize(text), flags=re.UNICODE))


def _tokens_match(subject_token: str, source_token: str) -> bool:
    """Match exact words or conservative grammatical variants."""
    if subject_token == source_token:
        return True

    shorter_length = min(len(subject_token), len(source_token))
    if shorter_length < 6:
        return False

    common_prefix_length = 0
    for subject_character, source_character in zip(subject_token, source_token):
        if subject_character != source_character:
            break
        common_prefix_length += 1

    return common_prefix_length >= max(6, int(shorter_length * 0.7))


def _subject_matches_window(subject_tokens: set[str], window_tokens: set[str]) -> bool:
    """Return true when every subject word has an exact or inflected match."""
    return all(
        any(_tokens_match(subject_token, window_token) for window_token in window_tokens)
        for subject_token in subject_tokens
    )


_ROLE_ABBREVIATIONS = {
    "fbo": frozenset({"forever", "business", "owner", "owners"}),
}
_BULLET_BOUNDARY_RE = re.compile(r"•|\n\s*\n")
_CONVERSION_TAIL_RE = re.compile(r"\s*[a-z%€£$]{0,3}\s*\(\s*[$€£]?\s*\d[\d.,]*\s*\)")
_ROLE_DIGIT_RE = re.compile(r"\d")
_FBO_ROLE_RE = re.compile(
    r"\bfbo(?:s|['’]s)?\b|\bforever\s+business\s+owners?\b",
    re.IGNORECASE,
)
_OTHER_ROLE_RE = re.compile(
    r"\b(?:preferred|retail|novus)\s+customers?\b|\bcustomers?\b(?!\s+service)"
    r"|\b(?:assistant\s+)?(?:supervisors?|managers?)\b|\bmembers?\b|\bdistributors?\b",
    re.IGNORECASE,
)
_ROLE_CURRENCY_CODES = frozenset("""
aed ars aud bdt bob brl cad chf clp cny cop crc czk dkk dop dzd egp eur gbp
ghs gtq hkd huf idr ils inr jpy kes kgs krw kzt lkr mad mxn myr ngn nok nzd
pab pen php pkr pln pyg ron rsd rub sar sek sgd thb tnd try twd tzs uah ugx
usd uyu vnd zar
""".split())
_ROLE_UNIT_ALIASES = {"$": "usd", "us$": "usd", "€": "eur", "£": "gbp", "%": "pct", "cc": "cc"}
_ROLE_UNIT_BEFORE_RE = re.compile(r"(us\$|\$|€|£)\s{0,2}$", re.IGNORECASE)
_ROLE_UNIT_AFTER_RE = re.compile(r"\s{0,2}(%|€|£|\$|cc(?![a-z])|[a-z]{3}(?![a-z]))", re.IGNORECASE)


def _role_mentions(text: str) -> list[tuple[int, str]]:
    mentions = [(match.start(), "fbo") for match in _FBO_ROLE_RE.finditer(text)]
    mentions += [(match.start(), "other") for match in _OTHER_ROLE_RE.finditer(text)]
    return sorted(mentions)


_ROLE_SENTENCE_END_RE = re.compile(r"\.(?=\s|$)|;")


def _trailing_prose_role(source_text: str, end: int) -> str | None:
    """The role that prose right after this amount assigns it to, within its clause.

    Algeria writes "Minimum order size FBO: 0,200CC as a first order for Preferred
    Customers": the heading names FBO, but the clause gives 0,200CC to Preferred
    Customers. A role that is itself a label ("Preferred Customer: €50") starts
    the next rule, and a new sentence or a clause after a semicolon ("; Preferred
    Customers have no minimum") is a separate rule, so neither is read back onto
    this amount.
    """
    right_boundary = _BULLET_BOUNDARY_RE.search(source_text, end)
    right = right_boundary.start() if right_boundary else len(source_text)
    tail = _CONVERSION_TAIL_RE.match(source_text, end)
    group_end = tail.end() if tail and tail.end() <= right else end
    for stop in (
        _ROLE_DIGIT_RE.search(source_text, group_end, right),
        _ROLE_SENTENCE_END_RE.search(source_text, group_end, right),
    ):
        if stop:
            right = min(right, stop.start())
    segment = source_text[group_end:right]
    for position, role in _role_mentions(segment):
        mention = (_FBO_ROLE_RE if role == "fbo" else _OTHER_ROLE_RE).match(segment, position)
        if mention and re.match(r"\s*:", segment[mention.end():]):
            continue
        return role
    return None


def _occurrence_role(source_text: str, start: int, end: int) -> str | None:
    """Return the role attributed to this occurrence within its source bullet."""
    left = 0
    for boundary in _BULLET_BOUNDARY_RE.finditer(source_text, 0, start):
        left = boundary.end()
    right_boundary = _BULLET_BOUNDARY_RE.search(source_text, end)
    right = right_boundary.start() if right_boundary else len(source_text)
    tail = _CONVERSION_TAIL_RE.match(source_text, end)
    group_end = tail.end() if tail and tail.end() <= right else end
    next_figure = _ROLE_DIGIT_RE.search(source_text, group_end, right)
    after = _role_mentions(source_text[group_end:next_figure.start() if next_figure else right])
    before = _role_mentions(source_text[left:start])
    # Directory records usually bind the role as a label immediately before the
    # amount ("FBO: €81").  A later label in the same extracted bullet can
    # describe a different audience, such as "Preferred Customer: no minimum".
    # Letting that later label override the one that precedes the figure makes a
    # correctly stated FBO amount look unsupported.  A following role is still
    # useful for prose that states the role after its amount.
    # Prose that names a role right after the amount, in the same sentence, is the
    # most specific attribution and outranks a heading label before it.
    trailing = _trailing_prose_role(source_text, end)
    if trailing:
        return trailing
    if before:
        return before[-1][1]
    return after[0][1] if after else None


def _adjacent_unit(text: str, start: int, end: int) -> str:
    """Return the unit immediately beside a figure, when one is stated."""
    before = _ROLE_UNIT_BEFORE_RE.search(text[max(0, start - 4):start])
    if before:
        token = before.group(1).lower()
        return _ROLE_UNIT_ALIASES.get(token, token)
    after = _ROLE_UNIT_AFTER_RE.match(text, end)
    if after:
        token = after.group(1).lower()
        if token in _ROLE_UNIT_ALIASES:
            return _ROLE_UNIT_ALIASES[token]
        if token in _ROLE_CURRENCY_CODES:
            return token
    return ""


def _explicit_role_label_before_amount(text: str, amount_start: int) -> str | None:
    """Return a role only when the source labels this exact amount with it."""
    prefix = text[max(0, amount_start - 90):amount_start]
    for role, pattern in (("fbo", _FBO_ROLE_RE), ("other", _OTHER_ROLE_RE)):
        if re.search(rf"(?:{pattern.pattern})\s*:\s*(?:[a-z]{{1,3}}\$|[^\w\s]+)?\s*$", prefix, pattern.flags):
            return role
    return None


def _with_role_equivalents(
    window_tokens: set[str], attributed_role: str | None = None,
    claim_unit: str = "", source_unit: str = "",
) -> set[str]:
    """Add a full role spelling only for the source figure assigned to it."""
    tokens = set(window_tokens)
    units_agree = not claim_unit or not source_unit or claim_unit == source_unit
    for abbreviation, expansion in _ROLE_ABBREVIATIONS.items():
        forms = {abbreviation, f"{abbreviation}s"}
        if attributed_role == abbreviation and tokens & forms and units_agree:
            tokens |= forms | expansion
    return tokens


def _sentence_for_claim(answer: str, start: int, end: int) -> str:
    """Return the sentence-like local answer window around a numeric claim."""
    left = max(answer.rfind(".", 0, start), answer.rfind("\n", 0, start), answer.rfind(":", 0, start))
    right_candidates = [position for position in (answer.find(".", end), answer.find("\n", end)) if position != -1]
    right = min(right_candidates) if right_candidates else len(answer)
    return answer[left + 1 : right].strip()


def _context_for_claim(answer: str, start: int, end: int, radius: int = 220) -> str:
    """Return nearby answer text that can include a named subject before the number."""
    return answer[max(0, start - radius) : min(len(answer), end + radius)].strip()


# A sentence, clause or line end. Markdown emphasis may close between the
# punctuation and the space: "**Aldersgrense:** Bare voksne personer som er 18
# år" ends its label at ":**", and without allowing for the asterisks the label
# and the capitalised first word after it read as one subject, {aldersgrense,
# bare}, which no source states beside 18.
_SEGMENT_BOUNDARY_RE = re.compile(r"[\n\r]+|(?<=[.!?:;])[*_]*\s")


def _is_title_case_word(word: str) -> bool:
    return word[:1].isupper() and (len(word) == 1 or word[1:].islower())


def _is_acronym(word: str) -> bool:
    return 2 <= len(word) <= 6 and word.isupper()


def _entity_phrases(text: str) -> list[tuple[str, bool, bool]]:
    """Capitalised phrases, each flagged when it is an acronym freed from a segment's first word,
    and whether the phrase itself begins at the segment's first word.

    A segment's first word is capitalised by spelling, not because it is a
    name. Beside a lone acronym it became half of a two-word subject: "Suomessa
    FBO, joka ei ole tehnyt ostosta 36 ..." ("In Finland an FBO who ...")
    required "suomessa" beside 36 in the Finnish 4.05(a) text, and the sentence
    restating that clause was deleted; "Kun FBO" ("When an FBO") did the same.
    The acronym is the name, so it is kept as a one-word subject that must still
    be found beside the figure, and the word in front of it is dropped.

    The third element records whether the entity's own first word is also the
    segment's first word ("Ifølge Company Policy for Norge": "Ifølge" starts
    both). A later capitalised modifier ("According to the US Company Policy":
    "US" starts only the entity, not the sentence) is never sentence-initial
    capitalisation, so it is not exempt from the market-modifier check below.
    """
    entities: list[tuple[str, bool, bool]] = []
    for segment in _SEGMENT_BOUNDARY_RE.split(text):
        first_entity = len(entities)
        current: list[str] = []
        current_start = 0
        # Letters glued to a digit ("2CC", "B2C", "4B") are a unit or a code, not a
        # word of a name: "Under 2CC koster det €12" made "Under CC" a subject.
        # Bounded by non-word characters on both sides, so "GO2FBO" yields
        # nothing rather than the fragments "G" and "BO".
        segment_words = re.findall(r"(?<!\w)[^\W\d_]+(?!\w)", segment, flags=re.UNICODE)
        for index, word in enumerate(segment_words):
            if word[:1].isupper():
                if not current:
                    current_start = index
                current.append(word)
            elif current:
                entities.append((" ".join(current), False, current_start == 0))
                current = []
        if current:
            entities.append((" ".join(current), False, current_start == 0))
        if (
            len(entities) > first_entity
            and len(segment_words) >= 2
            and entities[first_entity][0] == f"{segment_words[0]} {segment_words[1]}"
            and _is_title_case_word(segment_words[0])
            and _is_acronym(segment_words[1])
        ):
            entities[first_entity] = (segment_words[1], True, False)
    return entities


def _capitalized_entity_phrases(text: str) -> list[str]:
    """Extract title-like phrases without a language-specific alphabet or stopword list.

    A phrase never spans a line break or sentence boundary. Word extraction
    discards punctuation, so a heading used to merge into the sentence beneath it:
    "How to Become a Recognized Manager\\n\\nYou must generate..." yielded the
    entity "Recognized Manager You", whose tokens matched no subject in the
    source. The number was then reported ungrounded and the whole answer was
    replaced by the insufficient-evidence fallback.
    """
    return [phrase for phrase, _, _ in _entity_phrases(text)]


# A short lead-in label at the start of the line the figure is on:
# "**Delivery Charge:** For purchases of HK$500 ...". Markdown emphasis and a
# list marker are allowed around it.
_LINE_LABEL_RE = re.compile(
    r"^\s*(?:[-*+•]\s+|\d+[.)]\s+)?[*_]{0,3}(?P<label>[^\W\d_][^\n:.!?;*_]{0,60}?)"
    r"\s*[*_]{0,3}\s*:[*_]{0,3}\s"
)
_LABEL_MAX_WORDS = 5


def _line_label(sentence_prefix: str) -> str:
    match = _LINE_LABEL_RE.match(sentence_prefix)
    if not match or len(re.findall(r"[^\W\d_]+", match.group("label"))) > _LABEL_MAX_WORDS:
        return ""
    return match.group("label")


# Marketing-plan ranks. With the role words above they decide whether a label
# names who or which tier a rule applies to; such a label always binds in full.
_TIER_RE = re.compile(
    r"\b(?:assistant|senior|soaring|sapphire|diamond|platinum|centurion|eagle|chairman)\b",
    re.IGNORECASE,
)
# Letter-digit codes ("B2C", "B2B", "2CC"), which word tokens cannot see.
_CODE_TOKEN_RE = re.compile(r"(?<![^\W_])(?=[^\W_]*\d)(?=[^\W_]*[^\W\d_])[^\W_]{2,8}(?![^\W_])")


def _code_tokens(text: str) -> set[str]:
    return set(_CODE_TOKEN_RE.findall(_normalize(text)))


def _names_role(label: str) -> bool:
    return bool(_role_mentions(label) or _TIER_RE.search(label))


def _spans(words: list[str], minimum_tokens: int) -> list[set[str]]:
    token_sets: list[set[str]] = []
    for start in range(len(words)):
        for end in range(len(words), start, -1):
            tokens = _word_tokens(" ".join(words[start:end]))
            if len(tokens) >= minimum_tokens and tokens not in token_sets:
                token_sets.append(tokens)
    return token_sets


def _label_binding(
    label: str, document_markets: frozenset[str], document_vocabulary: frozenset[str]
) -> tuple[list[set[str]], str]:
    """How an inline lead-in label ("**Delivery Charge:** ...") binds the figures on its line.

    A label is the model's own heading written inline, so a word in it that the
    document never uses cannot be required beside the figure: "**Standard
    Delivery:** ... HK$500 ... HK$50" lost both amounts because the Hong Kong
    record never says "standard". But a label must never bind less than the
    same sentence without it, so dropping words is paid for, not free:

    - a label naming the document's market binds nothing, as before;
    - a label naming a role or tier ("Senior Manager", "Supervisor", "FBO",
      "Preferred Customer") binds in full, one word included;
    - a label whose words the document all uses binds in full, and a one-word
      label must also pass the ordinary lexical check ("context");
    - otherwise the label words and codes the document uses must be beside the
      figure, and the sentence after the label must itself share content words
      with the figure's own rule ("body"). "**Shipping Fee:** A handling fee of
      HK$115 applies" keeps {fee}, which is beside 115, but its sentence shares
      no content word with the banking-fee rule, so 115 is still removed.
    """
    if document_markets and find_market_mentions(label) & document_markets:
        return [], ""
    words = [word for word in re.findall(r"[^\W\d_]+", label, flags=re.UNICODE) if len(word) >= 2]
    if _names_role(label):
        return _spans(words, 1 if len(words) == 1 else 2), ""
    codes = _code_tokens(label)
    known_words = [word for word in words if _in_vocabulary(_normalize(word), document_vocabulary)]
    known_codes = {code for code in codes if code in document_vocabulary}
    # Only a Title Case label was ever a capitalised subject. A sentence-case
    # label ("Delivery charge", "Bonus payment threshold") never bound its words,
    # so its words are not required now either; only its codes and its sentence.
    title_case = bool(words) and all(word[:1].isupper() for word in words)
    if len(known_words) == len(words) and known_codes == codes:
        if not title_case:
            return ([known_codes], "context") if known_codes else ([], "")
        if len(words) >= 2:
            return [tokens | known_codes for tokens in _spans(words, 2)], ""
        subject = _word_tokens(" ".join(words)) | known_codes
        return ([subject], "context") if subject else ([], "")
    subject = (_word_tokens(" ".join(known_words)) if title_case else set()) | known_codes
    return ([subject] if subject else []), "body"


def _in_vocabulary(token: str, vocabulary: frozenset[str]) -> bool:
    return token in vocabulary or any(
        _tokens_match(token, word) for word in vocabulary if len(word) >= 6 and len(token) >= 6
    )


_DOCUMENT_NAME_RE = re.compile(r"^\s*(.+?\.(?:pdf|docx?|txt|md|html?))(?=\s|$)", re.IGNORECASE)
_DOCUMENT_NAME_NOISE = frozenset({"pdf", "doc", "docx", "txt", "html", "htm"})


def _document_name_tokens(document: object) -> frozenset[str]:
    """Words of the file a retrieved document comes from ("COMPANY_POLICY_IT_IT.pdf")."""
    match = _DOCUMENT_NAME_RE.match(str(getattr(document, "title", "") or ""))
    if not match:
        return frozenset()
    return frozenset(
        token for token in _word_tokens(match.group(1).replace("_", " "))
        if len(token) >= 3 and token not in _DOCUMENT_NAME_NOISE
    )


def _without_document_name(words: list[str], name_tokens: frozenset[str]) -> list[str]:
    """Drop a run of two or more words that together name the source document."""
    kept: list[str] = []
    index = 0
    while index < len(words):
        end = index
        while end < len(words) and _in_vocabulary(_normalize(words[end]), name_tokens):
            end += 1
        if end - index >= 2:
            index = end
            continue
        kept.append(words[index])
        index += 1
    return kept


def _names_documents_market(word: str, document_markets: frozenset[str]) -> bool:
    """Whether a single capitalised word names one of the document's own markets.

    Recognition is by market name (``find_market_mentions``) or by adjective
    or demonym (``market_adjective_codes``); either is enough. An unknown
    regional or collective word -- "Benelux", "Scandinavian", "American",
    "US" -- is recognised by neither and returns False, which keeps base's
    behaviour of not forgiving it.
    """
    if not document_markets:
        return False
    if find_market_mentions(word) & document_markets:
        return True
    return bool(market_adjective_codes(word) & document_markets)


# A figure, its unit abbreviation and a parenthetical spelling that abbreviation
# out: "2CC (Crediti Caso)", "2 CC (Credit Certificates)", "**2CC** (Case Credits)".
_UNIT_EXPANSION_RE = re.compile(
    r"(?<![\w.])\d[\d.,]*\s?(?P<unit>[^\W\d_]{2,6})[*_]{0,3}\s*\((?P<expansion>[^()\n]{1,80})\)"
)


def _without_unit_expansions(text: str) -> str:
    """Drop a parenthetical that only expands the unit written beside a figure.

    Such a parenthetical names the unit, not the rule's subject. Letters glued to
    a figure are not words (see _entity_phrases), so in "acquista 2CC (Credit
    Certificati) nell'arco di 2 mesi consecutivi" the expansion alone became the
    subject of the months figure, was absent from the Italian 3.03 clause, and
    repair deleted the whole sentence. Spaced "2 CC (...)" survived only because
    "CC" joined the phrase and matched the source's "2CC".

    Narrow on purpose: the abbreviation must be a known unit (_unit_word_kind),
    and the parenthetical must have one word per letter, each starting with that
    letter. "2CC (Aloe Vera)" and "2CC di Aloe Vera Gel" keep their subject.
    """
    def replace(match: re.Match[str]) -> str:
        unit = match.group("unit")
        words = re.findall(r"[^\W\d_]+", match.group("expansion"))
        expands_unit = (
            unit.isupper()
            and bool(_unit_word_kind(unit.casefold()))
            and len(words) == len(unit)
            and all(word[:1].casefold() == letter.casefold() for word, letter in zip(words, unit))
        )
        if not expands_unit:
            return match.group(0)
        return text[match.start():match.start("expansion") - 1].rstrip() + " "

    return _UNIT_EXPANSION_RE.sub(replace, text)


def _subject_token_sets(
    claim: MeasurableClaim,
    document_markets: frozenset[str] = frozenset(),
    document_vocabulary: frozenset[str] | None = None,
    document_name_tokens: frozenset[str] = frozenset(),
) -> tuple[list[set[str]], str]:
    """Named subjects that connect a number to the policy topic, and what else must
    bind it ("", "context" or "body").

    See _label_binding for the two non-empty modes; every other subject binds
    exactly as it did before inline labels were read.
    """
    # Preserve this occurrence's position: splitting on the numeric text links
    # repeated values to the first subject instead of the current claim. The
    # prefix is already bounded to what precedes THIS occurrence.
    #
    # Bound the subject to the claim's own sentence. A heading two lines above
    # was supplying it: "Requirements to Reach Supervisor" gave {reach,
    # supervisor}, and every token must appear in the source window, so a source
    # sentence reading "Supervisor is achieved by generating a total of 10 Open
    # Group Case Credits" did not match. 10 was reported ungrounded, and the
    # sentence stating the requirement was deleted from the answer or the whole
    # answer was replaced. Measured live on rank-qualification questions, which
    # are close to this bot's core purpose.
    #
    # With no named subject in the sentence, the existing lexical-overlap path
    # applies, which is the same treatment as scripts that do not capitalise.
    # Only a line break or a sentence end bounds the subject. A colon must not:
    # "To qualify as Assistant Manager ... two paths: generate 120 ..." keeps its
    # subject after the colon, and cutting there let a number belonging to
    # another rank pass as grounded.
    sentence_prefix = re.split(r"[\n\r]|(?<=[.!?])[*_]*\s", claim.prefix)[-1]
    phrases = [
        (phrase, freed, starts_segment)
        for phrase, freed, starts_segment in _entity_phrases(_without_unit_expansions(sentence_prefix))
        if freed or len(_word_tokens(phrase)) >= 2
    ][-1:]
    label = _line_label(sentence_prefix) if document_vocabulary is not None else ""
    if label and (not phrases or phrases[0][0] in label):
        return _label_binding(label, document_markets, document_vocabulary)
    # A subject that names the market this document is about is established by
    # the document, not by the sentence beside the number.
    #
    # Observed live 2026-09-08. The New Zealand record states
    # "• Delivery Cost: $8 +gst ($9,20)." and the answer said "For New Zealand,
    # the delivery cost is $8 +GST ($9.20)." The subject became {new, zealand},
    # every token has to appear in the local source window, and that bullet does
    # not repeat the country -- the country is the record's identity. Both
    # figures were reported ungrounded and deleted. Removing the country from
    # the sentence made the same answer ground cleanly, which is backwards:
    # naming the market is what a good answer does.
    #
    # Only the market is forgiven, never an arbitrary title word. A rank subject
    # such as {assistant, manager} still has to be found next to the number, so
    # a figure belonging to a different rank cannot pass.
    if document_markets:
        phrases = [
            (phrase, freed, starts_segment) for phrase, freed, starts_segment in phrases
            if not (find_market_mentions(phrase) & document_markets)
        ]

    token_sets: list[set[str]] = []
    for phrase, freed, starts_segment in phrases:
        words = re.findall(r"[^\W\d_]+", phrase, flags=re.UNICODE)
        minimum_tokens = 1 if freed else 2
        # The document's own name is established by the document, as its market
        # is. "Ifølge Company Policy for Norge må du være 18 år" and "Secondo la
        # Company Policy italiana ... 2 mesi" required "company policy" beside the
        # figure, and no clause repeats its document's title. Only a run of two or
        # more name words is dropped, and never when the sentence names a market
        # the document is not about, wherever it stands: "Ifølge Company Policy
        # for Sverige ... 18 år" against the Norwegian clause keeps its full
        # phrase, as before. Market names come from
        # services.market_config.find_market_mentions (called, not changed), which
        # knows every market in markets.json and the global directory list,
        # including ones without a chat deployment such as Mexico and Spain.
        #
        # A market named as a CAPITALISED MODIFIER inside the document-name run
        # itself is a second, narrower leak this same forgiveness must not
        # cover: "According to the US Company Policy ... 25 Case Credits"
        # against a Canadian record names a market the document is not about,
        # every bit as much as a trailing "for Sverige" does, but the modifier
        # sits where the drop below would otherwise erase it along with
        # "Company Policy" once nothing bigger than "US" is left over. So every
        # capitalised word of this phrase other than one that is only
        # capitalised because it starts the sentence ("Ifølge Company Policy
        # for Norge": "Ifølge") must itself be a recognised mention of the
        # document's OWN market -- by name (find_market_mentions) or by
        # adjective/demonym (market_adjective_codes) -- or the drop does not
        # happen at all and the full phrase is kept exactly as base keeps it.
        # An own-market adjective ("the Canadian Company Policy" against a CA
        # record) is forgiven the same way a trailing "for Norge" is. Regional
        # or collective words find_market_mentions and market_adjective_codes
        # do not know ("Benelux", "Scandinavian", "American", "US") are never
        # forgiven, matching base.
        modifiers = words[1:] if starts_segment else words
        unrecognised_modifier = any(
            not _in_vocabulary(_normalize(word), document_name_tokens)
            and not _names_documents_market(word, document_markets)
            for word in modifiers
        )
        if (
            not unrecognised_modifier
            and document_name_tokens
            and not (find_market_mentions(_claim_sentence_text(claim, sentence_prefix)) - document_markets)
        ):
            unnamed = _without_document_name(words, document_name_tokens)
            if len(unnamed) != len(words):
                words = unnamed
                if len(_word_tokens(" ".join(words))) < 2:
                    continue
        # Consider every contiguous multi-word span, not only suffixes. A leading
        # grammatical word ("For Assistant Manager") was already handled; a
        # TRAILING one was not, so a heading like "Recognized Manager
        # Requirements" produced only spans containing "requirements", which
        # appears in no source, and a correct grounded number was rejected.
        # The number itself must still be present in the source: these spans only
        # decide which occurrence a number is bound to.
        for start in range(len(words)):
            for end in range(len(words), start, -1):
                tokens = _word_tokens(" ".join(words[start:end]))
                if len(tokens) >= minimum_tokens and tokens not in token_sets:
                    token_sets.append(tokens)
    return token_sets, ""


# What a figure measures, read from the unit written beside it. Compared only
# when both the answer and the source state one, so a figure written without a
# unit is judged exactly as before. The list is per measure, not per market:
# it names months, weeks and so on in the corpus languages.
_MEASURE_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern))
    for kind, pattern in (
        ("hour", r"h|hrs?|hours?|tunti\w*|tunnin|timer|timen|uur|uren|ore|heures?|stunden?|horas?"),
        ("day", r"days?|\w*päiv\w*|(?:virke|arbeids|kalender|arbets)?dag(?:e|er|ar|en|ene|arna)?"
                r"|werkdag\w*|giorn[oi]|jours?|tage?n?|días?|dias?"),
        ("week", r"weeks?|viik\w*|uker?|uka|uken|uger?|veck\w*|weken?|settiman[ae]|semaines?|wochen?|semanas?"),
        ("month", r"months?|\w*kuukau\w*|\w*måned\w*|\w*månad\w*|\w*maand\w*|mes[ei]?|meses|mês|mois|\w*monat\w*"),
        ("year", r"years?|vuo(?:si|de\w*|tta)|\w*vuotia\w*|år|års|året|jaar|jaren|ann[oi]|ans|années?"
                 r"|jahre?n?|años?|anos?"),
        ("cc", r"ccs?|crédits?"),
        ("currency:dollar", r"dollars?|dollaria|dollari"),
        ("currency:eur", r"euros?|euroa|euron"),
        ("currency:krone", r"kron(?:er|or|a|e)"),
        ("currency:gbp", r"pounds?"),
        ("percent", r"percent|prosent\w*|procent|prozent|pourcent"),
    )
)
_TIME_KINDS = frozenset({"hour", "day", "week", "month", "year"})
_MEASURE_TOKEN_RE = re.compile(r"[^\W\d_]+|[\d.;:!?()\[\]]")
# A comma ends the figure's clause for its period: in "25 Case Credits, and
# Home Office approval, which takes days, is needed" the days are not the limit's.
# A colon ends it only before a space: Finnish writes "2 CC:n arvosta".
_PERIOD_STOP_RE = re.compile(r"[\d.,;!?\n]|:(?![^\W\d_])")
# A currency code in front of the figure ("HKD 500"). Codes that are also common
# words are not read there.
_CODE_BEFORE_RE = re.compile(r"(?<![^\W\d_])([a-z]{3})\s{1,2}$", re.IGNORECASE)
_AMBIGUOUS_CODE_WORDS = frozenset({"try", "mad", "pen", "cop", "ron", "bob"})
_PERIOD_WORD_LIMIT = 8
# The dollar amounts of different markets are written "$", "HK$" or "HKD"
# interchangeably, so only the family is compared; euro against dollar is not.
_CURRENCY_FAMILIES = {
    **{code: "dollar" for code in ("usd", "hkd", "cad", "aud", "nzd", "sgd", "twd")},
    **{code: "krone" for code in ("nok", "sek", "dkk")},
}


def _unit_word_kind(word: str) -> str:
    for kind, pattern in _MEASURE_WORDS:
        if pattern.fullmatch(word):
            return kind
    return ""


def _written_unit_kind(text: str, start: int, end: int) -> str:
    """The unit written as a symbol or code beside the figure ("HK$50", "HKD 500", "2CC", "30%")."""
    unit = _adjacent_unit(text, start, end)
    if not unit:
        code = _CODE_BEFORE_RE.search(text, max(0, start - 6), start)
        if code and code.group(1).lower() in _ROLE_CURRENCY_CODES - _AMBIGUOUS_CODE_WORDS:
            unit = code.group(1).lower()
    if unit == "cc":
        return "cc"
    if unit == "pct":
        return "percent"
    return f"currency:{_CURRENCY_FAMILIES.get(unit, unit)}" if unit else ""


def _unit_word_after(text: str, scan_from: int) -> str:
    """The unit named by the words right after a figure ("36 peräkkäiseen kalenterikuukauteen")."""
    words: list[str] = []
    for match in _MEASURE_TOKEN_RE.finditer(text, scan_from, min(len(text), scan_from + 80)):
        if not match.group(0)[0].isalpha():
            break
        words.append(unicodedata.normalize("NFKC", match.group(0)).casefold())
        # A fourth word is read only to finish "... Open Group Case Credits".
        if len(words) == 4:
            break
    for index, word in enumerate(words[:3]):
        if word == "case" and index + 1 < len(words) and words[index + 1].startswith("credit"):
            return "cc"
        kind = _unit_word_kind(word)
        # A short word before any unit ("25 per month", "18 or older") ends the
        # figure's own phrase; a unit further on belongs to something else.
        if kind or len(word) <= 3:
            return kind
    return ""


def _period_after(text: str, scan_from: int) -> str:
    """The first time unit later in the figure's own clause ("25 Case Credits in any calendar Month")."""
    limit = min(len(text), scan_from + 120)
    stop = _PERIOD_STOP_RE.search(text, scan_from, limit)
    content_words = 0
    for word in re.findall(r"[^\W\d_]+", text[scan_from:stop.start() if stop else limit]):
        word = unicodedata.normalize("NFKC", word).casefold()
        # Short words are too ambiguous across languages to read as a period
        # ("an", "ora", "dag"), and they do not count towards the limit, so
        # "2 CC koopt binnen een periode van twee opeenvolgende maanden"
        # reaches its months. "år" is the one short word that only means years.
        if len(word) < 4 and word != "år":
            continue
        word_kind = _unit_word_kind(word)
        if word_kind in _TIME_KINDS:
            return word_kind
        content_words += 1
        if content_words == _PERIOD_WORD_LIMIT:
            break
    return ""


def _measure(text: str, start: int, end: int) -> tuple[str, str]:
    """Return (unit, period) for the figure at text[start:end]; "" where none is written.

    The unit is what the figure counts ("25 Case Credits", "36 kuukautta",
    "HK$50"). The period is the first time unit later in the same clause
    ("25 Case Credits in any calendar Month"). A figure in parentheses reads on
    past its bracket: "trettiseks (36) sammenhengende kalendermåneder".
    """
    scan_from = end + 1 if text[end:end + 1] == ")" else end
    kind = _written_unit_kind(text, start, end) or _unit_word_after(text, scan_from)
    return kind, (kind if kind in _TIME_KINDS else _period_after(text, scan_from))


def _claim_measure(claim: MeasurableClaim) -> tuple[str, str]:
    """The claim's unit and period, read at this occurrence rather than the first equal figure."""
    position = len(claim.prefix.lstrip())
    if claim.context[position:position + len(claim.text)] == claim.text:
        return _measure(claim.context, position, position + len(claim.text))
    at = claim.sentence.find(claim.text)
    return _measure(claim.sentence, at, at + len(claim.text)) if at != -1 else ("", "")


def _with_unit_equivalents(window_tokens: set[str]) -> set[str]:
    """"2CC" in a source is "2 Case Credits" in an answer, and "Forever Business Owners" is "FBO".

    Used for subject matching only. The lexical fallback counts shared words, and
    adding words there let "Per restare attivo devi acquistare 2 Case Credits al
    mese" borrow the Preferred Customer clause's "2CC".
    """
    tokens = set(window_tokens)
    if tokens & {"cc", "ccs"}:
        tokens |= {"case", "credit", "credits"}
    if {"forever", "business"} <= tokens and tokens & {"owner", "owners"}:
        tokens |= {"fbo", "fbos"}
    return tokens


_UNIT_LETTERS = frozenset("hmdksx")
_RULE_SEPARATOR_RE = re.compile(r"\s/|/\s")
_CLOCK_READING_RE = re.compile(
    r"\s?(?:h\d{2}|h\b|[ap]\.?\s?m\b|uhr\b|heures?\b|hrs?\b|hours?\b|o['’]?clock\b|uur\b|u\b|timer?\b)",
    re.IGNORECASE,
)


def _claim_position(claim: MeasurableClaim) -> int:
    """This claim's offset in its context, or -1."""
    position = len(claim.prefix.lstrip())
    return position if claim.context[position:position + len(claim.text)] == claim.text else -1


def _glued_letter(text: str, end: int) -> str:
    """A single letter written straight after a figure ("2B"), unless it is a unit ("48h")."""
    match = re.match(r"([a-z])(?![^\W\d_])", text[end:end + 2], re.IGNORECASE)
    letter = match.group(1).lower() if match else ""
    return "" if letter in _UNIT_LETTERS else letter


def _claim_glued_letter(claim: MeasurableClaim) -> str:
    position = _claim_position(claim)
    return _glued_letter(claim.context, position + len(claim.text)) if position != -1 else ""


def _claim_reads_as_clock(claim: MeasurableClaim) -> bool:
    """True when the answer writes this figure as a time of day ("17h00", "9 am", "17 Uhr")."""
    if re.fullmatch(r"\d{1,2}[:.]\d{2}", claim.text):
        return True
    position = _claim_position(claim)
    if position == -1:
        return False
    after = claim.context[position + len(claim.text):position + len(claim.text) + 12]
    before = claim.context[max(0, position - 12):position]
    # "from 09 to 17": two hours joined as a range read as times as well.
    return bool(
        _CLOCK_READING_RE.match(after)
        or _CLOCK_RANGE_AFTER_RE.match(after)
        or _CLOCK_RANGE_BEFORE_RE.search(before)
    )


_CLOCK_RANGE_AFTER_RE = re.compile(
    r"\s?(?:-|–|—|to|à|bis|tot|til|till)\s?\d{1,2}(?:[:.h]\d{2})?(?!\d)", re.IGNORECASE
)
_CLOCK_RANGE_BEFORE_RE = re.compile(
    r"(?<!\d)\d{1,2}(?:[:.h]\d{2})?\s?(?:-|–|—|to|à|bis|tot|til|till)\s?$", re.IGNORECASE
)


def _claim_sentence_text(claim: MeasurableClaim, sentence_prefix: str) -> str:
    """The whole sentence a claim stands in: its prefix, the figure and what follows up to the end."""
    position = _claim_position(claim)
    rest = claim.context[position:] if position != -1 else claim.sentence
    stop = re.search(r"[.!?](?=\s|$)|\n", rest)
    return sentence_prefix + rest[:stop.start() if stop else len(rest)]


def _rule_segment(source_text: str, start: int, end: int, radius: int = 260) -> str:
    """The source text of the one rule a figure belongs to.

    A clause, further cut at a spaced slash, which separates alternatives inside
    a directory field: "B2C/ under 2CC - €18 ex VAT/ over 2CC- €12 ex VAT".
    """
    left = max(0, start - radius)
    for pattern in (_CLAUSE_DELIMITER_RE, _RULE_SEPARATOR_RE):
        for match in pattern.finditer(source_text, left, start):
            left = max(left, match.end())
    right = min(len(source_text), end + radius)
    for pattern in (_CLAUSE_DELIMITER_RE, _RULE_SEPARATOR_RE):
        match = pattern.search(source_text, end, right)
        if match:
            right = min(right, match.start())
    return source_text[left:right]


def _shares_rule_words(sentence: str, segment: str) -> bool:
    """The sentence shares a content word (four letters or more) with the rule, and either a
    second word or every word it has: a value line such as "(888) 440-ALOE (2563)" has one."""
    sentence_tokens = _word_tokens(sentence)
    shared = sentence_tokens & _word_tokens(segment)
    if not any(len(token) >= 4 for token in shared):
        return False
    return len(shared) >= 2 or shared == sentence_tokens


def _measures_agree(claim_measure: tuple[str, str], source_measure: tuple[str, str]) -> bool:
    """Whether an answer figure and a source figure count the same thing over the same period.

    Compared only where both write a unit or a period. A time word beside one
    figure and a count beside the other are two halves of one rule: "2 CC koopt
    binnen 2 maanden" restates "2 CC koopt binnen een periode van twee
    opeenvolgende maanden", whose only 2 is the CC. So a time unit is compared
    with the period stated in the count's own clause, which must state one:
    "2CC ... nell'arco di 4 mesi" does not borrow the 4 of "attivo con i 4CC".
    """
    (claim_kind, claim_period), (source_kind, source_period) = claim_measure, source_measure
    if claim_kind and source_kind and claim_kind != source_kind:
        if (claim_kind in _TIME_KINDS) == (source_kind in _TIME_KINDS):
            return False
        time_kind, count_period = (
            (claim_kind, source_period) if claim_kind in _TIME_KINDS else (source_kind, claim_period)
        )
        return count_period == time_kind
    return not (claim_period and source_period and claim_period != source_period)


def _occurrence_can_support(
    source_text: str,
    start: int,
    end: int,
    claim_letter: str,
    claim_reads_as_clock: bool,
    clock_spans: list[tuple[int, int]],
) -> bool:
    """False for a source figure that is part of a code, another house number, or a clock time.

    A figure glued to a letter in front ("(A2)", "B2C") is part of a code, not a
    quantity. One glued to a letter behind ("Kvarnbygatan 2B") is a house number
    and must be the same one. A clock time supports only a figure the answer
    writes as a time: "17" gains the variant "17.00", and in the Luxembourg
    record that is "Business Hours Office 09.00 am – 17.00 pm", not a count.
    """
    preceding = source_text[start - 1:start] if start else ""
    if preceding.isascii() and preceding.isalpha():
        return False
    if claim_letter and _glued_letter(source_text, end) != claim_letter:
        return False
    return claim_reads_as_clock or not any(
        span_start <= start and end <= span_end for span_start, span_end in clock_spans
    )


# A sentence or clause end, but never the point inside a decimal figure.
_CLAUSE_DELIMITER_RE = re.compile(r"(?<!\d)[.;](?!\d)")


# A point or comma before exactly three digits is a thousands group only where the
# source settles it, figure by figure: the figure is an amount of money in a
# currency that is never written to three decimal places. Observed live on
# 2026-09-12: the Mali record states delivery at "2.000 francs CFA", "3.000" and
# "4.000", the model wrote "2,000", "3,000" and "4,000", and repair deleted the
# whole fee schedule.
#
# Everything else stays as ambiguous as the note on _DIGIT_GROUP_RE says: a Case
# Credit figure ("1.612CC", "1.000 Case Credits"), a figure with no unit, and the
# ISO 4217 currencies with three minor digits, where "9.440 TND" is nine dinars
# and 440 millimes. Separators are never stripped from the text; a grouped source
# figure is only offered as an occurrence of the same whole number.
_THREE_DECIMAL_CURRENCIES = frozenset({"bhd", "iqd", "jod", "kwd", "lyd", "omr", "tnd"})
_GROUPING_CURRENCY_WORD_RE = re.compile(r"\s{0,2}(?:francs?(?:\s+cfa)?|f\s?cfa|cfa|xof|xaf|kr)(?![^\W\d_])")
_UNGROUPED_THOUSANDS_RE = re.compile(r"[1-9]\d{3,5}")


def _currency_groups_thousands(kind: str) -> bool:
    return kind.startswith("currency:") and kind.partition(":")[2] not in _THREE_DECIMAL_CURRENCIES


def _is_grouped_amount(source_text: str, start: int, end: int) -> bool:
    """Whether the source writes this "2.000"-shaped figure as money that cannot have three decimals."""
    kind = _measure(source_text, start, end)[0]
    if kind:
        return _currency_groups_thousands(kind)
    return bool(_GROUPING_CURRENCY_WORD_RE.match(source_text, end))


def _source_occurrences(
    source_text: str, number: str, radius: int = 260, grouped_amounts: bool = True
) -> list[tuple[str, int, int]]:
    """Return each matching clause window and the source occurrence position.

    ``grouped_amounts`` lets a whole number ("2000") also find the same figure
    grouped with a point or comma in the source ("2.000 francs CFA"), where
    _is_grouped_amount settles that the separator is a thousands group.
    """
    windows: list[tuple[str, int, int]] = []
    # "0,200CC" is a decimal and does not contain the figure 200. Only a leading
    # zero settles that: "3,000.00" is still reached through its "000.00" tail.
    pattern = re.compile(rf"(?<![\d.])(?<!\b0,){re.escape(number)}(?!\d|\.\d)")
    # A range is a pair of figures, and the source rarely writes it the way an
    # answer does. Algeria's record says "between 48h to 96h"; the model wrote
    # "48-96", the literal string was absent, and repair deleted a correctly
    # stated delivery time. The endpoints and their order are what matter, not
    # the unit letters or the joining word between them.
    range_parts = re.fullmatch(r"(?P<low>\d[\d.,]*)-(?P<high>\d[\d.,]*)", number)
    if range_parts:
        low, high = range_parts.group("low", "high")
        pattern = re.compile(
            rf"(?<![\d.]){re.escape(low)}\s*[^\d\s]{{0,4}}\s*(?:-|to|through|until)\s*"
            rf"{re.escape(high)}(?!\d|\.\d)"
        )
    matches = list(pattern.finditer(source_text))
    if grouped_amounts and not range_parts and _UNGROUPED_THOUSANDS_RE.fullmatch(number):
        grouped = re.compile(rf"(?<![\d.,]){number[:-3]}[.,]{number[-3:]}(?![.,]?\d)")
        matches += [
            match for match in grouped.finditer(source_text)
            if _is_grouped_amount(source_text, match.start(), match.end())
        ]
        matches.sort(key=lambda match: match.start())
    for match in matches:
        index = match.start()
        # PDF extraction inserts line breaks for visual wrapping and numbered
        # lists. Keep those lines attached to the heading that names the rule.
        # A decimal point is not a clause boundary. Treating it as one truncates
        # the window at the previous figure, and the subject that qualifies this
        # one is usually in front of it: in "The GO2FBO pack costs 352.38EUR and
        # it represents 1.612CC", the window for 1.612 began after "352." and no
        # longer contained "GO2FBO", so a correctly stated figure was reported
        # ungrounded. Found by generated notation coverage over real records.
        left_boundary = -1
        for delimiter in _CLAUSE_DELIMITER_RE.finditer(source_text, 0, index):
            left_boundary = delimiter.start()
        right_delimiter = _CLAUSE_DELIMITER_RE.search(source_text, match.end())
        right_boundary = right_delimiter.start() if right_delimiter else len(source_text)
        window_start = max(left_boundary + 1 if left_boundary != -1 else 0, index - radius)
        window_end = min(right_boundary, match.end() + radius)
        windows.append((source_text[window_start:window_end], match.start(), match.end()))
    return windows


def _source_windows(source_text: str, number: str, radius: int = 260) -> list[str]:
    """Return clause-bounded source windows around the same number."""
    return [window for window, _, _ in _source_occurrences(source_text, number, radius)]


def _claim_is_supported(
    claim: MeasurableClaim,
    source_text: str,
    document_markets: frozenset[str] = frozenset(),
    document_name_tokens: frozenset[str] | None = None,
) -> bool:
    """Return true only when the same number is linked to the same named topic.

    ``document_name_tokens`` is given by unsupported_numeric_claims, which holds
    the document and its title; both the validator's verdict and repair go
    through it. It also enables the inline-label reading, which needs the
    document's own vocabulary. Without it both stay off, so a caller holding only
    text (the structured-record rescue in NumericGroundingValidator.validate) is
    never more lenient than before.
    """
    vocabulary = (
        frozenset(_word_tokens(source_text) | _code_tokens(source_text))
        if document_name_tokens is not None else None
    )
    subject_token_sets, binding = _subject_token_sets(
        claim, document_markets, vocabulary, document_name_tokens or frozenset()
    )
    claim_kind, claim_period = _claim_measure(claim)
    claim_letter = _claim_glued_letter(claim)
    claim_reads_as_clock = _claim_reads_as_clock(claim)
    clock_spans = [(start, end) for start, end, keys in _time_occurrences(source_text) if keys]
    claim_at = claim.sentence.find(claim.text)
    claim_unit = _adjacent_unit(claim.sentence, claim_at, claim_at + len(claim.text)) if claim_at != -1 else ""
    claim_roles = _role_mentions(claim.sentence)
    claim_role = (
        min(claim_roles, key=lambda item: abs(item[0] - claim_at))[1]
        if claim_roles and claim_at != -1 else None
    )
    # A grouped source amount supports only a claim that could be the same money:
    # "2,000 CC" or "9,440 TND" in the answer never borrows "2.000 francs CFA".
    grouped_amounts = not claim_kind or _currency_groups_thousands(claim_kind)
    for number in _number_variants(claim.number):
        for window, occurrence_start, occurrence_end in _source_occurrences(
            source_text, number, grouped_amounts=grouped_amounts
        ):
            # The same figure measuring something else is not support. "36
            # viikkoon" (weeks) against "36 peräkkäiseen kalenterikuukauteen"
            # (months) was removed only by accident of a spurious subject, and
            # "25 Case Credits in any calendar week" against "... calendar Month"
            # was kept. Compared only when both sides write a unit or a period.
            source_kind, source_period = _measure(source_text, occurrence_start, occurrence_end)
            if not _measures_agree((claim_kind, claim_period), (source_kind, source_period)):
                continue
            if not _occurrence_can_support(
                source_text, occurrence_start, occurrence_end, claim_letter, claim_reads_as_clock, clock_spans
            ):
                continue
            source_role = _occurrence_role(source_text, occurrence_start, occurrence_end)
            # A source window can contain nearby rules for more than one role.
            # Reject a cross-role match only when the source explicitly labels
            # this particular amount ("FBO: €81").  Wider prose can truthfully
            # describe a shared first-order rule before or after naming a role.
            explicit_source_role = _explicit_role_label_before_amount(source_text, occurrence_start)
            # A heading such as "Minimum order size FBO:" is not this amount's label when
            # the clause after it gives the amount to another role.
            if explicit_source_role and explicit_source_role != source_role:
                explicit_source_role = None
            if claim_role and explicit_source_role and claim_role != explicit_source_role:
                continue
            window_tokens = _with_role_equivalents(
                _word_tokens(window),
                source_role,
                claim_unit,
                _adjacent_unit(source_text, occurrence_start, occurrence_end),
            )
            subject_window_tokens = _with_unit_equivalents(window_tokens) | _code_tokens(window)
            subject_bound = any(
                _subject_matches_window(subject_tokens, subject_window_tokens)
                for subject_tokens in subject_token_sets
            )
            if subject_token_sets and not subject_bound:
                continue
            if binding == "body":
                if _shares_rule_words(claim.sentence, _rule_segment(source_text, occurrence_start, occurrence_end)):
                    return True
                continue
            if subject_bound and binding != "context":
                return True

            # Some scripts do not capitalize names. In that case, retain a modest
            # lexical check instead of inventing a locale-specific entity grammar.
            context_overlap = _word_tokens(claim.context) & window_tokens
            if len(context_overlap) >= 2:
                return True
    return False


# Shortest national subscriber number in the markets this corpus covers is
# seven digits, so a shorter run cannot be a contact number and must be matched
# in context rather than as a digit substring.
_CONTACT_DIGIT_MINIMUM = 7


def _structured_record_number_is_supported(claim: MeasurableClaim, source_text: str) -> bool:
    """Allow structured-record numbers despite harmless display formatting changes.

    A directory record is a list of field values rather than prose, so the
    subject-aware matching used for policy text cannot work here: the subject of
    "Minimum Order 0,200CC" is a column heading, not a phrase in a sentence.
    This path therefore accepts a number that appears in the record at all --
    which is why it is reached only for office and staff records, and only after
    the stricter check has already declined.

    The one thing it will not accept is a short figure that appears solely
    inside a contact number. A record holding "+213 21 50 60 70" contains the
    digits of an invented "50 Case Credits" twice over, in the raw text and
    again once separators are stripped, and grounding it there would deliver a
    fabricated threshold with a citation attached.
    """
    contact_spans = [(match.start(), match.end()) for match in _phone_matches(source_text)]
    for number in _number_variants(claim.number):
        claim_digits = "".join(character for character in number if character.isdigit())
        is_contact_length = len(claim_digits) >= _CONTACT_DIGIT_MINIMUM
        pattern = re.compile(rf"(?<![\d.]){re.escape(number)}(?!\d|\.\d)")
        for match in pattern.finditer(source_text):
            inside_contact = any(
                start <= match.start() and match.end() <= end for start, end in contact_spans
            )
            # A full-length number found inside a contact run IS that contact.
            if inside_contact and not is_contact_length:
                continue
            return True

        # Office directories often store a phone number as one digit string while
        # an answer formats it with spaces, parentheses, or a country-code prefix.
        # Compare digits only in this structured-record path; policy rules retain
        # the stricter subject-aware matching above. Only contact-length runs
        # qualify: stripping every separator makes a short figure groundable by
        # coincidence against any long number in the record.
        if not is_contact_length:
            continue
        source_digits = "".join(character for character in source_text if character.isdigit())
        if claim_digits in source_digits:
            return True
    return False


def _phone_matches(text: str) -> list[re.Match[str]]:
    vanity = re.compile(r"(?<!\w)(?:\d{1,4}[- ]\s*){2,3}[a-z]{3,10}\s*\(\d{3,6}\)", re.I)
    vanity_matches = list(vanity.finditer(text))
    return [match for match in [*vanity_matches, *PHONE_RE.finditer(text)]
            if 7 <= sum(char.isdigit() for char in match.group()) <= 15
            and not any(other.start() <= match.start() and match.end() <= other.end()
                        for other in vanity_matches if other is not match)]


def _extract_claims(answer: str) -> list[MeasurableClaim]:
    """Extract numeric claims from an answer without assuming unit vocabulary."""
    claims: list[MeasurableClaim] = []
    phones = _phone_matches(answer)
    numbers = [match for match in NUMERIC_CLAIM_PATTERN.finditer(answer)
               if not any(phone.start() <= match.start() and match.end() <= phone.end() for phone in phones)]
    for match in sorted([*phones, *numbers], key=lambda item: item.start()):
        if _is_structural_reference(answer, match.start(), match.end()):
            continue
        claim = MeasurableClaim(
            text=match.group(0),
            number=match.group(0),
            start=match.start(),
            end=match.end(),
            sentence=_sentence_for_claim(answer, match.start(), match.end()),
            context=_context_for_claim(answer, match.start(), match.end()),
            prefix=answer[max(0, match.start() - 220):match.start()],
        )
        claims.append(claim)
    return claims


def _is_structural_reference(answer: str, start: int, end: int) -> bool:
    """Ignore presentation numbers that are not measurable factual claims."""
    before = answer[start - 1 : start] if start else ""
    after = answer[end : end + 1]
    if before in {"[", "("} and after in {"]", ")"}:
        return True

    line_start = answer.rfind("\n", 0, start) + 1
    line_prefix = answer[line_start:start]
    if not line_prefix.strip():
        # "3)" and "3:" were recognised; "3." - the markdown ordered list
        # marker - was not, so an answer laying its steps out as a numbered
        # list had those numbers treated as measurable claims. Observed in the
        # Belgium sponsoring answer on 2026-09-08: repair removed 3, 4, 5 and 6
        # from a delivered answer, taking the sentences with them.
        if after in {")", ":"}:
            return True
        if after == "." and answer[end + 1 : end + 2] in {" ", "", "\n"}:
            return True
    return False


def _grounded_phone_spans(answer: str, source_texts: list[str]) -> list[tuple[int, int]]:
    """Compare whole contact values, never digits concatenated across a document.

    A source contact label is required. Answer wording may be translated; numeric
    policy rules elsewhere still go through the existing subject-binding check.
    """
    label = re.compile(r"\b(?:telephone|phone|fax|call|customer care|toll.free)\b", re.I)

    def key(value: str) -> str:
        return re.sub(r"[\s()+.-]", "", value).casefold()

    approved = {
        key(match.group())
        for source in source_texts
        for match in _phone_matches(source)
        if label.search(source[max(0, match.start() - 65):match.start()])
    }
    return [(match.start(), match.end()) for match in _phone_matches(answer) if key(match.group()) in approved]


# A clock time, written with either separator: 09:00, 09.00, 9:00.
#
# The trailing guard rejects a further digit ("1:234") and a further
# separator-plus-digit ("09.00.30", hours.minutes.seconds), but must allow a
# sentence period: "The office opens at 09:00." is the ordinary case, and
# excluding it made this pattern match nothing at all.
#
# A decimal such as "1.50" also matches this shape. That is harmless here: the
# only effect of matching is to spare a figure from deletion when a source
# states the same figure, which is exactly what should happen anyway.
_TIME_RE = re.compile(r"(?<![\d:.])(\d{1,2})[:.](\d{2})(?!\d)(?![:.]\d)")
# "5:00 pm" following the time, allowing "p.m." and a non-breaking space.
_MERIDIEM_RE = re.compile(r"^[\s ]*([ap])\.?\s?m\.?\b", re.I)


# An hour with a meridiem and no minutes: "9am", "6 pm", "8 p.m.".
#
# Three of the 113 directory records that state office hours are written this
# way -- England, Ireland and Scotland, all as "Monday - 9am - 6pm" -- and the
# pattern above finds no time in them at all. Without this, a model writing
# 09:00-18:00 for those markets has nothing in the source to match against and
# loses the hours, which is the failure this whole check exists to prevent.
_HOUR_MERIDIEM_RE = re.compile(r"(?<![\d:.])(\d{1,2})\s?([ap])\.?\s?m\.?\b", re.I)


def _meridiem_hour_keys(match: re.Match[str]) -> set[str]:
    """Return the 24-hour form of an hour written without minutes."""
    hour = int(match.group(1))
    # A meridiem hour is 1-12. Anything else is not a clock reading.
    if not 1 <= hour <= 12:
        return set()
    if match.group(2).lower() == "p" and hour < 12:
        hour += 12
    elif match.group(2).lower() == "a" and hour == 12:
        hour = 0
    return {f"{hour:02d}00"}


def _time_occurrences(text: str) -> list[tuple[int, int, set[str]]]:
    """Every clock time in the text, in whichever notation it is written."""
    occurrences = [
        (match.start(), match.end(), _time_keys(text, match))
        for match in _TIME_RE.finditer(text)
    ]
    occurrences += [
        (match.start(), match.end(), _meridiem_hour_keys(match))
        for match in _HOUR_MERIDIEM_RE.finditer(text)
    ]
    return sorted(occurrences)


# A time on the other side of a range separator, in either direction. A dot
# value earns clock status from being part of a range even without a meridiem,
# which is how "09.00-17.00" is written.
_RANGE_AFTER_RE = re.compile(r"^\s*[-–—]\s*\d{1,2}[:.]\d{2}")
_RANGE_BEFORE_RE = re.compile(r"\d{1,2}[:.]\d{2}\s*[-–—]\s*$")


def _time_keys(text: str, match: re.Match[str]) -> set[str]:
    """Return the single 24-hour form this written time means, if it is one.

    Zero-padded so "9:00" and "09.00" compare equal, which is the point: the
    directory writes office hours as 09.00-17.00 and a model writes 09:00-17:00,
    so a literal comparison never matched and every component was reported
    ungrounded.

    Two corrections from an external review on 2026-09-08, both defects I
    introduced earlier the same day.

    A meridiem yields ONE value, not two. Keeping the bare hour alongside the
    24-hour form meant "5:00 pm" carried both 0500 and 1700, so a source
    reading "5:00 am" grounded it. A wrong time was exempted from deletion.

    A dot value is only a clock in a clock context. "9.00" in "the fee is 9.00
    dollars" matched the clock pattern and was exempted by an unrelated "09:00"
    elsewhere in the source, so an invented amount passed. I had called that
    harmless in a comment here; it is not. A dot now needs a meridiem or a range
    partner. A colon is unambiguous enough on its own.
    """
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return set()

    separator = text[match.start() + len(match.group(1))]
    meridiem = _MERIDIEM_RE.match(text[match.end():])
    if separator == "." and not meridiem:
        in_range = _RANGE_AFTER_RE.match(text[match.end():]) or _RANGE_BEFORE_RE.search(
            text[:match.start()]
        )
        if not in_range:
            return set()

    if meridiem:
        marker = meridiem.group(1).lower()
        if marker == "p" and hour < 12:
            hour += 12
        elif marker == "a" and hour == 12:
            hour = 0
        elif marker == "p" and hour > 12:
            # "17.00 pm" is how these records are written throughout - a
            # 24-hour value with a redundant meridiem. The hour already says
            # what is meant, so the marker is ignored rather than refused.
            pass
    return {f"{hour:02d}{minute:02d}"}


def _grounded_time_spans(answer: str, source_texts: list[str]) -> list[tuple[int, int]]:
    """Spans holding a clock time that a source states, in either notation.

    Office hours were being deleted from directory contact answers because of a
    notation mismatch alone. Observed live on 2026-09-08: 09.00-17.00 in the
    Belgium record, 09:00-17:00 in the answer, and the whole sentence removed.
    """
    approved: set[str] = set()
    for source in source_texts:
        for _, _, keys in _time_occurrences(source):
            approved |= keys

    spans = [(start, end) for start, end, keys in _time_occurrences(answer) if keys & approved]

    # Two grounded times joined into a range must become one span. The claim
    # extractor reads "09:00-17:00" greedily and produces "00-17", a claim that
    # begins inside the first time and ends inside the second, so it sits in
    # neither span on its own and would still be reported ungrounded.
    #
    # Times are merged only across a short gap containing no digits, which
    # covers "-", " to ", " bis ", " a " and the meridiem in "9:00 am to
    # 5:00 pm", without reaching across a sentence or joining a grounded time
    # to an invented one further along.
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged:
            gap = answer[merged[-1][1]:start]
            if len(gap) <= 8 and not any(character.isdigit() for character in gap):
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    return merged


def _document_markets(document: object) -> frozenset[str]:
    """The markets a retrieved document is about: named in its title, or its country.

    A directory title names the market ("Forever Luxemburg"); a policy title
    does not ("LU-FR-Benelux-Policy.pdf - Sec 7.03-c: ..."), and its market is
    the document's country. With the title alone, a French answer saying "Selon
    la politique de Forever Luxembourg, ... dans les 24 mois" had "Forever
    Luxembourg" required beside 24 in the policy text, and the deadline sentence
    was removed. A country that is not a market code never matches a mention.
    """
    markets = set(find_market_mentions(str(getattr(document, "title", "") or "")))
    country = str(getattr(document, "country", "") or "").strip().upper()
    if country:
        markets.add(country)
    return frozenset(markets)


def unsupported_numeric_claims(answer: str, source_documents: list[object]) -> list[MeasurableClaim]:
    """Return factual numeric claims that no retrieved source supports."""
    # The title travels with the content because it carries which market the
    # record is about, and a subject naming that market is established by the
    # document rather than by the sentence beside the number.
    sources = [
        (
            _normalize(str(getattr(document, "content", "") or "")),
            _document_markets(document),
            _document_name_tokens(document),
        )
        for document in source_documents
        if getattr(document, "content", "")
    ]
    if not sources:
        return []
    source_texts = [source_text for source_text, _, _ in sources]
    grounded_spans = _grounded_phone_spans(answer, source_texts) + _grounded_time_spans(answer, source_texts)
    return [
        claim
        for claim in _extract_claims(answer)
        if not any(start <= claim.start and claim.end <= end for start, end in grounded_spans)
        if not any(
            _claim_is_supported(claim, source_text, document_markets, name_tokens)
            for source_text, document_markets, name_tokens in sources
        )
    ]


def numbers_present_in_sources(numbers: list[str], source_documents: list[object]) -> dict[str, bool]:
    """Say, for each figure, whether any retrieved document contains it.

    Repair removing a figure means two opposite things, and the difference is
    the whole judgement: a number absent from the evidence was invented and its
    removal is the system working, while a number present in the evidence was
    real and something rejected it. Anything counting both as damage measures
    neither.
    """
    sources = [
        _normalize(str(getattr(document, "content", "") or ""))
        for document in source_documents
        if getattr(document, "content", "")
    ]
    return {
        str(number): any(
            _source_windows(source_text, variant)
            for source_text in sources
            for variant in _number_variants(str(number))
        )
        for number in numbers
    }


def removal_diagnostics(answer: str, source_documents: list[object]) -> list[dict[str, object]]:
    """Say, for each figure repair removed, whether the source contains it at all.

    Repair deleting a figure has two opposite meanings. If the number appears
    nowhere in the retrieved documents, the model invented it and the removal
    is the system working. If it does appear and was removed anyway, the number
    was real and subject matching rejected it - a correct answer quietly losing
    a fact the reader asked for.

    The log line cannot distinguish them, and guessing wrong leads to either
    loosening grounding until fabrications get through or hunting a matching
    bug that does not exist. This reports which one happened.
    """
    sources = [
        _normalize(str(getattr(document, "content", "") or ""))
        for document in source_documents
        if getattr(document, "content", "")
    ]
    diagnostics: list[dict[str, object]] = []
    for claim in unsupported_numeric_claims(answer, source_documents):
        present = any(
            _source_windows(source_text, number)
            for source_text in sources
            for number in _number_variants(claim.number)
        )
        diagnostics.append({"number": claim.number, "present_in_source": present})
    return diagnostics


def remove_unsupported_numeric_sentences(answer: str, source_documents: list[object]) -> tuple[str, list[str]]:
    """Remove only sentences containing unsupported numbers, preserving grounded text."""
    unsupported = unsupported_numeric_claims(answer, source_documents)
    if not unsupported:
        return answer, []

    spans: list[tuple[int, int]] = []
    # Decimal/time separators are not sentence endings. A bare period search
    # left fragments such as "00 pm" after deleting a sentence with 09.00-17.00.
    abbreviations = list(re.finditer(r"\b(?:[^\W\d_]\.){2,}", answer))
    boundaries = [match for match in re.finditer(r"[.!?](?=\s|$)|\n", answer)
                  if not any(abbreviation.start() <= match.start() < abbreviation.end()
                             for abbreviation in abbreviations)]
    for claim in unsupported:
        left = max((match.end() for match in boundaries if match.end() <= claim.start), default=0)
        right = next((match.end() for match in boundaries if match.start() >= claim.end), len(answer))
        spans.append((left, right))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    repaired = answer
    for start, end in reversed(merged):
        repaired = repaired[:start] + repaired[end:]
    repaired = _drop_orphaned_delimiters(repaired)
    repaired = re.sub(r"[ \t]+\n", "\n", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()
    repaired = _drop_orphaned_lead_ins(repaired)
    return repaired, [claim.text for claim in unsupported]


def _drop_orphaned_lead_ins(text: str) -> str:
    """Remove a line that introduces content this repair deleted.

    A colon is not a sentence boundary, so a lead-in survives while everything
    it promised is removed. Observed live on 2026-09-08 for "what is the
    delivery cost for sweden?", which was delivered as:

        For Sweden, the delivery costs are:

        The average lead time for orders to arrive in Sweden is 4-7 days.

    The costs were ungrounded and correctly removed; the promise of them was
    not, and the reader was left with a heading over nothing and an unrelated
    fact beneath it. That reads as a rendering fault and quietly loses the
    question that was asked.

    Only a lead-in whose own content is gone is dropped: one still followed by
    an indented or bulleted line is doing its job and is left alone. This is
    the same repair as _drop_orphaned_delimiters above, one level up - a
    fragment whose partner this function removed.
    """
    lines = text.split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        if line.rstrip().endswith(":"):
            following = next(
                (candidate for candidate in lines[index + 1:] if candidate.strip()),
                "",
            )
            # A list, an indented block, or a heading is what a lead-in
            # introduces. Ordinary prose beneath it is a new statement, not
            # the promised content.
            introduces_content = bool(
                re.match(r"\s*(?:[-*•]|\d+[.)]|[a-z][.)])\s", following)
                or (following[:1].isspace() if following else False)
                or re.match(r"\s*(?:#{1,6}\s|\*\*\S)", following)
            )
            if not introduces_content:
                continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _drop_orphaned_delimiters(text: str) -> str:
    """Remove brackets this repair orphaned, never a matched pair.

    Removing a sentence can cut one half of a parenthetical aside. Measured at
    1 in 10 on "How can i become a recognized manager?": the model wrote
    "(There is an exception: ... 999 Case Credits ...)", repair deleted the
    sentence holding the number, the stray ")" survived, and the integrity
    validator then read the unbalanced text as truncated and replaced the entire
    answer with "the approved policy documents do not contain enough
    information" - for a question the documents answer in full.

    Only delimiters with no partner are dropped, so text the repair did not
    touch is unchanged.
    """
    removable: set[int] = set()
    for opener, closer in (("(", ")"), ("[", "]")):
        open_positions: list[int] = []
        for index, character in enumerate(text):
            if character == opener:
                open_positions.append(index)
            elif character == closer:
                if open_positions:
                    open_positions.pop()
                else:
                    removable.add(index)
        removable.update(open_positions)
    if not removable:
        return text
    cleaned = "".join(char for index, char in enumerate(text) if index not in removable)
    return re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", cleaned))


class NumericGroundingValidator:
    """Block measurable claims that are absent from retrieved context."""

    name = "numeric_grounding"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return

        answer = context.chat_response.answer or ""
        source_documents = [
            (document, _normalize(document.content))
            for document in retrieval_result.documents
            if document.content
        ]
        if not source_documents:
            return

        # unsupported_numeric_claims already excludes source-grounded contact
        # values. The remaining check rescues numbers that appear only inside a
        # structured office/staff directory record rather than in running text.
        unsupported = [
            claim.text
            for claim in unsupported_numeric_claims(answer, retrieval_result.documents)
            if not any(
                _claim_is_supported(claim, source_text)
                or (
                    document.metadata.get("directory_section") in {"office", "staff"}
                    and _structured_record_number_is_supported(claim, source_text)
                )
                for document, source_text in source_documents
            )
        ]
        if not unsupported:
            return

        result.add_issue(
            ValidationIssue(
                code="NUMERIC_CLAIM_UNGROUNDED",
                message="One or more measurable claims in the answer were not found in the retrieved source text: "
                + "; ".join(unsupported),
                severity=ValidationSeverity.CRITICAL,
                field="answer",
            )
        )
