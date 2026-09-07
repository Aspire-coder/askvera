from app.retrieval.models import RetrievedDocument
from utils.inline_citations import separate_verified_citations
from utils.directory_fields import remove_unrequested_directory_fields
import pytest
from app.validation.validators.numeric_grounding_validator import unsupported_numeric_claims


@pytest.mark.parametrize('citation', ['([Source 1](s3://kb/policy.pdf))', '([Source 1], [1])'])
def test_verified_inline_link_does_not_become_numeric_claim(citation):
    doc = RetrievedDocument(id='policy', title='Policy', content='', source='s3://kb/policy.pdf')
    answer = 'The requirement is 2 Case Credits ' + citation + '.'
    assert separate_verified_citations(answer, [doc]) == 'The requirement is 2 Case Credits.'


@pytest.mark.parametrize('citation', ['[Source 1](https://unapproved.example/policy)',
                                      '[Source 99](s3://kb/policy.pdf)'])
def test_unverified_inline_link_is_not_silently_exempted(citation):
    doc = RetrievedDocument(id='policy', title='Policy', content='', source='s3://kb/policy.pdf')
    assert separate_verified_citations(citation, [doc]) == citation


def test_verified_link_cleanup_preserves_supported_rank_requirement():
    rule = ('Assistant Supervisor is achieved by generating a total of 2 Open Group Case Credits '
            'in any single Operating Company within any 2 consecutive Months.')
    doc = RetrievedDocument(id='rule', title='Policy', content=rule, source='s3://kb/policy.pdf')
    answer = ('To qualify as an Assistant Supervisor, generate a total of **2 Open Group Case Credits '
              'in any single Operating Company within any 2 consecutive Months** '
              '([Source 1](s3://kb/policy.pdf)).')
    cleaned = separate_verified_citations(answer, [doc])
    assert '2 Open Group Case Credits' in cleaned
    assert not unsupported_numeric_claims(cleaned, [doc])


def test_link_index_must_match_its_source_uri():
    documents = [RetrievedDocument(id=str(i), title='Policy', content='', source=f's3://kb/{i}.pdf')
                 for i in range(2)]
    answer = '[Source 1](s3://kb/1.pdf)'
    assert separate_verified_citations(answer, documents) == answer


def test_verified_metadata_removed_without_removing_claim():
    doc = RetrievedDocument(id="be", title="Directory.pdf", content="", source="", page="111-112")
    assert separate_verified_citations("Call +31 88 646 0200 [Source 1].\n**Source:** Directory.pdf, pages 111-112", [doc]) == "Call +31 88 646 0200 ."


def test_forged_citation_claim_and_unknown_marker_not_exempted():
    doc = RetrievedDocument(id="be", title="Directory.pdf", content="", source="", page="111-112")
    text = "Earn 5000 [Source 99].\nSource: Directory.pdf, guaranteed 5000, pages 999"
    assert separate_verified_citations(text, [doc]) == text


def test_french_single_field_and_explicit_both():
    text = "Réception : +31 88 646 0200.\nLe numéro pour les commandes en Belgique est le **+03 808 1023**."
    focused, changed = remove_unrequested_directory_fields(text, "Quel est le numéro de téléphone du bureau belge ?")
    assert changed and "+03" not in focused and "+31" in focused
    assert remove_unrequested_directory_fields(text, "Les deux numéros du bureau et des commandes ?")[0] == text


def test_exact_source_id_does_not_remove_sentence_spacing_as_numeric_claim():
    identifier = 'CA|en|CA-EN-Company-Policy.pdf|4.03'
    doc = RetrievedDocument(id=identifier, title='Policy', content='You need 4 Active Case Credits.', source='')
    text = f'You need 4 Active Case Credits. [{identifier}]\n\nRank is separate.'
    cleaned = separate_verified_citations(text, [doc])
    assert cleaned == 'You need 4 Active Case Credits. \n\nRank is separate.'
    assert not unsupported_numeric_claims(cleaned, [doc])


@pytest.mark.parametrize('token', ['CA|en|other.pdf|4.03', 'CA|en|policy.pdf|4x03'])
def test_unknown_full_source_id_is_not_exempted(token):
    doc = RetrievedDocument(id='CA|en|policy.pdf|4.03', title='Policy', content='', source='')
    assert separate_verified_citations(f'[{token}]', [doc]) == f'[{token}]'
