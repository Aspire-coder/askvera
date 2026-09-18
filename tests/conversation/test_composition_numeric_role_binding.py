"""B5/B6 (Lane B, conversation-quality project): a valid figure must not
disappear because a sentence-initial capitalised word sits in front of a
plural role acronym.

Reproduced without any model call, directly against
app.validation.validators.numeric_grounding_validator: a natural, correct
answer sentence such as "For FBOs, the minimum order size is 50 USD." was
losing its "50" to numeric-grounding repair. The cause traced to
_subject_token_sets / _entity_phrases: a sentence-initial word is capitalised
only by its position, and the code already forgives that ("Suomessa FBO", see
_entity_phrases's docstring) but only when the following word is a BARE
acronym ("FBO"). A plural acronym ("FBOs") is common in this corpus (the
matching role regex, _FBO_ROLE_RE, already accepts "fbo" or "fbos") and was
not recognised, so the two-word phrase "For FBOs" was kept as one subject
requiring "for" to appear beside the figure in the source - which almost no
source sentence does. Fixed by widening the acronym check
(_acronym_with_suffix) to accept a bare plural or possessive suffix on top of
the acronym test, still with no per-language word list.

This is a deterministic layer: repro-before/fixed-after, no model involved.
"""

from types import SimpleNamespace

from app.validation.validators.numeric_grounding_validator import (
    remove_unsupported_numeric_sentences,
    unsupported_numeric_claims,
)


def _document(content: str, **metadata: object) -> SimpleNamespace:
    return SimpleNamespace(content=content, title="doc", id="doc", metadata=metadata)


def test_sentence_initial_word_before_plural_role_acronym_does_not_orphan_figure() -> None:
    """B5: 'For FBOs, ...' must not need a literal 'for' beside the source figure.

    Before the fix this claim was reported unsupported: unsupported_numeric_claims
    returned a MeasurableClaim for "50", and remove_unsupported_numeric_sentences
    deleted the whole sentence, leaving an empty answer.
    """
    source = _document("Minimum order size FBO: 50 USD.")
    answer = "For FBOs, the minimum order size is 50 USD."

    assert unsupported_numeric_claims(answer, [source]) == []
    repaired, removed = remove_unsupported_numeric_sentences(answer, [source])
    assert removed == []
    assert repaired == answer


def test_two_roles_each_keep_their_own_supported_figure() -> None:
    """B2/B5 together: FBO and Preferred Customer minimum orders, both stated
    the same natural way, must both survive - not one silently dropped
    because the other role's mention sits in the widened source window.

    Before the fix, the FBO sentence's "50" was deleted while the Preferred
    Customer sentence's "25" (a three-word capitalised phrase, which already
    had a subject-set that dropped the leading grammatical word by luck)
    survived - an asymmetric, hard-to-notice failure exactly matching what
    B2's acceptance criterion (distinguish both roles when both are
    supported) requires not to happen.
    """
    source = _document(
        "Minimum order size FBO: 50 USD. Minimum order size Preferred Customer: 25 USD."
    )
    answer = (
        "For FBOs, the minimum order size is 50 USD. "
        "For Preferred Customers, the minimum order size is 25 USD."
    )

    assert unsupported_numeric_claims(answer, [source]) == []
    repaired, removed = remove_unsupported_numeric_sentences(answer, [source])
    assert removed == []
    assert repaired == answer
    assert "50 USD" in repaired and "25 USD" in repaired


def test_bare_role_acronym_still_binds_as_before() -> None:
    """Guard against a regression of the pre-existing bare-acronym path
    ("Suomessa FBO" / "Kun FBO" shape) that the widened check must not break.
    """
    source = _document("FBO: 100 CC.")
    answer = "As FBO, you need 100 Case Credits."

    assert unsupported_numeric_claims(answer, [source]) == []
