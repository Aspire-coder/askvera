"""Tests for fixed-checkpoint selector stability evaluation."""

from types import SimpleNamespace

from scripts.run_fixed_checkpoint_selector_evaluation import (
    checkpoint_rows_from_result,
    enrich_saved_report,
    replay_fixed_selector,
    summarize_replays,
)


def test_checkpoint_rows_preserve_selector_fields() -> None:
    document = SimpleNamespace(
        id="doc-1",
        title="Policy.pdf - Sec 1.01",
        content="No minimum capital investment is required.",
        source="s3://bucket/policy.pdf",
        document_version="2026.1",
        country="GB",
        language="en",
        page="1",
        score=1.25,
        metadata={
            "section_id": "1.01",
            "section_title": "Introduction",
            "document_type": "policy",
            "access_scope": "country",
        },
    )

    rows = checkpoint_rows_from_result(SimpleNamespace(documents=[document]))

    assert rows[0][0]["content"].startswith("No minimum")
    assert rows[0][0]["section_id"] == "1.01"
    assert rows[0][1] == 1.25


class _FakeSelectorProvider:
    enable_evidence_selector = None

    def __init__(self) -> None:
        self.calls = 0

    def _select_evidence_rows(self, message, rows, correlation_id):
        del message, correlation_id
        self.calls += 1
        rows[0][0]["evidence_selector_decision"] = "accepted"
        rows[0][0]["evidence_selector_selected_ranks"] = [1]
        rows[0][0]["evidence_selector_reason"] = "governing clause"
        rows[0][0]["evidence_selector_selected"] = True
        rows[0][0]["evidence_selector_relevant"] = True
        return [rows[0]]


def test_replay_uses_deep_copies_and_restores_provider_state() -> None:
    provider = _FakeSelectorProvider()
    rows = [
        (
            {
                "id": "doc-1",
                "section_id": "1.01",
                "country": "GB",
                "language": "en",
                "access_scope": "country",
                "metadata": {},
            },
            1.0,
        )
    ]
    case = {
        "scope": "locale_policy",
        "expected_behavior": "answer",
        "country": "GB",
        "relevant_sections": ["1.01"],
    }

    replays = replay_fixed_selector(
        provider=provider,
        question="Does joining cost money?",
        rows=rows,
        country="GB",
        language="en",
        case=case,
        repeats=3,
        correlation_base="test",
    )

    assert provider.calls == 3
    assert provider.enable_evidence_selector is None
    assert "evidence_selector_decision" not in rows[0][0]
    assert all(replay["selected_relevant"] for replay in replays)


def test_summary_reports_selector_variance() -> None:
    summary = summarize_replays(
        [
            {"decision": "accepted", "selected_ids": ["a"], "selected_relevant": True},
            {"decision": "accepted", "selected_ids": ["a"], "selected_relevant": True},
            {"decision": "rejected", "selected_ids": [], "selected_relevant": False},
        ]
    )

    assert summary["stable"] is False
    assert summary["unique_outcomes"] == 2
    assert summary["agreement_rate"] == 0.666667
    assert summary["relevant_selections"] == 2
    assert summary["accepted_relevant_selections"] == 2
    assert summary["invalid_responses"] == 0


def test_invalid_fallback_is_not_counted_as_selector_success() -> None:
    summary = summarize_replays(
        [
            {"decision": "invalid", "selected_ids": ["a"], "selected_relevant": True},
            {"decision": "invalid", "selected_ids": ["a"], "selected_relevant": True},
        ]
    )

    assert summary["relevant_selections"] == 2
    assert summary["accepted_relevant_selections"] == 0
    assert summary["invalid_responses"] == 2


def test_enrich_saved_report_separates_retrieval_from_selector() -> None:
    report = {
        "cases": [
            {
                "id": "CASE-1",
                "current": {
                    "checkpoint": [
                        {
                            "section_id": "1.01",
                            "country": "GB",
                            "access_scope": "country",
                        }
                    ],
                    "replays": [
                        {
                            "decision": "rejected",
                            "selected_ids": [],
                            "selected_relevant": False,
                        }
                    ],
                },
                "candidate": {
                    "checkpoint": [],
                    "replays": [
                        {
                            "decision": "rejected",
                            "selected_ids": [],
                            "selected_relevant": False,
                        }
                    ],
                },
            }
        ]
    }
    fixture = {
        "cases": [
            {
                "id": "CASE-1",
                "scope": "locale_policy",
                "country": "GB",
                "expected_behavior": "answer",
                "relevant_sections": ["1.01"],
            }
        ]
    }

    enriched = enrich_saved_report(report, fixture)

    assert enriched["summary"]["current"]["checkpoint_relevant_cases"] == 1
    assert enriched["summary"]["current"]["any_accepted_relevant"] == 0
    assert enriched["summary"]["candidate"]["checkpoint_relevant_cases"] == 0
