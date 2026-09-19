"""Phase 2 Lane F: complete an approved contact recommendation.

Both defects fixed here were reproduced through the real, existing
machinery - :func:`app.orchestrator.chat_orchestrator.AIOrchestrator.
_apply_support_contact_supplement` and
:func:`utils.directory_fields.build_support_contact_supplement` - not
guessed at. See ``docs/conversation-quality/phase2/CONTACT_COMPLETION.md``
for the full reproduction notes; the short version:

1. **Multilingual "recommends contact" detection was English-only.**
   ``_CARE_CONTACT_RECOMMENDATION_RE`` in ``chat_orchestrator.py`` only
   matches English phrasing ("contact customer care", "reach out to
   support", ...). An answer that recommends contacting an office entirely
   in French, German, Spanish, Dutch, Italian, Portuguese, Finnish,
   Swedish or Norwegian never matched it, so the support-contact
   supplement never fired for those answers - reproduced for all nine
   languages with the real orchestrator, mocking only the Comprehend PII
   boundary (see ``tests/conversation/test_contact_completion_multilingual.py``).
   :func:`recommends_contact_in_language` adds ONE bounded, documented
   per-language vocabulary table (mirroring the shape and narrowness of the
   existing English regex - a verb phrase plus a customer-care/support/
   office noun phrase, not a loose keyword list) for exactly those nine
   languages. It deliberately does not attempt every world language: an
   unrecognised or unlisted language returns ``False`` (append nothing)
   rather than guess.

2. **A fax-only record's contact detail was silently dropped.**
   ``build_support_contact_supplement`` only ever picks a phone, an email
   or a website (business hours only when explicitly requested); a record
   whose only approved contact field is a fax number produces no
   supplement at all - reproduced end-to-end: a Kenya record carrying only
   ``{"Fax": "+254 20 999999"}`` with a "please contact customer care"
   answer leaves the answer unchanged and sets only
   ``support_contact_unavailable`` in the metadata, even though the
   evidence *did* carry an approved contact detail (see
   ``tests/conversation/test_contact_completion_fax_fallback.py``).
   :func:`build_contact_supplement_with_fax_fallback` wraps the existing
   function and, only when it returns ``None`` because nothing else
   qualified, offers a fax value as a last resort - never in place of a
   phone/email/website that already qualified, and never when no fax
   value is present either.

Both requirements below were probed and found to already hold, so no code
change was made for them (see the same doc for the reproduction):

- an order phone is never presented as the office/customer-care phone
  (``utils.directory_fields.build_support_contact_supplement`` already
  keeps only one phone kind, preferring whichever the record labels
  ``phone``/``telephone`` over ``order_phone``);
- a sponsoring-directory contact may be used from any session country
  while a company-policy fact stays restricted to the session's own
  market (``app.evidence.approve_evidence``'s ``access_scope == "global"``
  exemption from ``_names_another_market``).

This module is pure and has no orchestrator, retrieval, model or network
dependency, per the Lane F ownership rules in
``docs/conversation-quality/TASK_BOARD.md`` (Phase 2). Wiring it into
``app/orchestrator/chat_orchestrator.py`` - the sole writer of that file -
is delivered as a patch under
``docs/conversation-quality/phase2/patches/``, not as a direct edit.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.response.outcome import ConversationOutcome, OutcomeKind
from app.response.quality import contact_for_country
from config.directory_field_vocabulary import normalize_language_code
from utils.directory_fields import build_support_contact_supplement

# One bounded, documented vocabulary per non-English language this project
# already ships localized support-contact labels for
# (``utils.directory_fields._SUPPORT_CONTACT_LABEL_TRANSLATIONS``) plus
# Finnish and Norwegian, which the coordinator's brief names explicitly.
# English is deliberately absent: the orchestrator's own
# ``_CARE_CONTACT_RECOMMENDATION_RE`` already owns English detection, and
# duplicating it here would create the "scattered English list" the brief
# asks this module to avoid. Each pattern mirrors that regex's shape - a
# verb phrase ("contact", "reach out to", "get in touch with", "speak to")
# followed by a customer-care/support/office noun phrase - translated by a
# fluent-enough reviewer pass, not machine-expanded from a word list, so a
# plain informational sentence in the same language (no recommendation to
# contact anyone) is not expected to match. Diacritics are written exactly
# as used in normal prose; matching is case-insensitive.
_RECOMMENDS_CONTACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "fr": re.compile(
        r"\b(?:contactez|contacter|veuillez\s+contacter|"
        r"(?:adressez[- ]vous|s['’]adresser)\s+(?:à|au))\b[^.?!]{0,40}?"
        r"\b(?:service\s+client|assistance|support|bureau)\b",
        re.IGNORECASE,
    ),
    "de": re.compile(
        r"\b(?:kontaktieren\s+sie|wenden\s+sie\s+sich\s+an|wenden\s+sie\s+sich)\b[^.?!]{0,40}?"
        r"\b(?:kundenservice|kundendienst|support|büro)\b",
        re.IGNORECASE,
    ),
    "es": re.compile(
        r"\b(?:contacte|contactar|póngase\s+en\s+contacto\s+con|"
        r"comuníquese\s+con)\b[^.?!]{0,40}?"
        r"\b(?:atención\s+al\s+cliente|servicio\s+al\s+cliente|soporte|oficina)\b",
        re.IGNORECASE,
    ),
    "nl": re.compile(
        r"\b(?:contact\s+op(?:nemen)?|neem\s+contact\s+op)\b[^.?!]{0,40}?"
        r"\b(?:klantenservice|klantendienst|ondersteuning|support|kantoor)\b",
        re.IGNORECASE,
    ),
    "it": re.compile(
        r"\b(?:contattare|contatti|si\s+rivolga\s+a)\b[^.?!]{0,40}?"
        r"\b(?:servizio\s+clienti|assistenza\s+clienti|supporto|ufficio)\b",
        re.IGNORECASE,
    ),
    "pt": re.compile(
        r"\b(?:contate|contatar|entre\s+em\s+contato\s+com)\b[^.?!]{0,40}?"
        r"\b(?:atendimento\s+ao\s+cliente|suporte|escritório)\b",
        re.IGNORECASE,
    ),
    "fi": re.compile(
        r"\bota(?:kaa)?\s+yhteyttä\b[^.?!]{0,40}?"
        r"\b(?:asiakaspalvelu\w*|tuke\w*|toimisto\w*)\b",
        re.IGNORECASE,
    ),
    "sv": re.compile(
        r"\bkontakta\b[^.?!]{0,40}?"
        r"\b(?:kundtjänst\w*|support\w*|kontoret)\b",
        re.IGNORECASE,
    ),
    "no": re.compile(
        r"\b(?:kontakt(?:e)?|ta\s+kontakt\s+med)\b[^.?!]{0,40}?"
        r"\b(?:kundeservice\w*|support\w*|kontoret)\b",
        re.IGNORECASE,
    ),
}

# Fable review, 2026-09-18 (finding F1): "Il n'est pas necessaire de
# contacter le service client" ("It is not necessary to contact customer
# care") still matches the pattern above - "contacter" plus "service
# client" are both present - and previously returned True, recommending a
# contact that the sentence actually says is unnecessary. This is the same
# defect the English ``_CARE_CONTACT_RECOMMENDATION_RE`` already has and
# already discloses (parity, not a new gap), but it is cheap and safe to
# close here: each language's ordinary clause-level negation word ("pas",
# "nicht", "no", "niet", "non", "nao", "inte", "ikke" - Finnish "ei" is
# listed too for the same reason, though no realistic Finnish negation of
# this module's imperative-mood pattern has been found) is a single closed,
# common word, so checking "does this exact negation word appear earlier in
# the SAME CLAUSE (the run of text between sentence-ending punctuation) as
# the matched verb phrase" is a small, bounded, clause-local check - not an
# attempt at general negation handling, which would need real parsing this
# module deliberately does not do. A negation word appearing in an EARLIER
# or LATER sentence never counts, so "Contact support today. It is not a
# problem." still returns True for the first sentence's recommendation.
#
# KNOWN LIMITATION (see tests/conversation/test_p2fix_reference_contact_edges.py
# ``test_negation_of_an_unrelated_earlier_clause_is_a_known_limitation``):
# clauses are split only on ".", "!", "?", not on commas, so a negation
# word that grammatically modifies an earlier, comma-separated clause of
# the SAME sentence can still suppress a later, genuinely unnegated
# recommendation in that sentence ("Der Kundenservice ist nicht
# telefonisch erreichbar, aber kontaktieren Sie das Buro." wrongly reports
# False). Accepted cost of keeping this guard cheap and closed rather than
# building real clause/dependency parsing.
_NEGATION_WORDS: dict[str, frozenset[str]] = {
    "fr": frozenset({"pas", "jamais"}),
    "de": frozenset({"nicht", "kein", "keine"}),
    "es": frozenset({"no", "nunca"}),
    "nl": frozenset({"niet", "geen"}),
    "it": frozenset({"non", "mai"}),
    "pt": frozenset({"nao", "não", "nunca"}),
    "fi": frozenset({"ei"}),
    "sv": frozenset({"inte", "aldrig"}),
    "no": frozenset({"ikke", "aldri"}),
}


def _clause_span(text: str, index: int) -> tuple[int, int]:
    """Start/end offsets of the sentence in ``text`` containing ``index``."""
    start = 0
    for sep in re.finditer(r"[.!?]", text):
        if sep.start() >= index:
            break
        start = sep.end()
    end_match = re.search(r"[.!?]", text[index:])
    end = index + end_match.start() if end_match else len(text)
    return start, end


def _negated_before(text: str, match_start: int, language_code: str) -> bool:
    """True when a closed-class negation word for ``language_code`` appears
    earlier in the same clause as the recommendation match at ``match_start``.
    """
    negation_words = _NEGATION_WORDS.get(language_code)
    if not negation_words:
        return False
    clause_start, _clause_end = _clause_span(text, match_start)
    preceding_text = text[clause_start:match_start]
    preceding_tokens = re.findall(r"[^\W_]+", preceding_text, flags=re.UNICODE)
    return any(token.casefold() in negation_words for token in preceding_tokens)


def recommends_contact_in_language(answer: str, language: str) -> bool:
    """True when ``answer`` recommends contacting an office/care channel.

    Only checks the bounded per-language table above. A language this
    module has no reviewed pattern for - including English, whose
    detection stays owned by the orchestrator's own regex, and anything
    unrecognised - returns ``False``: this function never guesses a
    recommendation from an unreviewed language, matching the "fail
    conservatively" rule for unknown languages. The language tag itself is
    normalized the same way Lane B's directory-field vocabulary normalizes
    one (Fable review, 2026-09-18, finding F1), so a region-tagged code
    such as "fr-FR" is recognized the same as "fr".
    """
    language_code = normalize_language_code(language)
    pattern = _RECOMMENDS_CONTACT_PATTERNS.get(language_code)
    if pattern is None:
        return False
    match = pattern.search(answer or "")
    if match is None:
        return False
    return not _negated_before(answer or "", match.start(), language_code)


# Mirrors utils.directory_fields._FIELD_LABEL_PATTERNS["fax"] - kept local
# (rather than importing a private name from a read-only-for-this-lane
# module) so this fallback does not silently drift if that pattern is ever
# narrowed or widened without this file being reviewed too.
_FAX_LABEL_RE = re.compile(r"^fax(?:\s*\d+)?$", re.IGNORECASE)
# Every language utils.directory_fields._SUPPORT_CONTACT_LABEL_TRANSLATIONS
# reviews (nl, fr, de, es, it, pt, sv) maps "fax" to the same literal word;
# Finnish and Norwegian use it unchanged too, so one label instead of a
# real per-language table is a deliberate, verified simplification, not an
# oversight - unlike the phone/email/website labels above, which do change
# per language and stay in that reviewed table, not this one.
_FAX_LABEL = "Fax"


def build_contact_supplement_with_fax_fallback(
    answer: str,
    approved_fields: dict[str, object],
    recommends_customer_care: bool,
    *,
    hours_requested: bool = False,
    language: str = "en",
) -> tuple[str, list[str]] | None:
    """Wrap :func:`build_support_contact_supplement` with a fax-only fallback.

    The wrapped function already prefers a phone, then an email/website,
    then (only if requested) business hours; it never picks a fax number.
    That is correct whenever anything else qualified - a fax line must
    never crowd out a phone or email - but when NOTHING else qualified and
    ``approved_fields`` carries a fax value, the approved evidence still
    has a usable contact detail that would otherwise be silently dropped
    (``support_contact_unavailable``), which understates what evidence
    actually contains. This never invents a fax number: it only surfaces
    one already present in ``approved_fields``, under its own "Fax" label
    (never as a phone), and only as a last resort.
    """
    primary = build_support_contact_supplement(
        answer,
        approved_fields,
        recommends_customer_care,
        hours_requested=hours_requested,
        language=language,
    )
    if primary is not None or not recommends_customer_care:
        return primary

    for raw_label, raw_value in approved_fields.items():
        label = str(raw_label).strip()
        value = str(raw_value).strip()
        if not label or not value:
            continue
        if _FAX_LABEL_RE.match(" ".join(label.split())):
            return f"{_FAX_LABEL}: {value}", [_FAX_LABEL]
    return None


# --- Phase 3 Lane 3: contact_escalation -------------------------------
#
# docs/conversation-quality/phase3/CX_LANES.md's ConversationOutcome-driven
# rendering layer. This offers the reviewed public contact (never a private
# per-market directory record - see ``_public_contact_value`` below) for the
# small set of outcome kinds where a reader who did not get a full answer
# should be pointed at customer care, without ever duplicating a contact the
# answer already carries.

# Outcome kinds this function ever renders a contact_offer for. Deliberately
# excludes safety_refusal and clarification per the Lane 3 brief: a refusal
# is not softened by an unrelated contact offer, and a clarification
# question is not yet a dead end. dependency_unavailable and cross_market_policy
# are included but still fall through to "no reviewed contact" -> None when
# ``country`` has none configured (config/public_contacts.json only lists a
# "default" plus specific markets).
_ESCALATION_KINDS = frozenset(
    {
        OutcomeKind.EVIDENCE_MISSING,
        OutcomeKind.PERSONAL_ACCOUNT,
        OutcomeKind.DEPENDENCY_UNAVAILABLE,
        OutcomeKind.PARTIAL_ANSWER,
        OutcomeKind.CROSS_MARKET_POLICY,
    }
)


def _public_contact_value(contacts: dict[str, str]) -> str | None:
    """Pick one reviewed public-contact value to fill the ``{contact}``
    placeholder, in the same phone-then-website preference
    ``build_support_contact_supplement`` already uses for the approved
    per-record contact block (phone first, then email/website) - this never
    adds a new preference order, it only applies the existing one to the
    smaller ``contact_for_country`` shape (``customerCarePhone`` /
    ``website``; see ``config/public_contacts.json``).
    """
    phone = contacts.get("customerCarePhone")
    if phone:
        return phone
    website = contacts.get("website")
    if website:
        return website
    return None


def _public_contact_already_present(answer_text: str, contacts: dict[str, str]) -> bool:
    """True when the reviewed public-contact value already appears verbatim
    in ``answer_text``. A pure substring check (language-independent, unlike
    :func:`recommends_contact_in_language`, which only recognizes a
    RECOMMENDATION sentence in nine languages) so a phone/website already
    quoted for ANY reason - including one the orchestrator's own
    ``_apply_support_contact_supplement`` already appended earlier this
    turn - is never duplicated here, regardless of the answer's language.
    """
    if not answer_text:
        return False
    for value in contacts.values():
        if value and value in answer_text:
            return True
    return False


def contact_escalation(
    outcome: ConversationOutcome,
    *,
    country: str,
    language: str,
    answer_text: str,
    render: Callable[..., str],
) -> str | None:
    """Return a rendered ``contact_offer`` sentence, or ``None``.

    Renders the ``contact_offer`` message key (Lane 4) with ``{contact}``
    filled from the existing reviewed public-contact source for the SESSION
    market (``country`` - reused via :func:`app.response.quality.contact_for_country`,
    never a new contact source): for ``cross_market_policy`` this means the
    session's own support contact, never the other market named in the
    question, matching the Lane 3 brief.

    Never renders for an outcome kind outside :data:`_ESCALATION_KINDS`
    (never for ``safety_refusal`` or ``clarification``), never when
    ``country`` has no reviewed public contact at all (a missing contact
    returns ``None``, never a placeholder), never for ``partial_answer``
    when nothing was actually left unsupported
    (``outcome.fields_unsupported`` empty), and never when ``answer_text``
    already recommends or already contains that contact - reusing
    :func:`recommends_contact_in_language` (an existing recommendation this
    module already detects, in the languages it knows) and a plain
    substring check (:func:`_public_contact_already_present`, language
    independent) so a duplicate contact is never appended after the
    orchestrator's own ``_apply_support_contact_supplement`` step already
    added one.

    ``render`` is the injected ``render(key, language, **placeholders) ->
    str`` callable Lane 4 owns; this module never inlines English copy.
    """
    if outcome.kind not in _ESCALATION_KINDS:
        return None
    if outcome.kind == OutcomeKind.PARTIAL_ANSWER and not outcome.fields_unsupported:
        return None

    contacts = contact_for_country(country)
    contact_value = _public_contact_value(contacts)
    if not contact_value:
        return None

    if _public_contact_already_present(answer_text, contacts):
        return None
    if recommends_contact_in_language(answer_text or "", language):
        return None

    return render("contact_offer", language, contact=contact_value)
