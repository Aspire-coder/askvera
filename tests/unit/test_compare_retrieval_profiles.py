"""Tests for exact case-level Current versus vNext reporting."""

from scripts.compare_retrieval_profiles import comparison_summary
from scripts.run_retrieval_canary import configure_vnext_experiment


def test_comparison_summary_reports_exact_improvements_and_regressions() -> None:
    current = [
        {"id": "A", "passed": True},
        {"id": "B", "passed": False},
        {"id": "C", "passed": True},
    ]
    candidate = [
        {"id": "A", "passed": True},
        {"id": "B", "passed": True},
        {"id": "C", "passed": False},
    ]

    summary = comparison_summary(current, candidate)

    assert summary["status"] == "failed"
    assert summary["improved_case_ids"] == ["B"]
    assert summary["regressed_case_ids"] == ["C"]
    assert summary["unchanged_case_ids"] == ["A"]


def test_comparison_summary_passes_only_without_regression() -> None:
    current = [{"id": "A", "passed": True}, {"id": "B", "passed": False}]
    candidate = [{"id": "A", "passed": True}, {"id": "B", "passed": True}]

    summary = comparison_summary(current, candidate)

    assert summary["status"] == "passed"
    assert summary["current_passed"] == 1
    assert summary["vnext_passed"] == 2


def test_vnext_experiment_adds_requested_factor_to_current_parity(monkeypatch) -> None:
    from config import settings

    for name in (
        "RETRIEVAL_VNEXT_RRF_ENABLED",
        "RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED",
        "RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED",
        "RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED",
        "RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED",
        "RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED",
        "RETRIEVAL_VNEXT_HARDENING_ENABLED",
        "RETRIEVAL_VNEXT_RERANK_ENABLED",
    ):
        monkeypatch.setattr(settings, name, True)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)

    configure_vnext_experiment(index_name="isolated", factor="rrf")

    assert settings.OPENSEARCH_VNEXT_INDEX == "isolated"
    assert settings.RETRIEVAL_VNEXT_RRF_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_HARDENING_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_RERANK_ENABLED is False


def test_vnext_parity_mirrors_live_provider_behavior(monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", True)

    configure_vnext_experiment(index_name="isolated", factor="parity")

    assert settings.OPENSEARCH_VNEXT_INDEX == "isolated"
    assert settings.RETRIEVAL_VNEXT_RRF_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_HARDENING_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_RERANK_ENABLED is False


def test_authority_stack_enables_only_the_three_reviewed_factors(monkeypatch) -> None:
    from config import settings

    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", False)

    configure_vnext_experiment(index_name="isolated", factor="authority-stack")

    assert settings.RETRIEVAL_VNEXT_AUTHORITY_RANKING_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_PARENT_CHILD_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_SIGNAL_CONFIDENCE_ENABLED is True
    assert settings.RETRIEVAL_VNEXT_RRF_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_PARENT_DIVERSITY_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_EVIDENCE_SELECTOR_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_HARDENING_ENABLED is False
    assert settings.RETRIEVAL_VNEXT_RERANK_ENABLED is False
