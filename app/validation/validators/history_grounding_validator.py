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
"""

from __future__ import annotations

from app.evidence_contract import unsupported_answer_sentences
from app.validation.models import ValidationContext, ValidationIssue, ValidationResult, ValidationSeverity

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


class HistoryGroundingValidator:
    """Block a delivered answer whose factual prose only history, not this turn's evidence, supports."""

    name = "history_grounding"

    def validate(self, context: ValidationContext, result: ValidationResult) -> None:
        retrieval_result = context.retrieval_result
        if retrieval_result is None or not retrieval_result.documents:
            return
        if not _evidence_lacks_policy_document(retrieval_result.documents):
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

        result.add_issue(
            ValidationIssue(
                code="HISTORY_SOURCED_CLAIM_UNGROUNDED",
                message=(
                    f"{len(unsupported)} answer sentence(s) were not supported by this turn's "
                    "retrieved evidence, which contains no company-policy document; the model "
                    "likely drew them from conversation history instead: "
                    + "; ".join(unsupported)
                ),
                severity=ValidationSeverity.CRITICAL,
                field="answer",
            )
        )
