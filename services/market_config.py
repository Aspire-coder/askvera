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
DEFAULT_SPONSORING_DIRECTORY_ALIASES_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "sponsoring_directory_country_aliases.json"
)
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


@lru_cache(maxsize=1)
def load_shared_offices() -> list[dict[str, Any]]:
    """Load owner-decided shared offices from ``global_directory_markets.json``.

    Each entry names a directory ``record_country`` whose office the owner
    decided also serves the listed countries (e.g. "Kenya/East Africa"). This
    is directory data only and never changes policy access. A missing file,
    missing ``shared_offices`` key or malformed entry fails open to nothing.
    """
    path = _global_directory_markets_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    offices = payload.get("shared_offices") if isinstance(payload, dict) else None
    if not isinstance(offices, list):
        return []
    loaded: list[dict[str, Any]] = []
    for entry in offices:
        if not isinstance(entry, dict):
            continue
        record_country = str(entry.get("record_country") or "").strip()
        serves = entry.get("serves")
        if not record_country or not isinstance(serves, list):
            continue
        names = [name.strip() for name in serves if isinstance(name, str) and name.strip()]
        if names:
            loaded.append({"record_country": record_country, "serves": names})
    return loaded


def find_shared_office_record_countries(message: str) -> set[str]:
    """Return the ``record_country`` of each shared office serving a country
    named in ``message`` that is not a configured market of its own.

    A served country that ``find_market_mentions`` already recognizes keeps
    its own directory record, so only whole names with no market entry of
    their own (e.g. "South Sudan") reach the serving office's record.
    """
    padded_message = f" {_normalize_market_text(message)} "
    if not padded_message.strip():
        return set()
    record_countries: set[str] = set()
    for office in load_shared_offices():
        for name in office["serves"]:
            normalized_name = _normalize_market_text(name)
            if not normalized_name or f" {normalized_name} " not in padded_message:
                continue
            if find_market_mentions(name):
                continue
            record_countries.add(office["record_country"])
    return record_countries


def _sponsoring_directory_aliases_path() -> Path:
    return Path(
        os.environ.get(
            "SPONSORING_DIRECTORY_ALIASES_CONFIG_PATH",
            DEFAULT_SPONSORING_DIRECTORY_ALIASES_CONFIG_PATH,
        )
    )


@lru_cache(maxsize=1)
def _sponsoring_directory_alias_groups() -> tuple[dict[str, Any], ...]:
    """Load the raw ``record_country -> terms`` groups from
    ``config/sponsoring_directory_country_aliases.json``.

    Kept separate from ``load_sponsoring_directory_country_aliases()``, the
    flattened ``term -> record_country`` map most callers (including that
    function itself) actually want, so the raw per-group term lists stay
    available to anything that needs them later. A missing or malformed
    file fails open to an empty tuple, matching how the other market config
    loaders degrade.
    """
    path = _sponsoring_directory_aliases_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return ()
    entries = payload.get("aliases") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return ()
    groups: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        record_country = str(entry.get("record_country") or "").strip()
        terms = entry.get("terms")
        if not record_country or not isinstance(terms, list):
            continue
        normalized_terms = frozenset(
            normalized
            for term in terms
            if isinstance(term, str) and (normalized := _normalize_market_text(term))
        )
        if normalized_terms:
            groups.append({"record_country": record_country, "terms": normalized_terms})
    return tuple(groups)


def load_sponsoring_directory_country_aliases() -> dict[str, str]:
    """Return the International Sponsoring Directory's own section-name aliases.

    A mapping of normalized user-facing term -> the exact ``record_country``
    section name the directory extraction uses for it (e.g. "uk" ->
    "England", "eswatini" -> "South Africa"). Sourced from
    ``config/sponsoring_directory_country_aliases.json``, kept separate from
    ``markets.json``/``market_name_aliases.json`` because the directory's PDF
    section headings sometimes group or spell countries differently than the
    generic, ISO-code-based market catalog does. Built fresh from
    ``_sponsoring_directory_alias_groups()`` (which does the actual, cached
    file read) each call, so it is never its own separately-cached snapshot.
    """
    aliases: dict[str, str] = {}
    for group in _sponsoring_directory_alias_groups():
        for term in group["terms"]:
            aliases[term] = group["record_country"]
    return aliases


def _all_configured_market_names() -> frozenset[str]:
    """Return every normalized market/alias name known to markets.json,
    global_directory_markets.json and market_name_aliases.json.

    Used only to keep a short sponsoring-directory alias term (e.g. "Guinea")
    from matching inside an unrelated, longer configured market name that
    happens to contain it (e.g. "Equatorial Guinea"); it never contributes a
    resolved country itself. Deliberately not its own lru_cache: it is cheap
    to recompute and both loaders it reads are already cached (and cleared)
    on their own, so a test that swaps markets.json/global_directory_markets.json
    and clears those caches is reflected here immediately, with no separate
    cache of its own to go stale.
    """
    markets = [*load_market_config()["markets"], *load_global_directory_markets()]
    localized = _localized_market_names()
    names: set[str] = set()
    for market in markets:
        code = str(market.get("code") or "").upper()
        for name in [str(market.get("name") or ""), *localized.get(code, [])]:
            normalized_name = _normalize_market_text(name)
            if normalized_name:
                names.add(normalized_name)
    return frozenset(names)


def superseded_market_codes_for_alias_term(term: str) -> frozenset[str]:
    """Return the market code(s), if any, that a sponsoring-alias TERM
    itself (not the group it belongs to) also unambiguously names via the
    ordinary, generic mechanism.

    This is the whole basis for deciding which generic market name(s) a
    matched alias term should replace in
    ``_directory_target_section_names()`` (``opensearch_sections.py``):
    replace a code's generic name only when the *exact term the alias table
    matched* is itself independently recognized by ``find_market_mentions``
    as naming that code - i.e. it is genuinely the same market under a
    different spelling/bundling, not merely a short word that happens to
    sit inside some unrelated longer name.

    This is what keeps the England group's "United Kingdom" replacing GB
    (``find_market_mentions("United Kingdom") == {"GB"}``) and the Guinea
    Bissau and Guinea Conakry group's "Guinea Conakry" replacing GN
    (``find_market_mentions("Guinea Conakry") == {"GN"}``), while a
    same-message but textually different alias term never wrongly
    supersedes an unrelated code: "China" (from the China group) resolves
    only to CN, never to HK, even though a *localized* Hong Kong alias
    happens to contain the substring "china" ("Hong Kong SAR China") -
    ``find_market_mentions`` requires an exact whole-name match, so it
    never makes that substring mistake either (review round 3: an earlier
    catalog-name-containment approach here did, and lost a real co-mentioned
    country - "China and Hong Kong offices", "American Samoa and the US",
    "Netherlands Antilles and Holland" - each time a short alias term
    happened to be a substring of an unrelated market's longer name).
    """
    return frozenset(find_market_mentions(term))


# A bare 2-3 letter alias term is real evidence of a country only when it
# opens the message or immediately follows one of these locative markers
# ("in the US", "in US") - never as an ordinary pronoun/word ("send US the
# address", "cost US to order", i.e. lowercased "us") and never inside an
# unrelated phrase such as a currency mention ("US dollars", preceded by
# "to", not "in"/"the"). find_market_mentions() already excludes short codes
# entirely for this exact reason; this table cannot drop "US" outright (it is
# the only way some messages name North America at all - e.g. "sign up in
# the US"), so it gets this narrower, explicit safeguard instead.
#
# Known accepted residual (review round 3): a sentence-OPENING bare "Us"
# ("Us, we order from Ghana", "Us and Poland") is indistinguishable, once
# casefolded, from a genuine sentence-opening "US" ("US minimum order?").
# There is no cheap, reliable signal to tell them apart post-normalization
# (case is already gone by the time this text is seen), so the "opens the
# message" branch below stays permissive and this residual is accepted
# rather than guarded further.
_SHORT_ALIAS_TERM_MAX_LEN = 3
_SHORT_ALIAS_LOCATIVE_PRECEDERS = frozenset({"in", "the"})


def _short_alias_term_is_located(padded_message: str, padded_name: str) -> bool:
    """True when ANY occurrence of a bare, short alias term in
    ``padded_message`` is preceded by a locative marker or opens the
    message. Checks every occurrence, not just the first, so "Send us the
    address; I am in the US" still matches on its second occurrence even
    though its first does not.
    """
    start = 0
    while True:
        index = padded_message.find(padded_name, start)
        if index == -1:
            return False
        prefix = padded_message[:index].rstrip(" ")
        if not prefix:
            return True
        preceding_token = prefix.rsplit(" ", 1)[-1]
        if preceding_token in _SHORT_ALIAS_LOCATIVE_PRECEDERS:
            return True
        start = index + 1


def find_sponsoring_directory_alias_matches(message: str) -> set[tuple[str, str]]:
    """Return ``(normalized_term, record_country)`` for every sponsoring
    alias term this message actually contains textually.

    This is the detailed form ``find_sponsoring_directory_alias_countries()``
    (below) summarizes into just the matched ``record_country`` values.
    ``_directory_target_section_names()`` in ``opensearch_sections.py``
    needs the term itself, not only the group it resolved to, to decide
    which generic market name(s) it may replace - see
    ``superseded_market_codes_for_alias_term()``.

    Every configured market/alias name (including the alias terms
    themselves) is consumed longest-name-first, exactly as
    ``find_market_mentions`` does, so a short alias term (e.g. "Guinea
    Bissau") cannot match inside a longer, unrelated configured market name
    that contains it (e.g. "Fooland Guinea Bissau"); matching only the
    sponsoring alias terms lets this run even when the message names no
    market of its own. A bare, short (<=3 letter) single-word term such as
    "US" additionally requires ``_short_alias_term_is_located()`` - see its
    docstring - so it cannot fire on the pronoun "us" or inside "US dollars".
    """
    aliases = load_sponsoring_directory_country_aliases()
    if not aliases:
        return set()
    normalized_message = _normalize_market_text(message)
    if not normalized_message:
        return set()
    padded_message = f" {normalized_message} "
    consumption_names = sorted(_all_configured_market_names() | set(aliases), key=len, reverse=True)
    matches: set[tuple[str, str]] = set()
    for name in consumption_names:
        padded_name = f" {name} "
        if padded_name not in padded_message:
            continue
        record_country = aliases.get(name)
        if (
            record_country
            and " " not in name
            and len(name) <= _SHORT_ALIAS_TERM_MAX_LEN
            and not _short_alias_term_is_located(padded_message, padded_name)
        ):
            record_country = None
        if record_country:
            matches.add((name, record_country))
        padded_message = padded_message.replace(padded_name, " ")
    return matches


def find_sponsoring_directory_alias_countries(message: str) -> set[str]:
    """Return the sponsoring directory section name(s) a message's country
    terms resolve to. See ``find_sponsoring_directory_alias_matches()`` for
    the per-term detail this summarizes."""
    return {record_country for _term, record_country in find_sponsoring_directory_alias_matches(message)}


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
    path = DEFAULT_MARKETS_CONFIG_PATH.with_name("market_name_aliases.json")
    return json.loads(path.read_text(encoding="utf-8"))["names"]


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

    markets = [market for market in load_market_config()["markets"] if market.get("enabled", True)]
    markets.extend(load_global_directory_markets())
    names: dict[str, set[str]] = {}
    localized = _localized_market_names()
    for market in markets:
        code = str(market["code"]).upper()
        for name in [market["name"], *localized.get(code, [])]:
            normalized_name = _normalize_market_text(name)
            if normalized_name:
                names.setdefault(normalized_name, set()).add(code)
    # Match longer names first so "Equatorial Guinea" does not also select
    # Guinea. Unambiguous full names only; never infer access from an alias.
    padded_message = f" {normalized_message} "
    matches: set[str] = set()
    for name in sorted(names, key=len, reverse=True):
        if len(names[name]) == 1 and f" {name} " in padded_message:
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
            # Demonyms such as "Tunisian" are one edit from a country name,
            # but must not trigger a country-typo confirmation.
            if (len(token) == len(normalized_name) + 1 and token.startswith(normalized_name)) or (
                len(token) == len(normalized_name) - 1 and normalized_name.startswith(token)
            ):
                continue
            if edit_distance_at_most_one(token, normalized_name):
                return market_name
    return None


# Generic English word-formation patterns for nationality adjectives
# ("Italy" -> "Italian", "Belgium" -> "Belgian", "Sweden" -> "Swedish",
# "Kyrgyzstan" -> "Kyrgyz"). They are applied to configured market names, so a
# new market is covered without a code change; they are not a list of market
# adjectives. Irregular forms that share no stem with the name ("Swiss",
# "British", "American") cannot be derived and are not recognised.
_ADJECTIVE_NAME_ENDINGS = ("", "a", "e", "o", "y", "ia", "ium", "en", "stan")
_ADJECTIVE_SUFFIXES = ("n", "an", "ian", "ish", "ese", "i")
_BARE_STEM_ENDINGS = frozenset({"y", "stan"})
_MIN_ADJECTIVE_STEM_LENGTH = 4


def _derived_market_adjectives(normalized_name: str) -> set[str]:
    forms: set[str] = set()
    for ending in _ADJECTIVE_NAME_ENDINGS:
        if not normalized_name.endswith(ending):
            continue
        stem = normalized_name[: len(normalized_name) - len(ending)]
        if len(stem) < _MIN_ADJECTIVE_STEM_LENGTH:
            continue
        if ending in _BARE_STEM_ENDINGS:
            forms.add(stem)
        forms.update(stem + suffix for suffix in _ADJECTIVE_SUFFIXES)
    forms.discard(normalized_name)
    return forms


def market_adjective_codes(word: str, session_country: str = "") -> set[str]:
    """Return markets a single English adjective such as "Italian" refers to.

    This is deliberately separate from ``find_market_mentions``, which is
    unchanged: a nationality adjective is far weaker evidence of a market
    request than a name ("my Italian downline"), so callers must supply the
    grammatical context themselves. The only caller is the cross-market
    company-policy refusal, which asks about the word directly modifying
    "company policy".

    A form derived from a single-word configured market name wins. Otherwise
    the word may name a language that a market publishes its company policy
    in ("Norwegian", "Dutch"); the result is then every such publishing market,
    which is only evidence that some market is meant, not which one.

    When ``session_country`` is given, a word naming one of that market's own
    configured languages returns an empty set, because "the German company
    policy" from an Austrian session may be asking for the German-language
    version of Austria's own policy.
    """
    target = _normalize_market_text(word)
    if not target or " " in target:
        return set()
    configured_markets = [market for market in load_market_config()["markets"] if market.get("enabled", True)]
    session = str(session_country or "").strip().upper()
    if session:
        for market in configured_markets:
            if str(market.get("code") or "").upper() != session:
                continue
            session_languages = {
                _normalize_market_text(str(language.get("name") or ""))
                for language in market.get("languages", [])
            }
            if target in session_languages:
                return set()

    derived = {
        str(market["code"]).upper()
        for market in [*configured_markets, *load_global_directory_markets()]
        if " " not in (name := _normalize_market_text(str(market.get("name") or "")))
        and name
        and target in _derived_market_adjectives(name)
    }
    if derived:
        return derived

    language_codes = {
        str(language.get("code") or "").lower()
        for market in configured_markets
        for language in market.get("languages", [])
        if _normalize_market_text(str(language.get("name") or "")) == target
    }
    return {code for code, entry in load_policy_locales().items() if entry["languages"] & language_codes}


def _normalize_market_text(value: str) -> str:
    """Normalize configured names and user wording for whole-name matching."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


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
