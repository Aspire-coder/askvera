import pytest

from app.retrieval.evaluation import promotion_gate, summarize_comparisons


def test_comparison_summary_and_promotion_gate_are_locale_aware():
    summary = summarize_comparisons(
        [
            {
                "same_section": True,
                "evidence_overlap": 0.8,
                "shadow_latency_ms": 100,
                "vnext_confidence_wins": True,
                "country": "CA",
                "language": "en",
                "failure_category": "none",
            },
            {
                "same_section": False,
                "evidence_overlap": 0.6,
                "shadow_latency_ms": 200,
                "vnext_confidence_wins": False,
                "country": "DE",
                "language": "de",
                "failure_category": "section_mismatch",
            },
        ]
    )

    assert summary["comparisons"] == 2
    assert summary["same_section_rate"] == 0.5
    assert summary["evidence_overlap_rate"] == pytest.approx(0.7)
    assert summary["by_country"] == {"CA": 1, "DE": 1}
    assert summary["by_language"] == {"en": 1, "de": 1}
    assert summary["by_locale"]["CA/en"]["comparisons"] == 1

    passed, reasons = promotion_gate(
        summary,
        min_same_section_rate=0.5,
        min_evidence_overlap=0.7,
        max_latency_ms=200,
    )

    assert passed is True
    assert reasons == []


def test_summary_keeps_token_and_cost_metrics_without_bad_value_failures():
    summary = summarize_comparisons(
        [
            {
                "country": "CA",
                "language": "fr",
                "input_tokens": 100,
                "outputTokens": 25,
                "costUsd": "0.0125",
                "shadow_latency_ms": "not-a-number",
            }
        ]
    )

    assert summary["input_tokens"] == 100
    assert summary["output_tokens"] == 25
    assert summary["total_tokens"] == 125
    assert summary["estimated_cost_usd"] == 0.0125
    assert summary["by_locale"]["CA/fr"]["estimated_cost_usd"] == 0.0125
    assert summary["missing_latency_count"] == 1

    passed, reasons = promotion_gate(
        summary,
        min_same_section_rate=0,
        min_evidence_overlap=0,
        max_latency_ms=1000,
    )
    assert passed is False
    assert "latency measurements are missing or invalid" in reasons
