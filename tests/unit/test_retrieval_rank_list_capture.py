"""Rank-list capture records live ranking evidence and changes nothing retrieved.

Rank fusion and selector top-1 could not be diagnosed offline: no saved list
held real text and vector ranks together, and the benchmark only kept the
parent-preferring candidate list. Under the orchestrator's diagnostic capture,
retrieval now also records each search's ranked hits with raw scores, the
merged order, the candidates sent to the selector and its raw picks, all by
section and document id. ``offline_retrieval_replay.py convert-artifact`` turns
a benchmark artifact carrying them into an ``rrf --capture`` file.

These tests pin that capture is off by default and request-scoped, that with it
on the documents, order, scores, confidence, searches and selector call are
identical, that the lists are exactly what production merged, that failure and
empty paths do not crash, that the keys reach no public or persisted sink, and
that the converter rejects malformed input.

No network: the OpenSearch client, embeddings, the selector model, session,
consent, caches, audit and analytics are stubs.
"""

from __future__ import annotations

import argparse
import contextvars
import copy
import importlib.util
import inspect
import json
import logging
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from opensearchpy.exceptions import ConnectionTimeout

from app.governance.models import GovernanceAction, GovernanceDecision
from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import AIOrchestrator
from app.retrieval import opensearch_sections
from app.retrieval.models import RetrievalAvailability
from app.retrieval.opensearch_sections import OpenSearchSectionProvider
from app.retrieval.providers import RetrievalQueryPlan
from app.retrieval.service import RetrievalService
from config import settings
from scripts import offline_retrieval_replay as tool
from utils.exceptions import SessionExpiredError
from utils.logging import JsonFormatter
from utils.validators import ChatRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTION = "What is the service fee?"
ANSWER = "The service fee is 2.50 per order."
FILE = "CA-EN-Company-Policy.pdf"
RANK_KEYS = (
    "retrieval_rank_lists",
    "candidate_section_ids",
    "evidence_selector_candidate_section_ids",
    "evidence_selector_selected_ranks",
)
# What the knowledge path emits today with the generation pointer off.
EXISTING_KEYS = {
    "provider", "candidate_count", "search_query_count", "typo_ranking_query_count", "typo_ranking_applied",
    "ranking_query_used", "global_documents_searched", "outline_preferred", "client_action",
    "conversation_intent", "global_query_translated", "explicit_section_reference",
    "evidence_selector_rejected", "evidence_selector_applied", "evidence_selector_confidence",
    "top_source_directly_answers", "lexical_confidence", "max_local_relevance", "strong_local_match",
    "parent_bound_children", "candidate_sources",
}
# A candidate that is ranked but never delivered: its document id can only
# appear in the rank lists, so finding it in a sink means the lists leaked.
PROBE_ID = "probe-rank-only-doc-9c1e"
SELECTOR_REPLY = '{"selected_ranks":[2,1,9],"directly_answers_top_rank":true,"top_rank_confidence":0.9}'


def _source(identifier: str, section_id: str, title: str, body: str, *, parent: str = "", chunk: str = "section") -> dict:
    content = f"Section {parent or section_id}: {title}\n{body}"
    return {
        "id": identifier, "section_id": section_id, "parent_section_id": parent, "chunk_type": chunk,
        "section_title": title, "content": content, "search_text": f"{title}\n{content}",
        "source_file": FILE, "source_uri": f"opensearch-section://{FILE}/{section_id}",
        "country": "CA", "language": "en", "document_type": "policy", "access_scope": "country",
        "status": "active", "ingestion_id": "ingestion-1", "start_page": 4, "end_page": 4,
    }


def _hit(source: dict, score: float) -> dict:
    return {"_id": source["id"], "_score": score, "_source": source}


PARENT = _source(f"CA|en|{FILE}|13.01", "13.01", "Service fee", "The service fee is 2.50 per order.")
CHILD = _source(f"CA|en|{FILE}|13.01-b", "13.01-b", "Service fee", "(b) The service fee is 2.50 per order.", parent="13.01", chunk="list_item")
REFUNDS = _source(f"CA|en|{FILE}|13.02", "13.02", "Service fee refunds", "A service fee is refunded when an order is cancelled.")
EXEMPT = _source(f"CA|en|{FILE}|13.03", "13.03", "Service fee exemptions", "No service fee applies to orders above 500.")
LEVELS = _source(f"CA|en|{FILE}|7.03", "7.03", "Order service levels", "Orders ship within two days.")
SHIPPING = _source(f"CA|en|{FILE}|13.04", "13.04", "Shipping fee", "Shipping is charged per parcel.")
WAIVERS = _source(f"CA|en|{FILE}|13.05", "13.05", "Service fee waivers", "Managers may request a waiver.")
PROBE = {**_source(PROBE_ID, "21.09", "Trademarks", "Use of the logo requires written approval."), "source_uri": f"opensearch-section://{FILE}/21.09"}
TEXT_HITS = [_hit(PARENT, 42.0), _hit(CHILD, 30.0), _hit(REFUNDS, 25.0), _hit(EXEMPT, 20.0), _hit(LEVELS, 12.0), _hit(SHIPPING, 8.0), _hit(PROBE, 1.5)]
VECTOR_HITS = [_hit(CHILD, 0.91), _hit(WAIVERS, 0.88), _hit(PARENT, 0.85), _hit(PROBE, 0.30)]


class _Client:
    def __init__(self, text_hits: list[dict], vector_hits: list[dict], fail_on: str | None = None) -> None:
        self.text_hits, self.vector_hits, self.fail_on = text_hits, vector_hits, fail_on
        self.bodies: list[str] = []

    def search(self, index, body):
        del index
        self.bodies.append(json.dumps(body, sort_keys=True))
        kind = "vector" if "knn" in body.get("query", {}) else "text"
        if kind == self.fail_on:
            raise ConnectionTimeout(599, "stub search timeout", None)
        hits = self.vector_hits if kind == "vector" else self.text_hits
        if callable(hits):
            return {"hits": {"hits": hits(len(self.bodies))}}
        return {"hits": {"hits": copy.deepcopy(hits)}}


class _Runtime:
    def __init__(self, reply: str, error: Exception | None = None) -> None:
        self.reply, self.error = reply, error
        self.calls: list[str] = []

    def converse(self, **kwargs):
        self.calls.append(json.dumps(kwargs, sort_keys=True, default=str))
        if self.error is not None:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.reply}]}}}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    for name, value in {
        "ADMIN_INGESTION_GENERATION_POINTER_ENABLED": False,
        "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED": True,
        "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED": False,
        "OPENSEARCH_ALLOW_ENGLISH_FALLBACK": False,
        "OPENSEARCH_GLOBAL_DOCUMENT_LANGUAGE": "en",
        "OPENSEARCH_RESULT_COUNT": 5,
        "OPENSEARCH_CANDIDATE_COUNT": 30,
        "OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT": 30,
        "RETRIEVAL_PARENT_DIVERSITY_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(opensearch_sections, "embed_text", lambda _text: [0.0] * 4)


def _provider(monkeypatch, *, plan=None, text_hits=None, vector_hits=None, reply=SELECTOR_REPLY, error=None, fail_on=None):
    client = _Client(TEXT_HITS if text_hits is None else text_hits, VECTOR_HITS if vector_hits is None else vector_hits, fail_on)
    runtime = _Runtime(reply, error)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: client)
    monkeypatch.setattr(opensearch_sections, "get_aws_clients", lambda: SimpleNamespace(bedrock_runtime=runtime))
    provider = OpenSearchSectionProvider()
    monkeypatch.setattr(provider, "_build_search_plan", lambda message, *_: plan or RetrievalQueryPlan([message]))
    return provider, client, runtime


def _retrieve(monkeypatch, *, capture: bool, message: str = QUESTION, **kwargs):
    provider, client, runtime = _provider(monkeypatch, **kwargs)
    # Looked up at call time, so each test fails on its own against code without the capture.
    token = opensearch_sections.enable_rank_list_capture() if capture else None
    try:
        result = provider.retrieve(message, "CA", "en", "fbo", "cid-rank-lists")
    finally:
        if token is not None:
            opensearch_sections.disable_rank_list_capture(token)
    return result, client, runtime


def _documents(result) -> list[tuple]:
    return [(d.id, d.score, d.title, d.content, d.source, d.metadata) for d in result.documents]


def _without_rank_keys(metadata: dict) -> dict:
    return {key: value for key, value in metadata.items() if key not in RANK_KEYS}


def _assert_retrieval_unchanged(on, off, on_client=None, off_client=None, on_runtime=None, off_runtime=None) -> None:
    assert _documents(on) == _documents(off)
    assert on.citations == off.citations
    assert on.confidence == off.confidence
    assert _without_rank_keys(on.metadata) == off.metadata
    if on_client is not None:
        assert on_client.bodies == off_client.bodies
    if on_runtime is not None:
        assert on_runtime.calls == off_runtime.calls


# --- default off, request-scoped ---------------------------------------------


def test_with_capture_off_retrieval_emits_exactly_the_existing_metadata_keys(monkeypatch) -> None:
    result, _, _ = _retrieve(monkeypatch, capture=False)

    assert result.documents, "the stub hits must survive retrieval for this control to mean anything"
    assert set(result.metadata) == EXISTING_KEYS
    assert not any("rank_list" in name.lower() for name in dir(settings))


def test_the_switch_is_off_by_default_request_scoped_and_not_configurable() -> None:
    flag = opensearch_sections._rank_list_capture_enabled
    assert flag.get() is False

    token = opensearch_sections.enable_rank_list_capture()
    try:
        assert flag.get() is True
    finally:
        opensearch_sections.disable_rank_list_capture(token)
    assert flag.get() is False

    def enable_inside() -> bool:
        opensearch_sections.enable_rank_list_capture()
        return flag.get()

    assert contextvars.copy_context().run(enable_inside) is True
    assert flag.get() is False, "a copied request context must not switch the parent on"

    source = inspect.getsource(opensearch_sections)
    block = source[source.index("RANK_LIST_CAPTURE_VERSION = 1"): source.index("def _generation_filters(")]
    assert "environ" not in block and "getenv" not in block
    assert block.replace("settings.OPENSEARCH_CANDIDATE_COUNT", "").count("settings.") == 0


# --- capture on: identical retrieval, real lists -----------------------------


def test_capture_on_changes_no_document_order_score_confidence_search_or_selector_call(monkeypatch) -> None:
    off, off_client, off_runtime = _retrieve(monkeypatch, capture=False)
    on, on_client, on_runtime = _retrieve(monkeypatch, capture=True)

    _assert_retrieval_unchanged(on, off, on_client, off_client, on_runtime, off_runtime)
    assert len(on_runtime.calls) == 1
    assert set(on.metadata) - set(off.metadata) == set(RANK_KEYS)


def test_capture_records_live_ranks_raw_scores_and_child_section_ids(monkeypatch) -> None:
    on, _, _ = _retrieve(monkeypatch, capture=True)
    lists = on.metadata["retrieval_rank_lists"]
    documents = lists["documents"]

    assert lists["version"] == 1
    assert lists["hit_fields"] == ["section_id", "rank", "raw_score", "document"]
    assert [(s["kind"], s["query_index"], s["weight"], s["hit_count"]) for s in lists["searches"]] == [
        ("text", 0, 1.0, len(TEXT_HITS)),
        ("vector", 0, 1.0, len(VECTOR_HITS)),
    ]
    for search, expected in zip(lists["searches"], (TEXT_HITS, VECTOR_HITS), strict=True):
        assert [(hit[0], hit[1], hit[2], documents[hit[3]][0]) for hit in search["hits"]] == [
            (hit["_source"]["section_id"], rank, hit["_score"], hit["_id"]) for rank, hit in enumerate(expected, start=1)
        ]
    child = next(document for document in documents if document[0] == CHILD["id"])
    assert child == [CHILD["id"], "13.01-b", "13.01", "CA", "en", "country", "policy", "list_item"]

    # candidate_section_ids is parallel to candidate_sources, whose "section" is the parent.
    sources, section_ids = on.metadata["candidate_sources"], on.metadata["candidate_section_ids"]
    assert len(section_ids) == len(sources) == len(lists["merged_order"])
    position = section_ids.index("13.01-b")
    assert sources[position]["section"] == "13.01"

    merged_ids = [documents[index][0] for _section, _score, index in lists["merged_order"]]
    assert [documents[index][0] for index in lists["selector_candidates"]] == merged_ids
    assert on.metadata["evidence_selector_candidate_section_ids"] == section_ids
    assert on.metadata["evidence_selector_selected_ranks"] == [2, 1, 9]
    assert lists["selector_outcome"] == "parsed"
    assert lists["recording_errors"] == 0

    blob = json.dumps({key: on.metadata[key] for key in RANK_KEYS})
    assert QUESTION not in blob
    for hit in [*TEXT_HITS, *VECTOR_HITS]:
        assert hit["_source"]["content"] not in blob
        assert hit["_source"]["section_title"] not in blob


def _full_plan_message() -> str:
    message = "What does section 13.01 say about the service fee?"
    assert opensearch_sections._section_reference(message), "the message must trigger the exact-section search"
    return message


def test_every_search_kind_is_labelled_weighted_and_leaves_retrieval_unchanged(monkeypatch) -> None:
    message = _full_plan_message()
    plan = RetrievalQueryPlan([message, "service charge per order"], include_global_documents=True, prefer_outline=True)

    off, off_client, off_runtime = _retrieve(monkeypatch, capture=False, message=message, plan=plan)
    on, on_client, on_runtime = _retrieve(monkeypatch, capture=True, message=message, plan=plan)

    _assert_retrieval_unchanged(on, off, on_client, off_client, on_runtime, off_runtime)
    lists = on.metadata["retrieval_rank_lists"]
    assert [(s["kind"], s["query_index"], s["weight"]) for s in lists["searches"]] == [
        ("exact", None, 1.0),
        ("text", 0, 1.0), ("vector", 0, 1.0),
        ("text", 1, 0.88), ("vector", 1, 0.88),
        ("outline", None, 1.0),
        ("global_text", None, 1.0), ("global_vector", None, 1.0),
    ]
    assert (lists["query_count"], lists["prefer_outline"], lists["include_global_documents"]) == (2, True, True)


def test_capture_serializes_only_trusted_runtime_scope_and_resolved_follow_up_provenance(monkeypatch) -> None:
    plan = RetrievalQueryPlan(
        [QUESTION],
        include_global_documents=True,
        runtime_scope_intent={
            "provenance": "runtime",
            "intent": "international_sponsoring",
            "decision_source": "deterministic_sponsoring_route",
        },
        authorized_policy_market="CA",
    )
    context_token = opensearch_sections.set_rank_list_context_resolution(
        {
            "provenance": "runtime",
            "status": "resolved_dependent_follow_up",
            "prior_user_turn_id": "history-user-2-0123456789abcdef",
        }
    )
    try:
        on, _, _ = _retrieve(monkeypatch, capture=True, plan=plan)
    finally:
        opensearch_sections.reset_rank_list_context_resolution(context_token)

    lists = on.metadata["retrieval_rank_lists"]
    assert lists["runtime_scope_intent"] == plan.runtime_scope_intent
    assert lists["authorized_policy_market"] == "CA"
    assert lists["context_resolution"] == {
        "provenance": "runtime",
        "status": "resolved_dependent_follow_up",
        "prior_user_turn_id": "history-user-2-0123456789abcdef",
    }
    case = tool.capture_case_from_rank_lists(
        json.loads(json.dumps(on.metadata)), case_id="provenance", question=QUESTION, country="CA", language="en",
        required_sections=[],
    )
    assert case["runtime_scope_intent"] == plan.runtime_scope_intent
    assert case["authorized_policy_market"] == "CA"
    assert case["context_resolution"] == lists["context_resolution"]


def test_capture_is_backward_compatible_when_new_runtime_provenance_is_absent(monkeypatch) -> None:
    on, _, _ = _retrieve(monkeypatch, capture=True)
    lists = on.metadata["retrieval_rank_lists"]
    assert lists["runtime_scope_intent"] is None
    assert lists["authorized_policy_market"] is None
    assert lists["context_resolution"] is None
    case = tool.capture_case_from_rank_lists(
        json.loads(json.dumps(on.metadata)), case_id="legacy", question=QUESTION, country="CA", language="en",
        required_sections=[],
    )
    assert case["runtime_scope_intent"] is None
    assert case["authorized_policy_market"] is None
    assert case["context_resolution"] is None


def test_converted_lists_are_exactly_the_hits_production_merged(monkeypatch) -> None:
    """Replaying the captured lists with the rows' text reproduces the live merged order."""
    seen: dict = {}
    original = OpenSearchSectionProvider._merge_hits

    def spy(self, text_hits, vector_hits, message, **kwargs):
        seen.update(text=copy.deepcopy(text_hits), vector=copy.deepcopy(vector_hits), kwargs=kwargs)
        return original(self, text_hits, vector_hits, message, **kwargs)

    monkeypatch.setattr(OpenSearchSectionProvider, "_merge_hits", spy)
    message = _full_plan_message()
    plan = RetrievalQueryPlan([message, "service charge per order"], include_global_documents=True, prefer_outline=True)
    on, _, _ = _retrieve(monkeypatch, capture=True, message=message, plan=plan)

    by_id = {hit["_id"]: hit["_source"] for hit in [*TEXT_HITS, *VECTOR_HITS]}
    case = tool.capture_case_from_rank_lists(
        json.loads(json.dumps(on.metadata)), case_id="fidelity", question=message, country="CA", language="en",
        required_sections=["CA:13.01-b"], source_lookup=lambda document: by_id.get(document["id"]),
    )
    text_hits, vector_hits = tool._flatten_capture(case)

    assert [(h["_id"], h["_score"]) for h in text_hits] == [(h["_id"], h["_score"]) for h in seen["text"]]
    assert [(h["_id"], h["_score"]) for h in vector_hits] == [(h["_id"], h["_score"]) for h in seen["vector"]]
    assert case["source_text"] == {"documents": 8, "resolved_from_extractions": 8, "identifiers_only": 0}
    replayed = original(OpenSearchSectionProvider(), text_hits, vector_hits, message, **seen["kwargs"])
    assert [(row["id"], score) for row, score in replayed] == [
        (identifier, score) for _section, score, identifier in case["captured"]["merged_order"]
    ]


# --- failure and empty paths ------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "error", "hardening", "outcome", "ranks"),
    [
        ("", ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"), False, "failed", None),
        ("not json at all", None, False, "invalid", None),
        ('{"relevant_evidence":false,"selected_ranks":[]}', None, True, "parsed", []),
    ],
    ids=["selector-raises", "selector-invalid", "selector-finds-nothing"],
)
def test_selector_failure_paths_do_not_crash_and_are_recorded(monkeypatch, reply, error, hardening, outcome, ranks) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RETRIEVAL_HARDENING_ENABLED", hardening)

    off, off_client, off_runtime = _retrieve(monkeypatch, capture=False, reply=reply, error=error)
    on, on_client, on_runtime = _retrieve(monkeypatch, capture=True, reply=reply, error=error)

    _assert_retrieval_unchanged(on, off, on_client, off_client, on_runtime, off_runtime)
    lists = on.metadata["retrieval_rank_lists"]
    assert lists["selector_outcome"] == outcome
    assert on.metadata["evidence_selector_selected_ranks"] == ranks
    assert on.metadata["evidence_selector_candidate_section_ids"], "the candidates shown are recorded even when the call fails"
    assert lists["recording_errors"] == 0


def test_zero_candidates_do_not_crash(monkeypatch) -> None:
    off, _, off_runtime = _retrieve(monkeypatch, capture=False, text_hits=[], vector_hits=[])
    on, _, on_runtime = _retrieve(monkeypatch, capture=True, text_hits=[], vector_hits=[])

    _assert_retrieval_unchanged(on, off)
    assert on.documents == [] and on_runtime.calls == off_runtime.calls == []
    lists = on.metadata["retrieval_rank_lists"]
    assert [search["hits"] for search in lists["searches"]] == [[], []]
    assert (lists["merged_count"], lists["merged_order"], lists["selector_outcome"]) == (0, [], "not_called")
    assert on.metadata["candidate_section_ids"] == []
    assert on.metadata["evidence_selector_candidate_section_ids"] is None
    assert on.metadata["evidence_selector_selected_ranks"] is None


def test_an_opensearch_failure_keeps_the_lists_captured_before_it(monkeypatch) -> None:
    off, _, _ = _retrieve(monkeypatch, capture=False, fail_on="vector")
    on, _, _ = _retrieve(monkeypatch, capture=True, fail_on="vector")

    assert off.availability is RetrievalAvailability.DEGRADED
    assert off.metadata["failed_search_channels"] == ["vector"]
    assert off.documents, "the healthy text channel remains usable"
    _assert_retrieval_unchanged(on, off)
    assert on.availability is RetrievalAvailability.DEGRADED
    assert on.metadata["failed_search_channels"] == ["vector"]
    assert [search["kind"] for search in on.metadata["retrieval_rank_lists"]["searches"]] == ["text"]


def test_with_the_selector_disabled_no_selector_candidates_are_recorded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_ENABLED", False)

    off, _, _ = _retrieve(monkeypatch, capture=False)
    on, _, on_runtime = _retrieve(monkeypatch, capture=True)

    _assert_retrieval_unchanged(on, off)
    assert on_runtime.calls == []
    assert on.metadata["retrieval_rank_lists"]["selector_outcome"] == "not_called"
    assert on.metadata["evidence_selector_candidate_section_ids"] is None
    assert on.metadata["retrieval_rank_lists"]["merged_order"]


def test_the_capture_is_bounded(monkeypatch) -> None:
    long = "x" * 300

    def unique_hits(call: int) -> list[dict]:
        return [
            _hit({**_source(f"{call}-{index}-{long}", f"{index}.{call}-{long}", "Fee", "Fee text."), "country": long}, 50.0 - index)
            for index in range(40)
        ]

    message = _full_plan_message()
    plan = RetrievalQueryPlan([f"{message} {index}" for index in range(12)], include_global_documents=True, prefer_outline=True)
    reply = json.dumps({"selected_ranks": list(range(1, 41))})
    on, _, _ = _retrieve(monkeypatch, capture=True, message=message, plan=plan, text_hits=unique_hits, vector_hits=unique_hits, reply=reply)

    lists = on.metadata["retrieval_rank_lists"]
    assert len(lists["searches"]) == 24 and lists["searches_not_recorded"] == 4
    assert all(search["hit_count"] == 40 and len(search["hits"]) == 30 for search in lists["searches"])
    assert lists["merged_count"] > 60 and len(lists["merged_order"]) == 60
    assert len(lists["documents"]) <= 24 * 30 + 60
    assert all(len(document[0]) <= 160 and len(document[1]) <= 48 and len(document[3]) <= 24 for document in lists["documents"])
    assert len(on.metadata["evidence_selector_selected_ranks"]) == 30
    assert len(on.metadata["candidate_section_ids"]) == 30
    size = len(json.dumps({key: on.metadata[key] for key in RANK_KEYS}))
    assert size <= 400_000, size


# --- orchestrator hook and leakage ------------------------------------------


class _Governance:
    def evaluate(self, **_: object) -> GovernanceDecision:
        return GovernanceDecision(allowed=True, action=GovernanceAction.ALLOW, provider="test")


class _BedrockLikeRouter:
    """Carries the retrieval metadata into the model metadata, as BedrockProvider does."""

    def generate(self, prompt, retrieval_result, correlation_id):
        del prompt, correlation_id
        return ModelResponse(
            text=ANSWER, citations=[document.to_source() for document in retrieval_result.documents], confidence=0.9,
            provider="bedrock", model_name="model-under-test", metadata={"retrieval": retrieval_result.metadata},
        )


@pytest.fixture
def sinks(monkeypatch):
    recorded: dict[str, list[str]] = {"audit": [], "cache": [], "semantic_cache": [], "session": []}
    stubs = {
        "validate_and_touch_session": lambda *_: None,
        "has_valid_consent": lambda *_: True,
        "scrub_pii": lambda text, *_, **__: text,
        "build_cache_key": lambda *_: "cache-key",
        "get_cache_value": lambda *_: None,
        "get_session_history": lambda *_: "",
        "semantic_cache_active": lambda *_, **__: False,
        "get_semantic_cache_value": lambda *_, **__: None,
        "append_session_turn": lambda *args: recorded["session"].append(json.dumps(args, default=str)),
        "write_audit_event": lambda *args: recorded["audit"].append(json.dumps(args, default=str)),
        # Exactly what the real writers serialise.
        "set_cache_value": lambda _key, value, *_: recorded["cache"].append(json.dumps(value)),
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(chat_orchestrator, name, stub)

    from services.semantic_cache import evidence_fingerprint

    def semantic(_message, _country, _language, _role, evidence, response, _cid):
        recorded["semantic_cache"].append(json.dumps({"evidence_fingerprint": evidence_fingerprint(evidence), "response": response}))

    monkeypatch.setattr(chat_orchestrator, "set_semantic_cache_value", semantic)
    monkeypatch.setattr(AIOrchestrator, "_should_semantic_cache_response", lambda self, response: True)
    return recorded


def _orchestrator(monkeypatch) -> AIOrchestrator:
    provider, _, _ = _provider(monkeypatch)
    return AIOrchestrator(retriever=RetrievalService(provider=provider), router=_BedrockLikeRouter(), governance=_Governance())


def _ask(orchestrator: AIOrchestrator, *, capture: bool, monkeypatch):
    monkeypatch.setattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED", capture)
    return orchestrator.handle_chat(ChatRequest(message=QUESTION, sessionId="session-1", country="CA", language="en"), "cid-orchestrator")


def _delivered(response) -> tuple:
    metadata = {key: value for key, value in response.metadata.items() if key != "diagnostic_capture"}
    if isinstance(metadata.get("retrieval"), dict):
        metadata["retrieval"] = _without_rank_keys(metadata["retrieval"])
    return response.answer, response.citations, response.confidence, metadata


def test_the_orchestrator_turns_rank_lists_on_only_inside_its_diagnostic_capture(monkeypatch, sinks) -> None:
    orchestrator = _orchestrator(monkeypatch)

    off = _ask(orchestrator, capture=False, monkeypatch=monkeypatch)
    on = _ask(orchestrator, capture=True, monkeypatch=monkeypatch)

    assert off.metadata.get("model_name") == "model-under-test", "the answer must come through generation"
    assert "diagnostic_capture" not in off.metadata
    assert not set(RANK_KEYS) & set(off.metadata.get("retrieval") or {})
    question = on.metadata["diagnostic_capture"]["retrievals"][0]
    assert question["stage"] == "question"
    assert set(RANK_KEYS) <= set(question["metadata"])
    assert question["metadata"]["retrieval_rank_lists"]["searches"][0]["hits"][0][1] == 1
    assert _delivered(on) == _delivered(off)
    assert opensearch_sections._rank_list_capture_enabled.get() is False


def test_the_rank_list_switch_ends_with_the_request_even_when_it_raises(monkeypatch, sinks) -> None:
    orchestrator = _orchestrator(monkeypatch)
    monkeypatch.setattr(chat_orchestrator, "validate_and_touch_session", lambda *_: False)

    with pytest.raises(SessionExpiredError):
        _ask(orchestrator, capture=True, monkeypatch=monkeypatch)

    assert opensearch_sections._rank_list_capture_enabled.get() is False
    assert chat_orchestrator._DIAGNOSTIC_CAPTURE.get() is None


def test_rank_lists_reach_no_api_response_cache_audit_trace_metric_analytics_or_log(monkeypatch, sinks, caplog) -> None:
    """Drive the real /api/chat handler with capture on and read every sink it writes."""
    from api import routes
    from app.metrics import responses as response_metrics
    from app.operations import pipeline_trace_store
    from services import analytics

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(settings, "WIDGET_AUTH_REQUIRED", False)
    monkeypatch.setattr(chat_orchestrator, "DIAGNOSTIC_CAPTURE_ENABLED", True)
    orchestrator = _orchestrator(monkeypatch)
    delivered: list = []

    class _Recording:
        def handle_chat(self, body, correlation_id):
            delivered.append(orchestrator.handle_chat(body, correlation_id))
            return delivered[-1]

    monkeypatch.setattr(routes, "ai_orchestrator", _Recording())
    traces: list[str] = []
    for method in ("start", "record", "finish"):
        monkeypatch.setattr(pipeline_trace_store, method, lambda *args, **kwargs: traces.append(json.dumps([args, kwargs], default=str)))
    metrics: list[str] = []
    monkeypatch.setattr(response_metrics, "_record", lambda metric: metrics.append(repr(metric)))
    persisted: list[str] = []

    class _Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def execute(self, _statement, parameters=None):
            persisted.append(json.dumps(parameters, default=str))

    monkeypatch.setattr(analytics, "get_engine", lambda: SimpleNamespace(begin=lambda: _Transaction()))

    envelope = routes.chat(
        ChatRequest(message=QUESTION, sessionId="session-1", country="CA", language="en"),
        SimpleNamespace(state=SimpleNamespace(correlation_id="cid-leak")),
    )

    # Positive control: the lists, and the never-delivered probe, did travel inside the response.
    response = delivered[0]
    internal = json.dumps(response.metadata, default=str)
    assert all(key in internal for key in RANK_KEYS) and PROBE_ID in internal
    assert response.metadata.get("model_name") == "model-under-test"
    assert persisted and sinks["cache"] and sinks["semantic_cache"] and traces and metrics
    formatter = JsonFormatter()
    logs = []
    for record in caplog.records:
        rendered = json.loads(formatter.format(record))
        logs.append(" ".join((record.getMessage(), json.dumps(rendered, default=str), repr(record.__dict__))))
    written = {
        "api_response": [json.dumps(envelope.model_dump(), default=str), json.dumps(response.to_api_result(), default=str)],
        "cache_value": [json.dumps(response.to_cache_value()), *sinks["cache"]],
        "semantic_cache": sinks["semantic_cache"],
        "audit": sinks["audit"],
        "session": sinks["session"],
        "pipeline_trace": traces,
        "metrics": metrics,
        "analytics": persisted,
        "logs": logs,
    }
    for sink, payloads in written.items():
        for payload in payloads:
            for marker in (*RANK_KEYS, PROBE_ID, "diagnostic_capture"):
                assert marker not in payload, f"{marker!r} reached {sink}"


# --- converter ----------------------------------------------------------------


def _captured_metadata(monkeypatch) -> dict:
    on, _, _ = _retrieve(monkeypatch, capture=True)
    return json.loads(json.dumps(on.metadata))


def _artifact(metadata: dict | None, *, case_id: str = "case-1") -> dict:
    retrievals = [] if metadata is None else [{"stage": "question", "metadata": metadata}]
    capture = {"turns": [{"turn": "final", "diagnostic_capture": {"retrievals": retrievals}}], "final_retrieval": None}
    return {"results": [{"id": case_id, "question": QUESTION, "request_country": "CA", "runs": [{"capture": capture}]}]}


def _convert(tmp_path: Path, artifact: object, *, output: str = "capture.json", pack: Path | None = None):
    artifact_path = tmp_path / f"artifact-{output}"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    arguments = argparse.Namespace(
        artifact=str(artifact_path), output=str(tmp_path / output), pack=str(pack) if pack else None,
        source_root=[], directory=None, code_root=tool.ROOT,
    )
    return tool.command_convert_artifact(arguments)


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("run_benchmark", PROJECT_ROOT / "scripts" / "run_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli(*arguments: str, cwd: Path) -> tuple[int, dict]:
    environment = {**os.environ, "PYTHONPATH": str(tool.ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("BEDROCK_MODEL_ARN", None)
    completed = subprocess.run(
        [sys.executable, str(tool.ROOT / "scripts" / "offline_retrieval_replay.py"), *arguments],
        capture_output=True, env=environment, cwd=str(cwd), timeout=180, check=False,
    )
    return completed.returncode, json.loads(completed.stdout.decode("utf-8"))


def test_a_benchmark_artifact_converts_and_rrf_reports_on_the_captured_lists(monkeypatch, sinks, tmp_path) -> None:
    """End to end offline: stub OpenSearch, orchestrator capture, the runner's own record, convert, rrf."""
    benchmark = _load_benchmark()
    provider, _, _ = _provider(monkeypatch)
    retrievals: list = []

    class _Recorder:
        def retrieve(self, *args, **kwargs):
            retrievals.append(provider.retrieve(*args, **kwargs))
            return retrievals[-1]

    orchestrator = AIOrchestrator(retriever=_Recorder(), router=_BedrockLikeRouter(), governance=_Governance())
    with benchmark._orchestrator_diagnostic_capture() as status:
        response = orchestrator.handle_chat(ChatRequest(message=QUESTION, sessionId="session-1", country="CA", language="en"), "cid-e2e")
    assert status == "enabled"
    capture = benchmark.capture_record(SimpleNamespace(retrieval=retrievals[-1], response=response, prior_responses=()), status)
    artifact = {"results": [{"id": "ho-rank-01", "question": QUESTION, "request_country": "CA", "runs": [{"capture": capture}]}]}
    artifact_path = tmp_path / "run-result.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps({"cases": [{"id": "ho-rank-01", "country": "CA", "language": "en",
                                                "expected": {"required_sections": ["CA:13.01-b", "sponsoring-099-x"]}}]}), encoding="utf-8")
    capture_path = tmp_path / "rank-capture.json"

    code, converted = _cli("convert-artifact", "--artifact", str(artifact_path), "--output", str(capture_path), "--pack", str(pack_path), cwd=tmp_path)

    assert (code, converted["status"]) == (0, "CONVERTED"), converted
    document = json.loads(capture_path.read_text(encoding="utf-8"))
    assert document["schema"] == tool.CAPTURE_SCHEMA and document["approximate"] is False
    case = document["cases"][0]
    assert (case["case_id"], case["language"], case["rank_lists_from"]) == ("ho-rank-01", "en", "final_turn_question_retrieval")
    assert case["required_sections"] == ["CA:13.01-b"] and case["unscored_required_sections"] == ["sponsoring-099-x"]
    assert [search["kind"] for search in case["searches"]] == ["text", "vector"]
    assert [hit["_id"] for hit in case["searches"][1]["hits"]] == [hit["_id"] for hit in VECTOR_HITS]

    code, report = _cli("rrf", "--capture", str(capture_path), cwd=tmp_path)

    assert code == 0, report
    assert report.get("status") != "BLOCKED" and report["approximate"] is False
    assert report["cases"][0]["production_positions"]["CA:13.01-b"] is not None
    assert report["cases"][0]["rrf_positions"]["CA:13.01-b"] is not None


def test_ids_resolve_to_local_extraction_rows_when_a_source_root_is_given(monkeypatch, tmp_path) -> None:
    metadata = _captured_metadata(monkeypatch)
    extraction = tmp_path / "root" / "outputs/chunk-comparison-full/current/CA/en/policy.sections.jsonl"
    extraction.parent.mkdir(parents=True)
    rows = [
        {"source_file": FILE, "country": "CA", "language": "en", "section_id": source["section_id"], "title": source["section_title"],
         "start_page": 4, "end_page": 4, "content": source["content"], "chunk_type": source["chunk_type"], "parent_section_id": source["parent_section_id"]}
        for source in (PARENT, CHILD)
    ]
    extraction.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps(_artifact(metadata)), encoding="utf-8")

    code, converted = _cli("convert-artifact", "--artifact", str(artifact_path), "--output", str(tmp_path / "resolved.json"),
                           "--source-root", str(tmp_path / "root"), cwd=tmp_path)

    assert code == 0, converted
    assert converted["source_text"]["case-1"] == {"documents": 8, "resolved_from_extractions": 2, "identifiers_only": 6}
    hits = json.loads((tmp_path / "resolved.json").read_text(encoding="utf-8"))["cases"][0]["searches"][0]["hits"]
    assert hits[0]["_source"]["content"] == PARENT["content"]


def _mutations():
    def search(metadata):
        return metadata["retrieval_rank_lists"]["searches"][0]

    def lists(metadata):
        return metadata["retrieval_rank_lists"]

    return {
        "not-an-object": lambda m: m.update(retrieval_rank_lists=[]),
        "version": lambda m: lists(m).update(version=2),
        "recording-failed": lambda m: lists(m).update(recording_failed=True),
        "document-fields": lambda m: lists(m).update(document_fields=["id"]),
        "documents-not-list": lambda m: lists(m).update(documents={}),
        "document-short": lambda m: lists(m)["documents"][0].pop(),
        "document-empty-id": lambda m: lists(m)["documents"][0].__setitem__(0, ""),
        "searches-not-list": lambda m: lists(m).update(searches={}),
        "unknown-kind": lambda m: search(m).update(kind="rerank"),
        "weight-string": lambda m: search(m).update(weight="1.0"),
        "weight-nan": lambda m: search(m).update(weight=math.nan),
        "negative-query-index": lambda m: search(m).update(query_index=-1),
        "hits-not-list": lambda m: search(m).update(hits={}),
        "hit-length": lambda m: search(m)["hits"][0].pop(),
        "rank-bool": lambda m: search(m)["hits"][0].__setitem__(1, True),
        "rank-repeated": lambda m: search(m)["hits"][1].__setitem__(1, 1),
        "score-string": lambda m: search(m)["hits"][0].__setitem__(2, "42"),
        "score-infinite": lambda m: search(m)["hits"][0].__setitem__(2, math.inf),
        "document-out-of-range": lambda m: search(m)["hits"][0].__setitem__(3, 999),
        "section-disagrees": lambda m: search(m)["hits"][0].__setitem__(0, "99.99"),
        "selector-candidate-out-of-range": lambda m: lists(m).update(selector_candidates=[999]),
        "selected-ranks-strings": lambda m: lists(m).update(selector_selected_ranks=["1"]),
        "untrusted-scope-intent": lambda m: lists(m).update(runtime_scope_intent={"provenance": "pack", "intent": "directory", "decision_source": "deterministic_directory_route"}),
        "unknown-scope-intent": lambda m: lists(m).update(runtime_scope_intent={"provenance": "runtime", "intent": "other", "decision_source": "deterministic_directory_route"}),
        "mismatched-intent-source": lambda m: lists(m).update(runtime_scope_intent={"provenance": "runtime", "intent": "directory", "decision_source": "planner_global_scope_only"}),
        "scope-intent-extra-key": lambda m: lists(m).update(runtime_scope_intent={"provenance": "runtime", "intent": "policy", "decision_source": "deterministic_policy_route", "extra": True}),
        "malformed-policy-market": lambda m: lists(m).update(authorized_policy_market="CAN"),
        "context-without-prior-turn": lambda m: lists(m).update(context_resolution={"provenance": "runtime", "status": "resolved_dependent_follow_up"}),
        "context-prior-turn-without-resolution": lambda m: lists(m).update(context_resolution={"provenance": "runtime", "status": "not_dependent", "prior_user_turn_id": "not-allowed"}),
        "context-raw-message-id": lambda m: lists(m).update(context_resolution={"provenance": "runtime", "status": "resolved_dependent_follow_up", "prior_user_turn_id": "What is the return policy?"}),
        "context-extra-key": lambda m: lists(m).update(context_resolution={"provenance": "runtime", "status": "unresolved", "extra": "not-allowed"}),
    }


@pytest.mark.parametrize("mutation", list(_mutations()))
def test_the_converter_rejects_malformed_rank_lists(monkeypatch, tmp_path, mutation) -> None:
    metadata = _captured_metadata(monkeypatch)
    _mutations()[mutation](metadata)

    with pytest.raises(tool.CaptureFormatError):
        tool.capture_case_from_rank_lists(metadata, case_id="x", question=QUESTION, country="CA", language="en", required_sections=[])
    payload, code = _convert(tmp_path, _artifact(metadata))
    assert (code, payload["status"]) == (2, "INVALID")
    assert not (tmp_path / "capture.json").exists()


@pytest.mark.parametrize(
    "artifact",
    [[], {"results": {}}, {"results": [{"id": 1, "runs": []}]}, {"results": [{"id": "a", "runs": ["x"]}]},
     {"results": [{"id": "a", "runs": [{"capture": "x"}]}]}, {"results": [{"id": "a", "runs": [{"capture": {"turns": "x"}}]}]}],
    ids=["not-object", "results-not-list", "id-not-string", "run-not-object", "capture-not-object", "turns-not-list"],
)
def test_the_converter_rejects_malformed_artifacts(tmp_path, artifact) -> None:
    payload, code = _convert(tmp_path, artifact)

    assert (code, payload["status"]) == (2, "INVALID")
    assert not (tmp_path / "capture.json").exists()


def test_conversion_is_blocked_without_both_lists_and_never_replaces_its_output(monkeypatch, tmp_path) -> None:
    payload, code = _convert(tmp_path, _artifact(None))
    assert (code, payload["status"]) == (3, "BLOCKED")
    assert payload["skipped"][0]["reason"].startswith("no retrieval_rank_lists")
    assert not (tmp_path / "capture.json").exists()

    text_only = _captured_metadata(monkeypatch)
    text_only["retrieval_rank_lists"]["searches"] = [s for s in text_only["retrieval_rank_lists"]["searches"] if s["kind"] == "text"]
    payload, code = _convert(tmp_path, _artifact(text_only))
    assert (code, payload["status"]) == (3, "BLOCKED")
    assert payload["skipped"] == [{"case_id": "case-1", "reason": "text and vector lists were not both captured"}]

    existing = tmp_path / "capture.json"
    existing.write_text("keep", encoding="utf-8")
    payload, code = _convert(tmp_path, _artifact(_captured_metadata(monkeypatch)))
    assert (code, payload["status"]) == (2, "REFUSED")
    assert existing.read_text(encoding="utf-8") == "keep"

    blocked, code = tool.command_rrf(argparse.Namespace(capture=str(tmp_path / "missing.json"), k=60, code_root=tool.ROOT))
    assert (code, blocked["status"]) == (3, "BLOCKED")
