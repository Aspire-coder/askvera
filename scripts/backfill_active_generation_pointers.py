"""Preview or register generation pointers for content that is already live."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from opensearchpy.exceptions import OpenSearchException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from scripts.ingestion.load_policy_sections_to_opensearch import _client  # noqa: E402
from services.aws_clients import init_aws_clients  # noqa: E402
from services.db import close_db, get_engine, init_db  # noqa: E402
from services.knowledge_generations import build_logical_document_id  # noqa: E402
from utils.logging import configure_logging  # noqa: E402


@dataclass(frozen=True)
class GenerationCandidate:
    logical_document_id: str
    country: str
    language: str
    source_file: str
    document_type: str
    access_scope: str
    ingestion_id: str
    section_count: int


def generation_candidates(
    records: Iterable[dict[str, Any]],
    *,
    pointers: dict[str, str] | None = None,
) -> list[GenerationCandidate]:
    """Return one unambiguous active generation for every source identity."""
    grouped: dict[
        tuple[str, str, str, str, str],
        dict[str, int],
    ] = defaultdict(lambda: defaultdict(int))
    for record in records:
        source = record.get("_source", record)
        identity = (
            str(source.get("country") or "").upper(),
            str(source.get("language") or "").lower(),
            str(source.get("source_file") or ""),
            str(source.get("document_type") or "").lower(),
            str(source.get("access_scope") or "").lower(),
        )
        ingestion_id = str(source.get("ingestion_id") or "")
        if not all(identity) or not ingestion_id:
            raise ValueError(
                "An active OpenSearch record is missing generation identity metadata."
            )
        grouped[identity][ingestion_id] += 1

    candidates: list[GenerationCandidate] = []
    for identity, generations in sorted(grouped.items()):
        country, language, source_file, document_type, access_scope = identity
        logical_document_id = build_logical_document_id(
            logical_document_id="",
            country=country,
            language=language,
            document_type=document_type,
            access_scope=access_scope,
            source_file=source_file,
        )
        selected_ingestion_id = (pointers or {}).get(logical_document_id, "")
        if len(generations) == 1:
            ingestion_id, section_count = next(iter(generations.items()))
        elif selected_ingestion_id in generations:
            ingestion_id = selected_ingestion_id
            section_count = generations[selected_ingestion_id]
        else:
            raise ValueError(
                "Multiple active generations exist for "
                f"{country}/{language}/{source_file}: "
                f"{', '.join(sorted(generations))}"
            )
        candidates.append(
            GenerationCandidate(
                logical_document_id=logical_document_id,
                country=country,
                language=language,
                source_file=source_file,
                document_type=document_type,
                access_scope=access_scope,
                ingestion_id=ingestion_id,
                section_count=section_count,
            )
        )
    return candidates


def load_active_records(
    *,
    client: Any | None = None,
    page_size: int = 1000,
) -> Iterable[dict[str, Any]]:
    """Page through live generation metadata without the unsupported scroll API."""
    search_client = client or _client()
    search_after: list[Any] | None = None

    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "track_total_hits": False,
            "_source": [
                "country",
                "language",
                "source_file",
                "document_type",
                "access_scope",
                "ingestion_id",
            ],
            "sort": [{"_id": "asc"}],
            "query": {"term": {"status": "active"}},
        }
        if search_after is not None:
            body["search_after"] = search_after

        response = search_client.search(
            index=settings.OPENSEARCH_INDEX,
            body=body,
        )
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return

        yield from hits
        if len(hits) < page_size:
            return

        next_search_after = hits[-1].get("sort")
        if not isinstance(next_search_after, list) or not next_search_after:
            raise RuntimeError(
                "OpenSearch did not return a search_after token for a full page."
            )
        if next_search_after == search_after:
            raise RuntimeError("OpenSearch pagination token did not advance.")
        search_after = next_search_after


def existing_pointers() -> dict[str, str]:
    """Return the current pointer map without changing database state."""
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT logical_document_id, active_ingestion_id
                FROM knowledge_active_generations
                """
            )
        ).all()
    return {str(logical_id): str(ingestion_id) for logical_id, ingestion_id in rows}


def pointer_coverage_failures(
    candidates: Iterable[GenerationCandidate],
    pointers: dict[str, str],
) -> list[str]:
    """Return missing, conflicting, or orphaned pointer failures."""
    expected = {
        candidate.logical_document_id: candidate.ingestion_id
        for candidate in candidates
    }
    failures = [
        f"missing pointer: {logical_id} -> {ingestion_id}"
        for logical_id, ingestion_id in sorted(expected.items())
        if logical_id not in pointers
    ]
    failures.extend(
        f"pointer mismatch: {logical_id} is {pointers[logical_id]}, expected {ingestion_id}"
        for logical_id, ingestion_id in sorted(expected.items())
        if logical_id in pointers and pointers[logical_id] != ingestion_id
    )
    failures.extend(
        f"orphaned pointer: {logical_id} -> {ingestion_id}"
        for logical_id, ingestion_id in sorted(pointers.items())
        if logical_id not in expected
    )
    return failures


def apply_backfill(candidates: Iterable[GenerationCandidate]) -> int:
    """Insert only missing pointers after rejecting any conflicting pointer."""
    candidate_list = list(candidates)
    failures = pointer_coverage_failures(candidate_list, existing_pointers())
    conflicts = [
        failure
        for failure in failures
        if not failure.startswith("missing pointer:")
    ]
    if conflicts:
        raise RuntimeError("; ".join(conflicts))

    inserted = 0
    with get_engine().begin() as connection:
        for candidate in candidate_list:
            result = connection.execute(
                text(
                    """
                    INSERT INTO knowledge_active_generations (
                        country, language, source_file, document_type,
                        access_scope, active_ingestion_id,
                        previous_ingestion_id, activated_at, activated_by,
                        logical_document_id
                    ) VALUES (
                        :country, :language, :source_file, :document_type,
                        :access_scope, :ingestion_id, '', now(),
                        'controlled-publication-backfill', :logical_document_id
                    )
                    ON CONFLICT (logical_document_id) DO NOTHING
                    """
                ),
                candidate.__dict__,
            )
            inserted += int(result.rowcount or 0)
            connection.execute(
                text(
                    """
                    INSERT INTO knowledge_document_generations (
                        ingestion_id, logical_document_id, country, language,
                        source_file, document_type, access_scope, status,
                        activated_at, activated_by
                    ) VALUES (
                        :ingestion_id, :logical_document_id, :country, :language,
                        :source_file, :document_type, :access_scope, 'active',
                        now(), 'controlled-publication-backfill'
                    )
                    ON CONFLICT (ingestion_id) DO NOTHING
                    """
                ),
                candidate.__dict__,
            )
            connection.execute(
                text(
                    """
                    UPDATE knowledge_documents
                    SET logical_document_id = :logical_document_id,
                        updated_at = now()
                    WHERE country = :country
                      AND language = :language
                      AND filename = :source_file
                      AND document_type = :document_type
                      AND access_scope = :access_scope
                      AND logical_document_id = ''
                    """
                ),
                candidate.__dict__,
            )
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing pointers. The default is a read-only dry run.",
    )
    parser.add_argument("--load-ssm", action="store_true")
    args = parser.parse_args()

    configure_logging()
    if args.load_ssm:
        settings.load_ssm_config()
    init_aws_clients()
    init_db("knowledge-generation-backfill")
    try:
        pointers = existing_pointers()
        candidates = generation_candidates(
            load_active_records(),
            pointers=pointers,
        )
        failures = pointer_coverage_failures(candidates, pointers)
        print(f"Active logical documents: {len(candidates)}")
        print(f"Existing generation pointers: {len(pointers)}")
        for failure in failures:
            print(f"- {failure}")
        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing every pointer.")
            return 1 if any("mismatch:" in item for item in failures) else 0
        inserted = apply_backfill(candidates)
        remaining = pointer_coverage_failures(candidates, existing_pointers())
        if remaining:
            raise RuntimeError("; ".join(remaining))
        print(f"Inserted generation pointers: {inserted}")
        print("PASS: every active document generation has one matching pointer.")
        return 0
    except (
        OpenSearchException,
        SQLAlchemyError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Generation pointer backfill failed: {exc}", file=sys.stderr)
        return 1
    finally:
        close_db("knowledge-generation-backfill")


if __name__ == "__main__":
    raise SystemExit(main())
