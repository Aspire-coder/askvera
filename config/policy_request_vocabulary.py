r"""Reviewed, per-locale vocabulary for recognising a company-policy request.

``app/evidence.py``'s cross-market refusal only fires when a message is
recognised as asking for a *company* policy (as opposed to, say, a shipping
policy, or a general question that happens to mention a country). For an
English session that recognition is the untouched legacy regex
(``_COMPANY_POLICY_REQUEST_RE`` in app/evidence.py,
``r"\b(?:company|local|national)\s+polic(?:y|ies)\b"``) - this module never
runs for an English session, and app/evidence.py's English code path is
byte-identical to main. This module supplies the SAME recognition, narrowly,
for the other 11 locales ``config/conversation_routes.json`` defines
controlled copy for.

## Design history: co-occurrence was rejected

An earlier version of this module recognised "a policy noun and a company
qualifier co-occurring anywhere in the message" per locale. An adversarial
review (Fable) rejected that version with two blocking findings:

- B1 (over-refusal): co-occurrence anywhere, plus "forever" and unanchored
  substrings like "national"/"local" as qualifiers, refused 31 of 42
  legitimate own-market questions - e.g. French "Quelle est la politique de
  retour de Forever si j'expedie un produit en Allemagne ?" (a RETURN
  policy question that merely mentions Germany as a shipping destination)
  was wrongly refused, because "politique" and "internationale" (which
  contains "national" as a substring) both appeared somewhere in the text.
- B4 (English regression): the English sponsoring pattern dropped a
  trailing ``\b`` and the ``international\s+sponsoring`` alternative
  relative to ``app.retrieval.providers.SPONSORING_QUESTION_RE``, and ran
  on English text at all, which main's app/evidence.py never did.

This rewrite fixes both by construction: NO code in this module ever runs
for an English session (app/evidence.py branches on language before calling
anything here), and every non-English pattern below is a tight, word-bounded
NOUN-PHRASE ADJACENCY pattern mirroring the shape of the English regex
itself ("(company|local|national) polic(y|ies)") - a policy noun directly
combined with a company/local/national qualifier, not "these two ideas
appear somewhere in the same message." "Forever"/"Forever Living" is never
used as a qualifier, anywhere.

## Sponsoring: no localized carve-out

main's English-only mixed-sponsoring carve-out
(``without_foreign_sponsoring_destinations`` / ``is_mixed_sponsoring_policy_request``
in app/evidence.py) is untouched and still English-only. For a non-English
session, this module instead answers a coarser question,
``contains_sponsoring_stem`` - if a sponsoring word is present anywhere,
app/evidence.py skips the company-policy gate entirely for that session
(the message is treated as not a company-policy request at all, so it is
never refused as cross-market). This under-refuses some sponsoring+policy
mixes in these locales the same way it always has, on main, before this
fix; over-refusal, not under-refusal, is what an adversarial review flagged
as the blocking defect (Fable B6), so the trade favours answering.

## Folding

``fold()`` NFD-decomposes (canonical decomposition only, never NFKD/
compatibility decomposition - see its docstring for why that distinction
matters), strips combining marks, and lower-cases (never ``str.casefold()``,
which expands "ß" to "ss" and so is NOT length-preserving). This keeps fold
a 1:1, position-preserving map for every character this module has been
tested against (plain accented Latin letters, "ß", precomposed ligatures
such as "ﬁ"/"ﬂ"/"Ĳ", and Cyrillic), which matters even though this module no
longer slices the original message by an offset found in folded text (that
positional use was removed along with the co-occurrence carve-out above) -
a future caller that does rely on stable offsets should not have to
rediscover this the hard way.
"""

from __future__ import annotations

import re
import unicodedata

# The 12 locales `config/conversation_routes.json` defines controlled copy
# for; "en" is deliberately absent from every dict below - the legacy
# English regex in app/evidence.py is the only English recognition, and it
# always applies (an English phrase counts as a company-policy request
# regardless of the session's own language, matching main's behaviour,
# which never looked at the session language for this check at all).
NON_ENGLISH_LOCALES: tuple[str, ...] = ("da", "de", "es", "fi", "fr", "it", "nl", "no", "ru", "sr", "sv")


def _unaccented(text: str) -> str:
    """Canonical (NFD) decomposition only - see module docstring.

    NFKD (compatibility decomposition) would also expand ligatures like
    "ﬁ" -> "f"+"i" and "Ĳ" -> "I"+"J", which changes the character count.
    Precomposed accented letters ("é", "ä", ...) DO have a canonical
    decomposition (base letter + combining mark), so NFD still lets us
    strip the mark and recover the plain base letter; "ß" and ligatures
    have no canonical decomposition at all and pass through unchanged.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def fold(text: str) -> str:
    """Fold text for locale-vocabulary matching: length-preserving, 1:1 with the input.

    NFD-decompose + strip combining marks + ``str.lower()`` (never
    ``casefold()``, which is not length-preserving - it expands "ß" to
    "ss"). Also normalises the Unicode right single quotation mark (U+2019)
    to a plain apostrophe, 1:1, so "l'entreprise" and "l'entreprise" (typed
    with a curly quote) compare equal.
    """
    unaccented = _unaccented(text or "")
    return unaccented.replace("’", "'").lower()


# ---------------------------------------------------------------------------
# 1. Flat fragment list moved out of chat_orchestrator.LOCALIZED_POLICY_PATTERN.
#    Unrelated to the company-policy gate below; kept here only because that
#    pattern's own fragment list must not drift from this module's docstring
#    promise. Untouched by the B1/B4 rewrite.
# ---------------------------------------------------------------------------
POLICY_NOUN_FRAGMENTS: tuple[str, ...] = (
    "policy", "beleid", "politique", "richtlinie", "politik", "política",
    "käytäntö", "politica", "retningslinj", "riktlinj", "политик",
)


def build_localized_policy_pattern(*, word_start: bool = True) -> re.Pattern[str]:
    """Rebuild the exact pattern ``LOCALIZED_POLICY_PATTERN`` used to build inline.

    Mirrors ``app/orchestrator/chat_orchestrator._follow_up_stem_pattern``
    (fold each fragment, join as an alternation, anchor at a word start
    unless ``word_start`` is False for compound matching) so moving the
    fragment list here changes nothing about what the pattern matches.
    """
    folded = (fold(fragment) for fragment in POLICY_NOUN_FRAGMENTS)
    return re.compile((r"(?<!\w)" if word_start else "") + "(?:" + "|".join(folded) + ")", re.UNICODE)


# ---------------------------------------------------------------------------
# 2. Non-English company-policy noun-phrase ADJACENCY patterns.
#
# Each pattern mirrors the shape of the English regex itself: a policy noun
# directly combined with a company/local/national qualifier - never "these
# two ideas somewhere in the same message." Sources are written with normal
# diacritics for readability and folded (see `fold`) before compiling, so
# an unaccented or differently-cased variant of the same phrase also
# matches. Every alternative is wrapped with word boundaries.
#
# LIST FOR NATIVE REVIEW - every pattern below, source form (pre-fold):
#   fr: politique (de l'|d'|de la |de )?(entreprise|soci[ée]t[ée])|politique (locale|nationale)
#   de: (unternehmens|firmen)richtlinien?|(unternehmens|firmen)politik|(lokale[nr]?|nationale[nr]?) (richtlinie|politik)
#   nl: bedrijfsbeleid|(lokaal|nationaal) beleid
#   fi: yrityks?en (käytän(tö|nö)|toimintaperiaat)\w*|yrityspolitiik\w*|yrityskäytän\w*
#   ru: политик\w* компании
#   sr: politik\w* (kompanije|firme)|политик\w* (компаније|фирме)
#   es: política de la empresa|política (local|nacional)
#   it: politica aziendale|politica dell'azienda|politica (locale|nazionale)
#   da: virksomhedens politik|firmaets politik
#   no: selskapets retningslinjer|selskapets policy|bedriftens retningslinjer
#   sv: företagets policy|bolagets policy|företagspolicy
# ---------------------------------------------------------------------------
_LOCALE_PATTERN_SOURCES: dict[str, str] = {
    "fr": r"politique (de l'|d'|de la |de )?(entreprise|soci[ée]t[ée])|politique (locale|nationale)",
    "de": r"(unternehmens|firmen)richtlinien?|(unternehmens|firmen)politik|(lokale[nr]?|nationale[nr]?) (richtlinie|politik)",
    "nl": r"bedrijfsbeleid|(lokaal|nationaal) beleid",
    "fi": r"yrityks?en (käytän(tö|nö)|toimintaperiaat)\w*|yrityspolitiik\w*|yrityskäytän\w*",
    "ru": r"политик\w* компании",
    "sr": r"politik\w* (kompanije|firme)|политик\w* (компаније|фирме)",
    "es": r"política de la empresa|política (local|nacional)",
    "it": r"politica aziendale|politica dell'azienda|politica (locale|nazionale)",
    "da": r"virksomhedens politik|firmaets politik",
    "no": r"selskapets retningslinjer|selskapets policy|bedriftens retningslinjer",
    "sv": r"företagets policy|bolagets policy|företagspolicy",
}


def _compile_locale_pattern(source: str) -> re.Pattern[str]:
    folded_source = fold(source)
    return re.compile(r"\b(?:" + folded_source + r")\b", re.UNICODE)


_LOCALE_PATTERNS: dict[str, re.Pattern[str]] = {
    locale: _compile_locale_pattern(source) for locale, source in _LOCALE_PATTERN_SOURCES.items()
}

# The legacy English phrase always applies, regardless of session language -
# matching main's app/evidence.py, which never looked at language for this
# check. Kept as a literal copy (not an import) so this module has no
# dependency on app.evidence, avoiding any import cycle; app/evidence.py's
# own copy is the one actually used for an English session (see its
# module-level `_COMPANY_POLICY_REQUEST_RE` and the language branch in
# `approve_evidence`) - this copy exists only so a non-English session's
# message that happens to contain the English phrase is still recognised,
# exactly as it already is on main.
_LEGACY_ENGLISH_COMPANY_POLICY_RE = re.compile(r"\b(?:company|local|national)\s+polic(?:y|ies)\b", re.IGNORECASE)


def is_company_policy_request(text: str, language: str = "en") -> bool:
    """True when ``text`` asks for a *company* policy.

    The legacy English phrase always applies (see module docstring). For a
    non-English ``language``, that locale's own adjacency pattern (only that
    locale's - never every locale's) is also checked, against folded text.
    """
    raw = text or ""
    if _LEGACY_ENGLISH_COMPANY_POLICY_RE.search(raw):
        return True
    locale = (language or "en").split("-", 1)[0].lower()
    pattern = _LOCALE_PATTERNS.get(locale)
    if pattern is None:
        return False
    return bool(pattern.search(fold(raw)))


# ---------------------------------------------------------------------------
# 3. Sponsoring stems: if present, app/evidence.py skips the company-policy
#    gate entirely for a non-English session (see module docstring - no
#    localized mixed-sponsoring carve-out). English sponsoring detection is
#    untouched: app.retrieval.providers.SPONSORING_QUESTION_RE, used only by
#    the (unmodified) English-only carve-out in app/evidence.py.
# ---------------------------------------------------------------------------
SPONSORING_STEMS: dict[str, tuple[str, ...]] = {
    "fr": ("parrain", "sponsoris"),
    "es": ("patrocin", "sponsor"),
    "de": ("sponsern", "spons"),
    "nl": ("spons",),
    "it": ("sponsor", "sponsorizz"),
    "da": ("spons",),
    "no": ("spons",),
    "fi": ("sponsoro",),
    "sv": ("sponsr", "spons"),
    "ru": ("спонсир", "спонсор"),
    "sr": ("sponzor", "спонзор"),
}

# The bare English/loanword stem "sponsor" applies to EVERY non-English
# locale, alongside each locale's own native stems above (Fable N1): a
# session typed in French, Finnish, Russian or Serbian can still use the
# English word "sponsor" or "sponsoring" ("le sponsoring en Allemagne",
# "sponsori on Saksa") - those locales had no stem that matched it at all
# (fr's "sponsoris" requires the "-is" suffix, fi's "sponsoro" requires
# "-oro", ru's "спонсор" is Cyrillic-only, sr's "sponzor" is spelled with a
# "z"), so a bare "sponsor" question skipped main's English carve-out
# entirely and was wrongly refused. This is deliberately just "sponsor",
# not the shorter "spons" - Fable also noted "spons" as a substring matches
# "respons..." ("responsible", "responsabilite", ...), which is
# under-refusal only (a real sponsoring question still recognised via the
# locale's own stems) and is left exactly as it was.
_COMMON_SPONSORING_STEM = "sponsor"


def contains_sponsoring_stem(text: str, language: str) -> bool:
    """True when ``text`` contains a sponsoring stem for ``language``.

    Only that locale's own stems are checked (never every locale's) - PLUS
    the shared bare "sponsor" stem, which every non-English locale accepts
    (see ``_COMMON_SPONSORING_STEM`` above).
    """
    locale = (language or "en").split("-", 1)[0].lower()
    if locale not in NON_ENGLISH_LOCALES:
        return False
    normalized = fold(text or "")
    if _COMMON_SPONSORING_STEM in normalized:
        return True
    stems = SPONSORING_STEMS.get(locale, ())
    return any(stem in normalized for stem in stems)
