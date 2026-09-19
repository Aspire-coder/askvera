"""Localized rendering for the CX conversation-experience layer (Lane 4).

Phase 3 (docs/conversation-quality/phase3/CX_DESIGN.md,
docs/conversation-quality/phase3/CX_LANES.md) fixes a small, shared table of
message keys that every other lane refers to by name and fills with
placeholder values -- they never inline an English sentence in code. This
module is the only place that turns ``(key, language, placeholders)`` into
user-visible text.

Rendering order, per the CX_LANES contract:

1. Resolve ``language`` to a locale with the existing normalizer
   (``app.evidence._locale_key``) -- the same primary-language-tag folding
   every other locale-aware code path already uses.
2. For the 12 reviewed route locales (``config/conversation_routes.json``'s
   ``locales`` keys), use the reviewed copy directly.
3. For any other configured language, translate the *English* template with
   ``services.controlled_copy.localize_reviewed_copy`` -- a constrained,
   temperature-0 Bedrock translation of reviewed copy that never invents
   facts. Placeholders are protected with opaque sentinel tokens first (see
   ``_protect_placeholders``) so the translation model has nothing shaped
   like a fill-in-the-blank to alter, then restored afterwards. If any
   sentinel was lost, duplicated, or altered, or the translation call itself
   failed, the English template is used instead -- this module never trusts
   an unverified translation.
4. Placeholders are substituted only after localization, so a placeholder
   value (an office phone number, a country name) is never sent through
   translation itself.
5. ``render`` never returns an empty string: the English template is the
   floor when nothing else is available.

Copy is data, not code: this module has no new sentences of its own, only
the plumbing that resolves and fills the keys Lane 4 writes into
``config/conversation_routes.json``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.evidence import _conversation_routes, _locale_key
from services.controlled_copy import localize_reviewed_copy

# Matches a named placeholder like "{topic}" or "{options}" -- the closed set
# the CX_LANES table documents ({topic} {country} {fields} {options}
# {contact}), but this pattern is deliberately generic so a new placeholder
# name never needs a matching code change here.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Opaque sentinel wrapper for a protected placeholder. Mathematical bracket
# characters (U+27E6/U+27E9) are not natural translation-prompt punctuation
# for any of the reviewed locales, and the wrapped name is always uppercase
# ASCII, so a faithful translation should carry the whole token through
# unchanged. The placeholder-integrity check below never trusts this by
# assumption, though -- it verifies the sentinel survived exactly once.
_SENTINEL_OPEN = "⟦"
_SENTINEL_CLOSE = "⟩"

# Locale list separator + final conjunction, as a small closed table for the
# 12 reviewed CX locales. Every other language falls back to English's
# ", "/" and ". Two items join as "a and b" (no leading comma); three or
# more as "a, b and c".
_LIST_SEPARATORS: dict[str, tuple[str, str]] = {
    "en": (", ", " and "),
    "fr": (", ", " et "),
    "es": (", ", " y "),
    "de": (", ", " und "),
    "nl": (", ", " en "),
    "it": (", ", " e "),
    "da": (", ", " og "),
    "fi": (", ", " ja "),
    "no": (", ", " og "),
    "sr": (", ", " i "),
    "sv": (", ", " och "),
    "ru": (", ", " и "),
}

# The same shape for a CHOICE between items ("a or b"), used by one-question
# clarifications ("Did you mean shipping cost or shopping cost?"). Finnish
# uses the interrogative "vai" because every clarification is a question.
_ALTERNATIVE_CONJUNCTIONS: dict[str, str] = {
    "en": " or ", "fr": " ou ", "es": " o ", "de": " oder ", "nl": " of ", "it": " o ",
    "da": " eller ", "fi": " vai ", "no": " eller ", "sr": " ili ", "sv": " eller ", "ru": " или ",
}

# Script-mismatch detection: a bounded, deterministic check, not a language
# identifier. It only recognizes Cyrillic vs. Latin, because that is the one
# script split among the 12 reviewed CX locales (ru is Cyrillic; the other
# 11 -- including sr, written in Latin script throughout this repository's
# conversation_routes.json -- are Latin). It is not a claim that any other
# script confusion is caught.
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_LATIN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏ]")
_CYRILLIC_LOCALES = frozenset({"ru"})


def render(key: str, language: str, **placeholders: Any) -> str:
    """Return localized, placeholder-filled copy for ``key``.

    Raises ``KeyError`` for a key that does not exist in the English route
    table at all -- an unknown key is a programming error in the caller, not
    a condition to render silently around.
    """
    locale = _locale_key(language)
    routes = _conversation_routes()
    english_responses = (routes.get("en", {}) or {}).get("responses", {}) or {}
    if key not in english_responses:
        raise KeyError(f"unknown conversation route key: {key!r}")
    english_template = str(english_responses[key]).strip()

    if locale in routes:
        locale_responses = (routes.get(locale, {}) or {}).get("responses", {}) or {}
        localized = locale_responses.get(key)
        template = str(localized).strip() if localized else ""
    else:
        template = _translate_template(english_template, locale, key)

    if not template:
        # Floor: reviewed English copy, never an empty string.
        template = english_template

    return _fill_placeholders(template, placeholders)


def _translate_template(english_template: str, locale: str, key: str) -> str:
    """Translate ``english_template`` for an unconfigured language.

    Placeholders are protected before the call and restored after; any
    translation that loses, duplicates, or alters a placeholder/sentinel --
    or that ``localize_reviewed_copy`` refused or failed to produce at all --
    falls back to the English template unchanged.
    """
    protected, sentinel_map = _protect_placeholders(english_template)
    candidate = localize_reviewed_copy(protected, locale, key)
    if not candidate:
        return english_template

    restored = candidate
    for sentinel, placeholder in sentinel_map.items():
        if restored.count(sentinel) != 1:
            return english_template
        restored = restored.replace(sentinel, placeholder)
    return restored


def _protect_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """Replace each ``{name}`` with an opaque sentinel; return the mapping back."""
    names = sorted(set(_PLACEHOLDER_RE.findall(text)))
    sentinel_map: dict[str, str] = {}
    protected = text
    for name in names:
        placeholder = "{" + name + "}"
        sentinel = f"{_SENTINEL_OPEN}{name.upper()}{_SENTINEL_CLOSE}"
        sentinel_map[sentinel] = placeholder
        protected = protected.replace(placeholder, sentinel)
    return protected, sentinel_map


def _fill_placeholders(template: str, placeholders: Mapping[str, Any]) -> str:
    result = template
    for name, value in placeholders.items():
        result = result.replace("{" + name + "}", str(value))
    return result


def join_list(items: Sequence[Any], language: str) -> str:
    """Join ``items`` with the locale's list separator and final conjunction.

    Two items join as "a and b" (no comma before the conjunction); three or
    more as "a, b and c". Falls back to the English separators for any
    language outside the 12-locale table.
    """
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    locale = _locale_key(language)
    separator, conjunction = _LIST_SEPARATORS.get(locale, _LIST_SEPARATORS["en"])
    return separator.join(values[:-1]) + conjunction + values[-1]


def join_alternatives(items: Sequence[Any], language: str) -> str:
    """Join ``items`` as a choice: "a or b", "a, b or c" (localized)."""
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    locale = _locale_key(language)
    separator = _LIST_SEPARATORS.get(locale, _LIST_SEPARATORS["en"])[0]
    conjunction = _ALTERNATIVE_CONJUNCTIONS.get(locale, _ALTERNATIVE_CONJUNCTIONS["en"])
    return separator.join(values[:-1]) + conjunction + values[-1]


def mixed_language_or_empty(text: str, language: str) -> bool:
    """Deterministically flag empty copy or an obvious script mismatch.

    True when ``text`` is empty/whitespace-only, or when its script clearly
    does not match ``language`` -- e.g. purely Latin text rendered for "ru",
    or purely Cyrillic text rendered for any other configured locale (English
    included). This is a bounded, documented check, not a language
    identifier: text with no alphabetic characters at all (e.g. only digits
    or punctuation) is never flagged on script grounds, and a genuinely mixed
    string that contains *some* of the expected script alongside the other
    is not flagged either -- only the unambiguous "wrong script entirely"
    case is caught.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True
    locale = _locale_key(language)
    has_cyrillic = bool(_CYRILLIC_RE.search(stripped))
    has_latin = bool(_LATIN_RE.search(stripped))
    if not has_cyrillic and not has_latin:
        return False
    if locale in _CYRILLIC_LOCALES:
        return has_latin and not has_cyrillic
    return has_cyrillic and not has_latin
