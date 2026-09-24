"""Build a native-speaker review pack for AskVera's localized CX copy.

AskVera's fallback, clarification and CX (conversation-experience) copy is
translated into 12 route languages but has never been checked by a native
speaker of each language. This script builds a per-language review pack: one
CSV a reviewer can work through in about an hour, plus a README explaining
how to fill it in.

SOURCES (read-only -- this script never writes to any of them):

* ``config/conversation_routes.json`` -- ``locales.<lang>.responses`` is the
  table of customer-facing message keys and their localized text. This is
  the copy table that ``app/response/cx_render.py::render()`` reads at
  runtime (see that module's docstring for the full rendering contract).
  Only the ``responses`` block is customer-facing copy; ``patterns`` and
  ``scope_terms`` are inbound-message matching phrases, not rendered text,
  so they are out of scope for this review pack.
* ``config/claim_safety.json`` -- ``responses`` is a second, flat
  locale -> string table (no nested key), read by
  ``services/claim_safety.py::localized_claim_response()`` for the
  regulated "a Forever Living product treats/cures a disease" refusal. It is
  folded into the pack as a single extra key so every piece of rendered CX
  copy is covered in one place.
* ``config/public_contacts.json`` is contact data (phone numbers, addresses,
  office hours per country), not language copy. It is not part of the
  review pack; ``app/response/cx_render.py`` and
  ``app/orchestrator/conversation_repair.py`` / ``answer_language.py`` were
  checked and hold no additional hardcoded locale-keyed copy of their own --
  everything they render is pulled from the two files above.

The 12 route languages are English (the source) plus fr, es, de, nl, it, da,
fi, no, sr, sv, ru -- the same set ``config/conversation_routes.json``'s
``locales`` keys and ``app/orchestrator/answer_language.py``'s
``ROUTE_COPY_LANGUAGES`` both enumerate.

OUTPUT (under docs/conversation-quality/phase3/copy_review/):

* ``<lang>.csv`` for each of the 11 non-English languages, UTF-8 with a BOM
  (``utf-8-sig``) so Excel opens accented characters correctly without a
  manual import step.
* ``README.md`` describing the pack, how to fill in a row, how to
  regenerate it, a string-count table, and the mechanical findings below.

This script makes no judgement about translation quality -- that is the
reviewer's job. It only flags things that are checkable without knowing the
language:

* a key present in English but missing (absent or empty) in a language;
* a placeholder set, e.g. ``{topic}``/``{country}``, that differs between
  the English text and the translation;
* a translation identical to the English source (likely never translated);
* an empty translation string;
* a translation whose length, relative to English, falls outside 0.5x-2.0x
  (a rough proxy for truncation or run-on machine-translation artifacts --
  not a judgement of quality by itself).

RUNTIME BEHAVIOUR WHEN A KEY IS MISSING

A missing key is not just a review gap -- two different runtime code paths
handle a missing locale entry differently, and it matters to a reviewer
which one a given key uses. This was traced by reading every caller of
``app/response/cx_render.py::render()`` and
``app/evidence.py::localized_conversation_response()`` (plus, since the
trace surfaced it, ``app/evidence.py::assistant_meta_response()``, a third
function with its own missing-key behaviour -- see ``KEY_RUNTIME_PATHS``
below for the full per-key result):

* ``app/response/cx_render.py::render()`` -- used by
  ``app/response/cx_compose.py``, ``app/response/contact_completion.py`` and
  ``app/response/partial_answer.py``. Its docstring calls this "Floor:
  reviewed English copy": when the locale has no entry for the key, the
  REVIEWED ENGLISH template is shown to the customer, verbatim. No
  translation call is made.
* ``app/evidence.py::localized_conversation_response()`` -- used directly by
  ``app/orchestrator/chat_orchestrator.py`` for most fallback/refusal
  copy. When the locale has no entry for the key, it calls
  ``services/controlled_copy.py::localize_reviewed_copy()``, which makes an
  UNREVIEWED Bedrock translation call of the English text, at request time,
  once per turn -- this is real, production, per-request behaviour, not a
  build-time step.
* ``app/evidence.py::assistant_meta_response()`` -- a third function, also
  in ``app/evidence.py``, called from
  ``chat_orchestrator.py::_static_assistant_response()`` for the exact-phrase
  "hi"/"thanks"/"bye"-style short-circuit that runs before retrieval. Its
  missing-key behaviour matches ``render()``'s: it falls straight back to
  the reviewed English text, with no translation call. It renders
  ``greeting``, ``thanks``, ``wellbeing``, ``casual``, ``capability`` and
  ``farewell`` -- of these, ``farewell`` is reachable ONLY through this
  function (the later, planner-driven ``localized_conversation_response``
  branch in ``chat_orchestrator.py`` never includes "farewell" in its
  response-key set), while the other five are also independently reachable
  through ``localized_conversation_response()`` from a second call site
  (``chat_orchestrator.py::_conversation_route_response()``, reached after
  retrieval when the early exact-phrase short-circuit did not match) -- so
  which behaviour a customer actually gets for those five keys depends on
  which of the two call sites handles that particular turn.

Every key's classification is one of:

* ``"cx_render"`` -- only reachable through an English-floor function
  (``render()`` or ``assistant_meta_response()``). Missing-key value:
  ``english_shown``.
* ``"conversation_route"`` -- only reachable through
  ``localized_conversation_response()``. Missing-key value:
  ``machine_translated_at_request_time``.
* ``"both"`` -- reachable through both an English-floor function AND
  ``localized_conversation_response()``, from two different call sites, so
  which behaviour applies depends on which code path handles the turn.
  Missing-key value: ``both_paths_differ``.
* ``"unreferenced"`` -- present in ``config/conversation_routes.json`` but,
  as far as this trace found, never passed as the ``key`` argument to any of
  the three functions above by any production code path (``dependency_unavailable``,
  ``clarify_country``, ``clarify_role``, ``repair_ack``, ``suggest_intro`` --
  the ``CX_LANES.md`` design doc documents some of these as intended keys,
  but no caller constructs them today; ``dependency_unavailable`` failures
  are rendered with the ``bedrock_error`` copy instead). Missing-key value:
  ``not_rendered_in_production_today``.

``product_disease_claim_refusal`` (the claim_safety.json key) is a special
case: it is rendered by neither ``render()`` nor
``localized_conversation_response()`` but by its own function,
``services/claim_safety.py::localized_claim_response()``, whose missing-key
behaviour is the same English-floor shape as ``render()`` (falls back to
``responses.get("en")``, never translates) -- so it is classified
``"cx_render"`` here for consistency, though today every one of the 12
locales has an entry, so this key currently has no missing-key rows in any
CSV.

USAGE

    py -3 scripts/build_copy_review_pack.py

Regenerate any time the underlying copy in ``config/conversation_routes.json``
or ``config/claim_safety.json`` changes -- the script is deterministic (the
same inputs always produce byte-identical output) and always overwrites the
whole ``copy_review`` directory, so stale rows never linger after a key is
renamed or removed.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CONVERSATION_ROUTES_PATH = PROJECT_ROOT / "config" / "conversation_routes.json"
CLAIM_SAFETY_PATH = PROJECT_ROOT / "config" / "claim_safety.json"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "conversation-quality" / "phase3" / "copy_review"

# The synthetic key used for claim_safety.json's single flat response, which
# has no key of its own in that file (it is just {locale: string}).
CLAIM_SAFETY_KEY = "product_disease_claim_refusal"
CLAIM_SAFETY_SOURCE_LABEL = "config/claim_safety.json"
CONVERSATION_ROUTES_SOURCE_LABEL = "config/conversation_routes.json"

# The 11 non-English route languages reviewed by this pack, in the same
# order config/conversation_routes.json's locales table lists them.
NON_ENGLISH_LANGUAGES: tuple[str, ...] = (
    "fr", "es", "de", "nl", "it", "da", "fi", "no", "sr", "sv", "ru",
)

CSV_FIELDNAMES = [
    "key",
    "source_file",
    "english",
    "translation",
    "placeholders_english",
    "placeholders_translation",
    "placeholder_mismatch",
    "length_ratio",
    "runtime_when_missing",
    "reviewer_verdict",
    "reviewer_suggested_text",
    "reviewer_comment",
]

# Per-key classification of which runtime path(s) render it, traced by
# reading every caller of app/response/cx_render.py::render(),
# app/evidence.py::localized_conversation_response() and (since the trace
# surfaced it as a third function with the same "English floor" shape as
# render()) app/evidence.py::assistant_meta_response(). See this script's
# module docstring, "RUNTIME BEHAVIOUR WHEN A KEY IS MISSING", for the full
# reasoning and the call sites behind each entry.
#
# Values: "cx_render" (English-floor only), "conversation_route"
# (machine-translated-at-request-time only), "both" (reachable through an
# English-floor function AND localized_conversation_response(), from two
# different call sites), or "unreferenced" (present in
# conversation_routes.json but not passed as a key to any of the three
# functions by any production code path found).
KEY_RUNTIME_PATHS: dict[str, str] = {
    "catalogue_scope": "conversation_route",
    "wellbeing": "both",
    "greeting": "both",
    "thanks": "both",
    "farewell": "cx_render",
    "capability": "both",
    "casual": "both",
    "period_not_covered": "conversation_route",
    "country_typo_confirmation": "conversation_route",
    "insufficient_evidence": "both",
    "office_contact_lead_in": "conversation_route",
    "off_topic": "conversation_route",
    "medical_claim": "conversation_route",
    "income_claim": "conversation_route",
    "bedrock_error": "conversation_route",
    "sensitive_pii": "conversation_route",
    "guardrail_blocked": "conversation_route",
    "reference_clarification": "conversation_route",
    "dependency_unavailable": "unreferenced",
    "evidence_missing_detail": "cx_render",
    "cross_market_policy_scope": "cx_render",
    "international_directory_note": "cx_render",
    "personal_account_limit": "cx_render",
    "partial_answer_gap": "cx_render",
    "clarify_field": "cx_render",
    "clarify_country": "unreferenced",
    "clarify_role": "unreferenced",
    "repair_ack": "unreferenced",
    "contact_offer": "cx_render",
    "suggest_intro": "unreferenced",
    "suggest_topic_delivery_cost": "cx_render",
    "suggest_topic_payment_methods": "cx_render",
    "suggest_topic_contact": "cx_render",
    "suggest_topic_returns": "cx_render",
    "field_label_phone": "cx_render",
    "field_label_order_phone": "cx_render",
    "field_label_email": "cx_render",
    "field_label_website": "cx_render",
    "field_label_address": "cx_render",
    "field_label_business_hours": "cx_render",
    "field_label_payment_methods": "cx_render",
    "field_label_delivery_cost": "cx_render",
    "field_label_delivery_time": "cx_render",
    "field_label_fax": "cx_render",
    CLAIM_SAFETY_KEY: "cx_render",
}

# One-line note on the *code site* behind a classification, shown in the
# README per-key path table -- only filled in where the classification alone
# would be misleading about which module/function actually does the work.
KEY_RUNTIME_NOTES: dict[str, str] = {
    "farewell": "app/evidence.py::assistant_meta_response() only -- never reachable via localized_conversation_response().",
    "greeting": "assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites.",
    "thanks": "assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites.",
    "wellbeing": "assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites.",
    "casual": "assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites.",
    "capability": "assistant_meta_response() (early exact-phrase route) and localized_conversation_response() (later planner-routed route) are both real call sites.",
    "insufficient_evidence": "cx_compose.py's render(\"insufficient_evidence\", ...) and chat_orchestrator.py's localized_conversation_response(\"insufficient_evidence\", ...) are both real call sites.",
    "dependency_unavailable": "Never passed as a key anywhere; a dependency_unavailable failure is actually rendered with the bedrock_error copy instead.",
    "clarify_country": "conversation_repair.py documents this key but never constructs a Clarification with it.",
    "clarify_role": "conversation_repair.py documents this key but never constructs a Clarification with it.",
    "repair_ack": "conversation_repair.py documents this key but never constructs a Clarification with it.",
    "suggest_intro": "Present in conversation_routes.json but never passed to render() -- suggestions are delivered as structured items, not this intro sentence.",
    "product_disease_claim_refusal": "services/claim_safety.py::localized_claim_response(), not render() or localized_conversation_response() -- same English-floor shape as render(), and all 12 locales are populated today so this key has no missing-key rows.",
}

_RUNTIME_WHEN_MISSING_BY_PATH: dict[str, str] = {
    "cx_render": "english_shown",
    "conversation_route": "machine_translated_at_request_time",
    "both": "both_paths_differ",
    "unreferenced": "not_rendered_in_production_today",
}


def runtime_when_missing(key: str) -> str:
    """Return this key's documented behaviour when a language lacks it."""
    path = KEY_RUNTIME_PATHS.get(key)
    if path is None:
        raise KeyError(f"no runtime-path classification recorded for key: {key!r}")
    return _RUNTIME_WHEN_MISSING_BY_PATH[path]


_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")

LENGTH_RATIO_LOW = 0.5
LENGTH_RATIO_HIGH = 2.0


class SourceString(NamedTuple):
    key: str
    source_file: str
    english: str


def extract_placeholders(text: str) -> list[str]:
    """Return the sorted, de-duplicated ``{placeholder}`` tokens in ``text``."""
    return sorted(set(_PLACEHOLDER_RE.findall(text or "")))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_english_strings() -> list[SourceString]:
    """Return every customer-facing English string, in a stable, documented order.

    Order: conversation_routes.json's ``responses`` keys in file order, then
    the single claim_safety.json response. This fixed order is what makes
    regeneration deterministic and each CSV's row order predictable for a
    reviewer working through it top to bottom.
    """
    routes = _load_json(CONVERSATION_ROUTES_PATH)
    en_responses = ((routes.get("locales", {}) or {}).get("en", {}) or {}).get("responses", {}) or {}
    strings = [
        SourceString(key=key, source_file=CONVERSATION_ROUTES_SOURCE_LABEL, english=str(value))
        for key, value in en_responses.items()
    ]

    claim_safety = _load_json(CLAIM_SAFETY_PATH)
    claim_responses = claim_safety.get("responses", {}) or {}
    if "en" in claim_responses:
        strings.append(
            SourceString(
                key=CLAIM_SAFETY_KEY,
                source_file=CLAIM_SAFETY_SOURCE_LABEL,
                english=str(claim_responses["en"]),
            )
        )
    return strings


def load_language_translations(language: str) -> dict[str, str]:
    """Return ``{key: text}`` for every key this pack tracks, for one language.

    A key with no entry at all for ``language`` (a missing locale block, or
    the key absent within it) is simply left out of the returned mapping --
    callers treat "absent from this dict" as the "missing" finding.
    """
    translations: dict[str, str] = {}

    routes = _load_json(CONVERSATION_ROUTES_PATH)
    lang_responses = ((routes.get("locales", {}) or {}).get(language, {}) or {}).get("responses", {}) or {}
    for key, value in lang_responses.items():
        translations[key] = str(value)

    claim_safety = _load_json(CLAIM_SAFETY_PATH)
    claim_responses = claim_safety.get("responses", {}) or {}
    if language in claim_responses:
        translations[CLAIM_SAFETY_KEY] = str(claim_responses[language])

    return translations


def build_row(source: SourceString, translation: str | None) -> dict[str, str]:
    """Build one CSV row (all values as strings) for ``source`` in one language."""
    english = source.english
    has_translation = translation is not None
    translation_text = translation if has_translation else ""

    english_placeholders = extract_placeholders(english)
    translation_placeholders = extract_placeholders(translation_text) if has_translation else []

    if not has_translation:
        placeholder_mismatch = "yes" if english_placeholders else "no"
    else:
        placeholder_mismatch = "yes" if set(english_placeholders) != set(translation_placeholders) else "no"

    if has_translation and translation_text.strip() and english.strip():
        length_ratio = f"{len(translation_text) / len(english):.2f}"
    else:
        length_ratio = ""

    return {
        "key": source.key,
        "source_file": source.source_file,
        "english": english,
        "translation": translation_text,
        "placeholders_english": " ".join(english_placeholders),
        "placeholders_translation": " ".join(translation_placeholders),
        "placeholder_mismatch": placeholder_mismatch,
        "length_ratio": length_ratio,
        # Present key: left blank (nothing runs at request time -- the
        # reviewed translation is just used). Missing key: what the customer
        # gets today, per KEY_RUNTIME_PATHS -- see runtime_when_missing().
        "runtime_when_missing": "" if has_translation else runtime_when_missing(source.key),
        "reviewer_verdict": "",
        "reviewer_suggested_text": "",
        "reviewer_comment": "",
    }


class LanguageFindings(NamedTuple):
    language: str
    missing_keys: list[str]
    placeholder_mismatch_keys: list[str]
    identical_to_english_keys: list[str]
    empty_string_keys: list[str]
    length_ratio_outlier_keys: list[str]
    string_count: int


def build_language_pack(
    sources: list[SourceString], language: str
) -> tuple[list[dict[str, str]], LanguageFindings]:
    translations = load_language_translations(language)
    rows: list[dict[str, str]] = []
    missing_keys: list[str] = []
    placeholder_mismatch_keys: list[str] = []
    identical_to_english_keys: list[str] = []
    empty_string_keys: list[str] = []
    length_ratio_outlier_keys: list[str] = []

    for source in sources:
        translation = translations.get(source.key)
        row = build_row(source, translation)
        rows.append(row)

        if translation is None:
            missing_keys.append(source.key)
            continue
        if not translation.strip():
            empty_string_keys.append(source.key)
        if row["placeholder_mismatch"] == "yes":
            placeholder_mismatch_keys.append(source.key)
        if translation.strip() and translation == source.english:
            identical_to_english_keys.append(source.key)
        if row["length_ratio"]:
            ratio = float(row["length_ratio"])
            if ratio < LENGTH_RATIO_LOW or ratio > LENGTH_RATIO_HIGH:
                length_ratio_outlier_keys.append(source.key)

    findings = LanguageFindings(
        language=language,
        missing_keys=missing_keys,
        placeholder_mismatch_keys=placeholder_mismatch_keys,
        identical_to_english_keys=identical_to_english_keys,
        empty_string_keys=empty_string_keys,
        length_ratio_outlier_keys=length_ratio_outlier_keys,
        string_count=len(rows) - len(missing_keys),
    )
    return rows, findings


def write_csv(language: str, rows: list[dict[str, str]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{language}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return csv_path


LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "nl": "Dutch",
    "it": "Italian",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "sr": "Serbian",
    "sv": "Swedish",
    "ru": "Russian",
}


def _findings_lines(findings: LanguageFindings) -> list[str]:
    lang_name = LANGUAGE_NAMES.get(findings.language, findings.language)
    lines = [f"### {lang_name} (`{findings.language}`)", ""]

    def bullet(label: str, keys: list[str]) -> str:
        if not keys:
            return f"- {label}: none"
        return f"- {label} ({len(keys)}): " + ", ".join(f"`{k}`" for k in keys)

    lines.append(bullet("Missing keys (present in English, absent here)", findings.missing_keys))
    lines.append(bullet("Placeholder mismatches", findings.placeholder_mismatch_keys))
    lines.append(bullet("Identical to English (possibly untranslated)", findings.identical_to_english_keys))
    lines.append(bullet("Empty strings", findings.empty_string_keys))
    lines.append(
        bullet(
            f"Length ratio outside {LENGTH_RATIO_LOW}-{LENGTH_RATIO_HIGH}x",
            findings.length_ratio_outlier_keys,
        )
    )
    lines.append("")
    return lines


_PATH_CUSTOMER_DESCRIPTION: dict[str, str] = {
    "cx_render": (
        "The reviewed ENGLISH template is shown as-is (no translation call). "
        "`app/response/cx_render.py::render()` (or, for `farewell` and "
        "`product_disease_claim_refusal`, an equivalent English-floor "
        "function -- see this script's module docstring)."
    ),
    "conversation_route": (
        "An UNREVIEWED machine translation of the English text is generated "
        "by a live Bedrock call at request time, once per turn, and shown "
        "immediately -- no human ever reviews it. "
        "`app/evidence.py::localized_conversation_response()` -> "
        "`services/controlled_copy.py::localize_reviewed_copy()`."
    ),
    "both": (
        "Depends which code path handles the turn: the reviewed ENGLISH "
        "template (`assistant_meta_response()`, the early exact-phrase "
        "route) on some turns, or an UNREVIEWED machine translation "
        "generated at request time (`localized_conversation_response()`, "
        "the later planner-routed route) on others."
    ),
    "unreferenced": (
        "Nothing -- this key is not rendered by any production code path "
        "this trace found, in any language, so a customer never sees this "
        "text regardless of whether it is missing. Dead/unused config."
    ),
}

# Keys whose customer-facing text is a safety or compliance message, so a
# missing translation is a materially different risk than a missing
# "greeting" -- flagged explicitly in the README's missing-strings section.
_SAFETY_KEYS: frozenset[str] = frozenset({"guardrail_blocked", "sensitive_pii"})


def _missing_key_languages(sources: list[SourceString], all_findings: list[LanguageFindings]) -> dict[str, list[str]]:
    """Return ``{key: [language, ...]}`` for every key missing in >=1 language.

    Languages are listed in ``all_findings`` order (the same order as
    ``NON_ENGLISH_LANGUAGES``), so the result is deterministic.
    """
    by_key: dict[str, list[str]] = {source.key: [] for source in sources}
    for findings in all_findings:
        for key in findings.missing_keys:
            by_key[key].append(findings.language)
    return {key: languages for key, languages in by_key.items() if languages}


def _missing_strings_section(sources: list[SourceString], all_findings: list[LanguageFindings]) -> list[str]:
    missing_by_key = _missing_key_languages(sources, all_findings)
    safety_path = KEY_RUNTIME_PATHS["guardrail_blocked"]
    lines = [
        "## Missing strings: what customers see today",
        "",
        "For every key that is missing in at least one language, this is what",
        "a customer in that language is actually shown right now -- traced from",
        "the runtime code, not a guess (see this script's module docstring,",
        "\"RUNTIME BEHAVIOUR WHEN A KEY IS MISSING\", for the full trace).",
        "",
        "**`guardrail_blocked` and `sensitive_pii` are safety messages** -- a",
        "missing translation for either one means a customer who triggered a",
        "safety guardrail, or whose message contained something that looked",
        "like sensitive personal information, is currently shown an",
        f"unreviewed, machine-translated safety notice (both are classified"
        f" `{safety_path}` -> `machine_translated_at_request_time` below),",
        "rather than reviewed copy.",
        "",
        "| Key | Path | What the customer gets | Languages missing it |",
        "| --- | --- | --- | --- |",
    ]
    if not missing_by_key:
        lines.append("| - | - | no keys are missing in any language | - |")
        lines.append("")
        return lines

    for source in sources:
        if source.key not in missing_by_key:
            continue
        path = KEY_RUNTIME_PATHS[source.key]
        description = _PATH_CUSTOMER_DESCRIPTION[path]
        languages = ", ".join(f"`{lang}`" for lang in missing_by_key[source.key])
        key_label = f"**`{source.key}`** (safety)" if source.key in _SAFETY_KEYS else f"`{source.key}`"
        lines.append(f"| {key_label} | `{path}` | {description} | {languages} |")
    lines.append("")
    return lines


def _runtime_path_table(sources: list[SourceString]) -> list[str]:
    lines = [
        "## Runtime path per key",
        "",
        "Every one of the 45 keys, classified by which runtime function(s)",
        "actually render it in production (see this script's module",
        "docstring for the full trace and the missing-key behaviour each",
        "path implies). A blank note means the classification alone is not",
        "misleading about which code renders it.",
        "",
        "| Key | Path | Note |",
        "| --- | --- | --- |",
    ]
    for source in sources:
        path = KEY_RUNTIME_PATHS[source.key]
        note = KEY_RUNTIME_NOTES.get(source.key, "")
        lines.append(f"| `{source.key}` | `{path}` | {note} |")
    lines.append("")
    return lines


def build_readme(sources: list[SourceString], all_findings: list[LanguageFindings]) -> str:
    english_count = len(sources)
    count_table_lines = [
        "| Language | Code | Strings reviewable | Missing keys |",
        "| --- | --- | --- | --- |",
        f"| English (source) | `en` | {english_count} | - |",
    ]
    for findings in all_findings:
        lang_name = LANGUAGE_NAMES.get(findings.language, findings.language)
        count_table_lines.append(
            f"| {lang_name} | `{findings.language}` | {findings.string_count} | {len(findings.missing_keys)} |"
        )

    findings_sections: list[str] = []
    for findings in all_findings:
        findings_sections.extend(_findings_lines(findings))

    lines = [
        "# AskVera CX copy review pack",
        "",
        "AskVera's fallback, clarification and CX (conversation-experience) copy",
        "is translated into 12 route languages but had never been checked by a",
        "native speaker of each language. This pack is one CSV per non-English",
        "language, sized so a reviewer can work through the whole language in",
        "about an hour.",
        "",
        "## Sources",
        "",
        "- `config/conversation_routes.json` -> `locales.<lang>.responses` --",
        "  the message-key table `app/response/cx_render.py::render()` reads at",
        "  runtime. Only `responses` is reviewed here; `patterns` and",
        "  `scope_terms` are inbound-message matching phrases, not text shown",
        "  to a customer.",
        "- `config/claim_safety.json` -> `responses` -- the regulated",
        "  \"a Forever Living product treats/cures a disease\" refusal, read by",
        "  `services/claim_safety.py`. It has no key of its own in that file,",
        "  so this pack labels its row `product_disease_claim_refusal`.",
        "- `config/public_contacts.json` is contact data (phone numbers,",
        "  addresses, hours), included in the task brief as reference only --",
        "  it is not language copy and is not part of this review pack.",
        "",
        "## How to fill in a row",
        "",
        "Each row is one piece of copy in one language. Compare `english` and",
        "`translation` and fill in the three reviewer columns:",
        "",
        "- **reviewer_verdict**: `OK` (translation is correct and natural),",
        "  `FIX` (translation is wrong, unnatural, or has a problem you can",
        "  describe), or `UNSURE` (you are not confident either way -- leave a",
        "  comment explaining why).",
        "- **reviewer_suggested_text**: your corrected text, only when the",
        "  verdict is `FIX`. Leave blank for `OK` or `UNSURE`.",
        "- **reviewer_comment**: free text -- why you flagged it, or any other",
        "  note. Optional for `OK`.",
        "",
        "**A row with an empty `translation` is a missing key, not a blank",
        "one to skip.** Its `runtime_when_missing` column says what a customer",
        "gets today instead (see \"Missing strings: what customers see today\"",
        "below for the full picture). These rows still need your work: read",
        "`english`, write a proper translation into",
        "`reviewer_suggested_text`, and leave `reviewer_verdict` as `FIX` --",
        "there is no existing translation to mark `OK`, and `UNSURE` should",
        "only be used if you cannot produce a translation yourself (e.g. a",
        "term you are not confident about) and need to say why in",
        "`reviewer_comment`.",
        "",
        "Guidance while reviewing:",
        "",
        "- **Keep every `{placeholder}` exactly as written**, including the",
        "  braces and the name inside them (e.g. `{topic}`, `{country}`,",
        "  `{fields}`, `{options}`, `{contact}`). These are filled in by code",
        "  after translation -- renaming, dropping, or translating the name",
        "  inside the braces breaks the message at render time. The",
        "  `placeholders_english` / `placeholders_translation` /",
        "  `placeholder_mismatch` columns are this script's own mechanical",
        "  check of that; a `yes` there is always worth a look even before you",
        "  read the sentence.",
        "- **Register and tone**: plain, friendly, second person -- match the",
        "  English original's register, not a more formal or more casual one.",
        "- **Legal and compliance strings** (the medical and income claim",
        "  refusals, the FDA disclaimer, `product_disease_claim_refusal`, and",
        "  similar) **must keep their exact meaning**. Do not mark a faithful",
        "  but blunt or awkward-sounding legal translation as `FIX` just to",
        "  make it read more smoothly -- if the meaning is intact, that's",
        "  `OK`. Flag it instead if the translation softens, drops, or adds a",
        "  claim the English does not make (e.g. implying a product does",
        "  treat something, or dropping the referral to a healthcare",
        "  professional).",
        "",
        "## How to regenerate this pack",
        "",
        "Run from the repository root:",
        "",
        "```",
        "py -3 scripts/build_copy_review_pack.py",
        "```",
        "",
        "The script reads `config/conversation_routes.json` and",
        "`config/claim_safety.json` (never writes to either) and rewrites every",
        "file in this directory. It is deterministic: given the same inputs, two",
        "runs produce byte-identical output. Any in-progress reviewer columns",
        "(`reviewer_verdict`, `reviewer_suggested_text`, `reviewer_comment`) are",
        "**not preserved** across a regenerate -- copy them out first if a",
        "review is partway done and the underlying copy has changed.",
        "",
        "## String counts",
        "",
        *count_table_lines,
        "",
        *_runtime_path_table(sources),
        *_missing_strings_section(sources, all_findings),
        "## Mechanical findings",
        "",
        "The script itself checks the things below without judging the",
        "language -- these are not translation-quality judgements, only",
        "structural facts about the current copy. A reviewer should treat every",
        "listed key as a `FIX` (or at least an `UNSURE`) candidate for that",
        "language's CSV row, since the row's translation is unreliable in one",
        "of these mechanical ways (or, for a missing key, not reviewable at all).",
        "",
        *findings_sections,
    ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    sources = load_english_strings()

    if OUTPUT_DIR.exists():
        for existing in OUTPUT_DIR.glob("*.csv"):
            existing.unlink()

    all_findings: list[LanguageFindings] = []
    for language in NON_ENGLISH_LANGUAGES:
        rows, findings = build_language_pack(sources, language)
        write_csv(language, rows, OUTPUT_DIR)
        all_findings.append(findings)

    readme = build_readme(sources, all_findings)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    total_rows = sum(f.string_count + len(f.missing_keys) for f in all_findings)
    try:
        display_path = OUTPUT_DIR.relative_to(PROJECT_ROOT)
    except ValueError:
        display_path = OUTPUT_DIR
    print(
        f"Wrote {len(NON_ENGLISH_LANGUAGES)} language CSVs "
        f"({len(sources)} English source strings each) and README.md to "
        f"{display_path} "
        f"({total_rows} total rows)."
    )


if __name__ == "__main__":
    main()
