"""Demo W6 (A): an own-market directory question with no country named searches that market's record.

Live (NL session, English, fresh conversation): "What is the delivery cost?",
"Is there a minimum order amount?" and "What payment methods do they take?"
each reached retrieval with target_country_names [] and
include_global_documents false, so the approved record
sponsoring-080-netherlands-benelux (record_country "Netherlands Benelux") was
never searched. The session-market fallback covered only contact/sponsoring
wording, and the planner backstop needed a "Forever <Name>" record in the
question.

Every test is offline. AWS clients, embeddings, the OpenSearch client, sockets
and the planner model are replaced before use; the real ones raise.
"""

from __future__ import annotations

import copy
import json
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.aws_clients as aws_clients
import services.embeddings as embeddings
from app.retrieval import opensearch_sections
from app.retrieval import providers as retrieval_providers
from app.retrieval.opensearch_sections import (
    OpenSearchSectionProvider,
    _directory_record_country_score,
    _directory_target_country_names,
)
from config import settings
from services import market_config

OWN_RECORD = "Netherlands Benelux"
OWN_MARKET_QUESTIONS = [
    "What is the delivery cost?",
    "Is there a minimum order amount?",
    "What payment methods do they take?",
    "What is the delivery time?",
    "What is the minimum order size?",
]
POLICY_ONLY_QUESTIONS = [
    "What is the return policy?",
    "What is the minimum order policy?",
    "What is the delivery cost policy?",
    "What are the rules for payment methods?",
]


def _live_call(*_: object, **__: object):
    raise AssertionError("W6 tests must never make an AWS, embedding, OpenSearch, network or model call")


def _clear_config_caches() -> None:
    for name in (
        "load_market_config",
        "load_global_directory_markets",
        "load_shared_offices",
        "_sponsoring_directory_alias_groups",
    ):
        loader = getattr(market_config, name, None)
        if loader is not None and hasattr(loader, "cache_clear"):
            loader.cache_clear()


@pytest.fixture(autouse=True)
def _offline(monkeypatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _live_call)
    monkeypatch.setattr(socket, "create_connection", _live_call)
    monkeypatch.setattr(aws_clients, "get_aws_clients", _live_call)
    monkeypatch.setattr(embeddings, "embed_text", _live_call)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", _live_call)
    monkeypatch.setattr(opensearch_sections, "embed_text", _live_call)
    monkeypatch.setattr(opensearch_sections, "_client", _live_call)
    _clear_config_caches()
    yield
    _clear_config_caches()


def _stub_planner(monkeypatch) -> MagicMock:
    """The model planner omits global_directory, as it did live."""
    runtime = MagicMock()
    runtime.converse.return_value = {
        "output": {"message": {"content": [{
            "text": '{"queries":["order terms"],"document_scopes":["locale_policy"],'
            '"intent":"knowledge","intent_confidence":0.99}'
        }]}}
    }
    monkeypatch.setattr(retrieval_providers.settings, "BEDROCK_QUERY_PLANNER_ENABLED", True)
    monkeypatch.setattr(retrieval_providers, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))
    return runtime


def _plan(monkeypatch, question: str, country: str = "NL"):
    _stub_planner(monkeypatch)
    return retrieval_providers._planned_retrieval_plan(question, country, "en", "cid-w6")


def _directory_row(record_country: str) -> dict:
    return {"document_type": "international_sponsoring_directory", "metadata": {"record_country": record_country}}


# --- fail-before: the session's own record is the target and is searched ---------------


@pytest.mark.parametrize("question", OWN_MARKET_QUESTIONS)
def test_own_market_operational_question_targets_the_session_record(question) -> None:
    targets = _directory_target_country_names(question, "NL")
    assert OWN_RECORD in targets
    # Only names configured for NL: markets.json "Netherlands" and the directory spelling.
    assert targets == {"Netherlands", OWN_RECORD}


@pytest.mark.parametrize("question", OWN_MARKET_QUESTIONS)
def test_planner_opens_the_directory_for_an_own_market_operational_question(monkeypatch, question) -> None:
    assert _plan(monkeypatch, question).include_global_documents is True


def test_the_record_name_comes_from_market_config_not_code(tmp_path, monkeypatch) -> None:
    path = tmp_path / "global_directory_markets.json"
    path.write_text(json.dumps({"markets": [{"name": "Holland Directory Record", "code": "NL"}]}), encoding="utf-8")
    monkeypatch.setenv("GLOBAL_DIRECTORY_MARKETS_CONFIG_PATH", str(path))
    _clear_config_caches()

    assert _directory_target_country_names("What is the delivery cost?", "NL") == {
        "Netherlands", "Holland Directory Record",
    }


# --- retrieval: the global search is filtered to the session record -------------------


def _hit(identifier: str, source: dict, score: float) -> dict:
    return {"_id": identifier, "_score": score, "_source": {"id": identifier, **source}}


NL_POLICY = _hit(
    "NL|en|policy|12.01", {
        "section_id": "12.01", "section_title": "Orders", "content": "Orders are placed through the FBO account.",
        "source_file": "NL-EN Benelux Company Policy", "country": "NL", "language": "en",
        "document_type": "policy", "access_scope": "country", "status": "active",
    }, 20.0,
)
BENELUX_RECORD = _hit(
    "sponsoring-080-netherlands-benelux", {
        "section_id": "sponsoring-080", "section_title": "Forever Netherlands Benelux",
        "content": "Delivery Cost: EUR 5,00 excl. VAT per order.", "source_file": "International Sponsoring Directory",
        "country": "GLOBAL", "language": "en", "document_type": "international_sponsoring_directory",
        "access_scope": "global", "status": "active", "metadata": {"record_country": OWN_RECORD},
    }, 18.0,
)


class _Client:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def search(self, index, body):
        del index
        self.bodies.append(copy.deepcopy(body))
        serialized = json.dumps(body)
        hits = [BENELUX_RECORD] if '"global"' in serialized else [NL_POLICY]
        return {"hits": {"hits": copy.deepcopy(hits)}}


def _retrieve(monkeypatch, question: str):
    for name, value in {
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED": False,
        "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED": False,
        "OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE": "en",
    }.items():
        monkeypatch.setattr(settings, name, value)
    client = _Client()
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0] * 4)
    _stub_planner(monkeypatch)
    result = OpenSearchSectionProvider().retrieve(question, "NL", "en", "fbo", "cid-w6")
    return result, client


def _global_bodies(client: _Client) -> list[dict]:
    return [body for body in client.bodies if '"access_scope": "global"' in json.dumps(body)]


def _record_filter_names(body: dict) -> set[str]:
    serialized = json.dumps(body)
    return {
        name for name in ("netherlands", "netherlands benelux", "germany", "belgium")
        if json.dumps({"query": name}) in serialized
    }


def test_delivery_cost_retrieval_searches_only_the_session_record(monkeypatch) -> None:
    result, client = _retrieve(monkeypatch, "What is the delivery cost?")

    assert result.metadata["global_documents_searched"] is True
    global_bodies = _global_bodies(client)
    assert len(global_bodies) == 2, "one text and one vector directory search"
    for body in global_bodies:
        assert _record_filter_names(body) == {"netherlands", "netherlands benelux"}
    assert "sponsoring-080-netherlands-benelux" in [document.id for document in result.documents]


# --- controls -------------------------------------------------------------------------


def test_company_policy_search_is_unchanged(monkeypatch) -> None:
    result, client = _retrieve(monkeypatch, "What is the delivery cost?")
    locale_bodies = [body for body in client.bodies if body not in _global_bodies(client)]
    assert locale_bodies, "the NL company-policy search still runs"
    for body in locale_bodies:
        assert '"country"' in json.dumps(body) and '"NL"' in json.dumps(body)
    assert "NL|en|policy|12.01" in [document.id for document in result.documents]


@pytest.mark.parametrize("question", POLICY_ONLY_QUESTIONS)
def test_policy_only_questions_keep_no_target_and_no_directory(monkeypatch, question) -> None:
    assert _directory_target_country_names(question, "NL") == set()
    assert _plan(monkeypatch, question).include_global_documents is False


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the delivery cost in Germany?", {"Germany"}),
        ("What payment methods are accepted in Belgium?", {"Belgium"}),
    ],
)
def test_a_named_foreign_country_still_wins(question, expected) -> None:
    targets = _directory_target_country_names(question, "NL")
    assert targets == expected
    assert OWN_RECORD not in targets


def test_no_foreign_directory_record_is_admitted_for_an_own_market_question() -> None:
    question = "What is the delivery cost?"
    targets = _directory_target_country_names(question, "NL")
    assert _directory_record_country_score(question, _directory_row(OWN_RECORD), targets) == 8.0
    for foreign in ("Germany", "Belgium", "Kenya/East Africa", "Mali"):
        assert _directory_record_country_score(question, _directory_row(foreign), targets) < 0


def test_unconfigured_session_market_opens_no_directory(monkeypatch) -> None:
    assert _directory_target_country_names("What is the delivery cost?", "XX") == set()
    assert _plan(monkeypatch, "What is the delivery cost?", country="XX").include_global_documents is False


def test_contact_wording_fallback_is_unchanged() -> None:
    assert _directory_target_country_names("What is the office phone number?", "NL") == {"Netherlands", OWN_RECORD}


@pytest.mark.parametrize("session", ["US", "KE", "SE"])
def test_market_without_a_configured_directory_record_keeps_policy_only_scope(monkeypatch, session) -> None:
    """Only markets listed in global_directory_markets.json fall back for operational fields."""
    assert _directory_target_country_names("What is the delivery cost?", session) == set()
    assert _plan(monkeypatch, "What is the delivery cost?", country=session).include_global_documents is False


def test_kenya_slash_record_and_shared_office_are_unchanged() -> None:
    question = "What is the delivery cost in Kenya?"
    kenya_targets = _directory_target_country_names(question, "NL")
    assert kenya_targets == {"Kenya"}
    assert _directory_record_country_score(question, _directory_row("Kenya/East Africa"), kenya_targets) == 8.0
    assert _directory_target_country_names("What is the delivery cost in South Sudan?", "NL") == {"Kenya/East Africa"}
    assert _directory_target_country_names("What is the delivery cost in Uganda?", "NL") == {"Uganda"}


# --- live defect: ordinary words must never become a market target ---------------------
# Live v2 re-check (SE session): "If I stop being an FBO, will the company buy back my
# leftover stock?" produced target_country_names ['Benin'] on every buy-back turn because
# the fuzzy single-token fallback scored "being" against "Benin".


@pytest.mark.parametrize(
    "question",
    [
        "If I stop being an FBO, will the company buy back my leftover stock?",
        "I have been being careful with my benefits.",
        "Can a woman be an FBO?",
        "Can I mail my order back?",
        "Is the aloe gel pure?",
    ],
)
@pytest.mark.parametrize("session", ["SE", "US", "NL"])
def test_ordinary_words_never_become_a_market_target(question, session) -> None:
    assert _directory_target_country_names(question, session) == set()


@pytest.mark.parametrize(
    ("question", "session", "forbidden", "expected"),
    [
        ("What is the phone number for my child?", "US", "Chile", {"United States"}),
        ("What is the office phone number for a woman?", "US", "Oman", {"United States"}),
        ("What is the office phone number? I am being careful.", "NL", "Benin", {"Netherlands", OWN_RECORD}),
    ],
)
def test_ordinary_words_do_not_replace_the_session_contact_fallback(question, session, forbidden, expected) -> None:
    targets = _directory_target_country_names(question, session)
    assert forbidden not in targets
    assert targets == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the Benin office phone number?", {"Benin"}),
        ("How can I join Mexcio through international sponsoring?", {"Mexico"}),
        ("What is the Chlie office phone number?", {"Chile"}),
        ("What is the Gahna phone number?", {"Ghana"}),
    ],
)
def test_real_country_names_and_swapped_letter_typos_still_target(question, expected) -> None:
    assert _directory_target_country_names(question, "US") == expected
