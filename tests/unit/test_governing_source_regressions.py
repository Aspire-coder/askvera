"""Entry-cost ranking and source-type boundaries, independent of model output."""
import pytest

from app.evidence import approve_evidence
from app.prompts import PromptBuilder
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.retrieval.section_index import _joining_cost_score, _source_score


@pytest.mark.parametrize('question', [
    'Does it cost money to join?', 'What enrollment fee do I pay?',
    'Is registration free?', 'How much will signing up cost?',
])
def test_entry_cost_clause_outscores_ongoing_fee(question):
    rule = {'content': 'No minimum capital investment is required.', 'rank': .5}
    fee = {'content': 'An FBO Support Fee is deducted from earned bonuses.', 'rank': .5}
    assert _source_score(rule, question) > _source_score(fee, question)


@pytest.mark.parametrize('question', ['What is the support fee?', 'How do I join?', 'What is the price of aloe?'])
def test_entry_cost_boost_does_not_apply_to_unrelated_questions(question):
    assert _joining_cost_score(question, 'No minimum capital investment is required.') == 0


def directory():
    return RetrievedDocument(id='global-be', title='International Sponsoring Directory',
                             content='Belgium: Telephone Office +31 88 646 0200.',
                             source='s3://approved/sponsoring.pdf', country='GLOBAL', language='en', score=5,
                             metadata={'access_scope': 'global', 'document_type': 'office_directory',
                                       'directory_kind': 'international_sponsoring'})


def test_global_directory_cannot_answer_foreign_company_policy():
    result = RetrievalResult(documents=[directory()], citations=[], confidence=.99)
    decision = approve_evidence('What does the Belgium company policy say about returns?', result, 'US', 'en')
    assert not decision.approved
    assert decision.reason == 'cross_market_policy_request'


def test_global_sponsoring_remains_available_across_markets():
    result = RetrievalResult(documents=[directory()], citations=[], confidence=.99)
    assert approve_evidence('What is the Belgium telephone in the sponsoring directory?', result, 'US', 'en').approved


def test_directory_is_not_labeled_policy_in_prompt():
    result = RetrievalResult(documents=[directory()], citations=[], confidence=.99)
    prompt = PromptBuilder().build(user_question='Belgium telephone?', conversation='', country='US',
                                   language='en', role='new_prospect', retrieval_result=result)
    assert 'directory record, not company policy' in prompt.retrieved_context
    assert 'Policy section:' not in prompt.retrieved_context


def test_global_record_does_not_receive_local_entry_cost_boost():
    content = 'No minimum capital investment is required.'
    assert _source_score({'content': content, 'access_scope': 'country'}, 'Cost to join?') > _source_score(
        {'content': content, 'access_scope': 'global'}, 'Cost to join?')


@pytest.mark.parametrize('question', ['What does registration cost?', 'Do I pay anything when signing up?'])
@pytest.mark.parametrize('condition', [
    'A customer who has qualified for a discount is eligible to opt-in to the Marketing Plan.',
    'When the customer purchases two CCs within two months, they are entitled to a discount.',
    'One who, having purchased two Case Credits, is Wholesale Qualified.',
])
def test_joining_cost_ranking_keeps_qualification_conditions_visible(question, condition):
    assert _joining_cost_score(question, condition) > 0


def test_joining_cost_boost_does_not_lift_unrelated_purchases_or_large_parent():
    assert _joining_cost_score('What does joining cost?', 'Purchases are delivered within two months.') == 0
    assert _joining_cost_score('What does joining cost?',
                               'A customer is eligible to opt-in. ' + 'Other policy text. ' * 100) == 0
