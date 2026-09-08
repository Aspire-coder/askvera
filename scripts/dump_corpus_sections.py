"""Dump approved corpus sections so benchmark cases can be written from source.

Benchmark cases are only worth running if their expected answers come from the
documents the system is actually allowed to cite. Writing them from memory, or
from what the bot said last time, produces a test that agrees with the bot by
construction.

This reads the live index and writes the sections out as plain text. It changes
nothing: the only OpenSearch calls are search and count.

Run on the application host, where the index is reachable:

    python scripts/dump_corpus_sections.py --load-ssm --out corpus_dump \\
        --country GB --document-type policy

Then author cases against the dumped text and record, in each case's
`source_evidence`, the section that supports it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PAGE_SIZE = 200
# A section long enough to matter is long enough to page; anything above this
# is almost certainly an ingestion accident worth seeing rather than hiding.
MAX_EXCERPT_CHARS = 20000


def _safe_name(value: str, fallback: str) -> str:
    """Make one path segment out of index metadata, which is not path-safe."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._-")
    return (cleaned or fallback)[:120]


def _has_value(field: str) -> dict[str, Any]:
    """Match sections where a metadata field is present AND not empty.

    Ingestion writes these fields as empty strings rather than leaving them
    out, so `exists` is satisfied by a document that carries no date at all.
    """
    # "?*" is one character followed by anything, so it matches any non-empty
    # value and nothing else. It works whichever way the field is mapped: on a
    # keyword field it tests the stored term, and on a text field an empty
    # string produces no tokens to match. A must_not on term "" does neither -
    # it silently excludes nothing on a text field, which is why the first two
    # runs of this reported a fully dated corpus we had already disproved by
    # reading DK-EN's section header.
    return {"wildcard": {field: {"value": "?*"}}}


def _filters(args: argparse.Namespace) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for field, value in (
        ("country", args.country),
        ("language", args.language),
        ("document_type", args.document_type),
        ("access_scope", args.access_scope),
    ):
        if value:
            clauses.append({"term": {field: value}})
    if not args.include_inactive:
        # Superseded sections are still in the index but are not answerable
        # material, so a case written from one would assert something the
        # system is right to refuse.
        clauses.append({"bool": {"should": [
            {"term": {"status": "active"}},
            {"bool": {"must_not": {"exists": {"field": "status"}}}},
        ], "minimum_should_match": 1}})
    return clauses


def report_inventory(client, query: dict[str, Any], total: int, index_name: str) -> dict[str, Any]:
    """Summarise the corpus without writing any sections."""
    # Sizing the corpus by hand means paging every section; an aggregation
    # answers it in one request and is what decides where cases are worth
    # authoring.
    response = client.search(
        index=index_name,
        body={
            "query": query,
            "size": 0,
            "aggs": {
                "countries": {
                    "terms": {"field": "country", "size": 100},
                    "aggs": {"types": {"terms": {"field": "document_type", "size": 20}}},
                },
                "documents": {
                    "terms": {"field": "source_file", "size": 100},
                    # Date-scope protection keys off effective_date and
                    # document_version. A document carrying neither answers
                    # a question about a past year normally, while an
                    # otherwise identical document that has them refuses it
                    # as a period not covered. Sizing that needs the counts.
                    # An exists filter alone is wrong here: these fields are
                    # written as empty strings rather than omitted, and
                    # OpenSearch counts an empty string as present. The first
                    # version of this reported every document dated, including
                    # DK-EN-Company-Policy.pdf, whose sections were then found
                    # to carry an empty effective_date.
                    "aggs": {
                        "dated": {"filter": _has_value("effective_date")},
                        "versioned": {"filter": _has_value("document_version")},
                    },
                },
            },
        },
    )
    aggregations = response.get("aggregations") or {}
    report = {
        "index": index_name,
        "matched": total,
        "by_country": [
            {
                "country": bucket["key"],
                "sections": bucket["doc_count"],
                "types": {
                    inner["key"]: inner["doc_count"]
                    for inner in bucket.get("types", {}).get("buckets", [])
                },
            }
            for bucket in aggregations.get("countries", {}).get("buckets", [])
        ],
        "by_document": [
            {
                "source_file": bucket["key"],
                "sections": bucket["doc_count"],
                "dated_sections": bucket.get("dated", {}).get("doc_count", 0),
                "versioned_sections": bucket.get("versioned", {}).get("doc_count", 0),
            }
            for bucket in aggregations.get("documents", {}).get("buckets", [])
        ],
        "undated_documents": sorted(
            bucket["key"]
            for bucket in aggregations.get("documents", {}).get("buckets", [])
            if bucket.get("dated", {}).get("doc_count", 0) == 0
        ),
    }
    # Check the aggregation against an actual section rather than trusting
    # it. Two earlier versions of this reported every document dated, and
    # both were believed until a section header was read by hand. An
    # aggregate that cannot be contradicted by its own output is worth
    # less than one that carries a sample.
    sampled = None
    if report["by_document"]:
        first = report["by_document"][0]
        probe = client.search(
            index=index_name,
            body={
                "query": {"term": {"source_file": first["source_file"]}},
                "size": 1,
                "_source": ["source_file", "section_id", "effective_date", "document_version"],
            },
        )["hits"]["hits"]
        if probe:
            found = probe[0].get("_source") or {}
            sampled = {
                "source_file": found.get("source_file", ""),
                "section_id": found.get("section_id", ""),
                "effective_date": found.get("effective_date", ""),
                "document_version": found.get("document_version", ""),
                "reported_dated_sections": first["dated_sections"],
                "reported_total_sections": first["sections"],
                "consistent": bool(str(found.get("effective_date") or "").strip())
                == (first["dated_sections"] > 0),
            }
    report["sampled_section"] = sampled
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Directory to write into.")
    parser.add_argument("--country", default="", help="Filter, e.g. GB.")
    parser.add_argument("--language", default="", help="Filter, e.g. en.")
    parser.add_argument("--document-type", default="", help="Filter, e.g. policy or directory.")
    parser.add_argument("--access-scope", default="", help="Filter, e.g. country or global.")
    parser.add_argument("--contains", default="", help="Only sections whose text matches this phrase.")
    parser.add_argument("--limit", type=int, default=400, help="Maximum sections to write.")
    parser.add_argument(
        "--per-document", type=int, default=0,
        help="Cap sections written per source document, so one large manual cannot "
             "fill the whole dump and leave every other document unrepresented.",
    )
    parser.add_argument(
        "--inventory", action="store_true",
        help="Report how many sections each country and document type holds, and write "
             "nothing. Use it to decide what to dump before dumping it.",
    )
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--load-ssm", action="store_true")
    parser.add_argument("--count-only", action="store_true", help="Report how much would be dumped.")
    args = parser.parse_args()

    from config import settings

    if args.load_ssm:
        settings.load_ssm_config()

    from app.retrieval.opensearch_sections import _client
    from services.aws_clients import init_aws_clients

    init_aws_clients()
    client = _client()

    must: list[dict[str, Any]] = list(_filters(args))
    if args.contains:
        must.append({"multi_match": {
            "query": args.contains,
            "fields": ["content", "search_text", "section_title"],
            "type": "phrase",
        }})
    query = {"bool": {"must": must}} if must else {"match_all": {}}

    total = client.count(index=settings.OPENSEARCH_INDEX, body={"query": query})["count"]
    print(f"{total} sections match in {settings.OPENSEARCH_INDEX}", file=sys.stderr)
    if args.count_only:
        return 0

    if args.inventory:
        print(json.dumps(
            report_inventory(client, query, total, settings.OPENSEARCH_INDEX),
            indent=2, ensure_ascii=False,
        ))
        return 0
    if total == 0:
        print("Nothing to dump; loosen the filters.", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_for_cap = 0
    per_document_counts: dict[str, int] = {}
    index_rows: list[dict[str, Any]] = []
    # Sorting by a stable key keeps successive dumps diffable, which matters
    # when re-checking a case after the corpus is refreshed.
    search_after: list[Any] | None = None

    while written < args.limit:
        body: dict[str, Any] = {
            "query": query,
            "size": min(PAGE_SIZE, args.limit - written),
            "sort": [{"_id": "asc"}],
            "_source": {"excludes": ["embedding", "content_embedding", "vector"]},
        }
        if search_after:
            body["search_after"] = search_after
        hits = client.search(index=settings.OPENSEARCH_INDEX, body=body)["hits"]["hits"]
        if not hits:
            break
        search_after = hits[-1]["sort"]

        for hit in hits:
            source = hit.get("_source") or {}
            # Sections arrive ordered by id, which groups them by document. Without
            # a cap the first document consumes the whole limit and every other one
            # is absent, so a dump of 400 from 17,896 sections can represent a
            # single manual and nothing else.
            document_key = str(source.get("source_file") or source.get("logical_document_id") or "")
            if args.per_document:
                seen = per_document_counts.get(document_key, 0)
                if seen >= args.per_document:
                    skipped_for_cap += 1
                    continue
                per_document_counts[document_key] = seen + 1
            country = _safe_name(source.get("country"), "unknown")
            document = _safe_name(source.get("source_file") or source.get("logical_document_id"), "document")
            section = _safe_name(source.get("section_id") or hit.get("_id"), f"section{written}")
            folder = args.out / country / document
            folder.mkdir(parents=True, exist_ok=True)

            content = str(source.get("content") or "")
            header = "\n".join(
                f"{label}: {source.get(key) or ''}"
                for label, key in (
                    ("section_id", "section_id"),
                    ("section_title", "section_title"),
                    ("country", "country"),
                    ("language", "language"),
                    ("document_type", "document_type"),
                    ("access_scope", "access_scope"),
                    ("document_version", "document_version"),
                    ("effective_date", "effective_date"),
                    ("source_uri", "source_uri"),
                    ("pages", "start_page"),
                )
            )
            (folder / f"{section}.txt").write_text(
                f"{header}\n{'-' * 70}\n{content[:MAX_EXCERPT_CHARS]}\n", encoding="utf-8"
            )
            index_rows.append({
                "path": str((folder / f"{section}.txt").relative_to(args.out)),
                "section_id": source.get("section_id") or "",
                "section_title": source.get("section_title") or "",
                "country": source.get("country") or "",
                "language": source.get("language") or "",
                "document_type": source.get("document_type") or "",
                "source_file": source.get("source_file") or "",
                "chars": len(content),
            })
            written += 1
            if written >= args.limit:
                break

    (args.out / "index.json").write_text(
        json.dumps({"index": settings.OPENSEARCH_INDEX, "matched": total, "written": written,
                    "sections": index_rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {written} sections to {args.out}", file=sys.stderr)
    if written < total:
        print(f"note: {total - written} more matched; raise --limit to include them.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
