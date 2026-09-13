"""Offline retrieval replay tool: fusion maths, capture replay and stage attribution.

No network. In-process tests bypass the tool's runtime import and pass the real
settings and retrieval module explicitly; the output-encoding test runs the CLI
in a subprocess on a temporary extraction.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import pytest

from app.retrieval import opensearch_sections
from config import settings
from scripts import offline_retrieval_replay as tool


def _source(identifier: str, section_id: str, content: str = "text") -> dict[str, object]:
    return {
        "id": identifier,
        "country": "NO",
        "language": "no",
        "section_id": section_id,
        "section_title": "",
        "content": content,
        "search_text": content,
        "access_scope": "country",
        "document_type": "policy",
        "status": "active",
    }


def test_reciprocal_rank_fusion_sums_weighted_reciprocal_ranks() -> None:
    searches = [
        {"weight": 1.0, "hits": [{"_id": "a"}, {"_id": "b"}]},
        {"weight": 0.5, "hits": [{"_id": "b"}, {"_id": "c"}, {"_id": "b"}]},
    ]

    fused = tool.reciprocal_rank_fusion(searches, k=60)

    assert [identifier for identifier, _score in fused] == ["b", "a", "c"]
    scores = dict(fused)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["b"] == pytest.approx(1 / 62 + 0.5 / 61)
    assert scores["c"] == pytest.approx(0.5 / 62)


def test_flatten_capture_matches_runtime_weighting() -> None:
    case = {
        "searches": [
            {"kind": "exact", "weight": 1.0, "hits": [{"_id": "x", "_score": 3.0}]},
            {"kind": "text", "weight": 0.88, "hits": [{"_id": "y", "_score": 10.0}]},
            {"kind": "vector", "weight": 0.88, "hits": [{"_id": "z", "_score": 0.5}]},
            {"kind": "global_text", "hits": [{"_id": "g", "_score": 2.0}]},
        ]
    }

    text_hits, vector_hits = tool._flatten_capture(case)

    assert [hit["_id"] for hit in text_hits] == ["x", "y", "g"]
    assert text_hits[0]["_score"] == 100.0
    assert text_hits[1]["_score"] == pytest.approx(8.8)
    assert text_hits[2]["_score"] == 2.0
    assert vector_hits[0]["_score"] == pytest.approx(0.44)
    with pytest.raises(ValueError):
        tool._flatten_capture({"searches": [{"kind": "rerank", "hits": [{"_id": "q"}]}]})


def test_rrf_without_a_capture_is_blocked(tmp_path) -> None:
    payload, code = tool.command_rrf(argparse.Namespace(capture=str(tmp_path / "missing.json"), k=60, code_root=tool.ROOT))

    assert code == 3
    assert payload["status"] == "BLOCKED"
    assert payload["schema"] == tool.CAPTURE_SCHEMA


def test_compare_capture_replays_production_merge_and_rrf(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_RESULT_COUNT", 5)
    monkeypatch.setattr(settings, "OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT", 30)
    capture = {
        "schema": tool.CAPTURE_SCHEMA,
        "cases": [
            {
                "case_id": "synthetic",
                "question": "reapply after resignation",
                "required_sections": ["NO:17.08-c"],
                "searches": [
                    {
                        "kind": "text",
                        "weight": 1.0,
                        "hits": [
                            {"_id": "p", "_score": 50.0, "_source": _source("p", "17.08")},
                            {"_id": "o", "_score": 40.0, "_source": _source("o", "17.09-c")},
                        ],
                    },
                    {"kind": "text", "weight": 1.0, "hits": [{"_id": "c", "_score": 5.0, "_source": _source("c", "17.08-c")}]},
                ],
            }
        ],
    }

    report = tool.compare_capture({"settings": settings, "sections": opensearch_sections}, capture)

    case = report["cases"][0]
    assert case["production_positions"] == {"NO:17.08-c": 3}
    assert case["rrf_positions"] == {"NO:17.08-c": 1}
    assert case["production_recall"][5] == 1.0
    assert case["candidate_overlap"] == 3
    with pytest.raises(ValueError):
        tool.compare_capture({"settings": settings, "sections": opensearch_sections}, {"schema": "other", "cases": []})


def test_describe_row_names_the_stage_that_excluded_a_row() -> None:
    rows = [({"id": f"r{index}", "rank": 1.0, "access_scope": "country"}, 2.0 - index / 100) for index in range(40)]
    result = {
        "rows": rows,
        "limit": 30,
        "candidates": [*rows[:29], ({"id": "g", "rank": 0.1, "access_scope": "global"}, 0.1)],
        "per_query": [{"query": "q", "ids": ["r35", "r5"]}],
    }

    assert tool.describe_row(result, "r5")["stage"] == "selector candidate"
    assert tool.describe_row(result, "r29")["stage"].startswith("inside the merged top limit but evicted")
    assert tool.describe_row(result, "r35")["stage"].startswith("merged, but ranked below")
    assert tool.describe_row(result, "r35")["text_query_ranks"] == [{"query_index": 0, "rank": 1}]
    assert tool.describe_row(result, "missing")["stage"].startswith("not returned")


def test_bm25_approximation_only_returns_matching_rows_in_score_order() -> None:
    documents = [
        {"id": "a", "section_title": "Voluntary resignation", "content": "Reapply after one year.", "search_text": "Voluntary resignation Reapply after one year."},
        {"id": "b", "section_title": "Returns", "content": "Refund within 30 days.", "search_text": "Returns Refund within 30 days."},
        {"id": "c", "section_title": "Other", "content": "You may reapply later.", "search_text": "Other You may reapply later."},
    ]

    hits = tool._locale_search(documents).search("voluntary resignation reapply", 30)

    assert [hit["_id"] for hit in hits] == ["a", "c"]
    assert hits[0]["_score"] > hits[1]["_score"]


def test_cli_output_is_utf8_safe_when_stdout_is_not_utf8(tmp_path) -> None:
    """Redirected Windows stdout defaults to cp1252; the JSON must still read back as UTF-8."""
    extraction = tmp_path / "policy.sections.jsonl"
    content = "Section 17.08: Frivillig oppsigelse.\n(c) Søknad etter ett (1) år, særlig uten downlines."
    extraction.write_text(
        json.dumps(
            {
                "source_file": "policy.pdf", "country": "NO", "language": "no", "section_id": "17.08-c",
                "title": "Søknad etter ett (1) år", "start_page": 1, "end_page": 1, "content": content,
                "chunk_type": "list_item", "parent_section_id": "17.08",
            },
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "views.json"
    environment = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(tool.ROOT), "PYTHONDONTWRITEBYTECODE": "1"}

    with output.open("wb") as handle:
        completed = subprocess.run(
            [sys.executable, str(tool.ROOT / "scripts" / "offline_retrieval_replay.py"), "views", "--extraction", str(extraction), "--show", "17.08-c"],
            stdout=handle, stderr=subprocess.DEVNULL, env=environment, cwd=str(tool.ROOT), timeout=120, check=False,
        )

    assert completed.returncode == 0
    payload = json.loads(output.read_bytes().decode("utf-8"))
    assert "Heading path: 17.08 Frivillig oppsigelse. > (c)" in payload["shown_views"][0]["view"]
    assert "særlig" in payload["shown_views"][0]["view"]


def _rank_lists(documents: list[list[str]], searches: list[dict[str, object]]) -> dict[str, object]:
    return {
        "version": 1,
        "hit_fields": ["section_id", "rank", "raw_score", "document"],
        "document_fields": list(tool._RANK_LIST_DOCUMENT_FIELDS),
        "documents": documents,
        "searches": searches,
        "searches_not_recorded": 0,
        "merged_count": len(documents),
        "merged_order": [[document[1], float(len(documents) - index), index] for index, document in enumerate(documents)],
        "selector_outcome": None,
        "selector_candidates": list(range(len(documents))),
        "selector_relevant_evidence": None,
        "selector_selected_ranks": [1],
        "recording_errors": 0,
        "query_count": 1,
        "prefer_outline": False,
        "include_global_documents": False,
        "target_country_names": [],
    }


def _real_shaped_artifact(case_id: str = "ho-real-01") -> dict[str, object]:
    """A synthetic artifact matching exactly the real run_benchmark shape.

    Top-level ``summary``/``cases`` (not ``results``); each case has ``id``,
    ``question`` and ``runs``; each run's ``capture`` carries the rank lists at
    both ``final_retrieval.metadata`` and the final turn's
    ``diagnostic_capture.retrievals[stage=question][-1].metadata``, as the real
    runner artifact does.
    """
    documents = [
        ["NO|no|p|17.08-c", "17.08-c", "17.08", "NO", "no", "country", "policy", "list_item"],
        ["NO|no|p|17.08", "17.08", "", "NO", "no", "country", "policy", "section"],
    ]
    rank_lists = _rank_lists(
        documents,
        [
            {"kind": "text", "query_index": 0, "weight": 1.0, "hit_count": 2, "hits": [["17.08-c", 1, 50.0, 0], ["17.08", 2, 10.0, 1]]},
            {"kind": "vector", "query_index": None, "weight": 1.0, "hit_count": 1, "hits": [["17.08-c", 1, 0.9, 0]]},
        ],
    )
    metadata = {"retrieval_rank_lists": rank_lists, "candidate_section_ids": ["17.08-c", "17.08"]}
    capture = {
        "version": 1,
        "orchestrator_capture": "enabled",
        "turns": [
            {
                "turn": "final",
                "diagnostic_capture": {"retrievals": [{"stage": "question", "metadata": metadata}]},
            }
        ],
        "final_retrieval": {"metadata": metadata},
    }
    case = {
        "id": case_id,
        "question": "Can I reapply after resignation?",
        "source_country": "NO",
        "request_country": "NO",
        "runs": [{"capture": capture}],
    }
    return {"summary": {"cases": 1}, "cases": [case]}


def test_capture_from_artifact_reads_the_real_runner_shape() -> None:
    """The converter accepts the real ``run_benchmark`` artifact's top-level ``cases`` key."""
    document, skipped = tool.capture_from_artifact(_real_shaped_artifact())

    assert skipped == []
    assert document["schema"] == tool.CAPTURE_SCHEMA
    assert document["approximate"] is False
    case = document["cases"][0]
    assert case["case_id"] == "ho-real-01"
    kinds = {search["kind"] for search in case["searches"]}
    assert kinds == {"text", "vector"}
    text_search = next(search for search in case["searches"] if search["kind"] == "text")
    hit = text_search["hits"][0]
    assert hit["_id"] == "NO|no|p|17.08-c"
    assert hit["_score"] == 50.0
    assert set(hit["_source"]) == set(tool._RANK_LIST_DOCUMENT_FIELDS)
    assert "content" not in hit["_source"]
    assert case["source_text"] == {"documents": 2, "resolved_from_extractions": 0, "identifiers_only": 2}


def test_capture_from_artifact_still_accepts_the_older_results_key() -> None:
    """``{"results": [...]}`` keeps working: an existing test builds artifacts in that shape."""
    artifact = _real_shaped_artifact()
    artifact = {"results": artifact["cases"]}

    document, skipped = tool.capture_from_artifact(artifact)

    assert skipped == []
    assert document["cases"][0]["case_id"] == "ho-real-01"


def test_capture_from_artifact_rejects_an_artifact_with_neither_key() -> None:
    with pytest.raises(tool.CaptureFormatError):
        tool.capture_from_artifact({"summary": {}, "not_cases_or_results": []})


def test_measure_views_counts_children_hidden_from_their_parent_view() -> None:
    clause = ("ord " * 70).strip()
    parent_content = "\n".join(["17.09 Oppsigelse.", *[f"({letter}) {clause}" for letter in "abcdefg"]])
    documents = [
        {**_source("NO|no|p|17.09", "17.09", parent_content), "chunk_type": "section", "parent_section_id": "", "source_file": "p"},
        {**_source("NO|no|p|17.09-a", "17.09-a", f"Section 17.09: Oppsigelse.\n(a) {clause}"), "chunk_type": "list_item", "parent_section_id": "17.09", "source_file": "p"},
        {**_source("NO|no|p|17.09-g", "17.09-g", f"Section 17.09: Oppsigelse.\n(g) {clause}"), "chunk_type": "list_item", "parent_section_id": "17.09", "source_file": "p"},
    ]

    metrics = tool.measure_views({"sections": opensearch_sections}, documents)

    assert metrics["truncated"] == 1
    assert metrics["children_of_truncated_sections"] == 2
    assert metrics["children_outside_parent_view"] == 1
    assert metrics["rows_with_parent_heading"] == 2
