"""Offline retrieval replay over local section extractions.

This tool never contacts AWS, OpenSearch, Bedrock, Redis or a database, and it
never writes into ``exports/`` or the frozen pack. It reuses the real runtime
code wherever that code is deterministic and local:

* loader-shaped documents: ``scripts/ingestion/load_policy_sections_to_opensearch._document``
  (embedding stubbed);
* planner-off queries: ``providers._planned_retrieval_plan`` with the planner disabled;
* ``OpenSearchSectionProvider._merge_hits``, ``section_index._source_score`` and
  ``opensearch_sections._selector_candidates``;
* the selector view: ``opensearch_sections._selector_candidate_text``.

Sub-commands
------------
``candidates``  Approximate the selector's 30-candidate list for a question.
                BM25 is a local approximation of the live ``multi_match``
                (no fuzziness, no index-time analyzer parity) and there are
                **no vector hits** and **no planner queries**: kNN and the LLM
                planner cannot be reproduced offline, so every rank is
                approximate and directional only. ``--write-capture`` saves the
                approximated per-query lists in the capture schema below.

                Known gaps against the live queries, documented rather than
                implemented (each changes absolute scores, so ranks may differ):

                * ``_text_query``: the ``section_id^8`` keyword field is omitted
                  (it only matches when the whole query equals a section id);
                  ``match_phrase`` clauses are approximated as boost times the
                  field's BM25 score when the phrase occurs; ``fuzziness: AUTO``
                  and the live analyzer are not reproduced.
                * ``_directory_text_query``: the ``match_phrase`` on
                  ``metadata.record_country`` with the whole message (boost 18)
                  and per target country name (boost 40) are omitted; the
                  record-country hard filter is applied.
                * Not issued at all: vector (kNN) queries, the exact-section
                  lookup's live scoring (a fixed 100 is used), the outline
                  query, planner queries and non-English global translation.
``views``       Measure how the selector view truncates extraction rows and
                held-out governing passages, and whether it names each row's
                governing heading.
``rrf``         Compare the production merge against reciprocal rank fusion on
                a captured per-query candidate file. Without a capture of the
                live text *and* vector lists this reports BLOCKED.
``convert-artifact``
                Build that capture file (``approximate: false``) from a
                ``run_benchmark`` artifact whose final turn carries the
                application's ``retrieval_rank_lists`` diagnostic metadata:
                live per-search ranks and raw scores, identified by section and
                document id only. ``--source-root``/``--directory`` resolve those
                ids to local extraction rows so the production-merge replay has
                text to score; otherwise ``_source`` holds identifiers only.
                Reports BLOCKED (exit 3, nothing written) when no run carries
                both text and vector lists, INVALID (exit 2) for a malformed
                artifact or rank list, and never replaces ``--output``.

Capture schema (``askvera-retrieval-capture/1``)::

    {"schema": "askvera-retrieval-capture/1", "approximate": false,
     "cases": [{"case_id": "...", "question": "...", "country": "NO", "language": "no",
                "required_sections": ["NO:17.08-c"], "required_ids": [],
                "target_country_names": [], "ranking_queries": [], "prefer_outline": false,
                "searches": [{"kind": "text|vector|exact|outline|global_text|global_vector",
                              "query": "...", "weight": 1.0,
                              "hits": [{"_id": "...", "_score": <raw OpenSearch score>,
                                        "_source": {<indexed document without embedding>}}]}]}]}

``_score`` is the raw OpenSearch score before the runtime's per-query weight;
``weight`` is 1.0 for the first planned query and 0.88 for later ones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCHEMA = "askvera-retrieval-capture/1"
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)+|[^\W_]+", re.UNICODE)
_BM25_K1 = 1.2
_BM25_B = 0.75
_CLAUSE_MARKER_RE = re.compile(r"^[ \t]*\(?([a-z]|[ivx]{2,4})\)[ \t]", re.MULTILINE)
_SECTION_PREFIX_RE = re.compile(r"section\s+(\S+?):\s*(\S.*)$", re.IGNORECASE)


def _import_runtime(code_root: Path) -> dict[str, Any]:
    """Import runtime modules from ``code_root`` with every network path stubbed."""
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))
    from config import settings

    settings.BEDROCK_QUERY_PLANNER_ENABLED = False
    import scripts.ingestion.load_policy_sections_to_opensearch as loader
    from app.retrieval import opensearch_sections, providers
    from app.retrieval.typo_safety import safe_typo_ranking_queries

    loader.embed_text = lambda _text: []
    opensearch_sections.embed_text = lambda _text: []
    return {
        "settings": settings,
        "loader": loader,
        "sections": opensearch_sections,
        "providers": providers,
        "safe_typo_ranking_queries": safe_typo_ranking_queries,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _analyze(text: str) -> list[str]:
    return _TOKEN_RE.findall(unicodedata.normalize("NFKC", text or "").casefold())


def load_documents(runtime: dict[str, Any], path: Path, *, document_type: str, access_scope: str) -> list[dict[str, Any]]:
    """Build loader-shaped documents for every extraction row."""
    loader = runtime["loader"]
    documents: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            section = json.loads(line)
            document = loader._document(
                section,
                source_uri_prefix="",
                status="active",
                ingestion_id="offline-replay",
                document_type=document_type,
                access_scope=access_scope,
            )
            document.pop("embedding", None)
            documents.append(document)
    return documents


class FieldIndex:
    """Per-field BM25 statistics over one filtered corpus."""

    def __init__(self, documents: list[dict[str, Any]], field_getter) -> None:
        self.terms = [Counter(_analyze(field_getter(document))) for document in documents]
        self.lengths = [sum(counter.values()) for counter in self.terms]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.df: Counter[str] = Counter()
        for counter in self.terms:
            self.df.update(counter.keys())
        self.count = len(documents)

    def score(self, index: int, query_terms: list[str]) -> float:
        counter = self.terms[index]
        length = self.lengths[index]
        total = 0.0
        for term in query_terms:
            frequency = counter.get(term, 0)
            if not frequency:
                continue
            df = self.df[term]
            idf = math.log(1 + (self.count - df + 0.5) / (df + 0.5))
            norm = 1 - _BM25_B + _BM25_B * (length / self.avgdl if self.avgdl else 1.0)
            total += idf * frequency * (_BM25_K1 + 1) / (frequency + _BM25_K1 * norm)
        return total

    @staticmethod
    def has_phrase(query_terms: list[str], text: str) -> bool:
        if not query_terms:
            return False
        return f" {' '.join(query_terms)} " in f" {' '.join(_analyze(text))} "


class Bm25Search:
    """Approximate the live ``multi_match`` best_fields query plus its phrase clauses."""

    def __init__(self, documents: list[dict[str, Any]], fields: dict[str, tuple[Any, float]], phrase_boosts: dict[str, float]) -> None:
        self.documents = documents
        self.fields = {name: (FieldIndex(documents, getter), boost, getter) for name, (getter, boost) in fields.items()}
        self.phrase_boosts = phrase_boosts

    def search(self, query: str, size: int) -> list[dict[str, Any]]:
        terms = _analyze(query)
        scored: list[tuple[float, int]] = []
        for index, document in enumerate(self.documents):
            best = 0.0
            phrase = 0.0
            for name, (field, boost, getter) in self.fields.items():
                field_score = field.score(index, terms)
                best = max(best, boost * field_score)
                phrase_boost = self.phrase_boosts.get(name)
                if phrase_boost and field_score and field.has_phrase(terms, getter(document)):
                    phrase += phrase_boost * field_score
            if best + phrase > 0:
                scored.append((best + phrase, index))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [
            {"_id": self.documents[index]["id"], "_score": round(score, 6), "_source": self.documents[index]}
            for score, index in scored[:size]
        ]


def _locale_search(documents: list[dict[str, Any]]) -> Bm25Search:
    return Bm25Search(
        documents,
        {
            "section_title": (lambda document: str(document.get("section_title") or ""), 6.0),
            "content": (lambda document: str(document.get("content") or ""), 3.0),
            "search_text": (lambda document: str(document.get("search_text") or ""), 1.0),
        },
        {"section_title": 5.0, "content": 2.0},
    )


def _directory_search(documents: list[dict[str, Any]]) -> Bm25Search:
    return Bm25Search(
        documents,
        {
            "record_country": (lambda document: str((document.get("metadata") or {}).get("record_country") or ""), 12.0),
            "section_title": (lambda document: str(document.get("section_title") or ""), 10.0),
            "content": (lambda document: str(document.get("content") or ""), 4.0),
            "search_text": (lambda document: str(document.get("search_text") or ""), 2.0),
        },
        {"section_title": 8.0},
    )


def _locale_documents(runtime: dict[str, Any], documents: list[dict[str, Any]], country: str, language: str) -> list[dict[str, Any]]:
    settings = runtime["settings"]
    countries = {code.upper() for code in runtime["sections"].get_document_country_codes(country)}
    normalized = (language or "en").split("-", 1)[0].lower()
    languages = {normalized} | ({"en"} if settings.OPENSEARCH_ALLOW_ENGLISH_FALLBACK else set())
    return [
        document
        for document in documents
        if document.get("access_scope") != "global"
        and str(document.get("country") or "").upper() in countries
        and str(document.get("language") or "").lower() in languages
        and document.get("status") == "active"
    ]


def _global_directory_documents(runtime: dict[str, Any], documents: list[dict[str, Any]], target_names: set[str]) -> list[dict[str, Any]]:
    sections = runtime["sections"]
    targets = {sections._normalize_text(name) for name in target_names if name}
    return [
        document
        for document in documents
        if document.get("access_scope") == "global"
        and document.get("document_type") in sections.GLOBAL_DIRECTORY_DOCUMENT_TYPES
        and (not targets or sections._normalize_text(str((document.get("metadata") or {}).get("record_country") or "")) in targets)
    ]


def replay_candidates(runtime: dict[str, Any], question: str, country: str, language: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the text-only approximation through the real merge and candidate code."""
    settings = runtime["settings"]
    sections = runtime["sections"]
    plan = runtime["providers"]._planned_retrieval_plan(question, country, language, "offline-replay")
    target_names = sections._directory_target_country_names(question, country)
    size = settings.OPENSEARCH_CANDIDATE_COUNT
    locale = _locale_search(_locale_documents(runtime, documents, country, language))
    searches: list[dict[str, Any]] = []
    explicit = sections._section_reference(question)
    if explicit:
        searches.append(
            {
                "kind": "exact",
                "query": explicit,
                "weight": 1.0,
                "hits": [
                    {"_id": document["id"], "_score": 100.0, "_source": document}
                    for document in locale.documents
                    if str(document.get("section_id") or "").lower() == explicit
                ],
            }
        )
    for index, query in enumerate(plan.queries):
        searches.append({"kind": "text", "query": query, "weight": 1.0 if index == 0 else 0.88, "hits": locale.search(query, size)})
    if plan.include_global_documents:
        directory = _directory_search(_global_directory_documents(runtime, documents, target_names))
        searches.append({"kind": "global_text", "query": question, "weight": 1.0, "hits": directory.search(question, size)})
    text_hits, vector_hits = _flatten_capture({"searches": searches})
    ranking_queries = runtime["safe_typo_ranking_queries"](question, plan.queries[1:])
    rows = sections.OpenSearchSectionProvider()._merge_hits(
        text_hits,
        vector_hits,
        question,
        ranking_queries=ranking_queries,
        prefer_outline=plan.prefer_outline,
        target_country_names=target_names,
    )
    limit = max(settings.OPENSEARCH_RESULT_COUNT, settings.OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT)
    return {
        "queries": plan.queries,
        "include_global_documents": plan.include_global_documents,
        "global_rows": sum(len(search["hits"]) for search in searches if search["kind"] == "global_text"),
        "searches": searches,
        "per_query": [{"query": search["query"], "ids": [hit["_id"] for hit in search["hits"]]} for search in searches],
        "target_country_names": sorted(target_names),
        "ranking_queries": ranking_queries,
        "prefer_outline": plan.prefer_outline,
        "rows": rows,
        "candidates": sections._selector_candidates(rows, limit),
        "limit": limit,
    }


def describe_row(result: dict[str, Any], row_id: str) -> dict[str, Any]:
    """Explain where one row landed and which stage kept it out of the candidates."""
    rows = result["rows"]
    limit = result["limit"]
    candidate_ids = [str(row.get("id") or "") for row, _score in result["candidates"]]
    query_ranks = [
        {"query_index": index, "rank": query["ids"].index(row_id) + 1}
        for index, query in enumerate(result["per_query"])
        if row_id in query["ids"]
    ]
    position = next((index for index, (row, _score) in enumerate(rows, start=1) if row.get("id") == row_id), None)
    description: dict[str, Any] = {"id": row_id, "text_query_ranks": query_ranks, "merged_position": position}
    if position is None:
        description["stage"] = "not returned by any approximated text query (top-30 per query)"
        return description
    row, score = rows[position - 1]
    cutoff = rows[min(limit, len(rows)) - 1][1] if rows else 0.0
    description.update(
        {
            "merged_score": score,
            "normalized_rank_component": round(float(row.get("rank") or 0.0), 6),
            "lexical_component": round(score - float(row.get("rank") or 0.0), 6),
            "score_at_candidate_cutoff": cutoff,
            "candidate_index": candidate_ids.index(row_id) + 1 if row_id in candidate_ids else None,
        }
    )
    if row_id in candidate_ids:
        description["stage"] = "selector candidate"
    elif position <= limit:
        description["stage"] = "inside the merged top limit but evicted by the global-document quota"
    else:
        description["stage"] = "merged, but ranked below the selector candidate cap"
    return description


def _extraction_files(source_roots: list[Path], country: str, languages: set[str]) -> list[Path]:
    for root in source_roots:
        found: list[Path] = []
        for language in sorted(languages):
            found.extend(sorted((root / "outputs/chunk-comparison-full/current" / country / language).glob("*.sections.jsonl")))
        if found:
            return found
    return []


def _pack(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verified_pack_files(pack: dict[str, Any], source_roots: list[Path]) -> dict[str, Path]:
    verified: dict[str, Path] = {}
    for entry in pack.get("source_extractions", []):
        for root in source_roots:
            candidate = root / entry["extraction_file"]
            if candidate.exists():
                if _sha256(candidate) != entry["extraction_sha256"]:
                    raise SystemExit(f"extraction SHA-256 mismatch: {candidate}")
                verified[entry["extraction_file"]] = candidate
                break
        else:
            raise SystemExit(f"missing pack extraction (pack policy is fail): {entry['extraction_file']}")
    return verified


def _corpus_for(runtime: dict[str, Any], source_roots: list[Path], directory: Path | None, country: str, language: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    languages = {(language or "en").split("-", 1)[0].lower(), "en"}
    documents: list[dict[str, Any]] = []
    files: list[dict[str, str]] = []
    for path in _extraction_files(source_roots, country, languages):
        documents.extend(load_documents(runtime, path, document_type="policy", access_scope="country"))
        files.append({"file": str(path), "sha256": _sha256(path)})
    if directory is not None:
        documents.extend(load_documents(runtime, directory, document_type="office_directory", access_scope="global"))
        files.append({"file": str(directory), "sha256": _sha256(directory)})
    return documents, files


def _family_ids(documents: list[dict[str, Any]], country: str, section_ids: list[str]) -> list[str]:
    """Return row ids for the named sections plus each child's parent, in every language."""
    wanted = set(section_ids)
    for document in documents:
        if str(document.get("country")) == country and document.get("section_id") in wanted and document.get("parent_section_id"):
            wanted.add(str(document["parent_section_id"]))
    return [
        str(document["id"])
        for document in documents
        if str(document.get("country")) == country and document.get("section_id") in wanted
    ]


def _pack_policy_cases(pack: dict[str, Any], source_roots: list[Path]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for case in pack["cases"]:
        policy = [section for section in case["expected"].get("required_sections") or [] if ":" in section]
        if not policy:
            continue
        country = policy[0].split(":", 1)[0]
        if not _extraction_files(source_roots, country, {case["language"]}):
            continue
        cases.append(
            {
                "id": case["id"],
                "question": case["question"],
                "country": case["country"],
                "language": case["language"],
                "required_sections": policy,
                "sections": [section.split(":", 1)[1] for section in policy],
                "extra": [],
            }
        )
    return cases


def command_candidates(args: argparse.Namespace) -> dict[str, Any]:
    runtime = _import_runtime(args.code_root)
    source_roots = [Path(root) for root in args.source_root]
    directory = Path(args.directory) if args.directory else None
    cases: list[dict[str, Any]] = []
    if args.pack:
        pack = _pack(Path(args.pack))
        _verified_pack_files(pack, source_roots)
        cases.extend(_pack_policy_cases(pack, source_roots))
    if args.question:
        targets = args.target or []
        cases.append(
            {
                "id": "ad-hoc",
                "question": args.question,
                "country": args.country,
                "language": args.language,
                "required_sections": [f"{args.country}:{target}" for target in targets],
                "sections": [],
                "extra": targets,
            }
        )
    reports: list[dict[str, Any]] = []
    captured: list[dict[str, Any]] = []
    for case in cases:
        documents, files = _corpus_for(runtime, source_roots, directory, case["country"], case["language"])
        result = replay_candidates(runtime, case["question"], case["country"], case["language"], documents)
        targets = _family_ids(documents, case["country"], [*case["sections"], *case["extra"]])
        reports.append(
            {
                "case_id": case["id"],
                "country": case["country"],
                "language": case["language"],
                "files": files,
                "query_count": len(result["queries"]),
                "include_global_documents": result["include_global_documents"],
                "global_rows_returned": result["global_rows"],
                "merged_rows": len(result["rows"]),
                "targets": [describe_row(result, target) for target in targets],
            }
        )
        captured.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "country": case["country"],
                "language": case["language"],
                "required_sections": case["required_sections"],
                "target_country_names": result["target_country_names"],
                "ranking_queries": result["ranking_queries"],
                "prefer_outline": result["prefer_outline"],
                "searches": result["searches"],
            }
        )
    if args.write_capture:
        Path(args.write_capture).write_text(
            json.dumps({"schema": CAPTURE_SCHEMA, "approximate": True, "cases": captured}, ensure_ascii=False),
            encoding="utf-8",
        )
    return {
        "approximation": "text-only local BM25; no kNN, no LLM planner, no fuzziness, no live analyzer; ranks are directional only",
        "cases": reports,
    }


def _heading_of(row: dict[str, Any]) -> str:
    """Mirror the extractor's ``Section <parent>: <heading>`` convention for a child row."""
    first_line = str(row.get("content") or "").split("\n", 1)[0].strip()
    match = _SECTION_PREFIX_RE.match(first_line)
    parent_id = str(row.get("parent_section_id") or "")
    if not parent_id or match is None:
        return ""
    prefix_id = match.group(1)
    if prefix_id != parent_id and not str(row.get("section_id") or "").startswith(f"{prefix_id}-"):
        return ""
    return match.group(2).strip()


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def _quote_fragments(quote: str) -> list[str]:
    return [fragment for fragment in (_normalized(part) for part in re.split(r"\.\.\.|…", quote)) if len(fragment) >= 12]


def _view_body(view: str) -> str:
    return view.split("\nText:\n", 1)[1] if "\nText:\n" in view else view


def measure_views(runtime: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate truncation, hidden-clause and heading-identity metrics for one file."""
    sections = runtime["sections"]
    budget = getattr(sections, "_SELECTOR_VIEW_CHARS", 1200)
    rows = [sections._hit_to_row({"_id": document["id"], "_score": 0.0, "_source": document}) for document in documents]
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("chunk_type") == "list_item" and row.get("parent_section_id"):
            by_parent.setdefault(str(row["parent_section_id"]), []).append(row)
    metrics: Counter[str] = Counter()
    view_lengths: list[int] = []
    for row in rows:
        content = str(row.get("content") or "")
        view = sections._selector_candidate_text(row, 0.0, 1)
        view_lengths.append(len(view))
        chunk = str(row.get("chunk_type") or "")
        metrics["rows"] += 1
        metrics[f"rows:{chunk}"] += 1
        metrics["content_chars"] += len(content)
        if len(content) > budget:
            metrics["truncated"] += 1
            metrics[f"truncated:{chunk}"] += 1
            metrics["hidden_chars"] += len(content) - budget
            metrics["hidden_clause_markers"] += len(list(_CLAUSE_MARKER_RE.finditer(content, budget)))
            if "[text truncated:" not in view.casefold():
                metrics["truncated_without_marker"] += 1
        heading = _heading_of(row)
        if heading:
            header = view.split("\nText:\n", 1)[0]
            metrics["rows_with_parent_heading"] += 1
            metrics["parent_heading_in_metadata_header"] += int(heading in header)
            metrics["parent_heading_anywhere_in_view"] += int(heading in view)
        if chunk == "section" and len(content) > budget:
            for child in by_parent.get(str(row.get("section_id") or ""), []):
                if child.get("source_file") != row.get("source_file") or child.get("language") != row.get("language"):
                    continue
                metrics["children_of_truncated_sections"] += 1
                metrics["children_outside_parent_view"] += int(not sections._clause_in_selector_view(row, child))
    ordered = sorted(view_lengths)
    return {
        **dict(metrics),
        "view_chars_total": sum(ordered),
        "view_chars_mean": round(sum(ordered) / len(ordered), 1) if ordered else 0,
        "view_chars_p95": ordered[int(0.95 * (len(ordered) - 1))] if ordered else 0,
        "view_chars_max": ordered[-1] if ordered else 0,
        "worst_case_30_candidate_chars": sum(ordered[-30:]),
    }


def _row_for(runtime: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    return runtime["sections"]._hit_to_row({"_id": document["id"], "_score": 0.0, "_source": document})


def held_out_quote_visibility(runtime: dict[str, Any], pack: dict[str, Any], files: dict[str, Path]) -> list[dict[str, Any]]:
    """Check whether each held-out governing quote is inside the selector view."""
    sections = runtime["sections"]
    cache: dict[str, list[dict[str, Any]]] = {}
    report: list[dict[str, Any]] = []
    for case in pack["cases"]:
        source = case.get("source") or {}
        extraction = source.get("extraction_file", "")
        if extraction not in files:
            continue
        directory = extraction.endswith(".directory.jsonl")
        if extraction not in cache:
            cache[extraction] = load_documents(
                runtime, files[extraction],
                document_type="office_directory" if directory else "policy",
                access_scope="global" if directory else "country",
            )
        section_id = str(source.get("section_id") or "").split(":", 1)[-1]
        documents = [document for document in cache[extraction] if document.get("section_id") == section_id]
        if not documents:
            report.append({"case_id": case["id"], "section_id": section_id, "status": "row not found"})
            continue
        row = _row_for(runtime, documents[0])
        fragments = _quote_fragments(str(source.get("quote") or ""))
        content = _normalized(str(row.get("content") or ""))
        view = _normalized(_view_body(sections._selector_candidate_text(row, 0.0, 1)))
        found = [fragment in content for fragment in fragments]
        entry: dict[str, Any] = {
            "case_id": case["id"],
            "section_id": section_id,
            "chunk_type": row.get("chunk_type"),
            "content_chars": len(str(row.get("content") or "")),
            "quote_verbatim_in_row": bool(fragments) and all(found),
            "quote_offset": content.find(fragments[0]) if fragments and found[0] else None,
            "quote_visible_in_own_view": bool(fragments) and all(fragment in view for fragment in fragments),
        }
        parent_id = str(row.get("parent_section_id") or "")
        parents = [
            document for document in cache[extraction]
            if parent_id and document.get("section_id") == parent_id and document.get("language") == row.get("language")
        ]
        if parents and row.get("chunk_type") == "list_item":
            parent_row = _row_for(runtime, parents[0])
            parent_view = _normalized(_view_body(sections._selector_candidate_text(parent_row, 0.0, 1)))
            entry["quote_visible_in_parent_view"] = bool(fragments) and all(fragment in parent_view for fragment in fragments)
            entry["parent_content_chars"] = len(str(parent_row.get("content") or ""))
        report.append(entry)
    return report


def _document_kind(path: Path) -> dict[str, str]:
    directory = path.name.endswith(".directory.jsonl")
    return {
        "document_type": "office_directory" if directory else "policy",
        "access_scope": "global" if directory else "country",
    }


def command_views(args: argparse.Namespace) -> dict[str, Any]:
    runtime = _import_runtime(args.code_root)
    source_roots = [Path(root) for root in args.source_root]
    output: dict[str, Any] = {"files": []}
    pack_files: dict[str, Path] = {}
    if args.pack:
        pack = _pack(Path(args.pack))
        pack_files = _verified_pack_files(pack, source_roots)
        output["held_out_quotes"] = held_out_quote_visibility(runtime, pack, pack_files)
    paths = [Path(path) for path in args.extraction] or list(pack_files.values())
    shown: list[dict[str, str]] = []
    for path in paths:
        documents = load_documents(runtime, path, **_document_kind(path))
        output["files"].append({"file": str(path), "sha256": _sha256(path), **measure_views(runtime, documents)})
        for document in documents:
            if document.get("section_id") in set(args.show):
                shown.append({"id": document["id"], "view": runtime["sections"]._selector_candidate_text(_row_for(runtime, document), 0.0, 1)})
    if args.show:
        output["shown_views"] = shown
    return output


def _flatten_capture(case: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rebuild the production text and vector hit lists exactly as ``retrieve`` does."""
    text_hits: list[dict[str, Any]] = []
    vector_hits: list[dict[str, Any]] = []
    for search in case["searches"]:
        weight = float(search.get("weight", 1.0))
        kind = search["kind"]
        for hit in search["hits"]:
            raw = float(hit.get("_score") or 0.0)
            if kind == "exact":
                text_hits.append({**hit, "_score": max(raw, 100.0)})
            elif kind in {"text", "global_text"}:
                text_hits.append({**hit, "_score": raw * weight})
            elif kind == "outline":
                text_hits.append(dict(hit))
            elif kind in {"vector", "global_vector"}:
                vector_hits.append({**hit, "_score": raw * weight})
            else:
                raise ValueError(f"unknown search kind: {kind}")
    return text_hits, vector_hits


def reciprocal_rank_fusion(searches: list[dict[str, Any]], k: int = 60) -> list[tuple[str, float]]:
    """Fuse every captured ranked list; each list contributes ``weight / (k + rank)``."""
    fused: dict[str, float] = {}
    for search in searches:
        weight = float(search.get("weight", 1.0))
        seen: set[str] = set()
        for rank, hit in enumerate(search["hits"], start=1):
            identifier = str(hit.get("_id") or (hit.get("_source") or {}).get("id") or "")
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            fused[identifier] = fused.get(identifier, 0.0) + weight / (k + rank)
    return sorted(fused.items(), key=lambda pair: (-pair[1], pair[0]))


def _required_positions(order: list[dict[str, Any]], required_ids: list[str], required_sections: list[str]) -> dict[str, int | None]:
    positions: dict[str, int | None] = {}
    for identifier in required_ids:
        positions[identifier] = next((index for index, row in enumerate(order, start=1) if str(row.get("id") or "") == identifier), None)
    for key in required_sections:
        positions[key] = next(
            (
                index for index, row in enumerate(order, start=1)
                if f"{str(row.get('country') or '').upper()}:{row.get('section_id') or ''}" == key
            ),
            None,
        )
    return positions


def _recall(positions: dict[str, int | None], depth: int) -> float | None:
    if not positions:
        return None
    return round(sum(1 for position in positions.values() if position and position <= depth) / len(positions), 4)


def compare_capture(runtime: dict[str, Any], capture: dict[str, Any], k: int = 60) -> dict[str, Any]:
    """Replay the production merge and an RRF ordering over the same captured lists."""
    if capture.get("schema") != CAPTURE_SCHEMA:
        raise ValueError(f"capture schema must be {CAPTURE_SCHEMA}")
    sections = runtime["sections"]
    settings = runtime["settings"]
    limit = max(settings.OPENSEARCH_RESULT_COUNT, settings.OPENSEARCH_EVIDENCE_SELECTOR_CANDIDATE_COUNT)
    reports: list[dict[str, Any]] = []
    for case in capture["cases"]:
        text_hits, vector_hits = _flatten_capture(case)
        rows = sections.OpenSearchSectionProvider()._merge_hits(
            text_hits,
            vector_hits,
            case["question"],
            ranking_queries=list(case.get("ranking_queries") or []),
            prefer_outline=bool(case.get("prefer_outline")),
            target_country_names=set(case.get("target_country_names") or []),
        )
        production = [row for row, _score in sections._selector_candidates(rows, limit)]
        by_id = {str(row.get("id") or ""): (row, score) for row, score in rows}
        fused_pairs = [by_id[identifier] for identifier, _score in reciprocal_rank_fusion(case["searches"], k) if identifier in by_id]
        fused = [row for row, _score in sections._selector_candidates(fused_pairs, limit)]
        required_ids = list(case.get("required_ids") or [])
        required_sections = list(case.get("required_sections") or [])
        production_positions = _required_positions(production, required_ids, required_sections)
        rrf_positions = _required_positions(fused, required_ids, required_sections)
        reports.append(
            {
                "case_id": case.get("case_id", ""),
                "production_positions": production_positions,
                "rrf_positions": rrf_positions,
                "production_recall": {depth: _recall(production_positions, depth) for depth in (5, 10, 30)},
                "rrf_recall": {depth: _recall(rrf_positions, depth) for depth in (5, 10, 30)},
                "candidate_overlap": len({str(row.get("id")) for row in production} & {str(row.get("id")) for row in fused}),
            }
        )
    return {"k": k, "approximate": bool(capture.get("approximate")), "cases": reports}


def command_rrf(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if not args.capture or not Path(args.capture).exists():
        return (
            {
                "status": "BLOCKED",
                "reason": "no captured per-query text and vector candidate lists exist; capture them first (see module docstring)",
                "schema": CAPTURE_SCHEMA,
            },
            3,
        )
    runtime = _import_runtime(args.code_root)
    capture = json.loads(Path(args.capture).read_text(encoding="utf-8"))
    return compare_capture(runtime, capture, args.k), 0


# --- Runner-artifact converter ------------------------------------------------
#
# The benchmark runner stores the orchestrator's diagnostic capture per turn. When
# the application emits ``retrieval_rank_lists`` (rank-list capture), the final
# turn's question retrieval carries every search's ranked hits with raw scores,
# identified by section id and document id only. This rebuilds the capture
# schema from them so ``rrf --capture`` can replay real text and vector lists.

RANK_LISTS_KEY = "retrieval_rank_lists"
RANK_LISTS_VERSION = 1
_RANK_LIST_DOCUMENT_FIELDS = (
    "id", "section_id", "parent_section_id", "country", "language",
    "access_scope", "document_type", "chunk_type",
)
_TEXT_KINDS = frozenset({"exact", "text", "outline", "global_text"})
_VECTOR_KINDS = frozenset({"vector", "global_vector"})


class CaptureFormatError(ValueError):
    """A runner artifact, or the rank lists inside it, is not in the expected shape."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _document_index(value: Any, documents: list[Any], where: str, *, optional: bool) -> None:
    if value is None and optional:
        return
    if not _is_int(value) or not 0 <= value < len(documents):
        raise CaptureFormatError(f"{where} must index the documents table")


def _validate_rank_list_documents(rank_lists: dict[str, Any]) -> list[Any]:
    if list(rank_lists.get("document_fields") or []) != list(_RANK_LIST_DOCUMENT_FIELDS):
        raise CaptureFormatError(f"document_fields must be {list(_RANK_LIST_DOCUMENT_FIELDS)}")
    documents = rank_lists.get("documents")
    if not isinstance(documents, list):
        raise CaptureFormatError("documents must be a list")
    for position, document in enumerate(documents):
        if (
            not isinstance(document, list)
            or len(document) != len(_RANK_LIST_DOCUMENT_FIELDS)
            or not all(isinstance(value, str) for value in document)
            or not document[0]
        ):
            raise CaptureFormatError(f"documents[{position}] must be {len(_RANK_LIST_DOCUMENT_FIELDS)} strings with a non-empty id")
    return documents


def _validate_rank_list_search(search: Any, position: int, documents: list[Any]) -> None:
    where = f"searches[{position}]"
    if not isinstance(search, dict) or search.get("kind") not in _TEXT_KINDS | _VECTOR_KINDS:
        raise CaptureFormatError(f"{where} must be an object with a known kind")
    if not _is_number(search.get("weight")):
        raise CaptureFormatError(f"{where}.weight must be a finite number")
    query_index = search.get("query_index")
    if query_index is not None and not (_is_int(query_index) and query_index >= 0):
        raise CaptureFormatError(f"{where}.query_index must be null or a non-negative integer")
    hits = search.get("hits")
    if not isinstance(hits, list):
        raise CaptureFormatError(f"{where}.hits must be a list")
    previous = 0
    for hit_position, hit in enumerate(hits):
        hit_where = f"{where}.hits[{hit_position}]"
        if not isinstance(hit, list) or len(hit) != 4:
            raise CaptureFormatError(f"{hit_where} must be [section_id, rank, raw_score, document]")
        section_id, rank, score, document = hit
        if not isinstance(section_id, str):
            raise CaptureFormatError(f"{hit_where} section_id must be a string")
        if not _is_int(rank) or rank <= previous:
            raise CaptureFormatError(f"{hit_where} rank must be an integer above the previous rank")
        if not _is_number(score):
            raise CaptureFormatError(f"{hit_where} raw_score must be a finite number")
        _document_index(document, documents, hit_where, optional=True)
        if document is not None and documents[document][1] != section_id:
            raise CaptureFormatError(f"{hit_where} section_id disagrees with its document")
        previous = rank


def validate_rank_lists(rank_lists: Any) -> None:
    """Reject anything that is not a version-1 rank-list record."""
    if not isinstance(rank_lists, dict):
        raise CaptureFormatError(f"{RANK_LISTS_KEY} must be an object")
    if rank_lists.get("version") != RANK_LISTS_VERSION:
        raise CaptureFormatError(f"{RANK_LISTS_KEY}.version must be {RANK_LISTS_VERSION}")
    if rank_lists.get("recording_failed"):
        raise CaptureFormatError(f"{RANK_LISTS_KEY} reports that recording failed")
    documents = _validate_rank_list_documents(rank_lists)
    searches = rank_lists.get("searches")
    if not isinstance(searches, list):
        raise CaptureFormatError("searches must be a list")
    for position, search in enumerate(searches):
        _validate_rank_list_search(search, position, documents)
    candidates = rank_lists.get("selector_candidates")
    if candidates is not None:
        if not isinstance(candidates, list):
            raise CaptureFormatError("selector_candidates must be null or a list")
        for position, document in enumerate(candidates):
            _document_index(document, documents, f"selector_candidates[{position}]", optional=True)
    ranks = rank_lists.get("selector_selected_ranks")
    if ranks is not None and (not isinstance(ranks, list) or not all(_is_int(rank) for rank in ranks)):
        raise CaptureFormatError("selector_selected_ranks must be null or a list of integers")


def _final_question_metadata(run: Any) -> tuple[dict[str, Any] | None, str]:
    """Return the final turn's question-retrieval metadata that carries rank lists, and where it came from."""
    if not isinstance(run, dict):
        raise CaptureFormatError("each run must be an object")
    capture = run.get("capture")
    if capture is None:
        return None, "run has no capture"
    if not isinstance(capture, dict) or not isinstance(capture.get("turns", []), list):
        raise CaptureFormatError("run capture must be an object with a turns list")
    final = next((turn for turn in reversed(capture.get("turns") or []) if isinstance(turn, dict) and turn.get("turn") == "final"), None)
    diagnostic = (final or {}).get("diagnostic_capture") or {}
    retrievals = diagnostic.get("retrievals") if isinstance(diagnostic, dict) else None
    questions = [item for item in retrievals or [] if isinstance(item, dict) and item.get("stage") == "question"]
    candidates = [
        ("final_turn_question_retrieval", (questions[-1] if questions else {}).get("metadata")),
        ("final_retrieval", (capture.get("final_retrieval") or {}).get("metadata")),
    ]
    for where, metadata in candidates:
        if isinstance(metadata, dict) and RANK_LISTS_KEY in metadata:
            return metadata, where
    return None, f"no {RANK_LISTS_KEY} in the final turn's retrieval capture"


def _policy_requirements(pack_case: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    required = [str(value) for value in ((pack_case or {}).get("expected") or {}).get("required_sections") or []]
    return [value for value in required if ":" in value], [value for value in required if ":" not in value]


def capture_case_from_rank_lists(
    metadata: dict[str, Any],
    *,
    case_id: str,
    question: str,
    country: str,
    language: str,
    required_sections: list[str],
    source_lookup=None,
) -> dict[str, Any]:
    """Build one ``askvera-retrieval-capture/1`` case from one retrieval's rank-list metadata."""
    rank_lists = metadata[RANK_LISTS_KEY]
    validate_rank_lists(rank_lists)
    documents = [dict(zip(_RANK_LIST_DOCUMENT_FIELDS, row)) for row in rank_lists["documents"]]
    sources: list[dict[str, Any]] = []
    resolved = 0
    for document in documents:
        full = source_lookup(document) if source_lookup is not None else None
        resolved += int(full is not None)
        sources.append(full if full is not None else dict(document))
    searches = [
        {
            "kind": search["kind"],
            "query": search["kind"] if search.get("query_index") is None else f"{search['kind']}#{search['query_index']}",
            "weight": search["weight"],
            "hits": [
                {"_id": documents[index]["id"], "_score": score, "_source": sources[index]}
                for _section_id, _rank, score, index in search["hits"]
                if index is not None
            ],
        }
        for search in rank_lists["searches"]
    ]
    merged = rank_lists.get("merged_order") or []
    return {
        "case_id": case_id,
        "question": question,
        "country": country,
        "language": language,
        "required_sections": required_sections,
        "required_ids": [],
        "target_country_names": list(rank_lists.get("target_country_names") or []),
        # Planner and typo ranking queries are query text, which the capture
        # deliberately omits; the production replay runs without them.
        "ranking_queries": [],
        "prefer_outline": bool(rank_lists.get("prefer_outline")),
        "searches": searches,
        "source_text": {
            "documents": len(documents),
            "resolved_from_extractions": resolved,
            "identifiers_only": len(documents) - resolved,
        },
        "captured": {
            "merged_count": rank_lists.get("merged_count"),
            "merged_order": [
                [section_id, score, documents[index]["id"] if index is not None else None]
                for section_id, score, index in merged
            ],
            "candidate_section_ids": metadata.get("candidate_section_ids"),
            "selector_outcome": rank_lists.get("selector_outcome"),
            "selector_candidate_section_ids": metadata.get("evidence_selector_candidate_section_ids"),
            "selector_selected_ranks": metadata.get("evidence_selector_selected_ranks"),
            "searches_not_recorded": rank_lists.get("searches_not_recorded"),
            "recording_errors": rank_lists.get("recording_errors"),
        },
    }


def capture_from_artifact(
    artifact: Any,
    *,
    pack_cases: dict[str, dict[str, Any]] | None = None,
    source_lookup=None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert every run's final question retrieval that has both text and vector lists.

    ``run_benchmark`` writes its artifact as a top-level object with
    ``summary`` and ``cases`` (see ``scripts/run_benchmark.py``, ``_execute``'s
    ``json.dumps({"summary": summary, "cases": results})``); ``cases`` is
    accepted here as the canonical key. ``results`` is also accepted, unchanged,
    for any input built directly in that older shape.
    """
    if not isinstance(artifact, dict):
        raise CaptureFormatError("artifact must be an object with a results list")
    case_list = artifact["cases"] if isinstance(artifact.get("cases"), list) else artifact.get("results")
    if not isinstance(case_list, list):
        raise CaptureFormatError("artifact must be an object with a results list")
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for case in case_list:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not isinstance(case.get("runs"), list):
            raise CaptureFormatError("each result must be an object with a string id and a runs list")
        pack_case = (pack_cases or {}).get(case["id"])
        required, unscored = _policy_requirements(pack_case)
        for run_index, run in enumerate(case["runs"]):
            label = case["id"] if len(case["runs"]) == 1 else f"{case['id']}#run{run_index + 1}"
            metadata, where = _final_question_metadata(run)
            if metadata is None:
                skipped.append({"case_id": label, "reason": where})
                continue
            converted = capture_case_from_rank_lists(
                metadata,
                case_id=label,
                question=str(case.get("question") or ""),
                country=str(case.get("request_country") or (pack_case or {}).get("country") or ""),
                language=str((pack_case or {}).get("language") or ""),
                required_sections=required,
                source_lookup=source_lookup,
            )
            kinds = {search["kind"] for search in converted["searches"]}
            if not kinds & _TEXT_KINDS or not kinds & _VECTOR_KINDS:
                skipped.append({"case_id": label, "reason": "text and vector lists were not both captured"})
                continue
            converted.update({"run_index": run_index, "rank_lists_from": where, "unscored_required_sections": unscored})
            cases.append(converted)
    document = {
        "schema": CAPTURE_SCHEMA,
        "approximate": False,
        "provenance": {
            "source": f"run_benchmark artifact, {RANK_LISTS_KEY} version {RANK_LISTS_VERSION}",
            "notes": [
                "ranks and raw scores are the live OpenSearch lists as captured",
                "_source holds identifiers only unless resolved from local extractions (see each case's source_text); "
                "the production-merge replay then has no lexical text to score",
                "planner and typo ranking queries are not captured; the replay runs without them",
                "each case's captured block holds the live merged order and selector decision for comparison",
            ],
        },
        "cases": cases,
    }
    return document, skipped


def _extraction_source_lookup(runtime: dict[str, Any], source_roots: list[Path], directory: Path | None):
    """Resolve captured document ids to loader-shaped rows from local extractions, loading each locale once."""
    by_locale: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    global_rows: dict[str, dict[str, Any]] | None = None

    def lookup(document: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal global_rows
        if document.get("access_scope") == "global":
            if directory is None:
                return None
            if global_rows is None:
                global_rows = {row["id"]: row for row in load_documents(runtime, directory, **_document_kind(directory))}
            return global_rows.get(document["id"])
        key = (document.get("country") or "", document.get("language") or "")
        if key not in by_locale:
            by_locale[key] = {}
            for path in _extraction_files(source_roots, key[0], {key[1]}):
                by_locale[key].update({row["id"]: row for row in load_documents(runtime, path, **_document_kind(path))})
        return by_locale[key].get(document["id"])

    return lookup


def command_convert_artifact(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    output = Path(args.output)
    if output.exists():
        return {"status": "REFUSED", "reason": f"output already exists and is never replaced: {output}"}, 2
    try:
        artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "INVALID", "reason": f"artifact could not be read as JSON: {type(exc).__name__}"}, 2
    pack_cases = {str(case["id"]): case for case in _pack(Path(args.pack))["cases"]} if args.pack else None
    source_lookup = None
    if args.source_root or args.directory:
        runtime = _import_runtime(args.code_root)
        source_lookup = _extraction_source_lookup(
            runtime, [Path(root) for root in args.source_root], Path(args.directory) if args.directory else None
        )
    try:
        document, skipped = capture_from_artifact(artifact, pack_cases=pack_cases, source_lookup=source_lookup)
    except CaptureFormatError as exc:
        return {"status": "INVALID", "reason": str(exc)}, 2
    if not document["cases"]:
        return (
            {
                "status": "BLOCKED",
                "reason": f"no run carries both text and vector lists in {RANK_LISTS_KEY}; nothing written",
                "schema": CAPTURE_SCHEMA,
                "skipped": skipped,
            },
            3,
        )
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(document, ensure_ascii=True))
    return (
        {
            "status": "CONVERTED",
            "output": str(output),
            "sha256": _sha256(output),
            "schema": CAPTURE_SCHEMA,
            "cases": [case["case_id"] for case in document["cases"]],
            "source_text": {case["case_id"]: case["source_text"] for case in document["cases"]},
            "skipped": skipped,
        },
        0,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code-root", type=Path, default=ROOT, help="repository whose app code is replayed")
    sub = parser.add_subparsers(dest="command", required=True)

    candidates = sub.add_parser("candidates")
    candidates.add_argument("--source-root", action="append", default=[], help="directory containing outputs/ and tmp/")
    candidates.add_argument("--directory", help="global directory JSONL (optional)")
    candidates.add_argument("--pack", help="held-out pack; replays its policy cases")
    candidates.add_argument("--question")
    candidates.add_argument("--country", default="")
    candidates.add_argument("--language", default="en")
    candidates.add_argument("--target", action="append", help="section id to report (ad-hoc question)")
    candidates.add_argument("--write-capture", help="save the approximated per-query lists in the capture schema")

    views = sub.add_parser("views")
    views.add_argument("--source-root", action="append", default=[])
    views.add_argument("--pack")
    views.add_argument("--extraction", action="append", default=[])
    views.add_argument("--show", action="append", default=[], help="print the selector view for these section ids")

    rrf = sub.add_parser("rrf")
    rrf.add_argument("--capture")
    rrf.add_argument("--k", type=int, default=60)

    convert = sub.add_parser("convert-artifact", help="build a capture file from a run_benchmark artifact's rank lists")
    convert.add_argument("--artifact", required=True, help="run_benchmark artifact JSON")
    convert.add_argument("--output", required=True, help="capture file to create; never replaced")
    convert.add_argument("--pack", help="fixture supplying each case's language and required_sections")
    convert.add_argument("--source-root", action="append", default=[], help="resolve captured ids to local extraction rows")
    convert.add_argument("--directory", help="global directory JSONL for resolving global rows (optional)")
    return parser


def _write_json(payload: dict[str, Any]) -> None:
    """Write ASCII-escaped JSON so redirected output is valid UTF-8 under any console code page."""
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, indent=2, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "candidates":
        payload, code = command_candidates(args), 0
    elif args.command == "views":
        payload, code = command_views(args), 0
    elif args.command == "convert-artifact":
        payload, code = command_convert_artifact(args)
    else:
        payload, code = command_rrf(args)
    _write_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
