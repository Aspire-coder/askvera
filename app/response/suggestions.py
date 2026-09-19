"""Phase 3 Lane 3: suggested follow-up topics.

``docs/conversation-quality/phase3/CX_LANES.md`` reserves a small, closed set
of ``suggest_topic_<name>`` message keys (Lane 4 owns the copy). This module
picks at most two of them for a given turn, from a fixed, documented
priority order, and never picks a topic the market has no approved evidence
for or the topic the reader just asked about.

Pure by design: no I/O, no model calls, no orchestrator import. Copy is
data -- this module returns message KEYS, never rendered text; Lane 4's
``render``/``cx_render`` turns a key into a localized sentence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.response.outcome import ConversationOutcome, OutcomeKind

# The closed set of suggestible topics (docs/conversation-quality/phase3/CX_LANES.md
# message-key table: "a small closed set, e.g. suggest_topic_delivery_cost,
# suggest_topic_payment_methods, suggest_topic_contact, suggest_topic_returns").
# Order is the fixed, deterministic suggestion priority: the two most common
# post-answer questions in this chatbot's support-contact and directory-field
# traffic (delivery cost, payment methods) rank above the two topics that
# only became reachable once a reader has already hit a limit
# (contact -- see contact_escalation, which already offers a contact for
# several outcome kinds, so it ranks below the two "learn something new"
# topics -- and returns, a policy topic with no directory-field signal, so
# it is checked last).
_SUGGEST_TOPICS: tuple[str, ...] = ("delivery_cost", "payment_methods", "contact", "returns")

_MAX_SUGGESTIONS = 2

# Maps each suggestible topic to the canonical directory-field key(s)
# (utils.directory_fields / config.directory_field_vocabulary's canonical
# set: phone, order_phone, email, website, address, business_hours,
# payment_methods, delivery_cost, delivery_time, fax) that count as "the
# reader just asked about this topic," via ConversationOutcome.fields_requested
# (app/response/outcome.py, itself built from
# utils.directory_fields._requested_directory_field_set). "returns" has no
# canonical directory-field key -- it is a policy topic, not a directory
# field -- so it can never be excluded this way; it relies solely on
# ``topic_supported`` to stay out of markets without an approved returns
# policy.
_TOPIC_FIELD_ALIASES: dict[str, frozenset[str]] = {
    "delivery_cost": frozenset({"delivery_cost", "delivery_time"}),
    "payment_methods": frozenset({"payment_methods"}),
    "contact": frozenset({"phone", "order_phone", "email", "website", "address", "business_hours", "fax"}),
    "returns": frozenset(),
}

# Never suggest anything after these outcomes: dependency_unavailable means
# the pipeline itself could not run this turn (suggesting more questions is
# misleading when the last one already failed to be answered for reasons
# unrelated to topic), and safety_refusal is never followed by a nudge to
# ask something else.
_EXCLUDED_KINDS = frozenset({OutcomeKind.SAFETY_REFUSAL, OutcomeKind.DEPENDENCY_UNAVAILABLE})


def suggest_follow_ups(
    outcome: ConversationOutcome,
    *,
    language: str,
    country: str,
    topic_supported: Callable[[str, str], bool],
) -> list[str]:
    """Return at most two ``suggest_topic_<name>`` message keys.

    ``topic_supported(topic, country)`` is an INJECTED predicate (never
    called here on anything outside the closed ``_SUGGEST_TOPICS`` set) so
    the coordinator can back it with an existing corpus signal instead of
    this module inventing a new one. See
    ``docs/conversation-quality/phase3/CX_LANE3_CONTACTS_SUGGESTIONS_ACCOUNT.md``
    for the recommended signal (approved directory-record fields for the
    market) and why ``config/markets.json`` alone is not enough (it carries
    market/language enablement, not per-topic evidence coverage).

    ``language`` is accepted for signature symmetry with the other Lane 3
    entry points and because a future topic could need it to pick a
    locale-specific alias; it is unused today (topic selection depends only
    on what was asked and what the market has evidence for, both of which
    are language-independent).
    """
    del language  # symmetry with contact_escalation / detect_personal_account_request; unused today
    if outcome.kind in _EXCLUDED_KINDS:
        return []

    asked_fields = outcome.fields_requested
    suggestions: list[str] = []
    for topic in _SUGGEST_TOPICS:
        if _TOPIC_FIELD_ALIASES[topic] & asked_fields:
            continue
        if not topic_supported(topic, country):
            continue
        suggestions.append(f"suggest_topic_{topic}")
        if len(suggestions) >= _MAX_SUGGESTIONS:
            break
    return suggestions


def suggestible_topics() -> Sequence[str]:
    """The closed topic-name set (without the ``suggest_topic_`` prefix)."""
    return _SUGGEST_TOPICS
