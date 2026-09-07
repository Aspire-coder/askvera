"""The report must distinguish observed delivery from a correctness verdict."""
import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    'comparison_report', Path(__file__).resolve().parents[2] / 'scripts/report_matched_chat_comparison.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_missing_is_not_a_pass():
    assert report.describe(None) == 'NOT RUN'


def test_error_is_not_a_bot_refusal():
    assert report.describe({'error': 'RuntimeError'}) == 'ERROR: RuntimeError'


def test_delivered_is_not_scored_correct():
    assert report.describe({'response': {'answer': 'Example', 'metadata': {}}}) == 'answer returned'


def test_failure_layer_is_preserved():
    assert report.describe({'response': {'metadata': {
        'fallback': True, 'failure_layer': 'numeric_validator'}}}) == 'numeric_validator'


def test_same_code_baseline_not_reported_as_production(tmp_path):
    (tmp_path / 'current-manifest.json').write_text(json.dumps({
        'comparison_basis': 'same working-tree code, selector-only candidate'}), encoding='utf-8')
    assert 'NOT a verified deployed-production baseline' in report.comparison_basis(tmp_path)


def test_missing_manifest_not_reported_as_verified(tmp_path):
    assert 'UNVERIFIED' in report.comparison_basis(tmp_path)


def test_review_comparison_identifies_both_structural_arms(tmp_path):
    (tmp_path / 'current-manifest.json').write_text(json.dumps({'review_only_comparison': True}), encoding='utf-8')
    assert 'Neither arm is deployed production' in report.comparison_basis(tmp_path)


def test_writer_comparison_does_not_claim_approval_is_the_variable(tmp_path):
    (tmp_path / 'current-manifest.json').write_text(json.dumps({
        'review_only_comparison': True, 'scoped_writer_comparison': True}), encoding='utf-8')
    basis = report.comparison_basis(tmp_path)
    assert 'Both arms use structural selection and bound-evidence approval' in basis
    assert 'Only Fixed' in basis
    assert 'Neither arm is deployed production' in basis
