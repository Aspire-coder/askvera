"""Load extracted policy sections into OpenSearch.

Use this after extract_policy_sections.py produces a *.sections.jsonl file.
The script creates an index if needed, embeds each section, and bulk indexes
the section documents for RETRIEVAL_PROVIDER=opensearch_section evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection, helpers

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from services.embeddings import embed_text  # noqa: E402


def _client() -> OpenSearch:
    if not settings.OPENSEARCH_ENDPOINT:
        raise RuntimeError("OPENSEARCH_ENDPOINT is required.")
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials are required.")
    auth = AWSV4SignerAuth(credentials, settings.AWS_REGION, settings.OPENSEARCH_SERVICE)
    endpoint = settings.OPENSEARCH_ENDPOINT.replace("https://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": endpoint, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
        max_retries=settings.AWS_MAX_ATTEMPTS,
        retry_on_timeout=True,
    )


def _index_body() -> dict[str, Any]:
    return {
        "settings": {
            "index": {
                "knn": True,
            }
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "status": {"type": "keyword"},
                "source_file": {"type": "keyword"},
                "source_uri": {"type": "keyword"},
                "country": {"type": "keyword"},
                "language": {"type": "keyword"},
                "document_type": {"type": "keyword"},
                "section_id": {"type": "keyword"},
                "section_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "start_page": {"type": "integer"},
                "end_page": {"type": "integer"},
                "content": {"type": "text"},
                "search_text": {"type": "text"},
                "content_hash": {"type": "keyword"},
                "metadata": {"type": "object", "enabled": True},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                    },
                },
            }
        },
    }


def _section_id(section: dict[str, Any]) -> str:
    return "|".join(
        [
            str(section["country"]),
            str(section["language"]),
            str(section["source_file"]),
            str(section["section_id"]),
        ]
    )


def _search_text(section: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(section.get("source_file", "")),
            str(section.get("country", "")),
            str(section.get("language", "")),
            str(section.get("section_id", "")),
            str(section.get("title", "")),
            str(section.get("content", "")),
        ]
    )


def _load_sections(path: Path) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                sections.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return sections


def _document(section: dict[str, Any], *, source_uri_prefix: str, status: str) -> dict[str, Any]:
    content = str(section["content"])
    search_text = _search_text(section)
    source_file = str(section["source_file"])
    source_uri = source_uri_prefix.rstrip("/") + "/" + source_file if source_uri_prefix else ""
    metadata = {
        "source_file": source_file,
        "country": section["country"],
        "language": section["language"],
        "section_id": section["section_id"],
        "section_title": section["title"],
        "start_page": section["start_page"],
        "end_page": section["end_page"],
    }
    return {
        "id": _section_id(section),
        "status": status,
        "source_file": source_file,
        "source_uri": source_uri,
        "country": section["country"],
        "language": section["language"],
        "document_type": "policy",
        "section_id": section["section_id"],
        "section_title": section["title"],
        "start_page": section["start_page"],
        "end_page": section["end_page"],
        "content": content,
        "search_text": search_text,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "metadata": metadata,
        "embedding": embed_text(search_text),
    }


def _actions(sections: list[dict[str, Any]], *, index: str, source_uri_prefix: str, status: str) -> list[dict[str, Any]]:
    return [
        {
            "_op_type": "index",
            "_index": index,
            "_id": _section_id(section),
            "_source": _document(section, source_uri_prefix=source_uri_prefix, status=status),
        }
        for section in sections
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", required=True, type=Path, help="Path to *.sections.jsonl from extract_policy_sections.py")
    parser.add_argument("--index", default="", help="OpenSearch index name. Defaults to OPENSEARCH_INDEX.")
    parser.add_argument("--source-uri-prefix", default="", help="Original approved document S3 prefix, used in citations")
    parser.add_argument("--status", default="active")
    parser.add_argument("--recreate-index", action="store_true", help="Delete and recreate the index before loading")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    index = args.index or settings.OPENSEARCH_INDEX
    client = _client()
    if args.recreate_index and client.indices.exists(index=index):
        client.indices.delete(index=index)
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_body())

    sections = _load_sections(args.jsonl)
    success, errors = helpers.bulk(
        client,
        _actions(sections, index=index, source_uri_prefix=args.source_uri_prefix, status=args.status),
        raise_on_error=False,
    )
    print("OpenSearch policy section load complete")
    print("---------------------------------------")
    print(f"Index: {index}")
    print(f"Sections read: {len(sections)}")
    print(f"Indexed: {success}")
    print(f"Errors: {len(errors)}")
    if errors:
        print(json.dumps(errors[:3], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
