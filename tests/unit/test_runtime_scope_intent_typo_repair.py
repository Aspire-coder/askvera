"""Canary fix (2026-09-25): ``_runtime_scope_intent`` must tolerate typos too.

Reproduces (offline) ``tests/fixtures/retrieval_canary.json`` case
``mexico-sponsoring-multiple-typos``: "How can I become a member in Mexcio
through internationl sponsring?" (US/en). Ranking already tolerates the
misspellings via ``app.retrieval.typo_safety.safe_typo_ranking_queries``
(bounded, token-level edit-distance repairs built only from the planner's own
tokens), but ``_runtime_scope_intent`` (``app/retrieval/providers.py``) still
read the raw, uncorrected message: neither ``SPONSORING_QUESTION_RE`` nor
``directory_field_intent_present`` matched "sponsring"/"Mexcio", so the
question fell through to "ambiguous" and the directory country bonus in
``opensearch_sections._directory_record_country_score`` was zeroed, letting
an unrelated US policy clause outrank the correct Forever Mexico directory
record.

Fix: the caller (``_planned_retrieval_plan``) now also computes
``safe_typo_ranking_queries(message, merged[1:])`` and passes the result to
``_runtime_scope_intent`` as the new, keyword-only ``repaired_texts``
parameter (default ``()``, so every other caller is unchanged). Each
text-based branch inside ``_runtime_scope_intent`` now checks the raw message
AND every repaired form; a repaired form can only ever turn "ambiguous" into
a real intent, never suppress one the raw message alone would have produced,
and branch order (policy checked before sponsoring/directory) is unchanged.
"""

from app.retrieval.providers import _runtime_scope_intent
from app.retrieval.typo_safety import safe_typo_ranking_queries


def _repaired(raw: str, planner_queries: list[str]) -> list[str]:
    """Reproduce the call site's own repair computation for a test's raw text."""
    return safe_typo_ranking_queries(raw, planner_queries)


class TestRuntimeScopeIntentTypoRepair:
    def test_typo_d_sponsoring_question_recovers_intent_with_repair(self) -> None:
        raw = "How can I become a member in Mexcio through internationl sponsring?"
        planner_queries = ["How can I become a member in Mexico through international sponsoring?"]
        repaired = _repaired(raw, planner_queries)
        assert repaired, "expected safe_typo_ranking_queries to produce a repaired form"

        result = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="en",
            repaired_texts=repaired,
        )
        assert result["intent"] == "international_sponsoring"
        assert result["decision_source"] == "deterministic_sponsoring_route"

    def test_typo_d_sponsoring_question_without_repair_stays_ambiguous(self) -> None:
        """Documents the old (pre-fix) behaviour: no repaired text, no recovery."""
        raw = "How can I become a member in Mexcio through internationl sponsring?"
        result = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="en",
        )
        assert result["intent"] == "ambiguous"
        assert result["decision_source"] == "planner_global_scope_only"

    def test_policy_word_typo_wins_over_a_named_directory_field(self) -> None:
        """A typo'd policy word still suppresses to "policy", even alongside a
        genuine directory field ("delivery cost") in the same sentence -
        policy is checked first and a repair can never weaken that gate.
        """
        raw = "What is the polciy on delivery cost?"
        planner_queries = ["What is the policy on delivery cost?"]
        repaired = _repaired(raw, planner_queries)
        assert repaired

        # Without the repair, the directory field alone would have promoted
        # this to "directory" - the very suppression this fix must not weaken.
        without_repair = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="en",
        )
        assert without_repair["intent"] == "directory"

        with_repair = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="en",
            repaired_texts=repaired,
        )
        assert with_repair["intent"] == "policy"
        assert with_repair["decision_source"] == "deterministic_policy_route"

    def test_non_english_typo_d_directory_field_recovers_via_multilingual_route(self) -> None:
        """Spanish "telefono" (phone), misspelled, is recognized once repaired."""
        raw = "¿Cuál es su telefno?"
        planner_queries = ["¿Cuál es su telefono?"]
        repaired = _repaired(raw, planner_queries)
        assert repaired

        without_repair = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="es",
        )
        assert without_repair["intent"] == "ambiguous"

        with_repair = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="es",
            repaired_texts=repaired,
        )
        assert with_repair["intent"] == "directory"
        assert with_repair["decision_source"] == "multilingual_directory_field_route"

    def test_repair_never_adds_planner_words_that_were_not_typos(self) -> None:
        """An unrelated question must not flip to "international_sponsoring"
        merely because the planner's own query happens to add sponsoring
        vocabulary the user never typed - ``safe_typo_ranking_queries``
        returns [] here (nothing in the original was actually misspelled),
        so ``repaired_texts`` is empty and the classification is unaffected.
        """
        raw = "What are your business hours?"
        planner_queries = ["What are your business hours and sponsoring opportunities?"]
        repaired = _repaired(raw, planner_queries)
        assert repaired == []

        result = _runtime_scope_intent(
            raw,
            include_global_documents=True,
            named_markets=set(),
            shared_office_markets=set(),
            deterministic_directory_route=False,
            language="en",
            repaired_texts=repaired,
        )
        assert result["intent"] != "international_sponsoring"
