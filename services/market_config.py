"""Market and language configuration loaded from JSON."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_MARKETS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "markets.json"
DEFAULT_GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "global_directory_markets.json"
)
DEFAULT_POLICY_LOCALES_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "policy_locales.json"
REQUIRED_MARKET_FIELDS = {"code", "name", "enabled", "defaultLanguage", "languages", "privacyVersion", "displayOrder"}
REQUIRED_LANGUAGE_FIELDS = {"code", "name", "enabled"}


def _config_path() -> Path:
    try:
        from config import settings

        configured_path = getattr(settings, "MARKETS_CONFIG_PATH", None)
    except ImportError:
        configured_path = None
    return Path(os.environ.get("MARKETS_CONFIG_PATH", configured_path or DEFAULT_MARKETS_CONFIG_PATH))


def _global_directory_markets_path() -> Path:
    try:
        from config import settings

        configured_path = getattr(settings, "GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", None)
    except ImportError:
        configured_path = None
    return Path(
        os.environ.get("GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", configured_path or DEFAULT_GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH)
    )


@lru_cache(maxsize=1)
def load_global_directory_markets() -> list[dict[str, str]]:
    """Load the supplementary market names covered by the global sponsoring/
    office directory but absent from markets.json - either because no widget
    is deployed there (e.g. Japan) or because the directory spells an
    already-configured market's name differently (e.g. "Tanzania" vs
    markets.json's "Tanzania, United Republic of"). This only widens what
    find_market_mentions() recognizes for query planning and the cross-
    market evidence gate; it never changes which country's policy documents
    a session can access. A missing or malformed file fails open to an empty
    list rather than blocking chat requests, matching how conversation
    routing copy already degrades gracefully.
    """
    path = _global_directory_markets_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    markets = payload.get("markets")
    if not isinstance(markets, list):
        return []
    return [
        {"name": str(entry["name"]), "code": str(entry["code"]).upper()}
        for entry in markets
        if isinstance(entry, dict) and entry.get("name") and entry.get("code")
    ]


def _policy_locales_path() -> Path:
    """Return the content-managed catalog of policy locales currently published."""
    return Path(os.environ.get("POLICY_LOCALES_CONFIG_PATH", DEFAULT_POLICY_LOCALES_CONFIG_PATH))


@lru_cache(maxsize=1)
def load_policy_locales() -> dict[str, dict[str, Any]]:
    """Load active policy locales without embedding market rules in application code."""
    path = _policy_locales_path()
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    entries = payload.get("locales")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(f"Invalid policy locale config: {path} must contain a non-empty locales list.")

    catalog: dict[str, dict[str, Any]] = {}
    for entry in entries:
        market = str(entry.get("market") or "").upper()
        languages = [str(value).lower() for value in entry.get("languages", []) if str(value).strip()]
        if not market or not languages:
            raise RuntimeError(f"Invalid policy locale config entry in {path}.")
        catalog[market] = {
            "languages": set(languages),
            "documentCountries": {
                market,
                *(str(value).upper() for value in entry.get("documentCountries", []) if str(value).strip()),
            },
        }
    return catalog


@lru_cache(maxsize=1)
def load_market_config() -> dict[str, Any]:
    """Load the market configuration file once per process."""
    config_path = _config_path()
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    _validate_market_config(config, config_path)
    return config


def _validate_languages(code: str, languages: object) -> set[str]:
    """Validate one market's language entries and return enabled codes."""
    if not isinstance(languages, list) or not languages:
        raise RuntimeError(f"Invalid market config: {code}.languages must be a non-empty list.")

    enabled_codes: set[str] = set()
    all_codes: set[str] = set()
    for index, language in enumerate(languages):
        if not isinstance(language, dict):
            raise RuntimeError(f"Invalid market config: {code}.languages[{index}] must be an object.")

        missing_fields = REQUIRED_LANGUAGE_FIELDS - set(language)
        if missing_fields:
            raise RuntimeError(
                f"Invalid market config: {code}.languages[{index}] is missing "
                f"{', '.join(sorted(missing_fields))}."
            )

        language_code = str(language["code"])
        if language_code in all_codes:
            raise RuntimeError(f"Invalid market config: duplicate language {language_code} in {code}.")
        all_codes.add(language_code)

        if not isinstance(language["enabled"], bool):
            raise RuntimeError(f"Invalid market config: {code}.{language_code}.enabled must be true or false.")
        if language["enabled"]:
            enabled_codes.add(language_code)
    return enabled_codes


def _validate_market_config(config: dict[str, Any], config_path: Path) -> None:
    """Fail fast when markets.json is malformed."""
    markets = config.get("markets")
    if not isinstance(markets, list) or not markets:
        raise RuntimeError(f"Invalid market config: {config_path} must contain a non-empty markets list.")

    seen_market_codes: set[str] = set()
    seen_display_orders: set[int] = set()
    for index, market in enumerate(markets):
        if not isinstance(market, dict):
            raise RuntimeError(f"Invalid market config: market #{index + 1} must be an object.")

        missing_market_fields = REQUIRED_MARKET_FIELDS - set(market)
        if missing_market_fields:
            raise RuntimeError(
                f"Invalid market config: market #{index + 1} is missing {', '.join(sorted(missing_market_fields))}."
            )

        code = str(market["code"]).upper()
        if code in seen_market_codes:
            raise RuntimeError(f"Invalid market config: duplicate market code {code}.")
        seen_market_codes.add(code)

        if not isinstance(market["enabled"], bool):
            raise RuntimeError(f"Invalid market config: {code}.enabled must be true or false.")
        if not isinstance(market["displayOrder"], int):
            raise RuntimeError(f"Invalid market config: {code}.displayOrder must be a number.")
        if market["displayOrder"] in seen_display_orders:
            raise RuntimeError(f"Invalid market config: duplicate displayOrder {market['displayOrder']}.")
        seen_display_orders.add(market["displayOrder"])

        default_language = str(market["defaultLanguage"])
        enabled_language_codes = _validate_languages(code, market["languages"])

        if market["enabled"] and default_language not in enabled_language_codes:
            raise RuntimeError(
                f"Invalid market config: {code}.defaultLanguage must match an enabled language for that market."
            )


def get_markets() -> list[dict[str, Any]]:
    """Return enabled market objects in display order."""
    markets = load_market_config()["markets"]
    published = load_policy_locales()
    enabled_markets = [
        market
        for market in markets
        if market.get("enabled", True) and str(market.get("code") or "").upper() in published
    ]
    return sorted(enabled_markets, key=lambda market: (market.get("displayOrder", 9999), market.get("name", "")))


def market_display_name(code: str) -> str:
    """Return a market's configured name, or an empty string if it has none.

    find_market_mentions returns codes, and a code is not something to put in
    a sentence a reader will see: "What is the telephone number for GB?" is
    worse than the reference it replaces. The global directory list is checked
    too, because it names markets that markets.json does not carry.
    """
    normalized = str(code or "").strip().upper()
    if not normalized:
        return ""
    for market in load_market_config()["markets"]:
        if str(market.get("code") or "").upper() == normalized:
            return str(market.get("name") or "").strip()
    for market in load_global_directory_markets():
        if str(market.get("code") or "").upper() == normalized:
            return str(market.get("name") or "").strip()
    return ""


def get_countries() -> list[dict[str, Any]]:
    """Return the country/language shape expected by the public API."""
    countries: list[dict[str, Any]] = []
    for market in get_markets():
        published_languages = load_policy_locales()[str(market["code"]).upper()]["languages"]
        languages = [
            {"code": language["code"], "name": language["name"]}
            for language in market.get("languages", [])
            if language.get("enabled", True) and str(language["code"]).lower() in published_languages
        ]
        if languages:
            countries.append(
                {
                    "code": market["code"],
                    "name": market["name"],
                    "defaultLanguage": (
                        market["defaultLanguage"]
                        if market["defaultLanguage"] in {language["code"] for language in languages}
                        else languages[0]["code"]
                    ),
                    "privacyVersion": market["privacyVersion"],
                    "displayOrder": market["displayOrder"],
                    "languages": languages,
                }
            )
    return countries


def get_widget_countries() -> list[dict[str, Any]]:
    """Return markets that can be configured before their policy content is live."""
    public_countries = {country["code"]: country for country in get_countries()}
    countries = list(public_countries.values())

    for market in load_market_config()["markets"]:
        code = str(market.get("code") or "").upper()
        if (
            not market.get("enabled", True)
            or not market.get("widgetProvisioningEnabled", False)
            or code in public_countries
        ):
            continue
        languages = [
            {"code": language["code"], "name": language["name"]}
            for language in market.get("languages", [])
            if language.get("enabled", True)
        ]
        if languages:
            countries.append(
                {
                    "code": code,
                    "name": market["name"],
                    "defaultLanguage": market["defaultLanguage"],
                    "privacyVersion": market["privacyVersion"],
                    "displayOrder": market["displayOrder"],
                    "languages": languages,
                    "provisioningOnly": True,
                }
            )

    return sorted(countries, key=lambda country: (country["displayOrder"], country["name"]))


def get_country_codes() -> set[str]:
    """Return enabled market codes."""
    return {country["code"] for country in get_countries()}


def get_widget_country_codes() -> set[str]:
    """Return markets accepted by managed widget configuration."""
    return {country["code"] for country in get_widget_countries()}


@lru_cache(maxsize=1)
def _localized_market_names() -> dict[str, list[str]]:
    """Localised market names, generated plus curated.

    market_name_aliases.json is generated from Unicode CLDR by
    scripts/generate-market-name-aliases.mjs, which reads nothing but the
    market codes - so anything hand-added there disappears the next time it
    runs. Everyday abbreviations CLDR does not carry live in a separate
    curated file and are merged here, which keeps the generated file
    generated and makes the provenance of every alias legible.
    """
    path = DEFAULT_MARKETS_CONFIG_PATH.with_name("market_name_aliases.json")
    names: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))["names"]

    extra_path = DEFAULT_MARKETS_CONFIG_PATH.with_name("market_name_aliases_extra.json")
    if extra_path.exists():
        curated: dict[str, list[str]] = json.loads(
            extra_path.read_text(encoding="utf-8")
        ).get("names", {})
        merged = {code: list(values) for code, values in names.items()}
        for code, values in curated.items():
            merged.setdefault(code, [])
            merged[code].extend(value for value in values if value not in merged[code])
        return merged
    return names


# Words that can sit in front of a country name without qualifying it.
# Anything else in that position may be turning one country's name into
# another's - "DR Congo" is "Congo" with a qualifier - and a qualifier we do not
# recognise is a reason to ask, not to pick.
_MARKET_NAME_NEUTRAL_PREFIXES = frozenset(
    {
        "in", "for", "to", "from", "at", "on", "of", "and", "or", "with", "into",
        "a", "an", "my", "our", "your", "their", "its", "this", "that",
        "i", "we", "you", "they", "is", "are", "was", "were", "do", "does",
        "what", "how", "when", "where", "which", "who", "about", "regarding",
        "here", "there", "within", "across", "between", "customers", "orders",
    }
)


def _qualifier_before(padded_message: str, name: str) -> str:
    """The word immediately before this name in the message, if any."""
    index = padded_message.find(f" {name} ")
    if index <= 0:
        return ""
    preceding = padded_message[:index].split()
    return preceding[-1] if preceding else ""


@lru_cache(maxsize=1)
def _market_name_index() -> tuple[
    dict[str, frozenset[str]], frozenset[str], dict[str, frozenset[str]]
]:
    """Configured names, the ones that sit inside another market's name, and
    each name's own vocabulary.

    Built once. The shared-stem calculation compares every name against every
    other, which is 3,216 names and about ten million comparisons - measured at
    913ms when it ran per call, on a function every request uses. Cached the
    way the rest of this module caches its configuration.
    """
    markets = [
        market for market in load_market_config()["markets"] if market.get("enabled", True)
    ]
    markets.extend(load_global_directory_markets())
    localized = _localized_market_names()

    collected: dict[str, set[str]] = {}
    for market in markets:
        code = str(market["code"]).upper()
        for name in [market["name"], *localized.get(code, [])]:
            normalized_name = _normalize_market_text(name)
            if normalized_name:
                collected.setdefault(normalized_name, set()).add(code)

    names = {name: frozenset(codes) for name, codes in collected.items()}

    # Group by the codes a name maps to, so containment is compared between
    # different markets only, and each name's own vocabulary is available
    # without rescanning.
    by_codes: dict[frozenset[str], set[str]] = {}
    for name, codes in names.items():
        by_codes.setdefault(codes, set()).add(name)

    stems: set[str] = set()
    for name, codes in names.items():
        padded = f" {name} "
        for other, other_codes in names.items():
            if other_codes == codes:
                continue
            if padded in f" {other} ":
                stems.add(name)
                break

    own_words = {
        name: frozenset(word for sibling in by_codes[codes] for word in sibling.split())
        for name, codes in names.items()
    }
    return names, frozenset(stems), own_words


def find_market_mentions(message: str) -> set[str]:
    """Return enabled markets whose configured name is present in a message.

    Market discovery is driven by ``markets.json`` so newly configured
    countries work without adding retrieval-specific source code, plus the
    supplementary names in ``global_directory_markets.json`` for content
    covered by the global sponsoring/office directory that markets.json
    doesn't reflect (no widget deployment there, or a differently-spelled
    name for a market markets.json already has under a different code).
    Short market codes are deliberately not matched because ordinary words
    such as ``it`` and ``us`` would otherwise create false global-directory
    searches.
    """
    normalized_message = _normalize_market_text(message)
    if not normalized_message:
        return set()

    names, stems, own_words = _market_name_index()
    # Match longer names first so "Equatorial Guinea" does not also select
    # Guinea. Unambiguous full names only; never infer access from an alias.
    padded_message = f" {normalized_message} "
    matches: set[str] = set()
    for name in sorted(names, key=len, reverse=True):
        if len(names[name]) != 1 or f" {name} " not in padded_message:
            continue
        # A name that also sits inside another country's name is only safe on
        # its own. "Congo" preceded by a word we do not recognise may be
        # naming the other Congo - which is what "DR Congo" did, answering a
        # reader from the wrong country's policy. Returning nothing lets the
        # caller ask which country is meant; guessing does not.
        if name in stems:
            qualifier = _qualifier_before(padded_message, name)
            if qualifier and qualifier not in _MARKET_NAME_NEUTRAL_PREFIXES:
                if qualifier not in own_words[name]:
                    padded_message = padded_message.replace(f" {name} ", " ")
                    continue
        matches.update(names[name])
        padded_message = padded_message.replace(f" {name} ", " ")
    return matches


def find_probable_market_typo(message: str) -> str | None:
    """Return a likely-misspelled market name mentioned in a message, if any.

    Only used when ``find_market_mentions`` found no exact match - this never
    changes which market is used for an answer, it only powers a clarifying
    "did you mean X?" question (TRB-19189), so the guard is deliberately
    tight: single-word market names only (a typo in a multi-word name like
    "United Kingdom" is much more ambiguous to correct), a same-first-letter
    check, and a minimum length, mirroring the conservative shape of
    ``app.evidence._safe_short_phrase_variant``.
    """
    from utils.text_similarity import edit_distance_at_most_one

    normalized_message = _normalize_market_text(message)
    if not normalized_message:
        return None
    tokens = [token for token in normalized_message.split() if len(token) >= 4]
    if not tokens:
        return None

    for market in load_market_config()["markets"]:
        if not market.get("enabled", True):
            continue
        market_name = str(market.get("name") or "")
        normalized_name = _normalize_market_text(market_name)
        if not normalized_name or " " in normalized_name or len(normalized_name) < 4:
            continue
        for token in tokens:
            if token == normalized_name:
                continue  # an exact match belongs to find_market_mentions, not here
            if token[:1] != normalized_name[:1]:
                continue
            if edit_distance_at_most_one(token, normalized_name):
                return market_name
    return None


# Filler words that a reader may include and a catalogue entry does not.
# "Democratic Republic of the Congo" is how the country is usually written;
# the configured name is "Democratic Republic of Congo". That one word made the
# full name fail to match, so matching fell through to the substring "Congo" -
# which belongs to the REPUBLIC of Congo - and routed a reader asking about one
# country to another country's policy.
#
# Removed from both configured names and user wording, so the comparison stays
# symmetric. No configured name contains a standalone "the", so nothing in the
# catalogue changes meaning and no new ambiguity is introduced; both were
# checked against the live configuration before this was added.
_MARKET_NAME_FILLER_WORDS = frozenset({"the"})


def _normalize_market_text(value: str) -> str:
    """Normalize configured names and user wording for whole-name matching."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    collapsed = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    return " ".join(
        word for word in collapsed.split() if word not in _MARKET_NAME_FILLER_WORDS
    )


def get_language_codes_for_country(country_code: str) -> set[str]:
    """Return enabled language codes for a specific market."""
    normalized_code = country_code.upper()
    for country in get_countries():
        if country["code"] == normalized_code:
            return {language["code"] for language in country["languages"]}
    return set()


def get_supported_language_codes() -> set[str]:
    """Return every language enabled on any market.

    Response language and document authority are separate concerns: a reader may
    ask in one language about the market they selected. This set governs which
    language a reply may be written in. It never widens document access - the
    selected market still governs which policy documents are eligible.
    """
    return {
        language["code"]
        for country in get_countries()
        for language in country["languages"]
    }


def get_widget_language_codes_for_country(country_code: str) -> set[str]:
    """Return languages accepted for a provisioned widget market."""
    normalized_code = country_code.upper()
    for country in get_widget_countries():
        if country["code"] == normalized_code:
            return {language["code"] for language in country["languages"]}
    return set()


def get_document_country_codes(country_code: str) -> set[str]:
    """Return index metadata country codes accepted for a public market."""
    normalized_code = country_code.upper()
    entry = load_policy_locales().get(normalized_code)
    return set(entry["documentCountries"]) if entry else {normalized_code}
