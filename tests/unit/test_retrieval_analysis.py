from scripts.analyze_retrieval_evaluation import _mcnemar, _metric, _wilson


def test_wilson_interval_is_bounded() -> None:
    interval = _wilson(48, 58)
    assert 0.0 <= interval["lower"] < interval["upper"] <= 1.0


def test_metric_reports_recall_and_confidence_interval() -> None:
    result = _metric([1, 2, None, 7])
    assert result["labeled_cases"] == 4
    assert result["recall_at_1"] == 0.25
    assert "lower" in result["recall_at_5_ci95"]


def test_mcnemar_counts_directional_changes() -> None:
    result = _mcnemar([1, None, 2], [2, 1, None], 1)
    assert result["baseline_correct_candidate_wrong"] == 1
    assert result["candidate_correct_baseline_wrong"] == 1
    assert result["exact_two_sided_p_value"] == 1.0
