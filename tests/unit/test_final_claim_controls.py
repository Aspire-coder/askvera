"""Synthetic fixture integrity checks, not policy gold answers."""
import pytest

from app.retrieval.source_binding import EvidenceSource
from scripts.run_final_claim_controls import preflight_controls


def control(name, quote, content):
    source = EvidenceSource('test', 'v1', 'section', 'CA', content)
    payload = {'answer': quote, 'claims': [{'text': quote, 'support': [
        {'source_id': source.binding_id, 'quote': quote}]}]}
    return name, payload, False, 'Question?', 'CA', 'en', [source]


def test_parent_containing_quote_is_not_a_negative_binding_fixture():
    with pytest.raises(ValueError, match='unexpectedly binds'):
        preflight_controls([control('wrong-passage', 'Monthly rule.', 'Parent. Monthly rule. Bonus rule.')])


def test_actual_wrong_passage_is_a_valid_negative_fixture():
    preflight_controls([control('wrong-passage', 'Bonus rule.', 'Monthly rule.')])


def test_other_controls_must_bind_even_when_expected_to_fail_semantics():
    with pytest.raises(ValueError, match='does not belong'):
        preflight_controls([control('mixed-claim', 'Unknown text.', 'Monthly rule.')])
