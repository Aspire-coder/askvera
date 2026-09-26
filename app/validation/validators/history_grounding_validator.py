"""Catch prose facts pulled from conversation history rather than this turn's evidence.

Live, reproduced twice (correlation ids 35aec7ae-7d03-4dba-9755-22b7b04e4d85 and
4cb3d453-9629-492d-81bd-5c1be4ddbf31): a US session's third turn asked "Is this
the whole contract or are there other documents?" Retrieval returned exactly
one document, a global sponsoring-directory record; the US Company Policy was
never retrieved. The model answered anyway, quoting section 18.01(c)'s "entire
contract" language and listing sections 19, 20 and 21 - content that was in the
conversation history from an earlier turn, not in this turn's evidence.
``NumericGroundingValidator`` catches a figure invented this way; it has
nothing to say about prose.

This validator runs the same kind of sentence-coverage check
``app.evidence_contract`` uses for a declared claim list, but against this
turn's retrieved evidence text directly, and only when that evidence is
structurally thin or off-target for a policy answer (see
``_evidence_lacks_policy_document``). Outside that shape it does not run at
all: a well-evidenced answer, or a directory answer legitimately grounded in
a directory record's own fields, is untouched.

It never attempts a partial repair. Unlike numeric grounding, which strips
just the unsupported figure's sentence, a wrong "removal is safe only if what
remains is coherent" call is exactly what produced the P014 half-emptied
list. Flagging this CRITICAL under its own code, distinct from
``NUMERIC_CLAIM_UNGROUNDED``, means the orchestrator's existing repair path
(which only fires when every critical issue is a numeric one) is skipped and
the answer goes to the ordinary insufficient-evidence fallback instead -
never a partially stripped answer.

Canary fix (2026-09-25, retrieval_canary.json case
chained-followup-market-continuity): a production run on a three-turn
Belgium/Germany sponsoring conversation ("How do I sponsor someone in
Belgium?", "What about Germany?", "Tell me more.") showed this validator
firing wrongly, in two distinct ways this fix closes:

1. It fired on TURN 0, where no history exists at all, against an ordinary
   sentence ("The team can walk you through the sponsoring process and
   answer your questions about qualifications and next steps.") that simply
   is not covered by thin directory-only evidence - not because the model
   copied it from an earlier turn, since there was no earlier turn to copy
   from. The validator never actually checked that a flagged sentence came
   from history; it only checked that this turn's evidence did not cover
   it, which is also true of every generic connective/offer sentence a
   legitimate directory answer contains.
2. On the final turn, it fired against "What specific information would you
   like to know more about?" and "Please let me know what would be most
   helpful, and I'll provide the details from our approved resources." -
   a clarifying question and a forward-looking offer, neither of which
   asserts a fact at all, let alone one only history states.

Fix: ``ValidationContext`` now carries ``conversation_history`` (threaded
from the call site that already has the session's history text; empty by
default). This validator returns immediately when it is empty or
whitespace-only - turn 0 can never have a history-sourced claim - and
otherwise flags a sentence only when it is BOTH (a) not covered by this
turn's evidence (the original check) AND (b) IS covered by the conversation
history text itself (:func:`app.evidence_contract.answer_sentences_covered_by`,
the same token-coverage machinery run against history instead of evidence),
so an uncovered-but-also-not-in-history sentence (case 1 above) is left
alone. A sentence that ends in a question mark - checked language-agnostically
via terminal "?"/full-width "？"/Arabic "؟", or a Spanish sentence opening
with "¿" - is also never flagged (case 2 above): a question asserts no fact,
so it cannot be a fact copied from history, however much vocabulary it
happens to share with an earlier turn.

Review round 1 follow-up (2026-09-25): the fix above compared a flagged
sentence against the WHOLE history text, including the user's own turns.
That reopened a third false-positive class this validator must not produce:
a model answer that legitimately restates the user's own earlier question
("How do I sponsor someone in Belgium?" -> "To sponsor someone in
Belgium...") shares plenty of vocabulary with that user turn and would be
wrongly flagged, even though nothing was copied from an earlier ASSISTANT
answer - this validator's actual purpose (see the module docstring's opening
paragraphs; the reproduced failure copied prose the ASSISTANT stated in
history, not the user). :func:`_assistant_text` now parses the formatted
history (``services/session.py``'s ``append_session_turn``/``_format_history``
shape: a sequence of "user: <text>"/"vera: <text>" turns, where a line
that does not start a new "user:"/"vera:"/"assistant:" turn is a
continuation of a multi-line assistant answer) and returns only the
concatenated text of "vera:"/"assistant:" turns. Coverage is now checked
against that assistant-only text; if a history has no assistant turn at all
(e.g. malformed or user-only text), this validator returns without flagging,
the same conservative default as no history at all.

Canary fix, third mode (2026-09-26, same retrieval_canary.json case
chained-followup-market-continuity): a production deploy of main 65dbb74
rolled back because the blocking live canary's "Tell me more." turn was
turned into the insufficient-evidence fallback by this validator
(``output_validator_critical_fallback``, failure_layer history_grounding).
Retrieval was right (Forever Germany, confidence 0.95, evidence approved);
the one flagged sentence was "**Getting started** – how the business
opportunity works, or sponsoring someone" - a generic menu/option line the
model repeated from its OWN previous assistant turn. It passes both existing
checks (uncovered by the Germany directory record, covered by assistant
history, not a question), yet asserts no market fact at all, so blocking the
whole answer - and losing the Germany directory details with it - was wrong.

Fix: a history-sourced MENU LINE (:func:`_is_menu_line` - structurally a
bullet or numbered item whose text opens with a bold "**label**" followed by
a dash or colon, the exact shape of the line that failed live and of a menu
of options in any language) is now flagged only when it also carries a
*specific fact marker* that could mislead about this turn's market
(:func:`_carries_specific_fact`): a digit (numbers, section refs, amounts,
phone numbers, dates), a currency symbol or ISO code, an email/URL marker,
or a market/country name (resolved through the repo's shared, alias-driven
``services.market_config.find_market_mentions`` - the configured names and
their localized aliases, whole-name and casefolded, never a new country
list; an inflected or adjectival form such as "Belgian", "belgische" or
"В Бельгии" is NOT recognised, so it is not a marker). A menu line with none
of these is a generic option line and is left alone. Every other sentence -
prose, a plain bullet, a bare bold-label line - keeps the previous treatment
whether or not it carries a marker: the directory-contact-route REJ1 case
(tests/unit/test_directory_contact_route.py) relies on a marker-free
sentence that inverts a record's note ("...is not taking on any fresh
applicants...") still being caught, and the adversarial review of this fix
(2026-09-26) showed that same inverted note delivered as "- ..." or
"**Note**: ..." once plain bullets and bold labels were exempted, so the
exemption is confined to the one shape that actually failed live.
Everything still flagged keeps the CRITICAL severity and the fallback path
above; ``unsupported_answer_sentences``' thresholds are untouched. The
accepted residual: a digit-free, market-free, contact-free menu line copied
from history is now delivered even if it happens to state a policy fact.
"""

from __future__ import annotations

import re
import unicodedata

from app.evidence_contract import answer_sentences_covered_by, unsupported_answer_sentences
from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity
from app.validation.validators.numeric_grounding_validator import _AMBIGUOUS_CODE_WORDS, _ROLE_CURRENCY_CODES
from services.market_config import find_market_mentions

# Role labels services/session.py's formatted history uses to start a new
# turn ("user:") or a new assistant turn ("vera:"/"assistant:" - the second
# spelling is accepted too so this parser is not brittle to a future rename).
# Matched case-insensitively against the text before a line's first ":",
# stripped of surrounding whitespace.
_USER_ROLE_LABELS = frozenset({"user"})
_ASSISTANT_ROLE_LABELS = frozenset({"vera", "assistant"})


def _assistant_text(history: str) -> str:
    """Return only the concatenated text of assistant ("vera:") turns.

    ``history`` is the formatted text ``services/session.py``'s
    ``_format_history`` produces: one "user: <text>" or "vera: <text>" line
    per stored turn. A stored assistant answer can itself contain embedded
    newlines (a multi-paragraph reply); a continuation line - one that does
    not itself start with a recognized "user:"/"vera:"/"assistant:" role
    label - belongs to whichever turn most recently started, never to a new,
    unlabeled turn of its own. A line is a genuine continuation, not a new
    turn, by construction (not a keyword list): a role line's own text can
    still legitimately begin with a lookalike phrase (e.g. an assistant
    answer stating "Note: see section 5"), so what determines a continuation
    is where the label appears - the text before a line's OWN first ":",
    stripped and case-folded - being exactly one of the recognized labels.
    """
    current_is_assistant = False
    assistant_parts: list[str] = []
    for line in (history or "").split("\n"):
        label, separator, rest = line.partition(":")
        role = label.strip().casefold()
        if separator and role in _USER_ROLE_LABELS:
            current_is_assistant = False
        elif separator and role in _ASSISTANT_ROLE_LABELS:
            current_is_assistant = True
            assistant_parts.append(rest.strip())
        elif current_is_assistant:
            # A continuation line of the assistant turn most recently opened.
            assistant_parts.append(line.strip())
        # Any line before the first recognized role label (malformed input)
        # has nothing to attach to and is dropped, the same as it would be if
        # it were a user-turn continuation.
    return " ".join(part for part in assistant_parts if part)


# Terminal question-mark variants recognized without depending on any single
# language's grammar: ASCII "?", the full-width CJK "？", and the Arabic "؟".
# An opening Spanish inverted question mark ("¿...") is also checked, since a
# Spanish interrogative sentence may itself be only one clause of a longer,
# already-split sentence and not always end on "?" within the checked span.
_QUESTION_TERMINATORS = ("?", "？", "؟")
_SPANISH_INVERTED_QUESTION_MARK = "¿"


def _is_interrogative_sentence(sentence: str) -> bool:
    """True for a question, language-agnostically - it asserts no fact to ground.

    Checked structurally (terminal punctuation, or a leading Spanish "¿"),
    never by matching question words in any one language, the same
    discipline the rest of this module and ``app.evidence_contract`` use.
    """
    stripped = sentence.strip()
    if not stripped:
        return False
    if stripped.startswith(_SPANISH_INVERTED_QUESTION_MARK):
        return True
    return stripped.rstrip("\"'”’)]").endswith(_QUESTION_TERMINATORS)


# Fact markers (module docstring, third mode). Each is checked structurally,
# never by an English word list:
# - a digit, in any script (str.isdigit covers non-ASCII digits too);
# - a currency symbol (Unicode category "Sc": "$", "€", "£", "¥", "₽" ...) or
#   an ISO 4217 code written the way prose writes one, as an upper-case
#   whole token ("EUR", "USD"); the code set is the one
#   ``NumericGroundingValidator`` already maintains, minus the codes that
#   spell an ordinary word ("try", "pen" ...), and the upper-case requirement
#   also keeps a French "ils" (ILS) from ever counting;
# - an email/URL marker ("@", "http", "www.");
# - a market/country name, via the shared alias-driven whole-name matcher
#   ``services.market_config.find_market_mentions``.
_CURRENCY_CODES = _ROLE_CURRENCY_CODES - _AMBIGUOUS_CODE_WORDS
_UPPER_CODE_TOKEN_RE = re.compile(r"(?<![^\W\d_])([A-Z]{3})(?![^\W\d_])")
_CONTACT_MARKER_RE = re.compile(r"@|http|www\.", re.IGNORECASE)


def _carries_specific_fact(sentence: str) -> bool:
    """True when a sentence states something specific enough to mislead about a market.

    A history-sourced menu line that carries none of these markers is a
    generic option line which asserts no market fact, so repeating it
    from an earlier assistant turn is harmless and must not cost the reader
    the whole answer (module docstring, third mode). Anything with a marker
    keeps the original treatment.
    """
    if any(character.isdigit() for character in sentence):
        return True
    if any(unicodedata.category(character) == "Sc" for character in sentence):
        return True
    if any(match.group(1).lower() in _CURRENCY_CODES for match in _UPPER_CODE_TOKEN_RE.finditer(sentence)):
        return True
    if _CONTACT_MARKER_RE.search(sentence):
        return True
    return bool(find_market_mentions(sentence))


# The shape of a menu/option line, judged structurally (markdown, not any
# language's words): a bullet ("-", "*", "•") or a numbered marker ("1.",
# "1)", "(1)") AND, right after it, a bold "**label**" followed by a dash or
# colon - the live failure's "- **Getting started** – how the business
# opportunity works, or sponsoring someone". Both parts are required: the
# 2026-09-26 adversarial review showed a directory note inverted as a plain
# bullet ("- This office accepts new sponsoring applications ...") or as a
# bare bold-label line ("**Note**: the office is currently accepting ...")
# slipping through when either shape alone was exempted, so those keep the
# previous treatment. Deliberately not an en/em dash as the list marker,
# which French and Russian prose also use as a quotation dash, nor a letter
# marker ("a."), which is also an initial. ``utils.sentence_spans`` hands
# such a line through as its own sentence, marker included, so the marker is
# checked on the sentence text itself.
_LIST_MARKER_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\(?\d{1,3}[.)])\s+", re.UNICODE)
_MENU_LINE_RE = re.compile(r"^\s*(?:[-*•]|\(?\d{1,3}[.)])\s+\*\*[^*\n]+\*\*\s*[-–—:]", re.UNICODE)


def _is_menu_line(sentence: str) -> bool:
    """True for a bullet or numbered item that opens with a bold label and a dash/colon - a menu of options."""
    return bool(_MENU_LINE_RE.match(sentence))


def _list_item_text(sentence: str) -> str:
    """The item without its leading bullet/number marker, so "1." is never read as a fact."""
    return _LIST_MARKER_PREFIX_RE.sub("", sentence, count=1)


# Mirrors the check `app.prompts.builder._is_global_directory_record` uses to
# decide a retrieved document is a directory record rather than company
# policy. Duplicated locally, the same way `app.prompts.builder` duplicates it
# instead of importing the retrieval provider, so validation does not depend
# on retrieval internals either.
_DIRECTORY_DOCUMENT_TYPES = frozenset({"office_directory", "international_sponsoring_directory"})


def _is_directory_document(document: object) -> bool:
    """True for a directory/sponsoring record - never company policy prose.

    Deliberately narrower than the notion of "current-locale evidence" that
    gates retrieval approval (``app.evidence._has_current_locale_document``):
    that check treats a global document as approved evidence as long as it is
    not literally labelled ``document_type == "policy"``, which is exactly how
    a global sponsoring-directory record stood in for a locale policy answer
    in the reproduced failure - it was "evidence" by that test, just not
    evidence of the right kind. This check asks the opposite, stricter
    question directly: does this record actually carry directory/sponsoring
    metadata (``directory_kind`` or a known directory ``document_type``)? A
    document with neither marker is treated as policy-like prose, whether or
    not it happens to carry an explicit ``document_type: "policy"`` label -
    most retrieved policy sections in this corpus carry no ``document_type``
    at all, so requiring that label positively would silently stop matching
    the moment a caller retrieves an ordinary, unlabeled policy section.
    """
    metadata = getattr(document, "metadata", None) or {}
    return metadata.get("document_type") in _DIRECTORY_DOCUMENT_TYPES or bool(metadata.get("directory_kind"))


def _evidence_lacks_policy_document(documents: list) -> bool:
    """True when this turn's evidence is structurally unfit to ground a policy answer.

    Judged by document type and scope, never by matching words in any
    language: every retrieved document is a directory/sponsoring record and
    none of them is anything else - the exact shape of the reproduced failure
    (one global sponsoring-directory record standing in for a locale policy).
    A turn that retrieved even one non-directory document, however thin the
    evidence otherwise, is left alone: it may be an unlabeled policy section,
    and the sentence-coverage check below is what decides whether the answer
    is actually grounded in it. A directory-only turn answering a directory
    question is also left alone in effect, since its answer will legitimately
    overlap the directory record's own text and the coverage check will not
    flag it.
    """
    return bool(documents) and all(_is_directory_document(document) for document in documents)


def documents_are_directory_only(documents: list) -> bool:
    """Public wrapper for :func:`_evidence_lacks_policy_document`.

    Same predicate this validator gates on - every retrieved document is a
    directory/sponsoring record and none is anything else - exposed for a
    caller outside this module (the directory-contact-route trigger in
    ``app/orchestrator/chat_orchestrator.py``) that needs the identical
    check without a second, drifting implementation.
    """
    return _evidence_lacks_policy_document(documents)


class HistoryGroundingValidator:
    """Block a delivered answer whose factual prose only history, not this turn's evidence, supports."""

    name = "history_grounding"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return
        if not _evidence_lacks_policy_document(retrieval_result.documents):
            return

        # No history means nothing this turn's answer says can possibly be
        # "history-sourced" - most directly, turn 0 of a conversation, which
        # has no earlier turn to have copied prose from at all (see the
        # module docstring's case 1).
        history = context.conversation_history or ""
        if not history.strip():
            return
        # Only an earlier ASSISTANT answer is a source of "copied" facts; the
        # user's own turns are excluded so a model answer that legitimately
        # restates the user's own question is never mistaken for one (module
        # docstring's review round 1 follow-up).
        assistant_history = _assistant_text(history)
        if not assistant_history.strip():
            return

        answer = context.chat_response.answer or ""
        if not answer.strip():
            return

        evidence_texts = [
            document.content or document.excerpt for document in retrieval_result.documents
        ]
        unsupported = unsupported_answer_sentences(answer, evidence_texts)
        if not unsupported:
            return

        # A sentence only counts as "history-sourced" when an earlier
        # assistant turn itself actually covers it - an uncovered-by-evidence
        # sentence that assistant history ALSO does not cover is an ordinary
        # generic/offer sentence, or a restatement of the user's own
        # question, not a fact copied from an earlier assistant answer
        # (module docstring case 1 / review round 1 follow-up).
        history_sourced = set(answer_sentences_covered_by(unsupported, [assistant_history]))
        # A question asserts no fact, so it can never be a copied claim,
        # however much vocabulary it shares with history (module docstring
        # case 2). A history-sourced MENU LINE (bullet + bold label + dash)
        # with no specific fact marker (digit, currency, email/URL, market
        # name) is a generic option line repeated from the model's own
        # earlier turn and misleads about nothing (module docstring, third
        # mode); every other sentence keeps the previous treatment.
        flagged = [
            sentence
            for sentence in unsupported
            if sentence in history_sourced
            and not _is_interrogative_sentence(sentence)
            and (not _is_menu_line(sentence) or _carries_specific_fact(_list_item_text(sentence)))
        ]
        if not flagged:
            return

        result.add_issue(
            ValidationIssue(
                code="HISTORY_SOURCED_CLAIM_UNGROUNDED",
                message=(
                    f"{len(flagged)} answer sentence(s) were not supported by this turn's "
                    "retrieved evidence, which contains no company-policy document, but ARE "
                    "covered by conversation history; the model likely drew them from "
                    "conversation history instead: "
                    + "; ".join(flagged)
                ),
                severity=ValidationSeverity.CRITICAL,
                field="answer",
            )
        )
