"""AI chat orchestration for AskVera."""

import re
import unicodedata
from contextvars import ContextVar
from dataclasses import replace
from functools import lru_cache
from time import perf_counter
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from app.metrics.health import record_validation_outcome
from app.metrics.responses import record_delivered_response, record_numeric_repair
from app.models.responses import ModelResponse
from app.orchestrator.compound_requests import separate_question_and_command
from app.operations import pipeline_trace_store
from app.models.router import ModelRouter, model_router
from app.evidence import (
    EvidenceDecision,
    assistant_meta_response,
    approve_evidence,
    classify_intent,
    configured_conversation_response,
    is_planner_trusted_low_risk_subtype,
    localized_conversation_response,
    mentions_out_of_corpus_topic,
    with_approved_evidence,
)
from app.evidence_contract import parse_evidence_contract
from app.prompts import PromptBuilder
from app.response import ChatResponse, ResponseBuilder, response_builder
from app.response.quality import (
    contact_for_country,
    format_period_not_covered,
    has_incomplete_ending,
    remove_or_replace_contact_placeholders,
    unsupported_requested_years,
)
from app.retrieval import RetrievalService, confidence_from_sources, retrieval_service
from app.retrieval.models import RetrievalResult
from app.retrieval.cache_evidence import restore_evidence, serialize_evidence
from app.governance import GovernanceDecision, GovernanceEngine, governance_engine
from app.validation import OutputValidator, ValidationContext, ValidationResult, output_validator, validation_summary
from app.validation.validators.numeric_grounding_validator import (
    remove_unsupported_numeric_sentences,
    removal_diagnostics,
)
from config import settings
from config.vera_persona import FALLBACK_RESPONSES, fbo_enrollment_is_unavailable
from services.audit import write_audit_event
from services.aws_clients import get_aws_clients
from services.candidate_control import CandidateFlags, get_candidate_flags
from services.cache import (
    build_cache_key,
    get_cache_value,
    set_cache_value,
)
from services.semantic_cache import (
    SemanticCacheHit,
    get_semantic_cache_value,
    semantic_cache_active,
    set_semantic_cache_value,
)
from services.consent_service import has_valid_consent
from services.claim_safety import localized_claim_response
from services.guardrails import is_policy_safety_question
from services.market_config import (
    _localized_market_names,
    _normalize_market_text,
    find_market_mentions,
    find_probable_market_typo,
    find_sponsoring_directory_alias_countries,
    find_shared_office_record_countries,
    load_global_directory_markets,
    load_market_config,
    load_shared_offices,
    market_display_name,
)
from services.pii import contains_sensitive_pii_placeholder, remove_unresolved_pii_placeholders, scrub_pii
from services.session import append_session_turn, get_session_history
from services.session_service import validate_and_touch_session
from utils.exceptions import SessionExpiredError
from utils.exceptions import (
    BedrockServiceError,
    BedrockTimeoutError,
    LowConfidenceError,
    LowConfidenceThresholdError,
    RetrievalMissError,
)
from utils.inline_citations import separate_verified_citations
from utils.directory_fields import (
    build_support_contact_supplement,
    canonical_requested_order_size,
    directory_field_conflicts,
    parse_directory_fields,
    preserve_directory_role_labels,
    correct_directory_source_contradictions,
    repair_labeled_directory_contacts,
    remove_unrequested_directory_fields,
    restore_missing_directory_contacts,
    restore_missing_requested_directory_fields,
    restore_missing_requested_order_size,
)
from utils.logging import get_logger
from utils.validators import ChatRequest

LOGGER = get_logger("app.orchestrator")
# Reference follow-ups point back at the prior answer with no new subject of
# their own ("elaborate", "what else") - retrieval should reuse the prior
# self-contained question as-is.
FOLLOW_UP_REFERENCE_MARKERS = (
    "that",
    "this",
    "it",
    "them",
    "those",
    "previous",
    "earlier",
    "above",
    "first question",
    "last question",
    "more about",
    "more detail",
    "more details",
    "more information",
    "explain more",
    "tell me more",
    "elaborate",
    "expand on",
    "go deeper",
    "what else",
    "continue",
    "how so",
    "why is that",
)
# Topic-shift follow-ups carry a new subject alongside an implicit reference
# to the prior question's frame ("what about Kenya?", "and in Kenya?").
# Retrieval needs both the prior topic and the new subject, so these are
# merged with the anchor question instead of replacing it.
FOLLOW_UP_TOPIC_SHIFT_MARKERS = (
    "what about",
    "how about",
    "what if",
)
FOLLOW_UP_CONTEXT_MARKERS = FOLLOW_UP_REFERENCE_MARKERS + FOLLOW_UP_TOPIC_SHIFT_MARKERS
# "And for Guinea?" / "And in Uganda?" swap only the market and lean on the
# prior question for everything else, exactly like "what about Guinea?". Leading
# position, a short message and a named market are all required, so "And for
# returns, what is the policy?" is never pulled into history.
FOLLOW_UP_MARKET_ELLIPSIS = re.compile(r"^(?:and|but)\s+(?:for|in|about)\s+\S", re.IGNORECASE)
FOLLOW_UP_MARKET_ELLIPSIS_MAX_WORDS = 6


def _follow_up_unaccented(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _follow_up_tokens(text: str, *, casefold: bool = True) -> tuple[str, ...]:
    """Word tokens with accents removed, so "für", "fur" and "Für" compare alike."""
    unaccented = _follow_up_unaccented(text)
    return tuple(re.findall(r"[^\W_]+", unaccented.casefold() if casefold else unaccented, flags=re.UNICODE))


def _follow_up_stem_pattern(*fragments: str, word_start: bool = True) -> re.Pattern[str]:
    """One pattern over space-joined follow-up tokens; each fragment matches from a word start.

    Fragments are written with their accents and folded like the tokens, so "é"
    and "ё" need no second spelling. Only lower-case regex escapes are used.
    ``word_start=False`` also matches inside a compound ("leveringsbeleid").
    """
    folded = (_follow_up_unaccented(fragment).casefold() for fragment in fragments)
    return re.compile((r"(?<!\w)" if word_start else "") + "(?:" + "|".join(folded) + ")", re.UNICODE)


def _follow_up_token_set(*phrases: str) -> frozenset[str]:
    return frozenset(token for phrase in phrases for token in _follow_up_tokens(phrase))


# W14: the same short follow-up shapes in every conversation language. Offline
# probe 2026-09-12: "En voor Uganda?", "Und für Uganda?", "А для Уганды?" and the
# rest never reached the history path, so retrieval got the bare follow-up and
# the prior topic was lost. English is untouched; these apply to the tokens of
# the message start only, and every shape is bounded like its English twin.
#
# 1. Connector ellipsis ("And for Uganda?"): conjunction + preposition, at most
#    FOLLOW_UP_MARKET_ELLIPSIS_MAX_WORDS words, and a recognised market is required,
#    exactly as FOLLOW_UP_MARKET_ELLIPSIS. A question word right after the
#    connector makes it a full question ("Und für wen gilt das in Uganda?").
LOCALIZED_FOLLOW_UP_CONNECTORS = frozenset(
    _follow_up_tokens(f"{conjunction} {preposition}")
    for conjunctions, prepositions in (
        (("en", "maar"), ("voor", "in", "naar", "met")),  # nl
        (("et", "mais"), ("pour", "en", "au", "aux", "à", "dans")),  # fr
        (("und", "aber"), ("für", "fuer", "in", "im", "nach")),  # de
        (("y", "pero"), ("para", "en", "por")),  # es
        (("e", "mas"), ("para", "pra", "em", "no", "na", "nos", "nas")),  # pt
        (("e", "ma"), ("per", "in", "a", "ad", "nel", "nella")),  # it
        (("och", "men"), ("för", "i", "om")),  # sv
        (("og", "men"), ("for", "i", "om", "til")),  # da, no
        (("а", "и", "но"), ("для", "в", "во", "по")),  # ru
        (("a", "i"), ("dlya", "dlja", "v", "vo")),  # ru, transliterated
        (("a", "i", "ali"), ("za", "u", "na")),  # sr, Latin
        (("а", "и"), ("за", "у", "на")),  # sr, Cyrillic
    )
    for conjunction in conjunctions
    for preposition in prepositions
)
# 2. "What about X?" / "How about X?" openers. Like the English topic-shift
#    markers they need no market ("Qu'en est-il de la commande minimale ?"), but
#    the words after the opener must be short (LOCALIZED_FOLLOW_UP_MAX_CONTENT
#    content words) and must not be a question word or a bare pronoun ("Hur är
#    det med dig?" is small talk). Finnish, Russian and Serbian decline market
#    names and market_name_aliases.json lists only the base form, so there a
#    capitalised word that names no recognised market ("А что насчёт Уганды?",
#    "Entä Ugandassa?") keeps the message standalone rather than merging it
#    with the previous market, which could then never be replaced.
LOCALIZED_TOPIC_SHIFT_OPENERS: dict[str, tuple[str, ...]] = {
    "nl": ("wat dan met", "en wat dan met", "en wat met", "hoe zit het met", "hoe zit het dan met", "en hoe zit het met"),
    "fr": ("qu'en est-il", "et qu'en est-il", "et pour ce qui est", "et concernant"),
    "de": ("und was ist mit", "wie sieht es mit", "und wie sieht es mit", "wie steht es mit", "und wie steht es mit"),
    "es": ("y qué hay de", "y qué pasa con", "y qué tal", "y en cuanto a", "y respecto a"),
    "pt": ("e quanto", "e sobre", "e que tal", "e o que dizer de"),
    "it": ("e riguardo", "e per quanto riguarda", "e che dire di"),
    "sv": ("hur är det med", "och hur är det med", "och vad gäller", "hur blir det med"),
    "da": ("hvad med", "og hvad med", "hvad så med"),
    "no": ("hva med", "og hva med", "hva så med"),
    "fi": ("entä", "entäs", "no entä"),
    "ru": (
        "а что насчёт", "что насчёт", "а как насчёт", "как насчёт",
        "a chto naschet", "chto naschet", "a kak naschet", "kak naschet",
    ),
    "sr": (
        "a šta je sa", "šta je sa", "a šta sa", "a što se tiče",
        "а шта је са", "шта је са", "а шта са", "а што се тиче",
    ),
}
LOCALIZED_INFLECTED_NAME_LANGUAGES = frozenset({"fi", "ru", "sr"})
# 3. Topic ellipsis ("And the minimum order?"): conjunction + article, or bare
#    Swedish "och", then at most two content words, and a question mark. It keeps
#    the previous market, like "And the email?" does in English - and, like that
#    English case, only for a directory field: "And the warranty?" stays standalone
#    in English, so "En de garantie?" and "Y la empresa?" do too (W14b, Fable W14
#    note 1). The field must be in LOCALIZED_DIRECTORY_FIELD_TERMS, no policy word
#    may appear, and a capitalised word after a place preposition that names no
#    recognised market ("Och i Stockholm?", "E a Roma?") keeps the message standalone.
LOCALIZED_TOPIC_ELLIPSIS_OPENERS = tuple(
    _follow_up_tokens(f"{opener} {article}")
    for opener, articles in (
        ("en", ("de", "het")),  # nl
        ("et", ("le", "la", "les", "l'")),  # fr
        ("et pour", ("le", "la", "les", "l'")),  # fr
        ("und", ("der", "die", "das", "den", "dem")),  # de
        ("y", ("el", "la", "los", "las")),  # es
        ("e", ("o", "a", "os", "as")),  # pt
        ("e", ("il", "lo", "la", "i", "gli", "le", "l'")),  # it
        ("och", ("",)),  # sv
    )
    for article in articles
)
# The fields of FOLLOW_UP_DIRECTORY_FIELD_TERMS - (tele)phone, opening hours, email,
# address, website, delivery/shipping, payment/pay, minimum order - and nothing
# more. Stems match from a word start, so compounds such as "Lieferkosten",
# "verzendkosten" and "leveranskostnaden" count; stems that would also start an
# unrelated word ("liefer" -> "Lieferant", "livr" -> "livre") are spelled out.
# Bare "hours" words ("heures", "horas", "ore") are left out as too loose. One
# pattern serves every language, so a shared stem ("adres", "levering") is listed once.
LOCALIZED_DIRECTORY_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "nl": (
        "telefoon", r"e ?mail", "adres", "website", "openingstijd", "openingsuren",
        "levering", "levertijd", "leverkost", r"leveren\b", "bezorg", "verzend", "betaal", "betaling", r"betalen\b",
        r"minim\w* bestel", "minimumbestel", "bestelminimum",
    ),
    "fr": (
        "téléphone", "courriel", "adresse", r"site (?:web|internet)", "horaire", r"heures d ouverture",
        "livraison", "livraision", r"livrer\b", "expédition", r"expédier\b", "envoi", "paiement", r"payer\b",
        r"commande\w* minim", r"minim\w* (?:de )?commande",
    ),
    "de": (
        "telefon", "adress", "anschrift", "webseite", "internetseite", "öffnungszeit", "oeffnungszeit",
        "geschäftszeit", "geschaeftszeit", r"liefer(?:ung|kost|zeit|geb|dauer|n\b|kots)", "versand", "zustell",
        "zahlung", "bezahl", r"zahlen\b", "mindestbestell", r"minim\w* bestell",
    ),
    "es": (
        "teléfono", "correo", "dirección", r"(?:sitio|página) web", "horario",
        "entrega", "envío", r"enviar\b", "pago", r"pagar\b", r"pedido\w* mínim", r"mínim\w* (?:de )?pedido",
        r"compra\w* mínim",
    ),
    "pt": (
        "telefone", "endereço", r"site\b", "horário", "frete", "pagamento",
        r"encomenda\w* mínim", r"mínim\w* (?:de )?encomenda",
    ),
    "it": (
        "indirizzo", r"sito\b", "posta elettronica", "orari", "consegna", "spedizion", r"spedire\b",
        "pagament", r"pagare\b", r"ordin\w* minim", r"minim\w* (?:d |di )?ordin",
    ),
    "sv": (
        r"e ?post", "mejl", "webbplats", "hemsida", "webbsida", "öppettid", "leverans", r"leverera\b", "frakt",
        "betalning", r"betala\b", r"minsta (?:beställning|order)", "minimibeställning", "minimiorder",
    ),
    "da": (
        "telefon", r"e ?mail", "adresse", "hjemmeside", "webside", "åbningstid", "levering", "fragt", "forsendelse",
        "betaling", r"betale\b",
        "minimumsbestilling", "minimumsordre", r"mindste (?:bestilling|ordre)",
    ),
    "no": (
        "telefon", r"e ?post", "epost", "adresse", "nettside", "hjemmeside", "åpningstid", "levering", "frakt",
        "betaling", r"betale\b", "minstebestilling", "minsteordre", r"minste (?:bestilling|ordre)",
    ),
    "fi": (
        "puhelin", "sähköposti", "osoite", "osoitte", "verkkosivu", "kotisivu", "aukiolo",
        r"toimitus(?:maksu|kulu|aika|ajat)?\b", "toimituks", "maksu", r"maksaa\b", "vähimmäistilau", "minimitilau",
    ),
    "ru": (
        "телефон", r"электронн\w* почт", "имейл", "емейл", "адрес", "сайт", r"(?:час|врем|график)\w* работ",
        "доставк", "пересылк", "оплат", "платёж", r"минимальн\w* (?:сумм\w* )?заказ",
        "dostavk", "oplat", r"minimaln\w* zakaz", "sajt", r"sait\b",
    ),
    "sr": (
        "telefon", "imejl", "email", "adres", r"radn\w* vrem", "dostav", "isporuk", "pošiljk", "slanj",
        "plaćanj", "platit",
        r"minimaln\w* (?:porudžbin|narudžbin)",
        "имејл", "мејл", "сајт", r"радн\w* врем", "достав", "испорук", "пошиљк", "плаћањ", "платит",
        r"минималн\w* (?:поруџбин|наруџбин)",
    ),
}
LOCALIZED_DIRECTORY_FIELD_PATTERN = _follow_up_stem_pattern(
    *(fragment for fragments in LOCALIZED_DIRECTORY_FIELD_TERMS.values() for fragment in fragments)
)
# POLICY_WORD in the same languages: "And the delivery policy?" is not a field request.
LOCALIZED_POLICY_PATTERN = _follow_up_stem_pattern(
    "policy", "beleid", "politique", "richtlinie", "politik", "política", "käytäntö", "politica", "retningslinj", "riktlinj", "политик", word_start=False
)
# Place prepositions for the capitalised-name guard on the topic ellipsis.
LOCALIZED_PLACE_PREPOSITIONS = _follow_up_token_set(
    "in naar", "à a au aux en dans", "im nach", "em no na", "ad nel nella", "i till til", "u", "в во у"
)
# Governance (W14b, Fable W14 note 2): a localized "what about ..." question that
# names none of these is judged on its own words, like "What about the shipping?".
# Guarantee and promise words keep the anchor, as CONTENT_REQUEST_TERMS does in
# English; "garantie" also means warranty, which only errs toward keeping it.
LOCALIZED_CONTENT_REQUEST_PATTERN = _follow_up_stem_pattern(
    "garant", "gegarand", "zagarant", "гарант", "загарант", "taku", "taat", "belof", "beloof", "promes", "promet", "promis", "versprech",
    r"lov(?:a|ar|ade|at|e|er|et|ede)\b", "løft", "обещ", "обећ", "obeć",
    "reclam", "werb", "publicid", "publicit", "pubblicit", "annons", "reklam", "mainos", "témoign", "testimon",
    "getuig", "erfahrungsbericht", "slogan", "рекла", "отзыв", "оглас",
)
LOCALIZED_FOLLOW_UP_MAX_CONTENT = 2
LOCALIZED_FOLLOW_UP_MAX_TAIL = 5
# Articles, prepositions and conjunctions that do not count as content words.
LOCALIZED_FOLLOW_UP_FUNCTION_WORDS = _follow_up_token_set(
    "the de het een van voor naar in met en",
    "le la les l du des d a au aux pour et",
    "der die das den dem ein eine im für nach mit und aus von",
    "el los las del al para y",
    "o os as do da dos no na nos nas em ao aos e",
    "il lo i gli di della alla ad nel nella per",
    "för till om och",
    "for til og",
    "в во для по на с со и а",
    "u za sa",
    "у за са",
)
# A question word, pronoun or verb among the content words makes a full question
# or small talk ("En voor wie is dit?", "Et pour quoi faire ?", "Hvad med dig?").
LOCALIZED_FOLLOW_UP_STOP_WORDS = _follow_up_token_set(
    "wie wat waar wanneer waarom welke welk hoe hoeveel hoelang jij jou je ik mij is zijn jullie ons",
    "qui quoi que qu quand ou pourquoi comment combien quel quelle quels quelles toi vous moi tu nous est sont",
    "wer wen wem wessen was wo wann warum weshalb wieso welche welcher welches dir dich ihnen euch ich sie ist sind "
    "mir uns",
    "quién quiénes qué cuál cuáles cuándo dónde cómo cuánto cuánta cuántos cuántas porqué ti usted ustedes yo es son "
    "estás está nosotros nosotras mí conmigo",
    "quem qual quais quando onde como quanto quanta quantos quantas porque você vocês são mim nós",
    "chi che cosa quale quali dove come quanti quante perché te voi lei io sono noi me",
    "vem vad var när varför hur vilken vilket vilka dig mig er oss du jag ni är",
    "hvem hvad hvor hvornår hvorfor hvordan hvilken hvilket hvilke jer os jeg vi",
    "hva deg meg dere",
    "mikä mitä kuka ketkä missä mistä mihin milloin miksi miten kuinka paljonko sitten sinä sinulle te minulle "
    "minä me",
    "что чего чем кто кого кому как где куда когда почему зачем сколько какой какая какие чей потом тогда "
    "ты вы тебя вас тобой вами я мне меня нас",
    "šta što ko koga kome kako gde gdje kada kad zašto koliko koji koja koje onda ti vi tebe vas tobom vama ja mi "
    "mnom nama",
    "шта што ко кога коме како где када зашто колико који која које онда ти ви тебе тобом вама ја ми мном нама",
)
# Removed together with a replaced market name, so "the delivery cost in Mali?"
# becomes "the delivery cost?" rather than "the delivery cost in?". English, Dutch,
# French and German place connectors with an optional article; in any other
# language the connector simply stays, which retrieval tolerates. The same
# connector is also what lets a lower-case name count as a market ("in kenya").
# "van", "von", "de", "à" and the elided "de l'" joined in W8c (Fable W8b note 1:
# "openingstijden van mali", "Lieferkosten von mali" and "de la turquie" kept the stale market).
REPLACED_MARKET_LEAD_IN = re.compile(
    r"(?<![^\W_])(?:in|for|of|from|at|to|naar|voor|uit|van|au|aux|en|pour|du|de|à|nach|fur|für|aus|von)\s+"
    r"(?:(?:the|la|le|les|de|het|der|die|das)\s+|l['’]\s*)?$",
    re.IGNORECASE | re.UNICODE,
)
# "What about the netherlands?": a lower-case name after "what/how about" counts
# only when it closes the clause, so "What about china plates?" keeps "china".
REPLACED_MARKET_QUESTION_LEAD_IN = re.compile(r"(?<![^\W_])(?:what|how)\s+about\s+(?:the\s+)?$", re.IGNORECASE)
REPLACED_MARKET_CLAUSE_END = re.compile(r"\s*(?:[?.!,;:]|$)")
REPLACED_MARKET_POSSESSIVE = re.compile(r"['’]s\b", re.IGNORECASE)
# A follow-up that opens like a question and asks for no new content is judged on
# its own words rather than on the question it inherits for retrieval. Both lists
# are deliberately narrow: anything unmatched keeps the inherited context, which
# is the safer direction. See AIOrchestrator._governance_text.
QUESTION_OPENERS = re.compile(
    r"^(?:what|how|when|where|which|who|why|whose|whom|is|are|was|were|do|does|did|can|could|"
    r"should|would|will|may|might|has|have|had)\b",
    re.IGNORECASE,
)
# "Do it anyway" opens with an auxiliary verb but continues an instruction rather
# than asking anything. Those cues keep the inherited context.
CONTINUATION_TERMS = re.compile(
    r"\b(?:anyway|anyhow|regardless|nonetheless|go\s+ahead|do\s+it|just\s+do|carry\s+on|"
    r"continue|proceed)\b",
    re.IGNORECASE,
)
# A message that opens with an instruction to produce something, and asks nothing,
# is a command rather than a question. Leading position matters: "Belgium, write
# the number down" is not what this targets, and a question containing any of
# these verbs keeps its question mark and is not matched.
LEADING_INSTRUCTION = re.compile(
    r"^(?:then\s+|now\s+|ok(?:ay)?[,\s]+|so\s+|just\s+|please\s+|and\s+)*"
    r"(?:just\s+|please\s+)*"
    r"(?:write|create|draft|generate|make|compose|post|publish|send|give\s+me|show\s+me)\b",
    re.IGNORECASE,
)
CONTENT_REQUEST_TERMS = re.compile(
    r"\b(?:write|writing|create|creating|make|making|draft|drafting|compose|composing|generate|"
    r"generating|produce|producing|post|posting|publish|publishing|send|sending|word|phrase|"
    r"caption|captions|script|slogan|tagline|testimonial|advert\w*|ad\s+copy|claim|claims|"
    r"promise|promises|guarantee|guarantees|guaranteed)\b",
    re.IGNORECASE,
)
# A wh-question needs no question mark to read as a question ("How much would
# those products cost"). Auxiliary openers still do: "do that" is an instruction.
WH_QUESTION_OPENERS = re.compile(r"^(?:what|how|when|where|which|who|why|whose|whom)\b", re.IGNORECASE)
# A bounded request for one directory field that names no market of its own
# ("What payment methods do they take?", "And the hours?"). Recorded as TC-070:
# Paraguay was lost on exactly this turn. It inherits a target only through
# _inherited_directory_target, never by adding generic words such as "cost" to
# the follow-up markers, which would drag history into standalone questions.
# "minimum order" is a directory record field too: live 2026-09-12, "What is
# the delivery cost in Mali?" -> "What's the minimum order amount?" lost Mali.
FOLLOW_UP_DIRECTORY_FIELD_TERMS = re.compile(
    r"\b(?:(?:tele)?phone|hours|opening\s+times?|e-?mail|address|website|"
    r"deliver(?:y|ies|s|ed)?|shipping|payments?|payment\s+methods?|pay|"
    r"minimum\s+(?:orders?|amounts?|requirements?)|order\s+minimums?)\b",
    re.IGNORECASE,
)
# The localized vocabulary above is also the authoritative narrow field list for
# short continuations. Keep the English pattern for its readable fast path, and
# add the existing per-language stems without broadening policy matching.
FOLLOW_UP_DIRECTORY_FIELD_TERMS = re.compile(
    rf"(?:{FOLLOW_UP_DIRECTORY_FIELD_TERMS.pattern}|{LOCALIZED_DIRECTORY_FIELD_PATTERN.pattern})",
    re.IGNORECASE | re.UNICODE,
)
FOLLOW_UP_DIRECTORY_FIELD_MAX_WORDS = 10
# These labels intentionally do not identify one retrievable directory field.
# A bare topic ellipsis using them must clarify rather than inherit a market.
AMBIGUOUS_DIRECTORY_TOPIC_TERMS = re.compile(
    r"\b(?:office|contact|kantoor|bureau|kontakt|oficina|contacto|kontor|"
    r"toimisto|yhteystiedot|ufficio|contatto|büro|офис|контакт|kontor|"
    r"kancelarija|канцеларија)\b",
    re.IGNORECASE | re.UNICODE,
)
# A short reply that supplies a detail for the question just asked. Recorded as
# TC-051 ("I live in Arizona.") and TC-055 ("I bought it 45 days ago.").
CLARIFICATION_REPLY = re.compile(
    r"^(?:(?:i\s+am|i['’]m|i\s+live|i\s+bought|i\s+purchased|i\s+ordered|i\s+joined|i\s+signed\s+up|"
    r"i\s+mean|we\s+are|we['’]re|we\s+live)\b"
    r"|(?:about\s+|around\s+|over\s+|almost\s+)?\d+\s+(?:days?|weeks?|months?|years?)(?:\s+ago)?\s*[.!]?$)",
    re.IGNORECASE,
)
CLARIFICATION_REPLY_MAX_WORDS = 10
POLICY_WORD = re.compile(r"\bpolic(?:y|ies)\b", re.IGNORECASE)
# B3: a narrow English-only signal that the delivered answer is directing the
# reader to contact a human channel - never a refusal/fallback/guardrail
# pattern, and never inferred from the user's question.
_CARE_CONTACT_RECOMMENDATION_RE = re.compile(
    r"\b(?:contact|reach\s+out\s+to|get\s+in\s+touch\s+with|speak\s+(?:to|with))\s+"
    r"(?:your\s+)?(?:local\s+)?(?:customer\s+(?:care|service|support)|support(?:\s+team)?|"
    r"(?:the\s+)?(?:local\s+)?forever\s+(?:business\s+)?office)\b",
    re.IGNORECASE,
)


def _support_contact_response_is_ineligible(chat_response: ChatResponse) -> bool:
    """A refusal/fallback/guardrail answer never gets a support-contact block."""
    metadata = chat_response.metadata or {}
    return bool(
        metadata.get("fallback")
        or metadata.get("failure_layer")
        or metadata.get("response_source") in {"guardrail", "fallback", "client_action"}
    )


def _support_contact_segments(value: str) -> list[str]:
    """Split a directory ``record_country`` (or a market name) into lower-cased
    word segments on both "/" and whitespace - "Kenya/East Africa" ->
    ["kenya", "east", "africa"]."""
    return [part.casefold() for part in re.split(r"[/\s]+", value.strip()) if part]


def _resolve_support_contact_target_names(lookup_text: str, country: str) -> list[str]:
    """Return the market name(s) actually named in ``lookup_text`` plus the
    ``record_country`` of a configured shared office serving a named country
    that has no market entry of its own, else the session market's own name.
    Never guesses a market from nothing."""
    mentioned = [name for name in (market_display_name(code) for code in find_market_mentions(lookup_text)) if name]
    mentioned.extend(sorted(find_shared_office_record_countries(lookup_text)))
    if mentioned:
        return mentioned
    session_name = market_display_name(country)
    return [session_name] if session_name else []


def _resolve_directory_field_target_names(lookup_text: str, country: str) -> list[str]:
    """Resolve sponsoring-record aliases without widening support handoffs."""
    explicit_aliases = sorted(find_sponsoring_directory_alias_countries(lookup_text))
    explicit_targets = _resolve_support_contact_target_names(lookup_text, "")
    if explicit_aliases or explicit_targets:
        return list(dict.fromkeys([*explicit_aliases, *explicit_targets]))
    session_name = market_display_name(country)
    session_aliases = sorted(find_sponsoring_directory_alias_countries(session_name or ""))
    return session_aliases or ([session_name] if session_name else [])


def _directory_record_matches_a_target(record_country: str, target_names: list[str]) -> bool:
    """True only for a whole-segment/word match - never a region word (``East
    Africa``, ``Benelux``) or a country named only inside a record's body."""
    tokens = _support_contact_segments(record_country)
    for name in target_names:
        name_words = _support_contact_segments(name)
        width = len(name_words)
        if not width or width > len(tokens):
            continue
        if any(tokens[start:start + width] == name_words for start in range(len(tokens) - width + 1)):
            return True
    return False


def _find_matching_support_contact_record(documents: list, target_names: list[str]):
    """Return the single GLOBAL directory record matching ``target_names``, or
    ``None`` when there is no match or more than one different record matches
    - this never falls back to "the first directory record"."""
    matched: dict[str, Any] = {}
    for document in documents:
        if document.country != "GLOBAL":
            continue
        if not (
            document.metadata.get("directory_kind")
            or document.metadata.get("directory_section")
            or isinstance(document.metadata.get("directory_fields"), dict)
        ):
            continue
        record_country = str(document.metadata.get("record_country") or "").strip()
        if record_country and _directory_record_matches_a_target(record_country, target_names):
            matched[document.id or document.content] = document
    if len(matched) != 1:
        return None
    return next(iter(matched.values()))


def _support_contact_approved_fields(document: Any) -> dict[str, object]:
    """Return the record's approved field map - never invented, always the
    same fields already surfaced by the retrieval/directory pipeline."""
    directory_fields_value = document.metadata.get("directory_fields")
    if isinstance(directory_fields_value, dict):
        return directory_fields_value
    return parse_directory_fields(document.content)


def _directory_field_sets_for_response(
    documents: list,
    lookup_text: str,
    country: str,
) -> list[dict[str, object]]:
    """Return fields from the one directory record allowed to repair an answer.

    Retrieval can retain neighbouring records as supporting evidence.  They
    must never become an answer trailer or a source for post-generation field
    repair.  Prefer the uniquely matching country record; when the request
    cannot resolve a country, permit repair only if retrieval itself contains
    one directory record.  Ambiguity deliberately produces no repair.
    """
    matched_documents = _directory_documents_for_response(documents, lookup_text, country)
    if len(matched_documents) != 1:
        return []
    return [_support_contact_approved_fields(matched_documents[0])]


def _directory_documents_for_response(
    documents: list,
    lookup_text: str,
    country: str,
) -> list[Any]:
    """Return only directory records matching the request's resolved market."""
    candidates: list[Any] = []
    for document in documents:
        if document.country != "GLOBAL":
            continue
        if not (
            document.metadata.get("directory_kind")
            or document.metadata.get("directory_section")
            or isinstance(document.metadata.get("directory_fields"), dict)
        ):
            continue
        fields = _support_contact_approved_fields(document)
        if fields:
            candidates.append(document)

    target_names = _resolve_directory_field_target_names(lookup_text, country)
    matched = [
        document
        for document in candidates
        if _directory_record_matches_a_target(str(document.metadata.get("record_country") or ""), target_names)
    ]
    if matched:
        return matched
    if len(candidates) == 1:
        return candidates
    return []


def _support_contact_already_quoted(answer: str, approved_fields: dict[str, object], added_labels: list[str]) -> bool:
    """True when the answer already quotes a phone or email value the
    supplement would add - never duplicate an already-delivered contact."""
    answer_digits = re.sub(r"\D", "", answer)
    answer_lower = answer.casefold()
    for label in added_labels:
        label_lower = label.casefold()
        if "phone" not in label_lower and "email" not in label_lower:
            continue
        value = str(approved_fields.get(label, "")).strip()
        value_digits = re.sub(r"\D", "", value)
        if value_digits and len(value_digits) >= 7 and value_digits in answer_digits:
            return True
        if value and value.casefold() in answer_lower:
            return True
    return False


# Marks a citation that was added ONLY to back the appended support-contact
# block, not any claim the answer itself makes. camelCase like the other keys
# RetrievedDocument.to_source() emits ("documentVersion", "sectionTitle"), and
# named after the "support_contact_supplemented" response-metadata key so the
# block, its metadata and its citation read as one feature. Citations stay a
# flat list of dicts - this is a field on a source, not a new collection - so
# every existing caller that iterates them keeps working unchanged.
SUPPORT_CONTACT_SUPPLEMENT_CITATION_FIELD = "supportContactSupplement"


def _add_citation_if_absent(citations: list, source: dict) -> list:
    """Append ``source`` only when no existing citation already carries its URI."""
    if any(existing.get("uri") == source.get("uri") for existing in citations):
        return list(citations)
    return [*citations, source]


DIRECTORY_DETAIL_TERMS = re.compile(
    r"\b(address|office|business\s+hours?|office\s+hours?|telephone|phone|email|website|contact|sponsor)\b",
    re.IGNORECASE,
)
# Maps a directory clarification card's id to the wording that names that
# specific field unambiguously. "office"/"contact" are deliberately absent -
# both are too generic to pin down a single field on their own, so a message
# containing only those still counts as ambiguous. Used to detect when the
# user already named exactly one field, so _directory_clarification_response
# doesn't ask them to choose again from a card that duplicates what they
# already said (TRB-19189-follow-up, reported after deploy).
DIRECTORY_FIELD_TERMS: dict[str, re.Pattern[str]] = {
    # "number" alone is ambiguous - an FBO number and an order number are both
    # numbers - so it counts only when qualified by a word meaning a line you
    # call. Without this, "what is the customer care number for the UK office?"
    # named no field at all, and the reader who had just said which detail they
    # wanted was asked to choose it from a list of seven.
    "directory-telephone": re.compile(
        r"\b(telephone|phone)\b|\b(?:customer\s+care|contact|helpline|support|care)\s+numbers?\b",
        re.IGNORECASE,
    ),
    "directory-hours": re.compile(r"\b(business\s+hours?|office\s+hours?|hours)\b", re.IGNORECASE),
    "directory-email": re.compile(r"\bemail\b", re.IGNORECASE),
    # Excludes "address" inside "email address" (e.g. "what's the email
    # address for the UK office?") - without this, that phrase matches both
    # directory-email and directory-address, so len(named_fields) != 1 and
    # the field is (wrongly) never treated as already specified, producing
    # an unresolvable loop: the generic "which detail?" clarification fires
    # again even after the user names or clicks "Email address".
    "directory-address": re.compile(r"(?<!email\s)\baddress\b", re.IGNORECASE),
    "directory-website": re.compile(r"\bwebsite\b", re.IGNORECASE),
    "directory-sponsoring": re.compile(r"\bsponsor\w*\b", re.IGNORECASE),
}
# Deliberately directory-shaped so the retrieval planner's existing global-
# directory intent classification picks it up; carries no country name so it
# falls back to the request's own selected country.
OFFICE_CONTACT_LOOKUP_QUERY = "What is the office phone number, email address, and website for this country?"
OFFICE_CONTACT_FIELD_RE = re.compile(r"phone|telephone|email|e-mail", re.IGNORECASE)


CROSS_MARKET_POLICY_SCOPE_RESPONSE = (
    "Local company policy for another market is only available to readers in "
    "that market, so I'm not able to share it here. I can help with the "
    "policies that apply to your own market, and Forever Living support or "
    "your upline can point you to the right contact for the other market."
)


# Diagnostic capture for offline evaluation (scripts/run_benchmark.py).
#
# Off by default, and nothing in the API turns it on. While it is off none of
# the capture code runs and response metadata is exactly what it was. The
# benchmark enables it in its own process so each turn's response carries a
# "diagnostic_capture" record: what retrieval returned, what the output
# validator found, the answer handed to numeric repair, and what repair
# removed and why. A single-run comparison could not tell generation variance
# from a repair removal, because none of that was recorded.
#
# Recording only. It never changes an answer, a citation or a repair decision,
# and the key is in neither ChatResponse's public API metadata nor its cache
# value.
DIAGNOSTIC_CAPTURE_ENABLED = False
DIAGNOSTIC_CAPTURE_VERSION = 1
_DIAGNOSTIC_CAPTURE: ContextVar[dict[str, Any] | None] = ContextVar("askvera_diagnostic_capture", default=None)
_CAPTURED_DOCUMENT_METADATA = (
    "section_id", "parent_section_id", "access_scope", "document_type", "parent_bound_child",
    "ingestion_id", "logical_document_id", "content_hash",
)
_CAPTURED_RETRIEVAL_METADATA = (
    "provider", "candidate_count", "evidence_selector_applied", "evidence_selector_confidence",
    "evidence_selector_rejected", "top_source_directly_answers", "parent_bound_children",
    "conversation_intent", "conversation_subtype", "intent_confidence", "client_action",
    "global_documents_searched", "strong_local_match", "explicit_section_reference",
    "generation_lookup",
    "retrieval_rank_lists", "candidate_section_ids", "evidence_selector_candidate_section_ids",
    "evidence_selector_selected_ranks",
)


def _captured_issues(result: ValidationResult) -> list[dict[str, object]]:
    return [
        {"code": issue.code, "severity": issue.severity.value, "field": issue.field, "message": issue.message[:500]}
        for issue in result.issues
    ]


def _record_capture_failure(capture: dict[str, Any], stage: str) -> None:
    """Log a failed recording and note it in the capture; the response goes on unchanged."""
    LOGGER.exception("diagnostic_capture_failed", stage=stage)
    capture.setdefault("errors", []).append(stage)


def _record_diagnostic_retrieval(stage: str, retrieval_result: RetrievalResult | None) -> None:
    """Append one retrieval to the current turn's capture, when capture is on.

    Never raises: a recording failure is logged and noted, never delivered.
    """
    capture = _DIAGNOSTIC_CAPTURE.get()
    if capture is None or retrieval_result is None:
        return
    try:
        _append_diagnostic_retrieval(capture, stage, retrieval_result)
    except Exception:  # noqa: BLE001 - diagnostic recording must never break a response
        _record_capture_failure(capture, stage)


def _append_diagnostic_retrieval(capture: dict[str, Any], stage: str, retrieval_result: RetrievalResult) -> None:
    metadata = retrieval_result.metadata or {}
    sources = metadata.get("candidate_sources")
    capture["retrievals"].append({
        "stage": stage,
        "confidence": retrieval_result.confidence,
        "documents": [
            {
                "id": document.id,
                "source": document.source,
                "country": document.country,
                "language": document.language,
                "score": document.score,
                **{key: document.metadata[key] for key in _CAPTURED_DOCUMENT_METADATA if key in document.metadata},
            }
            for document in retrieval_result.documents
        ],
        "metadata": {key: metadata[key] for key in _CAPTURED_RETRIEVAL_METADATA if key in metadata},
        # The selector's candidates as the provider reports them. "section" is
        # parent_section_id when there is one, so a child candidate cannot be
        # told apart from its parent here. None means no list was exposed.
        "candidate_sections": [
            {key: source.get(key) for key in ("section", "country", "uri", "score")}
            for source in sources
            if isinstance(source, dict)
        ] if isinstance(sources, list) else None,
    })


def _record_diagnostic_validation(
    chat_response: ChatResponse,
    result: ValidationResult,
    outcome: str,
    numeric_repair: dict[str, Any] | None = None,
) -> None:
    """Append one output validation, and any numeric repair it attempted, when capture is on.

    Never raises: removal_diagnostics re-runs claim extraction, and a failure
    there or anywhere in recording is logged and noted, never delivered.
    """
    capture = _DIAGNOSTIC_CAPTURE.get()
    if capture is None:
        return
    try:
        _append_diagnostic_validation(capture, chat_response, result, outcome, numeric_repair)
    except Exception:  # noqa: BLE001 - diagnostic recording must never break a response
        _record_capture_failure(capture, f"validation:{outcome}")


def _append_diagnostic_validation(
    capture: dict[str, Any],
    chat_response: ChatResponse,
    result: ValidationResult,
    outcome: str,
    numeric_repair: dict[str, Any] | None,
) -> None:
    repair_record = None
    if numeric_repair is not None:
        repaired_result = numeric_repair.get("result")
        repair_record = {
            "removed_numeric_claims": list(numeric_repair["removed"]),
            # Each figure the validator could not ground, and whether the
            # evidence contains it at all: absent means the model invented it,
            # present means a real figure that subject matching rejected.
            "removal_reasons": [
                {**diagnostic, "reason": "unsupported_numeric_claim"}
                for diagnostic in removal_diagnostics(chat_response.answer or "", numeric_repair["documents"])
            ],
            "answer_after_repair": numeric_repair["answer"],
            "post_repair_issues": _captured_issues(repaired_result) if repaired_result is not None else None,
            "accepted": outcome == "numeric_repair_accepted",
        }
    capture["validations"].append({
        "answer_before_validation": chat_response.answer,
        "issues": _captured_issues(result),
        "critical": result.has_critical(),
        "outcome": outcome,
        "numeric_repair": repair_record,
    })


def _record_diagnostic_raw_answer(text: str) -> None:
    """Keep the model's own answer, before any editor touches it, when capture is on.

    pre_repair_answer is taken after citation separation, directory
    restoration, PII scrubbing and placeholder clean-up, so a sentence one of
    those removed was indistinguishable from one the model never wrote.
    Never raises, and never changes what is delivered.
    """
    capture = _DIAGNOSTIC_CAPTURE.get()
    if capture is None:
        return
    try:
        capture.setdefault("raw_model_answers", []).append(str(text or ""))
    except Exception:  # noqa: BLE001 - diagnostic recording must never break a response
        _record_capture_failure(capture, "raw_model_answer")


@lru_cache(maxsize=1)
def _load_public_market_place_names() -> tuple[str, ...]:
    names: set[str] = set()
    aliases = _localized_market_names()
    for market in [*load_market_config().get("markets", []), *load_global_directory_markets()]:
        code = str(market.get("code") or "").upper()
        names.add(str(market.get("name") or "").strip())
        names.update(str(alias).strip() for alias in aliases.get(code, []))
    return tuple(sorted(name for name in names if name))


def _public_market_place_names() -> tuple[str, ...]:
    """Configured market names in every configured language.

    A generated answer names the user's market ("here in Canada") and, for
    international sponsoring, the destination market. Comprehend labels those
    bare names ADDRESS, and the masked token then made the placeholder
    clean-up delete the whole line, policy figure included. A missing or
    malformed config degrades to the previous behaviour (nothing preserved)
    and is not cached, so a later request retries it.
    """
    try:
        return _load_public_market_place_names()
    except Exception:  # noqa: BLE001 - config trouble must not break PII scrubbing
        LOGGER.exception("public_market_place_names_unavailable")
        return ()


class ConsentRequiredError(Exception):
    """Raised when a chat request has not accepted the current legal terms."""


# Metadata flags recorded by the answer-editing steps in
# _secure_and_complete_response. Kept in one list so the diagnostic log stays
# complete when a step is added: a new editor that records a flag missing from
# here is invisible exactly when something goes wrong.
_ANSWER_EDIT_FLAGS = (
    "inline_citations_separated",
    "directory_contacts_restored",
    "directory_role_label_corrected",
    "unrequested_directory_fields_removed",
    "directory_order_size_restored",
    "directory_order_size_canonicalized",
    "directory_source_contradiction_corrected",
    "directory_contact_fields_repaired",
    "directory_source_conflict_detected",
    "response_pii_scrubbed",
    "contact_placeholder_actions",
    "unresolved_pii_placeholders_removed",
    "empty_after_output_cleanup",
)


class AIOrchestrator:
    """Coordinate the existing ASK Vera chat request lifecycle."""

    def __init__(
        self,
        prompt_builder: PromptBuilder | None = None,
        retriever: RetrievalService | None = None,
        router: ModelRouter | None = None,
        builder: ResponseBuilder | None = None,
        validator: OutputValidator | None = None,
        governance: GovernanceEngine | None = None,
    ) -> None:
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retriever = retriever or retrieval_service
        self.model_router = router or model_router
        self.response_builder = builder or response_builder
        self.output_validator = validator or output_validator
        self.governance_engine = governance or governance_engine

    def handle_chat(self, body: ChatRequest, correlation_id: str) -> ChatResponse:
        """Run the existing chat flow and return response data."""
        if not DIAGNOSTIC_CAPTURE_ENABLED:
            return self._handle_chat(body, correlation_id)
        from app.retrieval.opensearch_sections import disable_rank_list_capture, enable_rank_list_capture

        token = _DIAGNOSTIC_CAPTURE.set(
            {"version": DIAGNOSTIC_CAPTURE_VERSION, "retrievals": [], "validations": [], "errors": []}
        )
        rank_list_token = enable_rank_list_capture()
        try:
            response = self._handle_chat(body, correlation_id)
            capture = _DIAGNOSTIC_CAPTURE.get()
        finally:
            disable_rank_list_capture(rank_list_token)
            _DIAGNOSTIC_CAPTURE.reset(token)
        # Attached after the turn was persisted and counted, with the same
        # answer and citations: recording must not change what was delivered.
        return self._replace_answer(response, response.answer, {"diagnostic_capture": capture})

    def _handle_chat(self, body: ChatRequest, correlation_id: str) -> ChatResponse:
        """The chat flow itself; handle_chat adds optional diagnostic capture around it."""
        LOGGER.info(
            "ai_orchestrator_request_started",
            correlation_id=correlation_id,
            country=body.country,
            language=body.language,
            role=body.role,
            session_id=body.sessionId,
        )
        if validate_and_touch_session(body.sessionId, correlation_id) is False:
            raise SessionExpiredError()
        if not has_valid_consent(body.sessionId, correlation_id):
            raise ConsentRequiredError()

        # Admin-portal "current vs experimental" toggle (services/candidate_control.py) -
        # read once per request and threaded down explicitly, rather than each
        # hook point calling get_candidate_flags() itself, so every function
        # below stays a pure, DB-free call when exercised directly (as most
        # unit tests do) and only this one entry point pays the lookup cost.
        candidate_flags = get_candidate_flags()
        scrubbed_input = scrub_pii(
            body.message,
            correlation_id,
            body.language,
            preserve_location_names=True,
            preserve_person_names=True,
        )
        response = self._mixed_request_response(body, scrubbed_input, correlation_id, candidate_flags)
        if response is None:
            response = self._handle_scrubbed_chat(body, scrubbed_input, correlation_id, candidate_flags)
        # Persist the original request and the actual delivered response exactly
        # once, including refusals, cache hits and partial mixed-intent answers.
        append_session_turn(body.sessionId, scrubbed_input, response.answer, correlation_id)
        # Counted at the same single choke point, and for the same reason: this
        # is the one place every return path has converged, so the fallback rate
        # measures what was actually delivered rather than what one branch
        # intended. Sessions that raise above (expired, consent) are not
        # deliveries and are correctly absent.
        record_delivered_response(response.metadata)
        return response

    def _mixed_request_response(
        self, body: ChatRequest, scrubbed_input: str, correlation_id: str, candidate_flags: CandidateFlags,
    ) -> ChatResponse | None:
        parts = separate_question_and_command(scrubbed_input)
        if parts is None:
            return None
        question, command = parts
        question_decision = self._evaluate_governance(question, body, correlation_id)
        command_decision = self._evaluate_governance(command, body, correlation_id)
        metadata = command_decision.metadata or {}
        issue_codes = {str(issue.get("code", "")) for issue in metadata.get("risk", {}).get("issues", [])}
        explicit_refusal = metadata.get("topic") in {"income_claim", "medical_claim", "off_topic"} or bool(
            issue_codes & {"INCOME_CLAIM_RISK", "MEDICAL_CLAIM_RISK"})
        if (not question_decision.allowed or command_decision.allowed or not explicit_refusal
                or metadata.get("providerError")):
            return None
        # Preserve every scope/session field. The unsafe command never enters
        # retrieval, the model prompt, or the safe-question cache key.
        safe_body = body.model_copy(update={"message": question})
        response = self._handle_scrubbed_chat(safe_body, question, correlation_id, candidate_flags)
        decline = self._governance_user_message(
            command_decision, body.language, body.country, command, correlation_id,
        )
        return self._replace_answer(response, f"{response.answer}\n\n{decline}", {
            "mixed_intent": True, "refused_part_count": 1,
        })

    def _handle_scrubbed_chat(
        self, body: ChatRequest, scrubbed_input: str, correlation_id: str, candidate_flags: CandidateFlags,
    ) -> ChatResponse:
        """Run the normal checked pipeline; the entry point owns turn persistence."""
        chat_response = self._early_conversation_response(
            scrubbed_input, body, correlation_id, candidate_flags
        )
        if chat_response:
            return chat_response
        history = get_session_history(body.sessionId, correlation_id)
        retrieval_query = self._build_retrieval_query(scrubbed_input, history, correlation_id)
        request_query = self._build_request_query(scrubbed_input, retrieval_query, history)
        governance_decision = self._evaluate_governance(
            self._governance_text(scrubbed_input, request_query), body, correlation_id
        )
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message, candidate_flags
            )

        cache_key = build_cache_key(request_query, body.country, body.language, body.role)
        cached_response = self._cached_response(
            cache_key, body, correlation_id, scrubbed_input, resolved_request=request_query
        )
        if cached_response:
            return cached_response

        try:
            retrieval_result = self.retriever.retrieve(
                retrieval_query, body.country, body.language, body.role, correlation_id
            )
        except (BotoCoreError, ClientError, ConnectionError, TimeoutError, OSError) as exc:
            # C5 (conversation-quality task board): this call was previously
            # unguarded, so a retrieval-backend outage (timeout, connection
            # refused, auth/signing failure) raised straight out of
            # handle_chat with no ChatResponse at all - not even the wrong
            # wording, no wording, and no session-turn persistence, since the
            # exception propagated before append_session_turn ever runs.
            # A dependency being unreachable is not the same situation as the
            # documents genuinely lacking the answer (failure_layer
            # "evidence_gate"/"low_confidence"), so it gets its own
            # "dependency_unavailable" layer and the reviewed "bedrock_error"
            # copy - honest about a technical problem, not a confident denial
            # that the information isn't available.
            LOGGER.exception("retrieval_dependency_unavailable", correlation_id=correlation_id)
            return self._validate_response(
                self.response_builder.fallback(
                    localized_conversation_response("bedrock_error", body.language)
                    or FALLBACK_RESPONSES["bedrock_error"],
                    correlation_id,
                    metadata={"failure_layer": "dependency_unavailable"},
                ),
                body,
                correlation_id,
            )
        _record_diagnostic_retrieval("question", retrieval_result)
        chat_response, retrieval_result, evidence_decision = self._route_or_approve_evidence(
            retrieval_query,
            retrieval_result,
            scrubbed_input,
            body,
            correlation_id,
            candidate_flags,
            history,
        )
        if chat_response:
            return chat_response
        assert evidence_decision is not None
        cached_response, semantic_candidate, semantic_lookup_ms = self._semantic_cached_response(
            request_query, retrieval_result, body, correlation_id, scrubbed_input
        )
        if cached_response:
            return cached_response
        prompt_package = self.prompt_builder.build(
            user_question=scrubbed_input,
            conversation=history,
            country=body.country,
            language=body.language,
            role=body.role,
            retrieval_result=retrieval_result,
            metadata={"correlation_id": correlation_id},
        )
        try:
            model_response = self.model_router.generate(prompt_package, retrieval_result, correlation_id)
        except LowConfidenceError as exc:
            failure_layer = self._low_confidence_failure_layer(exc)
            if candidate_flags.narrowing_fallback:
                narrowing_response = self._candidate_narrowing_response(body, correlation_id, history)
                if narrowing_response:
                    return self._validate_response(
                        narrowing_response,
                        body,
                        correlation_id,
                        retrieval_result=retrieval_result,
                    )
            return self._validate_response(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language, body.message, body.country),
                    correlation_id,
                    metadata={"failure_layer": failure_layer},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )
        except (BedrockTimeoutError, BedrockServiceError):
            # Deliberately narrow. generate() can also raise ConfigurationError,
            # which is a deploy defect rather than a transient outage: telling
            # the user "try again in a moment" would be false and would hide
            # the defect, so it still propagates to the route's error envelope.
            # GuardrailBlockedError must never be relabelled as a technical
            # hiccup either, which a broad AskVeraError catch would have done.
            #
            # C5: model_router.generate can also fail with a dependency error
            # that is NOT a LowConfidenceError (e.g. BedrockTimeoutError,
            # BedrockServiceError - raised when Bedrock itself times out or
            # errors, not when the model simply lacked evidence). Previously
            # this propagated straight out of handle_chat, past every
            # ChatResponse-producing path, and was only ever caught (if at
            # all) by api/routes.py's `except AskVeraError` - which returns a
            # completely different response SHAPE (a `success: false` error
            # envelope with an HTTP error status) instead of an ordinary chat
            # answer. That means it never ran through response_builder or
            # output validation, was never persisted to session history
            # (append_session_turn runs after this call, in _handle_chat),
            # and never carried a metadata.failure_layer at all - so a caller
            # that only inspects failure_layer (or a Lane G regression case
            # expecting a normal chat turn) sees nothing. Route it through
            # the same fallback path used for every other failure kind
            # instead, with its own distinct layer name.
            LOGGER.exception("model_dependency_unavailable", correlation_id=correlation_id)
            return self._validate_response(
                self.response_builder.fallback(
                    localized_conversation_response("bedrock_error", body.language)
                    or FALLBACK_RESPONSES["bedrock_error"],
                    correlation_id,
                    metadata={"failure_layer": "dependency_unavailable"},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )
        _record_diagnostic_raw_answer(model_response.text)

        if model_response.finish_reason == "guardrail_intervened":
            return self.response_builder.fallback(
                localized_conversation_response("guardrail_blocked", body.language)
                or (
                    "I couldn't provide that response because it did not pass AskVera's safety checks. "
                    "Please rephrase the question without private information or unsafe claims."
                ),
                correlation_id,
                metadata={
                    "failure_layer": "aws_guardrail",
                    "response_source": "guardrail",
                },
            )

        contracted_response = self._apply_evidence_contract(model_response, retrieval_result, correlation_id)
        if contracted_response is None:
            return self._validate_response(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language, body.message, body.country),
                    correlation_id,
                    metadata={"failure_layer": "evidence_contract"},
                ),
                body,
                correlation_id,
                retrieval_result=retrieval_result,
            )
        model_response, retrieval_result = contracted_response

        chat_response = self.response_builder.build(
            model_response=model_response,
            retrieval_result=retrieval_result,
            correlation_id=correlation_id,
            session_metadata={
                "session_id": body.sessionId,
                "country": body.country,
                "language": body.language,
                "role": body.role,
                "cache": "miss",
                "evidence_decision": evidence_decision.to_metadata(),
            },
        )
        chat_response = self._secure_and_complete_response(
            chat_response,
            retrieval_result,
            body.language,
            correlation_id,
            user_question=body.message,
            country=body.country,
            resolved_request=request_query,
        )
        chat_response = self._validate_response(
            chat_response,
            body,
            correlation_id,
            model_response=model_response,
            retrieval_result=retrieval_result,
        )
        governance_decision = self._evaluate_governance(
            chat_response.answer,
            body,
            correlation_id,
            allow_claim_topics=self._answer_explains_reviewed_policy(body, chat_response),
            is_generated_answer=True,
        )
        if not governance_decision.allowed:
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message, candidate_flags
            )
        self._record_semantic_shadow_result(
            semantic_candidate,
            chat_response,
            body,
            correlation_id,
            semantic_lookup_ms,
        )
        write_audit_event(
            {
                "type": "chat",
                "country": body.country,
                "language": body.language,
                "confidence": chat_response.confidence,
                "validation": chat_response.metadata.get("validation"),
                "failure_layer": chat_response.metadata.get("failure_layer"),
                "finish_reason": chat_response.metadata.get("finish_reason"),
            },
            correlation_id,
        )
        self._cache_response(
            cache_key,
            request_query,
            retrieval_result,
            chat_response,
            body,
            correlation_id,
        )
        return chat_response

    def _secure_and_complete_response(
        self,
        chat_response: ChatResponse,
        retrieval_result: RetrievalResult,
        language: str,
        correlation_id: str,
        *,
        user_question: str,
        country: str = "",
        resolved_request: str = "",
    ) -> ChatResponse:
        """Restore approved directory fields, then enforce outbound PII safety."""
        citation_cleaned = separate_verified_citations(chat_response.answer, retrieval_result.documents)
        if citation_cleaned != chat_response.answer:
            chat_response = self._replace_answer(chat_response, citation_cleaned, {"inline_citations_separated": True})
        chat_response, matched_directory_documents = self._repair_directory_fields(
            chat_response,
            retrieval_result,
            language,
            user_question,
            country,
            resolved_request,
        )

        role_safe_answer, role_label_corrected = preserve_directory_role_labels(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
        )
        if role_label_corrected:
            chat_response = self._replace_answer(
                chat_response,
                role_safe_answer,
                {"directory_role_label_corrected": True},
            )

        focused_answer, extra_fields_removed = remove_unrequested_directory_fields(
            chat_response.answer,
            user_question,
        )
        if extra_fields_removed:
            chat_response = self._replace_answer(
                chat_response,
                focused_answer,
                {"unrequested_directory_fields_removed": True},
            )

        has_fbo_order_field = any(
            bool(
                (
                    document.metadata.get("directory_fields")
                    if isinstance(document.metadata.get("directory_fields"), dict)
                    else parse_directory_fields(document.content)
                    if document.metadata.get("directory_kind") or document.metadata.get("directory_section")
                    else {}
                ).get("Minimum order size FBO")
            )
            for document in retrieval_result.documents
        )
        order_safe_answer, order_restored = restore_missing_requested_order_size(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
            user_question,
            suppress_restore=has_fbo_order_field and fbo_enrollment_is_unavailable(country),
        )
        # A restoration that leaves the answer structurally incomplete is worse
        # than the omission it fixes: the output validator discards the whole
        # answer and the reader is told the approved documents do not cover
        # their question. That is what happened to the Algeria minimum-order
        # answer, where retrieval was correct and the model's reply was fine
        # until this step appended a fragment to it.
        #
        # The check is the validator's own, so this step cannot drift back into
        # producing answers the validator will throw away.
        if order_restored and has_incomplete_ending(order_safe_answer, language):
            # Whether the answer already carries the figure. Skipping keeps the
            # answer well formed, which is not the same as keeping it complete:
            # if the model never stated the minimum order, refusing to restore
            # it leaves the reader without the fact they asked for. Recorded so
            # that case is visible rather than assumed not to happen.
            restored_only = order_safe_answer[len(chat_response.answer.strip()):]
            LOGGER.warning(
                "directory_order_size_restore_skipped",
                correlation_id=correlation_id,
                reason="restored_answer_would_be_incomplete",
                answer_already_states_a_minimum_order=bool(
                    re.search(r"minimum\s+(?:first\s+)?order", chat_response.answer or "", re.IGNORECASE)
                ),
                skipped_addition_chars=len(restored_only.strip()),
            )
            order_restored = False
        if order_restored:
            chat_response = self._replace_answer(
                chat_response,
                order_safe_answer,
                {"directory_order_size_restored": True},
            )

        canonical_order_answer = (
            None if fbo_enrollment_is_unavailable(country)
            else canonical_requested_order_size(
                (document.content for document in retrieval_result.documents),
                user_question,
                language=language,
            )
        )
        if canonical_order_answer and canonical_order_answer != chat_response.answer:
            chat_response = self._replace_answer(
                chat_response,
                canonical_order_answer,
                {"directory_order_size_canonicalized": True},
            )

        source_safe_answer, source_contradiction_corrected = correct_directory_source_contradictions(
            chat_response.answer,
            (document.content for document in retrieval_result.documents),
        )
        if source_contradiction_corrected:
            chat_response = self._replace_answer(
                chat_response,
                source_safe_answer,
                {"directory_source_contradiction_corrected": True},
            )

        chat_response = self._apply_directory_source_conflict_gate(
            chat_response,
            matched_directory_documents,
            user_question,
            language,
        )

        chat_response = self._apply_support_contact_supplement(
            chat_response,
            retrieval_result,
            resolved_request,
            user_question,
            country,
            language,
        )

        safe_answer = scrub_pii(
            chat_response.answer,
            correlation_id,
            language,
            allowed_texts=[
                *settings.PII_APPROVED_PUBLIC_TERMS,
                *contact_for_country(country).values(),
                *(document.content for document in retrieval_result.documents),
            ],
            allowed_name_texts=[user_question],
            allowed_location_texts=_public_market_place_names(),
        )
        if safe_answer != chat_response.answer:
            chat_response = self._replace_answer(chat_response, safe_answer, {"response_pii_scrubbed": True})

        contact_safe_answer, contact_changes = remove_or_replace_contact_placeholders(
            chat_response.answer,
            country,
        )
        if contact_changes:
            chat_response = self._replace_answer(
                chat_response,
                contact_safe_answer,
                {"contact_placeholder_actions": contact_changes},
            )

        cleaned_answer = remove_unresolved_pii_placeholders(chat_response.answer)
        if cleaned_answer != chat_response.answer:
            chat_response = self._replace_answer(
                chat_response,
                cleaned_answer,
                {"unresolved_pii_placeholders_removed": True},
            )
        if not chat_response.answer.strip():
            refusal = self._replace_answer(
                chat_response,
                self._insufficient_evidence_message(language, user_question, country),
                {"empty_after_output_cleanup": True, "fallback": True},
            )
            # The refusal states no policy fact, so it cites no source. Keeping
            # the citations built for the emptied answer presented a policy
            # passage as the source of "the documents do not contain enough
            # information".
            chat_response = ChatResponse(
                answer=refusal.answer,
                citations=[],
                suggestions=refusal.suggestions,
                cards=refusal.cards,
                confidence=refusal.confidence,
                metadata=refusal.metadata,
                correlation_id=refusal.correlation_id,
            )
        return chat_response

    def _repair_directory_fields(
        self,
        chat_response: ChatResponse,
        retrieval_result: RetrievalResult,
        language: str,
        user_question: str,
        country: str,
        resolved_request: str,
    ) -> tuple[ChatResponse, list[Any]]:
        """Repair requested fields using only the uniquely resolved record."""
        if not chat_response.citations:
            return chat_response, []

        lookup_text = resolved_request or user_question
        matched_documents = _directory_documents_for_response(
            retrieval_result.documents,
            lookup_text,
            country,
        )
        field_sets = _directory_field_sets_for_response(
            retrieval_result.documents,
            lookup_text,
            country,
        )
        completed_answer = chat_response.answer
        if len(field_sets) == 1:
            completed_answer, contacts_repaired = repair_labeled_directory_contacts(
                completed_answer,
                field_sets[0],
            )
            if contacts_repaired:
                chat_response = self._replace_answer(
                    chat_response,
                    completed_answer,
                    {"directory_contact_fields_repaired": True},
                )

        completed_answer, requested_fields = restore_missing_requested_directory_fields(
            completed_answer,
            field_sets,
            user_question,
        )
        completed_answer, contact_fields = restore_missing_directory_contacts(
            completed_answer,
            field_sets,
            user_question,
            language=language,
        )
        restored_fields = [*requested_fields, *contact_fields]
        if restored_fields:
            chat_response = self._replace_answer(
                chat_response,
                completed_answer,
                {"directory_contacts_restored": restored_fields},
            )
        return chat_response, matched_documents

    def _apply_directory_source_conflict_gate(
        self,
        chat_response: ChatResponse,
        matched_documents: list[Any],
        user_question: str,
        language: str,
    ) -> ChatResponse:
        """Prevent one duplicate directory value being presented as definitive."""
        conflict_field_sets = [
            _support_contact_approved_fields(document)
            for document in matched_documents
        ]
        source_conflicts = directory_field_conflicts(conflict_field_sets, user_question)
        if not source_conflicts:
            return chat_response

        answer_folded = " ".join((chat_response.answer or "").casefold().split())
        missing_values = [
            value
            for values in source_conflicts.values()
            for value in values
            if " ".join(value.casefold().split()) not in answer_folded
        ]
        if not missing_values:
            return self._replace_answer(
                chat_response,
                chat_response.answer,
                {"directory_source_conflict_detected": sorted(source_conflicts)},
            )

        conflict_fallback = localized_conversation_response("insufficient_evidence", language) or (
            "I found conflicting approved information and cannot give one value as definitive."
        )
        return self._replace_answer(
            chat_response,
            conflict_fallback,
            {
                "directory_source_conflict_detected": sorted(source_conflicts),
                "fallback": True,
                "failure_layer": "directory_source_conflict",
            },
        )

    def _apply_support_contact_supplement(
        self,
        chat_response: ChatResponse,
        retrieval_result: RetrievalResult,
        resolved_request: str,
        user_question: str,
        country: str,
        language: str = "en",
    ) -> ChatResponse:
        """Append an approved support-contact block when the answer recommends care.

        Only ever echoes fields already present on exactly one GLOBAL
        directory record whose ``record_country`` matches a market actually
        named in the resolved request (or the session market, when the
        request names none). Never falls back to "first directory record",
        never fires for a refusal/fallback/guardrail answer, and never
        duplicates a phone or email already quoted in the answer.

        ``language`` is the request language ``_secure_and_complete_response``
        already resolved for this turn - the same value the rest of that
        method's steps use. It selects the block's field LABELS from the
        reviewed table in :mod:`utils.directory_fields`; it never translates,
        adds or alters a field VALUE, and any language without a reviewed
        table (including "en") keeps the record's own English labels.

        The block is separated from the answer by a blank line, and the
        record's citation - when the supplement is what introduced it - is
        marked ``supportContactSupplement`` so a reader can tell a source
        cited only for an appended contact detail from one that backs a claim
        the answer actually makes. The marker is camelCase to match the other
        source keys (``documentVersion``, ``sectionTitle``) and named after
        the existing ``support_contact_supplemented`` metadata key. A record
        the answer *already* cites backs the answer too, so that citation is
        deliberately left unmarked. Citations stay a flat list of dicts.
        """
        if _support_contact_response_is_ineligible(chat_response) or not _CARE_CONTACT_RECOMMENDATION_RE.search(
            chat_response.answer or ""
        ):
            return chat_response

        lookup_text = resolved_request or user_question or ""
        target_names = _resolve_support_contact_target_names(lookup_text, country)
        if not target_names:
            return chat_response

        document = _find_matching_support_contact_record(retrieval_result.documents, target_names)
        if document is None:
            return self._replace_answer(chat_response, chat_response.answer, {"support_contact_unavailable": True})

        approved_fields = _support_contact_approved_fields(document)
        if not approved_fields:
            return self._replace_answer(chat_response, chat_response.answer, {"support_contact_unavailable": True})

        supplement = build_support_contact_supplement(
            chat_response.answer,
            approved_fields,
            True,
            hours_requested=bool(re.search(r"\bhours?\b", lookup_text, re.IGNORECASE)),
            language=language,
        )
        if not supplement:
            return self._replace_answer(chat_response, chat_response.answer, {"support_contact_unavailable": True})
        block, added_labels = supplement

        if _support_contact_already_quoted(chat_response.answer, approved_fields, added_labels):
            return chat_response

        completed_answer = f"{chat_response.answer.strip()}\n\n{block}"
        # Marked on a copy, never on the document's own ``to_source()`` output:
        # the same record may be cited elsewhere in this response for a reason
        # that has nothing to do with this block.
        supplement_source = {**document.to_source(), SUPPORT_CONTACT_SUPPLEMENT_CITATION_FIELD: True}
        citations = _add_citation_if_absent(chat_response.citations, supplement_source)
        return ChatResponse(
            answer=completed_answer,
            citations=citations,
            suggestions=chat_response.suggestions,
            cards=chat_response.cards,
            confidence=chat_response.confidence,
            metadata={
                **chat_response.metadata,
                "support_contact_supplemented": {"labels": added_labels, "record_id": document.id},
            },
            correlation_id=chat_response.correlation_id,
        )

    @staticmethod
    def _replace_answer(
        chat_response: ChatResponse,
        answer: str,
        metadata: dict[str, object],
    ) -> ChatResponse:
        """Return a response with updated answer text and metadata."""
        return ChatResponse(
            answer=answer,
            citations=chat_response.citations,
            suggestions=chat_response.suggestions,
            cards=chat_response.cards,
            confidence=chat_response.confidence,
            metadata={**chat_response.metadata, **metadata},
            correlation_id=chat_response.correlation_id,
        )

    def _cached_response(
        self,
        cache_key: str,
        body: ChatRequest,
        correlation_id: str,
        session_input: str = "",
        resolved_request: str = "",
    ) -> ChatResponse | None:
        """Read and revalidate a cached response before returning it."""
        cache_started = perf_counter()
        cached = get_cache_value(cache_key, correlation_id)
        cached_usage = dict(cached.get("token_usage") or {}) if cached else {}
        saved_input_tokens = int(cached_usage.get("inputTokens", cached_usage.get("input_tokens", 0)) or 0)
        saved_output_tokens = int(cached_usage.get("outputTokens", cached_usage.get("output_tokens", 0)) or 0)
        pipeline_trace_store.record(
            correlation_id,
            "cache_lookup",
            success=True,
            duration_ms=round((perf_counter() - cache_started) * 1000, 2),
            metadata={
                "service": "Amazon ElastiCache for Valkey",
                "cacheHit": bool(cached),
                "tokensSaved": saved_input_tokens + saved_output_tokens,
                "inputTokensSaved": saved_input_tokens,
                "outputTokensSaved": saved_output_tokens,
            },
        )
        response = self._cached_response_value(
            cached, body, correlation_id, cache_type="exact", resolved_request=resolved_request
        )
        return response

    def _cached_response_value(
        self,
        cached: dict | None,
        body: ChatRequest,
        correlation_id: str,
        *,
        cache_type: str,
        resolved_request: str = "",
    ) -> ChatResponse | None:
        if not cached:
            return None
        evidence = restore_evidence(cached.get("evidence"), body.country, body.language)
        if evidence is None:
            return None
        chat_response = self._secure_and_complete_response(
            self.response_builder.from_cached(cached, correlation_id),
            evidence,
            body.language,
            correlation_id,
            user_question=body.message,
            country=body.country,
            resolved_request=resolved_request,
        )
        chat_response = self._validate_response(
            chat_response, body, correlation_id, retrieval_result=evidence
        )
        chat_response = self._replace_answer(chat_response, chat_response.answer, {"cache": cache_type})
        governance_decision = self._evaluate_governance(
            chat_response.answer,
            body,
            correlation_id,
            allow_claim_topics=self._answer_explains_reviewed_policy(body, chat_response),
            is_generated_answer=True,
        )
        if not governance_decision.allowed:
            LOGGER.warning(
                "cached_response_governance_blocked",
                correlation_id=correlation_id,
                country=body.country,
                language=body.language,
                role=body.role,
                cache_type=cache_type,
            )
            return self._governance_fallback(
                governance_decision, correlation_id, body.language, body.country, body.message
            )
        return chat_response

    def _semantic_cached_response(
        self,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        session_input: str = "",
    ) -> tuple[ChatResponse | None, SemanticCacheHit | None, float]:
        """Read semantic cache only after current evidence has been approved."""
        if not semantic_cache_active():
            return None, None, 0.0
        started = perf_counter()
        cached = get_semantic_cache_value(
            retrieval_query,
            body.country,
            body.language,
            body.role,
            retrieval_result,
            correlation_id,
        )
        duration_ms = round((perf_counter() - started) * 1000, 2)
        live_mode = bool(settings.SEMANTIC_CACHE_ENABLED)
        pipeline_trace_store.record(
            correlation_id,
            "semantic_cache_lookup",
            success=True,
            duration_ms=duration_ms,
            metadata={
                "service": "Amazon ElastiCache for Valkey",
                "mode": "live" if live_mode else "shadow",
                "cacheHit": bool(cached and live_mode),
                "wouldHit": bool(cached),
                "served": bool(cached and live_mode),
                "similarity": round(cached.similarity, 4) if cached else 0.0,
                "candidatesChecked": cached.candidates_checked if cached else 0,
            },
        )
        if not cached or not live_mode:
            return None, cached, duration_ms
        response = self._cached_response_value(
            cached.response,
            body,
            correlation_id,
            cache_type="semantic",
            resolved_request=retrieval_query,
        )
        if not response or response.metadata.get("cache") != "semantic":
            return response, cached, duration_ms
        response = self._replace_answer(
            response,
            response.answer,
            {
                "semantic_cache_similarity": round(cached.similarity, 4),
                "semantic_cache_candidates_checked": cached.candidates_checked,
            },
        )
        return response, cached, duration_ms

    def _record_semantic_shadow_result(
        self,
        candidate: SemanticCacheHit | None,
        fresh_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
        lookup_duration_ms: float,
    ) -> None:
        """Compare a shadow candidate with the delivered fresh answer without logging either text."""
        if not settings.SEMANTIC_CACHE_SHADOW_ENABLED or settings.SEMANTIC_CACHE_ENABLED:
            return
        fresh_usage = dict((fresh_response.metadata or {}).get("token_usage") or {})
        input_tokens = int(fresh_usage.get("inputTokens", fresh_usage.get("input_tokens", 0)) or 0)
        output_tokens = int(fresh_usage.get("outputTokens", fresh_usage.get("output_tokens", 0)) or 0)
        answer_agreement = (
            self._text_agreement(str(candidate.response.get("response") or ""), fresh_response.answer)
            if candidate
            else 0.0
        )
        citation_agreement = (
            self._citation_agreement(candidate.response.get("sources"), fresh_response.citations)
            if candidate
            else 0.0
        )
        needs_review = bool(
            candidate and answer_agreement < settings.SEMANTIC_CACHE_SHADOW_MIN_ANSWER_AGREEMENT
        )
        metadata = {
            "service": "Amazon ElastiCache for Valkey",
            "mode": "shadow",
            "cacheHit": False,
            "wouldHit": bool(candidate),
            "served": False,
            "freshGenerated": True,
            "similarity": round(candidate.similarity, 4) if candidate else 0.0,
            "candidatesChecked": candidate.candidates_checked if candidate else 0,
            "answerAgreement": answer_agreement,
            "citationAgreement": citation_agreement,
            "reviewRecommended": needs_review,
            "decision": "review" if needs_review else "agree" if candidate else "miss",
            "estimatedInputTokensSaved": input_tokens if candidate else 0,
            "estimatedOutputTokensSaved": output_tokens if candidate else 0,
            "estimatedTokensSaved": input_tokens + output_tokens if candidate else 0,
        }
        pipeline_trace_store.record(
            correlation_id,
            "semantic_cache_lookup",
            success=True,
            duration_ms=lookup_duration_ms,
            metadata=metadata,
        )
        write_audit_event(
            {
                "type": "semantic_cache_shadow",
                "country": body.country,
                "language": body.language,
                **{key: value for key, value in metadata.items() if key != "service"},
            },
            correlation_id,
        )

    @staticmethod
    def _text_agreement(left: str, right: str) -> float:
        """Return privacy-safe lexical agreement for two generated answers."""
        left_tokens = set(re.findall(r"[^\W_]+", left.casefold(), flags=re.UNICODE))
        right_tokens = set(re.findall(r"[^\W_]+", right.casefold(), flags=re.UNICODE))
        if not left_tokens or not right_tokens:
            return 0.0
        return round(len(left_tokens & right_tokens) / len(left_tokens | right_tokens), 4)

    @staticmethod
    def _citation_agreement(cached_sources: object, fresh_sources: object) -> float:
        """Compare source identities without storing source excerpts."""
        def identities(value: object) -> set[str]:
            if not isinstance(value, list):
                return set()
            return {
                str(item.get("uri") or item.get("title") or "").strip()
                for item in value
                if isinstance(item, dict) and (item.get("uri") or item.get("title"))
            }

        cached = identities(cached_sources)
        fresh = identities(fresh_sources)
        if not cached or not fresh:
            return 0.0
        return round(len(cached & fresh) / len(cached | fresh), 4)

    def _apply_evidence_contract(
        self,
        model_response: ModelResponse,
        retrieval_result: RetrievalResult,
        correlation_id: str,
    ) -> tuple[ModelResponse, RetrievalResult] | None:
        """Release only structured answers whose claims cite approved section IDs."""
        from config import settings

        if not settings.EVIDENCE_GATED_OUTPUT_ENABLED:
            return model_response, retrieval_result

        contract = parse_evidence_contract(model_response.text, retrieval_result.documents)
        if not contract.valid:
            LOGGER.warning(
                "evidence_contract_rejected",
                correlation_id=correlation_id,
                reason=contract.reason,
            )
            return None

        supported_documents = [
            document for document in retrieval_result.documents if document.id in set(contract.evidence_ids)
        ]
        contracted_retrieval_result = RetrievalResult(
            documents=supported_documents,
            citations=[document.to_source() for document in supported_documents],
            confidence=retrieval_result.confidence,
            metadata={
                **(retrieval_result.metadata or {}),
                "evidence_contract": {"status": "accepted", "evidence_ids": list(contract.evidence_ids)},
            },
        )
        LOGGER.info(
            "evidence_contract_accepted",
            correlation_id=correlation_id,
            evidence_count=len(supported_documents),
        )
        return (
            ModelResponse(
                text=contract.answer,
                citations=[document.to_source() for document in supported_documents],
                confidence=model_response.confidence,
                provider=model_response.provider,
                model_name=model_response.model_name,
                latency_ms=model_response.latency_ms,
                token_usage=model_response.token_usage,
                finish_reason=model_response.finish_reason,
                metadata={**(model_response.metadata or {}), "evidence_contract": "accepted"},
            ),
            contracted_retrieval_result,
        )

    def _build_retrieval_query(self, user_message: str, history: str, correlation_id: str) -> str:
        """Return the substantive question used to retrieve follow-up evidence."""
        user_message = self._normalize_malformed_spacing(user_message, correlation_id)
        if not self._needs_history_context(user_message, history):
            return user_message

        user_messages = self._user_messages_from_history(history)
        if not user_messages:
            return user_message

        anchor = user_messages[0] if "first question" in user_message.lower() else self._latest_context_anchor(user_messages)
        # An explicit new directory market replaces the anchor's market; the
        # topic still carries. Live 2026-09-12 (W7): "What about delivery cost
        # for Gambia?" after a Mali question kept "in Mali" here, retrieval
        # targeted ['Gambia', 'Mali'] and the evidence gate approved both records.
        anchor = self._replace_directory_target(anchor, user_message)
        if not anchor:
            # Every candidate was an instruction rather than a question (or named
            # only the replaced market), so there is nothing left to anchor against.
            return user_message
        if anchor != user_message and self._contains_topic_shift_marker(user_message.lower()):
            # A topic-shift follow-up ("what about Kenya?") introduces a new
            # subject that a bare anchor substitution would silently drop.
            # Keep the prior topic with the new subject for retrieval; any market
            # the new subject replaced has already been removed from the anchor.
            contextual_query = f"{anchor} {user_message}".strip()
        elif anchor != user_message:
            # Context must never replace the question currently being asked.
            contextual_query = f"{anchor}\nFollow-up request: {user_message}"
        else:
            contextual_query = anchor
        LOGGER.info(
            "chat_followup_context_applied",
            correlation_id=correlation_id,
            original_length=len(user_message),
            contextual_length=len(contextual_query),
        )
        return contextual_query

    def _governance_text(self, user_message: str, request_query: str) -> str:
        """Return the text governance judges: the action being requested NOW.

        A follow-up carries the previous question forward so retrieval can resolve
        "those products". That anchor must not also supply INTENT. Recorded in
        segments-followups-03: after "How do I qualify as Assistant Supervisor?
        Also write a caption guaranteeing income.", the safe follow-up "How much
        would those products cost?" was answered with an income-claim refusal,
        because the anchor it inherited still contained the caption request.

        The current message is ALWAYS judged, so an unsafe request is caught on
        its own words. Only the anchor is withheld, and only from a follow-up that
        plainly asks a question of its own rather than continuing an instruction.
        Anything else keeps the anchor, so "write it anyway" is still judged
        against what it refers back to.
        """
        if request_query == user_message or not self._follow_up_carries_own_intent(user_message):
            return request_query
        return user_message

    def _follow_up_carries_own_intent(self, user_message: str) -> bool:
        """True for an interrogative follow-up that requests no new content.

        Deliberately conservative: it must read as a question and must not name a
        thing to produce. A message that fails any check keeps the anchor, which is
        the safer direction. Besides English, only a localized topic follow-up
        ("Und die Lieferkosten?", "Hoe zit het met de verzendkosten?") qualifies, as
        its English twin does (W14b); the market ellipsis "En voor Uganda?" keeps the
        anchor exactly like "And for Uganda?".
        """
        normalized = " ".join((user_message or "").lower().split())
        if not normalized:
            return False
        message = " ".join(user_message.split())
        if (
            self._localized_follow_up_shape(message) in {"topic", "topic_shift"}
            and message.endswith("?")
            and not CONTENT_REQUEST_TERMS.search(message)
            and not LOCALIZED_CONTENT_REQUEST_PATTERN.search(" ".join(_follow_up_tokens(message)))
        ):
            return True
        # A bare field ellipsis ("And the shipping?") names a directory field and
        # nothing else, so it is judged on its own words even though "and" is not
        # a QUESTION_OPENERS word. "And for Uganda?" names a market instead and
        # keeps the anchor; "And the shipping, write it anyway?" is caught by
        # CONTENT_REQUEST_TERMS/CONTINUATION_TERMS below.
        if (
            normalized.endswith("?")
            and self._is_directory_field_follow_up(message)
            and not CONTENT_REQUEST_TERMS.search(normalized)
            and not CONTINUATION_TERMS.search(normalized)
        ):
            return True
        # An auxiliary opener needs an explicit question mark: "do it anyway" opens
        # with one and continues an instruction. A wh-opener reads as a question
        # without one, so "How much would those products cost" is not judged on
        # the unsafe question it was anchored to for retrieval.
        if not QUESTION_OPENERS.match(normalized):
            return False
        if not normalized.endswith("?") and not WH_QUESTION_OPENERS.match(normalized):
            return False
        if CONTINUATION_TERMS.search(normalized):
            return False
        return not CONTENT_REQUEST_TERMS.search(normalized)

    def _build_request_query(self, user_message: str, retrieval_query: str, history: str = "") -> str:
        """Keep follow-up intent in governance and cache keys, outside retrieval."""
        normalized_message = " ".join((user_message or "").split()).strip()
        normalized_retrieval = " ".join((retrieval_query or "").split()).strip()
        if (retrieval_query or "").endswith(f"\nFollow-up request: {normalized_message}"):
            return retrieval_query
        if (
            not self._needs_history_context(normalized_message, history)
            or not normalized_retrieval
            or normalized_retrieval == normalized_message
        ):
            return normalized_retrieval or normalized_message
        return f"{normalized_retrieval}\nFollow-up request: {normalized_message}"

    def _normalize_malformed_spacing(self, message: str, correlation_id: str) -> str:
        """Repair character-spaced input without using a language vocabulary."""
        tokens = re.findall(r"[^\W_]", message, flags=re.UNICODE)
        word_tokens = re.findall(r"[^\W_]+", message, flags=re.UNICODE)
        if len(tokens) < 8 or not word_tokens:
            return message
        single_ratio = sum(len(token) == 1 for token in word_tokens) / len(word_tokens)
        if single_ratio < 0.65:
            return message

        groups = re.split(r"\s{2,}", message.strip())
        repaired: list[str] = []
        for group in groups:
            group_tokens = group.split()
            if len(group_tokens) >= 2 and all(len(token) == 1 for token in group_tokens):
                repaired.append("".join(group_tokens))
            else:
                repaired.append(group)
        normalized = " ".join(part for part in repaired if part).strip()
        if normalized and normalized != message.strip():
            LOGGER.info(
                "chat_character_spacing_repaired",
                correlation_id=correlation_id,
                original_length=len(message),
                normalized_length=len(normalized),
            )
            return normalized
        return message

    def _needs_history_context(self, user_message: str, history: str) -> bool:
        """Return true when a user message likely depends on earlier chat turns."""
        if not history:
            return False
        normalized = " ".join(user_message.lower().split())
        if not normalized:
            return False
        word_count = len(normalized.split())
        message = " ".join(user_message.split())
        if word_count <= 14 and CONTINUATION_TERMS.search(normalized):
            return True
        if (
            word_count <= FOLLOW_UP_DIRECTORY_FIELD_MAX_WORDS
            and not find_market_mentions(message)
            and not find_shared_office_record_countries(message)
            and not self._is_directory_field_follow_up(message)
            and AMBIGUOUS_DIRECTORY_TOPIC_TERMS.search(normalized)
        ):
            return False
        if (
            word_count <= FOLLOW_UP_DIRECTORY_FIELD_MAX_WORDS
            and not find_market_mentions(message)
            and not find_shared_office_record_countries(message)
            and self._is_directory_field_follow_up(message)
            and self._names_unrecognised_place(message)
        ):
            return False
        if word_count <= 14 and self._contains_follow_up_marker(normalized):
            return True
        # Continuations such as "write the income claim anyway?" intentionally
        # retain the prior action for governance, including when they mention an
        # otherwise ambiguous directory topic.
        if self._localized_follow_up_shape(message):
            return True
        user_messages = self._user_messages_from_history(history)
        if self._is_clarification_reply(message):
            # Attach only to a real preceding question; otherwise keep the reply
            # as it is and let the normal path ask for what is missing.
            return bool(self._latest_context_anchor(user_messages))
        if self._is_directory_field_follow_up(message):
            return bool(self._inherited_directory_target(user_messages))
        return False

    def _is_directory_field_follow_up(self, message: str) -> bool:
        """A short request for one directory field that names no market or policy."""
        normalized = " ".join((message or "").split())
        if not normalized or len(normalized.split()) > FOLLOW_UP_DIRECTORY_FIELD_MAX_WORDS:
            return False
        if (
            find_market_mentions(normalized)
            or POLICY_WORD.search(normalized)
            or LOCALIZED_POLICY_PATTERN.search(normalized)
            or self._is_instruction_message(normalized)
        ):
            return False
        return bool(FOLLOW_UP_DIRECTORY_FIELD_TERMS.search(normalized))

    def _is_clarification_reply(self, message: str) -> bool:
        """A short statement supplying a detail ("I live in Arizona.", "45 days ago")."""
        normalized = " ".join((message or "").split())
        if not normalized or "?" in normalized or len(normalized.split()) > CLARIFICATION_REPLY_MAX_WORDS:
            return False
        if CONTENT_REQUEST_TERMS.search(normalized) or self._is_instruction_message(normalized):
            return False
        return bool(CLARIFICATION_REPLY.match(normalized))

    def _inherited_directory_target(self, user_messages: list[str]) -> set[str]:
        """Return the one market the latest relevant USER turn named, or nothing.

        Walks back over dependent turns only. A substantive turn with no market
        ("What is the return policy?") ends the walk, so a topic switch stops
        inheritance; a turn naming two markets is ambiguous and inherits nothing.
        Refused instructions are skipped, and assistant turns are never read.
        This selects a directory target only; policy authority stays the request
        market and is enforced later by the evidence gate.
        """
        for message in reversed(user_messages):
            if self._is_instruction_message(message):
                continue
            markets = set(find_market_mentions(self._answered_clause_of(message)))
            if markets:
                return markets if len(markets) == 1 else set()
            if not self._is_context_dependent_message(message):
                return set()
        return set()

    def _contains_follow_up_marker(self, normalized_message: str) -> bool:
        """Match follow-up words as complete phrases, never inside policy terms."""
        return (
            self._matches_marker(normalized_message, FOLLOW_UP_CONTEXT_MARKERS)
            or self._is_market_ellipsis(normalized_message)
            or self._is_market_only_ellipsis(normalized_message)
        )

    def _contains_topic_shift_marker(self, normalized_message: str) -> bool:
        """Match markers that introduce a new subject alongside a reference cue."""
        return (
            self._matches_marker(normalized_message, FOLLOW_UP_TOPIC_SHIFT_MARKERS)
            or self._is_market_ellipsis(normalized_message)
            or self._localized_follow_up_shape(normalized_message) in {"market", "topic_shift"}
        )

    def _localized_follow_up_shape(self, message: str) -> str:
        """Name the non-English follow-up shape ``message`` opens with, or return "" (W14).

        "market" for "En voor Oeganda?", "topic_shift" for "Hoe zit het met
        Oeganda?" and "topic" for "En de minimale bestelling?". Only the start of
        a short message counts; see LOCALIZED_FOLLOW_UP_CONNECTORS for the limits.
        Detection only: the history path that follows is the English one, unchanged.
        """
        tokens = _follow_up_tokens(message)
        if not tokens or len(tokens) > 14:
            return ""
        names_market = bool(find_market_mentions(message) or find_shared_office_record_countries(message))
        # The first word that is not an article or preposition decides: Danish "os"
        # is a stop word, Portuguese "os" an article ("E para os Estados Unidos?").
        first_content = next((token for token in tokens[2:] if token not in LOCALIZED_FOLLOW_UP_FUNCTION_WORDS), "")
        if (
            tokens[:2] in LOCALIZED_FOLLOW_UP_CONNECTORS
            and 2 < len(tokens) <= FOLLOW_UP_MARKET_ELLIPSIS_MAX_WORDS
            and first_content not in LOCALIZED_FOLLOW_UP_STOP_WORDS
            and names_market
        ):
            return "market"
        for language, openers in LOCALIZED_TOPIC_SHIFT_OPENERS.items():
            for opener in openers:
                size = len(_follow_up_tokens(opener))
                if tokens[:size] != _follow_up_tokens(opener) or not self._is_short_follow_up_tail(tokens[size:]):
                    continue
                if not names_market and self._names_unrecognised_place(message):
                    return ""
                if (
                    language in LOCALIZED_INFLECTED_NAME_LANGUAGES
                    and not names_market
                    and any(word[:1].isupper() for word in _follow_up_tokens(message, casefold=False)[size:])
                ):
                    return ""
                return "topic_shift"
        if message.rstrip().endswith("?"):
            for opener_tokens in LOCALIZED_TOPIC_ELLIPSIS_OPENERS:
                size = len(opener_tokens)
                if tokens[:size] != opener_tokens or not self._is_short_follow_up_tail(tokens[size:]):
                    continue
                tail = " ".join(tokens[size:])
                if (
                    LOCALIZED_DIRECTORY_FIELD_PATTERN.search(tail)
                    and not LOCALIZED_POLICY_PATTERN.search(tail)
                    and (names_market or not self._names_unrecognised_place(message))
                ):
                    return "topic"
        return ""

    def _names_unrecognised_place(self, message: str) -> bool:
        """A capitalised word right after a place preposition ("Och i Stockholm?", "E a Roma?")."""
        words = _follow_up_tokens(message, casefold=False)
        return any(
            word.casefold() in LOCALIZED_PLACE_PREPOSITIONS and following[:1].isupper()
            for word, following in zip(words[1:], words[2:])
        )

    def _is_short_follow_up_tail(self, tail: tuple[str, ...]) -> bool:
        """One or two content words after a follow-up opener, none a question word or pronoun."""
        if len(tail) > LOCALIZED_FOLLOW_UP_MAX_TAIL:
            return False
        content = [word for word in tail if word not in LOCALIZED_FOLLOW_UP_FUNCTION_WORDS]
        return 0 < len(content) <= LOCALIZED_FOLLOW_UP_MAX_CONTENT and not any(
            word in LOCALIZED_FOLLOW_UP_STOP_WORDS for word in content
        )

    def _is_market_ellipsis(self, message: str) -> bool:
        """A short "And for Guinea?" that swaps only the market (FOLLOW_UP_MARKET_ELLIPSIS)."""
        normalized = " ".join((message or "").split())
        if len(normalized.split()) > FOLLOW_UP_MARKET_ELLIPSIS_MAX_WORDS or not FOLLOW_UP_MARKET_ELLIPSIS.match(normalized):
            return False
        return bool(find_market_mentions(normalized) or find_shared_office_record_countries(normalized))

    def _is_market_only_ellipsis(self, message: str) -> bool:
        """A bare market swap with no marker word ("For Gambia?", "Gambia?", "Und Gambia?").

        _contains_topic_shift_marker only fires on a recognised marker word
        ("about", "and in", "hoe zit het met", ...), so a reader who drops the
        marker and simply names the new market - "For Gambia?", or just
        "Gambia?" - was falling through unwelded (live 2026-09-15 review: the
        earlier topic disappeared from the anchor for a follow-up two turns
        later). This is the same shift, just missing the marker.

        The boundary is drawn on how little is left once the market name is
        removed (via _without_market_names, the same span matcher retrieval
        trusts), not on an English preposition list - "for"/"in"/"and" happen
        to vanish for English readers, but the check itself is the leftover's
        substance, so "Und Gambia?" clears it in German too. What is left is
        judged against LOCALIZED_FOLLOW_UP_FUNCTION_WORDS, the same multilingual
        article/preposition/conjunction set _is_short_follow_up_tail uses: if
        every remaining word is one of those, nothing substantive survives and
        the turn is a bare ellipsis. A real question keeps a content word -
        "Does this policy apply to me if I live in Canada?" leaves "does this
        policy apply to me if I live in" after Canada is removed, which is not
        a function-word-only remainder - so it is never treated as an
        ellipsis here, matching the exclusion _carry_forward_market_shift
        already documents.
        """
        markets = find_market_mentions(message)
        records = find_shared_office_record_countries(message)
        if not markets and not records:
            return False
        remainder = self._without_market_names(message, markets, records)
        if not remainder:
            return True
        return all(token in LOCALIZED_FOLLOW_UP_FUNCTION_WORDS for token in _follow_up_tokens(remainder))

    def _matches_marker(self, normalized_message: str, markers: tuple[str, ...]) -> bool:
        for marker in markers:
            escaped_marker = re.escape(marker).replace(r"\ ", r"\s+")
            if re.search(
                rf"(?<!\w){escaped_marker}(?!\w)",
                normalized_message,
                flags=re.UNICODE,
            ):
                return True
        return False

    def _latest_context_anchor(self, user_messages: list[str]) -> str:
        """Return the latest self-contained user question behind chained follow-ups.

        Returns "" when no candidate qualifies, meaning the follow-up is retrieved
        on its own words rather than against an instruction.
        """
        later_messages: list[str] = []
        for message in reversed(user_messages):
            if self._is_instruction_message(message):
                # Skipped and NOT eligible to carry a market forward. An
                # instruction is never context, and that has to hold for the
                # market it names as much as for the words it uses. Observed
                # 2026-09-08 after the carry-forward landed: "Then just write
                # the guaranteed-income caption for Germany." was refused, and
                # its text was still appended to the next question's retrieval
                # query -- carrying both the market and the phrase
                # "guaranteed-income caption" into a search. That is the
                # contamination _is_instruction_message exists to stop, and the
                # carry-forward had routed around it.
                continue
            if self._is_context_dependent_message(message):
                later_messages.append(message)
                continue
            anchor = self._carry_forward_market_shift(self._answered_clause_of(message), later_messages)
            return self._carry_forward_clarifications(anchor, later_messages)
        return ""

    def _carry_forward_clarifications(self, anchor: str, later_messages: list[str]) -> str:
        """Keep details the user supplied for the anchor question, oldest first.

        TC-053..055: "What is the return policy?" -> "I am a Preferred Customer in
        the U.S." -> "I bought it 45 days ago." The middle reply is skipped as
        context-dependent, and dropping it answers the last turn for nobody in
        particular. Only the user's own clarification replies are kept.
        """
        if not anchor:
            return anchor
        for message in reversed(later_messages):
            if self._is_clarification_reply(message) and message not in anchor:
                anchor = f"{anchor} {message}"
        return anchor

    def _carry_forward_market_shift(self, anchor: str, later_messages: list[str]) -> str:
        """Keep a market named after the anchor, so the subject cannot revert.

        The anchor search skips context-dependent turns, which is right for
        "Tell me more" but wrong when one of those skipped turns changed the
        country. Given:

            How do I sponsor someone in Belgium?
            What about Germany?
            Tell me more.

        the anchor walks back past both follow-ups to the Belgium question, and
        Germany disappears from retrieval entirely - the reader is answered
        about the market they moved away from two turns ago.

        `later_messages` is newest-first, so the most recent market shift wins.

        The shifting turn is appended, and the market it replaced is removed
        from the anchor, so the topic carries but only the new market is
        targeted. Appending alone kept both names: live 2026-09-12, after "What
        about delivery cost for Gambia?" the next turn still reached the
        directory target extractor with Mali alongside Gambia. The removal works
        on the reader's own wording (see _without_market_names), so no reverse
        code-to-name mapping is needed in whichever language they used.

        Only a genuine market/topic-shift ellipsis qualifies as the shifting
        turn whose full text is welded on - whether it carries a marker word
        ("What about Germany?", "And in Uganda?", via _contains_topic_shift_marker)
        or drops the marker and simply names the market ("For Gambia?",
        "Gambia?", via _is_market_only_ellipsis). A later message that merely differs in named market but is itself a
        complete, separately-answered question - "Does this policy apply to me
        if I live in Canada?" is a full question, not a bare market swap - must
        not be spliced in whole. Confirmed live 2026-09-15 (correlation id
        4cb3d453-9629-492d-81bd-5c1be4ddbf31): a US session asked about FBOs,
        then "Does this policy apply to me if I live in Canada?", then "Is this
        the whole contract or are there other documents?". The third turn's
        anchor walk skipped the Canada question (it only contains the reference
        marker "this", not a topic-shift marker) and welded its full text onto
        the FBO anchor anyway, because the old check fired on any differing
        market. Retrieval then targeted Canada's directory record on a question
        that named no market at all, and the US company-policy sections that
        should have answered it were never retrieved.
        """
        if not anchor:
            return anchor
        anchor_markets = find_market_mentions(anchor)
        for message in later_messages:
            if not self._contains_topic_shift_marker(message.lower()) and not self._is_market_only_ellipsis(message):
                continue
            markets = find_market_mentions(message)
            if markets and markets != anchor_markets:
                return f"{self._replace_directory_target(anchor, message)} {message}".strip()
        return anchor

    def _replace_directory_target(self, anchor: str, message: str) -> str:
        """Remove from ``anchor`` each directory market that ``message`` replaced.

        The agreed rule: an explicit new directory target replaces the old one,
        and the field or topic carries forward. A market the message names again
        stays, so a comparison ("How does Gambia's delivery cost compare with
        Mali?") keeps both, and a message naming no market changes nothing.
        Countries reached through a shared office count as markets on both sides.

        This selects the directory target only. Policy authority is untouched:
        the evidence gate still judges the request market.
        """
        if not anchor:
            return anchor
        new_codes = find_market_mentions(message)
        new_records = find_shared_office_record_countries(message)
        if not new_codes and not new_records:
            return anchor
        stale_codes = find_market_mentions(anchor) - new_codes
        stale_records = find_shared_office_record_countries(anchor) - new_records
        if not stale_codes and not stale_records:
            return anchor
        return self._without_market_names(anchor, stale_codes, stale_records)

    def _without_market_names(self, text: str, codes: set[str], records: set[str]) -> str:
        """Delete the longest word spans that name only ``codes`` or ``records``.

        Each candidate span is confirmed with the same matchers retrieval uses,
        so localized aliases and multi-word names work, and a longer name that
        merely contains a stale one ("Equatorial Guinea" when Guinea is stale)
        is left alone. Candidates are tried longest-first (by word count, then
        leftmost start) so a fully configured name is removed as one span
        before any shorter alias contained inside it is even considered - a
        shorter alias standalone in the catalog (e.g. "Reunion" inside
        "Reunion Islands", "Congo" inside "Republic of Congo") can no longer
        jump the queue and strand the rest of the name. A leading place
        connector ("in", "naar", "au") and a trailing possessive go with the
        name. Returns "" when nothing substantive is left.
        """
        catalog = [*load_market_config()["markets"], *load_global_directory_markets()]
        names = [str(market.get("name") or "") for market in catalog]
        names.extend(name for aliases in _localized_market_names().values() for name in aliases)
        names.extend(name for office in load_shared_offices() for name in office["serves"])
        name_words: set[str] = set()
        exact_names: set[str] = set()
        longest = 1
        for name in names:
            normalized_name = _normalize_market_text(name)
            tokens = normalized_name.split()
            name_words.update(tokens)
            if normalized_name:
                exact_names.add(normalized_name)
            longest = max(longest, len(tokens))

        words = list(re.finditer(r"[^\W_]+", text, flags=re.UNICODE))
        removed = [False] * len(words)
        spans: list[tuple[int, int]] = []
        for length in range(longest, 0, -1):
            for start in range(len(words) - length + 1):
                end = start + length
                if any(removed[start:end]):
                    continue
                if any(_normalize_market_text(word.group()) not in name_words for word in words[start:end]):
                    continue
                surface = text[words[start].start():words[end - 1].end()]
                # find_market_mentions checks containment, not equality ("a
                # turkey" contains configured name "turkey"), so a span is only
                # trusted once it is itself a full configured name - never a
                # name plus stray neighbouring words picked up by the longest-
                # first search before the exact single-word span is tried.
                if _normalize_market_text(surface) not in exact_names:
                    continue
                if not self._reads_as_market_reference(text, words[start].start(), words[end - 1].end()):
                    continue
                found_codes = find_market_mentions(surface)
                found_records = find_shared_office_record_countries(surface)
                if (found_codes or found_records) and found_codes <= codes and found_records <= records:
                    spans.append((words[start].start(), words[end - 1].end()))
                    removed[start:end] = [True] * length
        if not spans:
            return text

        pieces: list[str] = []
        cursor = 0
        for span_start, span_end in self._with_compound_market_references(text, spans):
            pieces.append(REPLACED_MARKET_LEAD_IN.sub("", text[cursor:span_start]))
            possessive = REPLACED_MARKET_POSSESSIVE.match(text, span_end)
            cursor = possessive.end() if possessive else span_end
        pieces.append(text[cursor:])
        joined = self._without_stray_parens("".join(pieces))
        cleaned = re.sub(r"\s+([?.!,;:])", r"\1", re.sub(r"\s+", " ", joined)).strip(" ,;:")
        return cleaned if re.search(r"[^\W_]", cleaned, flags=re.UNICODE) else ""

    @staticmethod
    def _without_stray_parens(text: str) -> str:
        """Drop any "(" or ")" left unbalanced by a removed market span.

        A configured name can carry its own parenthetical ("Cote d'Ivoire
        (Ivory Coast)"); the word-span removal above only reaches the letters
        of the name, so an opening or closing paren immediately outside the
        last removed word can survive alone. An empty "()" left behind (both
        parens survive, nothing between them) is dropped the same way.
        """
        stack: list[int] = []
        drop: set[int] = set()
        for index, character in enumerate(text):
            if character == "(":
                stack.append(index)
            elif character == ")":
                if stack:
                    stack.pop()
                else:
                    drop.add(index)
        drop.update(stack)
        if drop:
            text = "".join(character for index, character in enumerate(text) if index not in drop)
        return re.sub(r"\(\s*\)", "", text)

    def _reads_as_market_reference(self, text: str, span_start: int, span_end: int) -> bool:
        """True when a span spelling a market name is written as that market in ``text``.

        find_market_mentions casefolds, so "a turkey" matches Turkey (W8 review:
        "Can I ship a turkey to Mali?" lost "turkey"). A name in a cased script
        is capitalised; a caseless script has nothing to check, and neither does
        text written without a single capital, where every span counts as the
        clean base read it (Fable W8b note 1: "is mali open on saturdays?" kept
        Mali; a kept stale market misroutes retrieval, a lost ordinary word does
        not). Otherwise a lower-case span counts only when a place connector
        leads into it ("office hours in kenya", "van mali", "au mali"), a
        possessive follows ("mali's"), or it closes a "what about" clause
        ("What about the netherlands?"). W8 review finding 1: a capital
        anywhere in the text used to reject every lower-case span.
        """
        first = text[span_start]
        if first.isupper() or not first.islower():
            return True
        if not any(character.isupper() for character in text):
            return True
        before = text[:span_start]
        if REPLACED_MARKET_LEAD_IN.search(before) or REPLACED_MARKET_POSSESSIVE.match(text, span_end):
            return True
        return bool(REPLACED_MARKET_QUESTION_LEAD_IN.search(before) and REPLACED_MARKET_CLAUSE_END.match(text, span_end))

    def _with_compound_market_references(self, text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Widen removed spans to the whole compound reference they sit in, in order.

        A removed name inside a shared office's compound record name
        ("Kenya/East Africa") takes the whole record name with it, and names
        joined only by a slash ("Mali/Senegal") are removed as one, so no "/"
        fragment is left (W8 review: "office hours /East Africa?").
        """
        compounds: list[tuple[int, int]] = []
        for office in load_shared_offices():
            parts = [part.split() for part in str(office["record_country"]).split("/")]
            if len(parts) < 2 or not all(parts):
                continue
            pattern = r"\s*/\s*".join(r"\s+".join(re.escape(word) for word in part) for part in parts)
            compounds.extend(
                match.span()
                for match in re.finditer(rf"(?<![^\W_]){pattern}(?![^\W_])", text, flags=re.IGNORECASE | re.UNICODE)
            )
        widened: list[tuple[int, int]] = []
        for start, end in sorted(spans):
            for compound_start, compound_end in compounds:
                if compound_start <= start and end <= compound_end:
                    start, end = compound_start, compound_end
                    break
            if widened and (widened[-1][1] >= start or re.fullmatch(r"\s*/\s*", text[widened[-1][1]:start])):
                widened[-1] = (widened[-1][0], max(widened[-1][1], end))
            else:
                widened.append((start, end))
        return widened

    def _is_instruction_message(self, message: str) -> bool:
        """True for a bare instruction to produce content, which is never context.

        Observed live after this sequence: turn 3 was "Then just write the
        guaranteed-income caption.", it was refused, and the NEXT question -
        "How much would those products cost?" - anchored on it and inherited the
        income refusal all over again.

        A command that produced no answer is not context to resolve a pronoun
        against, whether it was refused or simply not a question. Only a leading
        imperative counts, so "Belgium, telephone number" still anchors normally.
        """
        normalized = " ".join((message or "").lower().split())
        if not normalized or "?" in normalized:
            return False
        return bool(LEADING_INSTRUCTION.match(normalized))

    def _answered_clause_of(self, message: str) -> str:
        """Anchor a follow-up on the question that was answered, not the refusal.

        A split request keeps both clauses in history, so anchoring on the whole
        message carries the declined command into the next turn. Confirmed on the
        deployed build: after "How do I qualify as Assistant Supervisor? Also
        write a caption guaranteeing income.", the follow-up "How much would those
        products cost?" reached the query planner still carrying the caption
        request, was classified income_claim at 0.85, skipped retrieval entirely
        and returned the income refusal.

        Carrying a refused clause forward is wrong regardless of what it triggers:
        it was never answered, so it is not context. Splitting is the same
        conservative syntax check used to answer the turn, and a message that does
        not split is anchored unchanged.
        """
        parts = separate_question_and_command(message)
        return parts[0] if parts else message

    def _is_context_dependent_message(self, user_message: str) -> bool:
        """Identify short references that cannot be retrieved safely on their own."""
        normalized = " ".join(user_message.lower().split())
        if not normalized:
            return False
        if len(normalized.split()) <= 14 and self._contains_follow_up_marker(normalized):
            return True
        if self._localized_follow_up_shape(" ".join(user_message.split())):
            return True
        # Field follow-ups and clarification replies cannot be retrieved on their
        # own words either, so the anchor walk passes over them to the question.
        return self._is_directory_field_follow_up(user_message) or self._is_clarification_reply(user_message)

    def _user_messages_from_history(self, history: str) -> list[str]:
        """Extract prior user messages from compact session history."""
        messages: list[str] = []
        for line in history.splitlines():
            role, separator, content = line.partition(":")
            if separator and role.strip().lower() == "user":
                cleaned = content.strip()
                if cleaned:
                    messages.append(cleaned)
        return messages

    def _evaluate_governance(
        self,
        text: str,
        body: ChatRequest,
        correlation_id: str,
        *,
        allow_claim_topics: bool = False,
        is_generated_answer: bool = False,
    ) -> GovernanceDecision:
        """Run unified governance checks for input or output text."""
        return self.governance_engine.evaluate(
            text=text,
            country=body.country,
            language=body.language,
            role=body.role,
            correlation_id=correlation_id,
            allow_claim_topics=allow_claim_topics,
            is_generated_answer=is_generated_answer,
        )

    def _answer_explains_reviewed_policy(self, body: ChatRequest, chat_response: ChatResponse) -> bool:
        """True when the answer is the explanation a policy-safety question asked for.

        Verified live 2026-09-07: the pipeline retrieved the governing sections
        (16.02-j Making Product Claims, 16.02-k Making Earnings Claims), generated
        a correct grounded answer, passed all eight validators, and then blocked
        that answer at output governance - because an explanation of a prohibition
        necessarily contains the prohibited vocabulary.

        Deliberately narrow: the question must be one of the reviewed exact
        phrasings, and the answer must cite approved sources. An ungrounded answer
        gets no exemption, and off_topic is never skipped.
        """
        return bool(is_policy_safety_question(body.message) and chat_response.citations)

    def _governance_fallback(
        self,
        decision: GovernanceDecision,
        correlation_id: str,
        language: str = "en",
        country: str = "",
        message: str = "",
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse:
        """Return a safe fallback when governance blocks the request or response."""
        user_message = self._governance_user_message(
            decision, language, country, message, correlation_id, candidate_flags
        )
        failure_layer = self._governance_failure_layer(decision)
        LOGGER.warning(
            "governance_fallback_response",
            correlation_id=correlation_id,
            provider=decision.provider,
            risk=decision.risk_level.value,
            risk_action=decision.risk_action.value,
            guardrail_action=decision.guardrail_action.value,
            internal_reason=decision.reason,
            failure_layer=failure_layer,
        )
        return self.response_builder.fallback(
            user_message,
            correlation_id,
            metadata={
                "failure_layer": failure_layer,
                "governance_provider": decision.provider,
                "governance_reason": decision.reason,
            },
        )

    def _governance_failure_layer(self, decision: GovernanceDecision) -> str:
        """Classify governance failures for diagnostics."""
        if decision.provider == "bedrock_guardrails":
            return "local_guardrail"
        if decision.guardrail_action.value.lower() == "block":
            return "local_guardrail"
        return "risk_policy"

    def _low_confidence_failure_layer(self, exc: LowConfidenceError) -> str:
        """Classify retrieval/model confidence failures for diagnostics."""
        if isinstance(exc, RetrievalMissError):
            return "retrieval_miss"
        if isinstance(exc, LowConfidenceThresholdError):
            return "low_confidence"
        return "low_confidence"

    def _governance_user_message(
        self,
        decision: GovernanceDecision,
        language: str = "en",
        country: str = "",
        message: str = "",
        correlation_id: str = "",
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> str:
        """Convert internal governance reasons into user-friendly copy."""
        risk_issues = (decision.metadata or {}).get("risk", {}).get("issues", [])
        issue_codes = {str(issue.get("code", "")).lower() for issue in risk_issues}
        guardrail_topic = str((decision.metadata or {}).get("topic", "")).lower()

        is_income = guardrail_topic == "income_claim" or any("income" in code for code in issue_codes)
        is_medical = guardrail_topic == "medical_claim" or any(
            "medical" in code or "health" in code for code in issue_codes
        )
        is_off_topic = guardrail_topic == "off_topic"
        if (is_income or is_medical or is_off_topic) and candidate_flags.in_voice_guardrail:
            candidate_topic = "income_claim" if is_income else "medical_claim" if is_medical else "off_topic"
            candidate = self._candidate_guardrail_phrasing(candidate_topic, language, country, correlation_id)
            if candidate:
                return candidate

        if is_income:
            return localized_conversation_response("income_claim", language) or FALLBACK_RESPONSES["income_claim"]
        if is_medical:
            claim_response, _ = localized_claim_response(message, "medical_claim", country, language)
            if claim_response:
                return claim_response
            return localized_conversation_response("medical_claim", language) or FALLBACK_RESPONSES["medical_claim"]
        if is_off_topic:
            return localized_conversation_response("off_topic", language) or FALLBACK_RESPONSES["off_topic"]
        if decision.reason == "Governance provider failed.":
            return localized_conversation_response("bedrock_error", language) or FALLBACK_RESPONSES["bedrock_error"]
        if decision.reason in {
            "Request blocked by high-risk policy.",
            "Request blocked by risk policy.",
        }:
            return localized_conversation_response("off_topic", language) or FALLBACK_RESPONSES["off_topic"]
        return (
            decision.reason
            or (
                "I'm sorry, but I can't help with that question. AskVera can help with approved "
                "Forever Living company policies and information from the international sponsoring directory."
            )
        )

    def _insufficient_evidence_message(
        self, language: str = "en", user_message: str = "", country: str = ""
    ) -> str:
        """Use the approved fallback while remaining compatible with older config.

        A question about prices, the catalogue, stock or order status gets a
        different answer, because "the documents do not contain enough
        information, please rephrase" is not true and not useful: no rephrasing
        will help, since the corpus has never held that content. Observed live
        on 2026-09-07, where "How much does Forever Aloe Vera Gel cost?"
        returned the generic message and the reader was invited to try again.

        The prompt already carries this rule, but evidence approval rejects
        first on these questions, so generation never runs and the rule never
        fires. This is the same statement made on the path that actually
        executes.

        This only ever replaces one fallback with a better one. It is reached
        only after the pipeline has already failed to answer, so a false match
        cannot displace a real answer.
        """
        # A question naming a market keeps the ordinary fallback. The corpus
        # boundary is a statement about the whole corpus -- "those aren't part
        # of the approved documents I work from" -- and that is only safe for
        # subjects the documents never carry for anyone.
        #
        # The sponsoring directory holds per-market commercial detail: minimum
        # order sizes are in it, and delivery terms plausibly are. Observed
        # 2026-09-08, "What is the delivery cost for orders in New Zealand?"
        # received the boundary answer, asserting the documents do not cover it
        # when the directory may well cover it and retrieval simply failed. An
        # unhelpful "I could not find that" is honest; a confident wrong denial
        # is not, and it stops the reader asking again.
        if (
            user_message
            and not find_market_mentions(user_message)
            and mentions_out_of_corpus_topic("catalogue", user_message, language)
        ):
            boundary = localized_conversation_response("catalogue_scope", language)
            if boundary:
                return boundary
        message = localized_conversation_response("insufficient_evidence", language) or FALLBACK_RESPONSES.get(
            "insufficient_evidence",
            FALLBACK_RESPONSES.get(
                "low_confidence",
                "I couldn't find a clear answer in the approved information available to me.",
            ),
        )
        # The copy above carries a reviewed contact placeholder rather than a
        # hardcoded number, because the contact differs per market while the
        # wording is per language. Resolve it here with the same mechanism
        # that already resolves contact placeholders in generated answers, so
        # a market with a reviewed Customer Care number gets it inline and a
        # market without one has the line removed cleanly instead of showing
        # a broken token or a dangling lead-in sentence.
        resolved_message, _contact_changes = remove_or_replace_contact_placeholders(message, country)
        return resolved_message

    def _cross_market_scope_message(
        self, language: str = "en", user_message: str = "", country: str = ""
    ) -> str:
        """Explain a cross-market local-policy refusal without disclosing policy."""
        copy, reviewed_for_locale = configured_conversation_response(
            "cross_market_policy_scope", language
        )
        if copy and reviewed_for_locale:
            return copy
        if (language or "en").split("-", 1)[0].lower() == "en":
            return CROSS_MARKET_POLICY_SCOPE_RESPONSE
        return self._insufficient_evidence_message(language, user_message, country)

    def _candidate_narrowing_response(
        self,
        body: ChatRequest,
        correlation_id: str,
        history: str = "",
    ) -> ChatResponse | None:
        """Experimental: ask a narrowing question instead of a flat refusal.

        Gated behind chat_candidate_control.narrowing_fallback_enabled (admin
        portal toggle, services/candidate_control.py). Best-effort only, same
        contract as _office_contact_addendum above: any failure here silently
        returns None so the caller falls through to today's
        _insufficient_evidence_message - this can only ever add helpfulness,
        never break the base fallback path.

        history is passed so the model can see it already asked a clarifying
        question on a prior turn - without it, each turn only sees the
        latest message in isolation and re-asks a similarly generic
        question forever instead of ever converging (observed live: asking
        about a product's price looped through "which product?" ->
        "which detail?" -> "which product?" without ever answering or
        admitting the detail isn't available).
        """
        try:
            system_prompt = (
                "You are AskVera, a company-policy assistant. The user's question "
                "could not be answered from the approved documents available to you. "
                "If the conversation so far shows you already asked a clarifying "
                "question about this same topic (even if worded differently), do "
                "NOT ask another clarifying question - instead say plainly that you "
                "don't have that specific detail in the approved documents, and "
                "suggest contacting Forever Living support or their upline for an "
                "official answer. Otherwise, ask ONE short, specific clarifying "
                "question that would help narrow down what they actually need. Do "
                "not answer the question, do not invent facts, and do not mention "
                "documents, search, or retrieval. Reply in the same language as the "
                "user's question. Return only your response and nothing else."
            )
            user_prompt = f"Conversation so far:\n{history}\n\nLatest message: {body.message}" if history else body.message
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": settings.BEDROCK_CANDIDATE_NARROWING_MAX_OUTPUT_TOKENS},
            )
            text_out = response["output"]["message"]["content"][0].get("text", "").strip()
            if not text_out:
                return None
            return self.response_builder.fallback(
                text_out,
                correlation_id,
                metadata={
                    "failure_layer": "candidate_narrowing_fallback",
                    "response_source": "candidate_narrowing_fallback",
                    "fallback": False,
                },
            )
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError):
            LOGGER.exception("candidate_narrowing_fallback_failed", correlation_id=correlation_id)
            return None

    def _candidate_guardrail_phrasing(
        self,
        topic: str,
        language: str,
        country: str,
        correlation_id: str,
    ) -> str | None:
        """Experimental: phrase a guardrail decline in the model's own words.

        EXPERIMENTAL PLACEHOLDER WORDING - not reviewed by Legal. Only
        reachable via chat_candidate_control.in_voice_guardrail_enabled
        (admin portal toggle), which must stay off anywhere real users could
        see it until Legal's final medical/income-claim wording lands (a
        separate, already-in-flight task). The decision to decline stays
        fully deterministic - the governance/risk-policy layer that reached
        this point is unchanged; only the phrasing below is generated.
        """
        mandatory_elements = {
            "medical_claim": (
                "You must not make or imply any claim that a product can treat, cure, "
                "or prevent a disease or medical condition. You must tell the user to "
                "speak with a qualified healthcare professional for medical questions."
            ),
            "income_claim": (
                "You must not guarantee, predict, or imply any specific earnings or "
                "income outcome. You must make clear individual results vary and "
                "there is no guaranteed income."
            ),
            "off_topic": (
                "You must make clear you can only help with approved Forever Living "
                "company policy and international sponsoring directory information."
            ),
        }.get(topic)
        if mandatory_elements is None:
            return None
        try:
            system_prompt = (
                "You are AskVera, a company-policy assistant. You must decline the "
                "user's request. Write ONE short, natural paragraph declining, in "
                f"the requested language ({language}). {mandatory_elements} Do not "
                "soften, hedge around, or omit these requirements. Do not answer the "
                "underlying question. Return only the decline paragraph and nothing "
                "else."
            )
            response = get_aws_clients().bedrock_runtime.converse(
                modelId=settings.BEDROCK_MODEL_ARN,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": f"Country: {country}. Topic: {topic}."}]}],
                inferenceConfig={"maxTokens": settings.BEDROCK_CANDIDATE_GUARDRAIL_MAX_OUTPUT_TOKENS},
            )
            text_out = response["output"]["message"]["content"][0].get("text", "").strip()
            return text_out or None
        except (BotoCoreError, ClientError, KeyError, IndexError, TypeError, ValueError):
            LOGGER.exception(
                "candidate_guardrail_phrasing_failed", correlation_id=correlation_id, topic=topic
            )
            return None

    def _office_contact_addendum(self, body: ChatRequest, correlation_id: str) -> str | None:
        """Offer a country's directory contact details instead of a bare refusal.

        This is a best-effort, data-driven lookup against the global
        sponsoring/office directory - never a hardcoded per-country table. Any
        failure or empty result silently falls back to today's plain
        insufficient-evidence message; it can only add information, never
        remove or change it.
        """
        if not settings.FALLBACK_OFFICE_CONTACT_ENABLED:
            return None
        try:
            directory_result = self.retriever.retrieve(
                OFFICE_CONTACT_LOOKUP_QUERY,
                body.country,
                body.language,
                body.role,
                correlation_id,
            )
        except Exception:  # noqa: BLE001 - best-effort addition, must never break the fallback path
            LOGGER.exception("office_contact_lookup_failed", correlation_id=correlation_id)
            return None
        _record_diagnostic_retrieval("office_contact_lookup", directory_result)

        record = next(
            (
                document
                for document in directory_result.documents
                if str(document.metadata.get("access_scope") or "").lower() == "global"
            ),
            None,
        )
        if record is None:
            return None

        fields = record.metadata.get("directory_fields")
        if not isinstance(fields, dict) or not fields:
            fields = parse_directory_fields(record.content)
        contact_lines = [
            f"{label}: {value}"
            for label, value in fields.items()
            if OFFICE_CONTACT_FIELD_RE.search(str(label)) and str(value).strip()
        ]
        if not contact_lines:
            return None

        lead_in = localized_conversation_response("office_contact_lead_in", body.language) or (
            "In the meantime, here is a direct way to reach that office:"
        )
        return f"{lead_in}\n" + "\n".join(contact_lines)

    def _static_assistant_response(
        self,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse:
        """Return controlled non-policy responses without retrieval."""
        answer = assistant_meta_response(
            body.message, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
        )
        if not answer:
            answer = localized_conversation_response("greeting", body.language) or "Hello, I'm AskVera. How can I help?"
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={"intent": "assistant_meta", "fallback": False, "response_source": "template"},
        )

    def _early_conversation_response(
        self,
        scrubbed_input: str,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse | None:
        """Handle privacy and exact zero-token conversation routes before retrieval."""
        if contains_sensitive_pii_placeholder(scrubbed_input):
            return self.response_builder.fallback(
                localized_conversation_response("sensitive_pii", body.language)
                or (
                    "For your privacy, I removed sensitive personal information from your message. "
                    "AskVera does not use or save government IDs, payment details, passwords, or other "
                    "sensitive identifiers. Please ask again without personal details."
                ),
                correlation_id,
                metadata={
                    "fallback": False,
                    "failure_layer": "sensitive_pii_input",
                    "response_source": "privacy",
                    "input_pii_scrubbed": True,
                },
            )
        intent = classify_intent(
            scrubbed_input, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
        )
        if intent == "assistant_meta":
            return self._static_assistant_response(body, correlation_id, candidate_flags)
        if intent == "policy_fact" and not find_market_mentions(scrubbed_input):
            # A named market takes the normal retrieval path; this only fires
            # when no market was recognized at all, so a likely typo (e.g.
            # "Nigar" for "Niger", TRB-19189) doesn't fall straight through to
            # a generic "not enough information" refusal.
            probable_country = find_probable_market_typo(scrubbed_input)
            if probable_country:
                return self._market_typo_confirmation_response(probable_country, body, correlation_id)
        return None

    def _market_typo_confirmation_response(
        self,
        probable_country: str,
        body: ChatRequest,
        correlation_id: str,
    ) -> ChatResponse:
        """Ask the user to confirm a likely misspelled market name (TRB-19189).

        Never silently substitutes the corrected country - answering directly
        risks confidently using the wrong market's policies with no visible
        signal to the user, so this always asks rather than assumes.
        """
        template = localized_conversation_response("country_typo_confirmation", body.language) or (
            'Did you mean "{country}"? Please confirm, or rephrase your question with the country name.'
        )
        answer = template.replace("{country}", probable_country)
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "fallback": False,
                "response_source": "market_typo_confirmation",
                "probable_country": probable_country,
            },
        )

    def _conversation_route_response(
        self,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
    ) -> ChatResponse | None:
        """Convert a high-confidence semantic route into controlled response copy."""
        metadata = retrieval_result.metadata or {}
        client_action = str(metadata.get("client_action") or "")
        intent = str(metadata.get("conversation_intent") or "knowledge")
        subtype = str(metadata.get("conversation_subtype") or "")

        if client_action == "open_support_form":
            return self.response_builder.fallback(
                localized_conversation_response("support_request", body.language)
                or "Opening the support request form.",
                correlation_id,
                metadata={
                    "fallback": False,
                    "response_source": "client_action",
                    "client_action": client_action,
                    "intent": "support_request",
                },
            )

        # The planner is advisory here, exactly as it is for assistant_meta below.
        # Asking what the rules prohibit is not a request to make the prohibited
        # claim, so a reviewed policy-safety question must never be short-circuited
        # into claim-refusal copy. Declining the shortcut removes no protection:
        # the deterministic guardrails already exempted this same question at input
        # governance, and retrieval, the evidence gate, output governance and the
        # validators all still run. The matcher is a strict whole-message match, so
        # an appended instruction or compound request does not qualify.
        if intent in {"medical_claim", "income_claim"} and is_policy_safety_question(body.message):
            return None

        response_key = ""
        if intent == "assistant_meta":
            # The planner is advisory. Reviewed exact phrases always produce
            # assistant identity/capability copy; a "thanks" classification is
            # additionally trusted on its own once it clears every guard in
            # is_planner_trusted_low_risk_subtype - see that function for why
            # only "thanks" is safe to trust without an exact phrase match.
            intent_confidence = float(metadata.get("intent_confidence") or 0.0)
            if classify_intent(
                body.message, body.language, relaxed_typo_tolerance=candidate_flags.wider_typo_tolerance
            ) == "assistant_meta" or is_planner_trusted_low_risk_subtype(
                body.message, intent, subtype, intent_confidence
            ):
                response_key = (
                    subtype
                    if subtype in {"greeting", "capability", "thanks", "wellbeing", "casual"}
                    else "capability"
                )
            else:
                intent = "off_topic"
                response_key = "off_topic"
        elif intent == "medical_claim":
            if candidate_flags.in_voice_guardrail:
                candidate = self._candidate_guardrail_phrasing(
                    "medical_claim", body.language, body.country, correlation_id
                )
                if candidate:
                    return self.response_builder.fallback(
                        candidate,
                        correlation_id,
                        metadata={
                            "intent": "medical_claim",
                            "fallback": False,
                            "response_source": "candidate_guardrail_phrasing",
                        },
                    )
            answer, claim_scope = localized_claim_response(body.message, intent, body.country, body.language)
            if answer:
                return self.response_builder.fallback(
                    answer,
                    correlation_id,
                    metadata={
                        "intent": claim_scope,
                        "fallback": False,
                        "response_source": "reviewed_claim_copy",
                    },
                )
            response_key = intent
        elif intent in {"income_claim", "off_topic"}:
            if candidate_flags.in_voice_guardrail:
                candidate = self._candidate_guardrail_phrasing(intent, body.language, body.country, correlation_id)
                if candidate:
                    return self.response_builder.fallback(
                        candidate,
                        correlation_id,
                        metadata={
                            "intent": intent,
                            "fallback": False,
                            "response_source": "candidate_guardrail_phrasing",
                        },
                    )
            response_key = intent
        if not response_key:
            return None

        answer = localized_conversation_response(response_key, body.language)
        if not answer:
            return None
        return self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "intent": intent,
                "fallback": False,
                "response_source": "semantic_route",
            },
        )

    def _route_or_approve_evidence(
        self,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        scrubbed_input: str,
        body: ChatRequest,
        correlation_id: str,
        candidate_flags: CandidateFlags = CandidateFlags(),
        history: str = "",
    ) -> tuple[ChatResponse | None, RetrievalResult, EvidenceDecision | None]:
        """Resolve semantic routes or enforce the evidence gate for knowledge requests."""
        routed_response = self._conversation_route_response(retrieval_result, body, correlation_id, candidate_flags)
        if routed_response:
            return routed_response, retrieval_result, None

        evidence_decision = approve_evidence(retrieval_query, retrieval_result, body.country, body.language)
        scope_query = self._scope_query(scrubbed_input, retrieval_query, history)
        if evidence_decision.approved and self._is_cross_market_local_evidence(scope_query, retrieval_result, body):
            # Incidental local candidates must not veto a valid global answer.
            # Reapprove global evidence alone; never let the local policy stand
            # in for the foreign country's rules, even in comparison requests.
            globals_only = [doc for doc in evidence_decision.evidence if doc.metadata.get("access_scope") == "global"]
            sources = [doc.to_source() for doc in globals_only]
            scoped_result = replace(
                retrieval_result, documents=globals_only, citations=sources,
                confidence=min(retrieval_result.confidence, confidence_from_sources(sources)),
                metadata={**retrieval_result.metadata, "strong_local_match": False},
            )
            evidence_decision = approve_evidence(retrieval_query, scoped_result, body.country, body.language)
            if not evidence_decision.approved:
                evidence_decision = replace(evidence_decision, reason="cross_market_local_evidence")
        approved_result = with_approved_evidence(retrieval_result, evidence_decision)
        if evidence_decision.approved:
            unsupported_years = unsupported_requested_years(body.message, approved_result.documents)
            if unsupported_years:
                template = localized_conversation_response("period_not_covered", body.language) or (
                    "The approved documents available to me do not contain information for {period}. "
                    "I cannot speculate about policy changes outside the documented period."
                )
                answer = format_period_not_covered(template, unsupported_years)
                fallback = self._validate_response(
                    self.response_builder.fallback(
                        answer,
                        correlation_id,
                        metadata={
                            "fallback": False,
                            "failure_layer": "document_period_not_covered",
                            "response_source": "period_scope_guard",
                            "requested_periods": unsupported_years,
                        },
                    ),
                    body,
                    correlation_id,
                )
                return fallback, approved_result, evidence_decision
            return None, approved_result, evidence_decision

        LOGGER.warning(
            "evidence_decision_rejected",
            correlation_id=correlation_id,
            country=body.country,
            language=body.language,
            role=body.role,
            **evidence_decision.to_metadata(),
        )
        clarification = self._directory_clarification_response(
            retrieval_result,
            body,
            correlation_id,
            scrubbed_input,
        )
        if clarification:
            return clarification, approved_result, evidence_decision
        if candidate_flags.narrowing_fallback:
            narrowing_response = self._candidate_narrowing_response(body, correlation_id, history)
            if narrowing_response:
                return narrowing_response, approved_result, evidence_decision
        if evidence_decision.reason == "cross_market_policy_request":
            fallback_message = self._cross_market_scope_message(
                body.language, body.message, body.country
            )
        else:
            fallback_message = self._insufficient_evidence_message(
                body.language, body.message, body.country
            )
        office_contact_addendum = self._office_contact_addendum(body, correlation_id)
        if office_contact_addendum:
            fallback_message = f"{fallback_message}\n\n{office_contact_addendum}"
        fallback = self._validate_response(
            self.response_builder.fallback(
                fallback_message,
                correlation_id,
                metadata={
                    "failure_layer": "evidence_gate",
                    "evidence_decision": evidence_decision.to_metadata(),
                    "office_contact_offered": bool(office_contact_addendum),
                },
            ),
            body,
            correlation_id,
            retrieval_result=approved_result,
        )
        return fallback, approved_result, evidence_decision

    def _scope_query(self, current: str, contextual: str, history: str) -> str:
        """Inherit a target only for dependent turns without an explicit new market."""
        if not find_market_mentions(current) and self._needs_history_context(current, history):
            return contextual
        return current

    def _is_cross_market_local_evidence(
        self,
        scrubbed_input: str,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
    ) -> bool:
        """Return true when the message asks about a market this session's own evidence cannot cover.

        Only the raw current-turn message is checked, not the history-expanded
        retrieval query - a topic-shift follow-up query merges in the prior
        question's own market (e.g. "delivery cost for Belgium? What about
        Canada?"), which would make this session's own market look mentioned
        too and mask the mismatch.
        """
        mentioned_markets = {code.upper() for code in find_market_mentions(scrubbed_input)}
        if not (mentioned_markets - {body.country.upper()}):
            return False
        if not retrieval_result.documents:
            return False
        return any(document.metadata.get("access_scope") != "global" for document in retrieval_result.documents)

    def _directory_clarification_response(
        self,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
        scrubbed_input: str,
    ) -> ChatResponse | None:
        """Ask for the missing directory detail when approved evidence is ambiguous.

        This is deliberately narrow: governance has already run, and the response
        is used only when the planner searched global directory content but could
        not approve a sufficiently clear answer. It never weakens guardrails or
        invents a country, office, phone number, or other contact value.
        """
        metadata = retrieval_result.metadata or {}
        if not metadata.get("global_documents_searched"):
            return None
        if not metadata.get("candidate_count") or not DIRECTORY_DETAIL_TERMS.search(body.message or ""):
            return None
        named_fields = {
            field_id for field_id, pattern in DIRECTORY_FIELD_TERMS.items() if pattern.search(body.message or "")
        }
        if len(named_fields) == 1:
            # The user already said which single field they want (e.g. "do you
            # have a telephone number?") - asking them to choose it again from
            # a list that includes what they just said isn't a real
            # clarification. Fall through to the normal insufficient-evidence
            # path instead.
            return None
        # These card prompts are questions the system asks on the reader's
        # behalf, so they must not depend on a reference being resolved a turn
        # later. They read "for that country", and a reader who asked about the
        # UK office and tapped "Telephone number" sent "What is the telephone
        # number for that country?" - answered with insufficient evidence,
        # because nothing in that sentence says which country. Naming the market
        # removes the dependency instead of trusting history to carry it.
        # Only a market the message itself resolves to is named. The request's
        # own country is deliberately not used as a fallback: the reported case
        # was a widget set to the United States asking about the UK office, and
        # naming the widget's country would have produced "What is the telephone
        # number for United States?" - a confident question about the wrong
        # market, which is worse than the unresolvable reference it replaces.
        mentioned = find_market_mentions(body.message or "")
        market_phrase = market_display_name(next(iter(mentioned))) if len(mentioned) == 1 else ""
        market_phrase = market_phrase or "that country"
        answer = (
            "I found approved directory information, but I need one more detail to answer accurately. "
            "Are you asking for the telephone number, business hours, email address, office address, "
            "website, or sponsoring information?"
        )
        response = self.response_builder.fallback(
            answer,
            correlation_id,
            metadata={
                "failure_layer": "directory_clarification",
                "response_source": "directory_clarification",
                "fallback": False,
            },
            cards=[
                {"id": card_id, "label": label, "prompt": prompt.format(market=market_phrase)}
                for card_id, label, prompt in (
                    ("directory-telephone", "Telephone number", "What is the telephone number for {market}?"),
                    ("directory-hours", "Business hours", "What are the business hours for {market}?"),
                    ("directory-email", "Email address", "What is the email address for {market}?"),
                    ("directory-address", "Office address", "What is the office address for {market}?"),
                    ("directory-website", "Website", "What is the website for {market}?"),
                    (
                        "directory-sponsoring",
                        "Sponsoring information",
                        "What sponsoring information is available for {market}?",
                    ),
                )
            ],
        )
        return response

    def _validate_response(
        self,
        chat_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
        model_response: ModelResponse | None = None,
        retrieval_result: RetrievalResult | None = None,
    ) -> ChatResponse:
        """Validate a chat response and return a safe fallback for critical failures."""
        result = self.output_validator.validate(
            ValidationContext(
                chat_response=chat_response,
                model_response=model_response,
                retrieval_result=retrieval_result,
                country=body.country,
                language=body.language,
                role=body.role,
                correlation_id=correlation_id,
            )
        )
        if result.issues:
            # An INCOMPLETE_OUTPUT verdict is a heuristic reading of the text,
            # but whether the model actually ran out of room is a fact Bedrock
            # reports. Logging them together separates a genuinely truncated
            # answer from a complete one the heuristic misjudged - the two need
            # opposite fixes, and telling them apart from the text alone is
            # guesswork. The token count and the cap are logged beside it so a
            # near-miss is visible without a second deploy.
            LOGGER.warning(
                "output_validator_issues_detected",
                correlation_id=correlation_id,
                issue_count=len(result.issues),
                highest_severity=result.highest_severity.value,
                finish_reason=(model_response.finish_reason if model_response else ""),
                # Which post-generation edits touched this answer. Nine steps
                # run between generation and here, several of which delete
                # text, and each records a flag when it fires. Naming them
                # beside the verdict identifies the step that damaged an answer
                # without putting any of the answer into the logs.
                answer_edits=[
                    name for name in _ANSWER_EDIT_FLAGS if (chat_response.metadata or {}).get(name)
                ],
                output_tokens=(
                    int((model_response.token_usage or {}).get("outputTokens") or 0)
                    if model_response
                    else 0
                ),
                max_output_tokens=settings.BEDROCK_MAX_OUTPUT_TOKENS,
                issues=[
                    {
                        "code": issue.code,
                        "severity": issue.severity.value,
                        "field": issue.field,
                        "message": issue.message[:500],
                    }
                    for issue in result.issues
                ],
            )
        # Recorded before any repair attempt, so ValidationHealth reflects what
        # the model produced rather than what repair rescued.
        record_validation_outcome(has_critical=result.has_critical())
        numeric_repair_attempt: dict[str, Any] | None = None
        if result.has_critical():
            critical_codes = {
                str(issue.code).upper()
                for issue in result.issues
                if issue.severity.value.upper() == "CRITICAL"
            }
            if (
                critical_codes
                and all(code == "NUMERIC_CLAIM_UNGROUNDED" for code in critical_codes)
                and retrieval_result is not None
                and retrieval_result.documents
            ):
                repaired_answer, removed_numbers = remove_unsupported_numeric_sentences(
                    chat_response.answer,
                    retrieval_result.documents,
                )
                numeric_repair_attempt = {
                    "answer": repaired_answer,
                    "removed": removed_numbers,
                    "documents": retrieval_result.documents,
                    "result": None,
                }
                if repaired_answer and repaired_answer != chat_response.answer:
                    repaired_response = ChatResponse(
                        answer=repaired_answer,
                        citations=self._citations_after_repair(
                            chat_response, repaired_answer, model_response, retrieval_result, body, correlation_id
                        ),
                        suggestions=chat_response.suggestions,
                        cards=chat_response.cards,
                        confidence=chat_response.confidence,
                        metadata={
                            **(chat_response.metadata or {}),
                            "numeric_claim_repair": True,
                            "removed_numeric_claims": removed_numbers,
                        },
                        correlation_id=chat_response.correlation_id,
                    )
                    repaired_result = self.output_validator.validate(
                        ValidationContext(
                            chat_response=repaired_response,
                            model_response=model_response,
                            retrieval_result=retrieval_result,
                            country=body.country,
                            language=body.language,
                            role=body.role,
                            correlation_id=correlation_id,
                        )
                    )
                    numeric_repair_attempt["result"] = repaired_result
                    if not repaired_result.has_critical():
                        # Sections are logged alongside the removed figures so a
                        # reviewer can check the removal against the evidence
                        # the answer was actually built from. Without them, a
                        # log line saying a number was deleted gives no way to
                        # tell a correct repair from the false positive this
                        # validator produced on 2026-09-07.
                        LOGGER.warning(
                            "output_validator_numeric_claims_repaired",
                            correlation_id=correlation_id,
                            removed_numeric_claims=removed_numbers,
                            removed_claim_count=len(removed_numbers),
                            # Whether each removed figure exists in the
                            # evidence at all. Absent means the model invented
                            # it and the removal was right; present means the
                            # figure was real and subject matching rejected it,
                            # so the reader lost a fact they asked for. The two
                            # need opposite fixes.
                            removal_diagnostics=removal_diagnostics(
                                chat_response.answer or "", retrieval_result.documents
                            ),
                            evidence_sections=[
                                str((document.metadata or {}).get("section_id") or "")
                                for document in retrieval_result.documents[:5]
                            ],
                        )
                        record_numeric_repair(len(removed_numbers))
                        _record_diagnostic_validation(
                            chat_response, result, "numeric_repair_accepted", numeric_repair_attempt
                        )
                        return self._with_validation_metadata(repaired_response, repaired_result)
            failure_layer = self._validation_failure_layer(result)
            LOGGER.warning(
                "output_validator_critical_fallback",
                correlation_id=correlation_id,
                issue_count=len(result.issues),
                highest_severity=result.highest_severity.value,
                failure_layer=failure_layer,
                critical_issue_codes=[
                    issue.code
                    for issue in result.issues
                    if issue.severity.value.upper() == "CRITICAL"
                ],
            )
            _record_diagnostic_validation(chat_response, result, "critical_fallback", numeric_repair_attempt)
            return self._with_validation_metadata(
                self.response_builder.fallback(
                    self._insufficient_evidence_message(body.language, body.message, body.country),
                    correlation_id,
                    metadata={"failure_layer": failure_layer},
                ),
                result,
            )
        _record_diagnostic_validation(chat_response, result, "no_critical_issue")
        return self._with_validation_metadata(chat_response, result)

    def _citations_after_repair(
        self,
        chat_response: ChatResponse,
        repaired_answer: str,
        model_response: ModelResponse | None,
        retrieval_result: RetrievalResult,
        body: ChatRequest,
        correlation_id: str,
    ) -> list[dict[str, object]]:
        """Citations for an answer numeric repair has just shortened.

        Citations were chosen from the model's text before repair deleted
        sentences from it, so a model answer's citations are chosen again for
        the text the reader receives. Fallback, refusal, narrowing and other
        controlled copy keeps the citations it was built with (normally none):
        re-choosing them would attach policy passages to a refusal whose
        numeric addendum repair removed.

        Choosing citations must never fail the answer. On any error the
        citations built before repair are kept and the error is logged.
        """
        metadata = chat_response.metadata or {}
        if (
            metadata.get("fallback")
            or metadata.get("failure_layer")
            or metadata.get("response_source", "model") != "model"
        ):
            return chat_response.citations
        try:
            return self.response_builder.reconcile_citations(
                built_answer=model_response.text if model_response is not None else chat_response.answer,
                delivered_answer=repaired_answer,
                citations=chat_response.citations,
                retrieval_result=retrieval_result,
                session_country=body.country,
            )
        except Exception:  # noqa: BLE001 - citation choice is best-effort and must never break the answer
            LOGGER.exception("citation_reconcile_failed", correlation_id=correlation_id)
            return chat_response.citations

    def _validation_failure_layer(self, result: ValidationResult) -> str:
        """Classify critical validation failures for diagnostics."""
        critical_codes = {
            str(issue.code).lower()
            for issue in result.issues
            if issue.severity.value.upper() == "CRITICAL"
        }
        if any("numeric" in code or "ground" in code for code in critical_codes):
            return "numeric_validator"
        if any("citation" in code for code in critical_codes):
            return "citation_validator"
        return "output_validator"

    def _with_validation_metadata(self, chat_response: ChatResponse, result: ValidationResult) -> ChatResponse:
        """Attach validation summary metadata without changing the public API response."""
        return ChatResponse(
            answer=chat_response.answer,
            citations=chat_response.citations,
            suggestions=chat_response.suggestions,
            cards=chat_response.cards,
            confidence=chat_response.confidence,
            metadata={
                **(chat_response.metadata or {}),
                "validation": validation_summary(result),
            },
            correlation_id=chat_response.correlation_id,
        )

    def _should_cache_response(self, chat_response: ChatResponse) -> bool:
        """Return true only for complete model answers that are safe to reuse."""
        metadata = chat_response.metadata or {}
        if metadata.get("fallback"):
            return False

        # Guardrail safety copy should be generated fresh and must never be
        # replayed as though it were a document-grounded policy response.
        if metadata.get("failure_layer") or metadata.get("response_source") in {"guardrail", "client_action"}:
            return False

        validation = metadata.get("validation")
        if isinstance(validation, dict) and str(validation.get("highestSeverity", "")).upper() == "CRITICAL":
            return False

        if float(chat_response.confidence or 0.0) < settings.BEDROCK_MIN_CONFIDENCE:
            return False

        return bool((chat_response.answer or "").strip())

    def _should_semantic_cache_response(self, chat_response: ChatResponse) -> bool:
        """Require strong, cited evidence before an answer can be reused semantically."""
        return (
            self._should_cache_response(chat_response)
            and bool(chat_response.citations)
            and float(chat_response.confidence or 0.0) >= settings.SEMANTIC_CACHE_MIN_CONFIDENCE
        )

    def _cache_response(
        self,
        cache_key: str,
        retrieval_query: str,
        retrieval_result: RetrievalResult,
        chat_response: ChatResponse,
        body: ChatRequest,
        correlation_id: str,
    ) -> None:
        """Write exact cache and the more restrictive semantic cache."""
        if not self._should_cache_response(chat_response):
            LOGGER.info(
                "cache_write_skipped",
                correlation_id=correlation_id,
                reason="unsafe_or_low_confidence_response",
            )
            return
        cache_value = chat_response.to_cache_value()
        cache_value["evidence"] = serialize_evidence(retrieval_result)
        set_cache_value(cache_key, cache_value, correlation_id)
        if self._should_semantic_cache_response(chat_response):
            set_semantic_cache_value(
                retrieval_query,
                body.country,
                body.language,
                body.role,
                retrieval_result,
                cache_value,
                correlation_id,
            )


ai_orchestrator = AIOrchestrator()
