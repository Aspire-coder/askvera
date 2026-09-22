"""Phase 3 Lane 3: detect a PERSONAL-ACCOUNT lookup request.

``docs/conversation-quality/phase3/CX_LANES.md`` adds ``personal_account`` as
a new :class:`~app.response.outcome.OutcomeKind` (Lane 1) for a question this
chatbot has no backend for: a reader asking about the current state of
*their own* order, payment, commission or account, rather than asking a
policy question that happens to use the word "my". Nothing in this
repository already tells those two apart, so this module owns a narrow, new,
closed vocabulary (:mod:`config.personal_account_vocabulary`) rather than
reusing or widening an existing one -- there is no existing one to reuse.

**This is not a refusal.** A question that matches this shape still gets the
normal policy/evidence answer when the pipeline has one (e.g. a
"how is my bonus calculated" question that also asks the calculation
formula) -- this module never blocks the answer pipeline and is never
consulted by evidence approval, retrieval or the prompt. It only tells the
coordinator whether to ADD the ``personal_account_limit`` note (plus a
``contact_offer``, via :func:`app.response.contact_completion.contact_escalation`
with ``outcome.kind == OutcomeKind.PERSONAL_ACCOUNT``) alongside whatever
answer the pipeline already produced. See
``docs/conversation-quality/phase3/CX_LANE3_CONTACTS_SUGGESTIONS_ACCOUNT.md``
for the recommended hook site.

Pure by design: no I/O, no model calls, no orchestrator import.
"""

from __future__ import annotations

from config.personal_account_vocabulary import matches_personal_account_shape


def detect_personal_account_request(question: str, language: str) -> bool:
    """True when ``question`` asks about the reader's OWN account state.

    Delegates entirely to the closed, per-language vocabulary in
    :mod:`config.personal_account_vocabulary` -- see that module's
    docstring for the exact shape matched (a first-person possessive plus a
    concrete account-object noun plus a status/lookup verb phrase) and for
    the negative examples (calculation questions, future-payment-timing
    policy questions, capability questions, general policy questions using
    "my") that must NOT match. An unrecognised or unlisted language returns
    ``False`` rather than guess.
    """
    return matches_personal_account_shape(question, language)
