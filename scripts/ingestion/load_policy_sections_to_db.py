"""Load extracted policy sections into PostgreSQL.

Use this after scripts/ingestion/extract_policy_sections.py has produced a
*.sections.jsonl file. The loader upserts each section into policy_sections so
the app can test RETRIEVAL_PROVIDER=section without changing the source PDFs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.db import get_engine  # noqa: E402
from services.embeddings import embed_text  # noqa: E402


def _section_id(section: dict[str, Any]) -> str:
    source_file = str(section["source_file"])
    country = str(section["country"])
    language = str(section["language"])
    section_value = str(section["section_id"])
    return "|".join([country, language, source_file, section_value])


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


def load_sections(
    sections: list[dict[str, Any]],
    *,
    source_uri_prefix: str,
    document_type: str,
    replace_source: bool,
    embed: bool,
) -> int:
    """Upsert policy sections into the database."""
    if not sections:
        return 0

    engine = get_engine()
    source_file = str(sections[0]["source_file"])
    country = str(sections[0]["country"])
    language = str(sections[0]["language"])

    with engine.begin() as connection:
        if replace_source:
            connection.execute(
                text(
                    """
                    DELETE FROM policy_sections
                    WHERE source_file = :source_file
                      AND country = :country
                      AND language = :language
                      AND document_type = :document_type
                    """
                ),
                {
                    "source_file": source_file,
                    "country": country,
                    "language": language,
                    "document_type": document_type,
                },
            )

        for section in sections:
            content = str(section["content"])
            search_text = _search_text(section)
            embedding = embed_text(search_text) if embed else None
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
            connection.execute(
                text(
                    """
                    INSERT INTO policy_sections (
                        id,
                        source_file,
                        source_uri,
                        country,
                        language,
                        document_type,
                        section_id,
                        section_title,
                        start_page,
                        end_page,
                        content,
                        search_text,
                        embedding,
                        metadata,
                        content_hash,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :source_file,
                        :source_uri,
                        :country,
                        :language,
                        :document_type,
                        :section_id,
                        :section_title,
                        :start_page,
                        :end_page,
                        :content,
                        :search_text,
                        CAST(:embedding AS jsonb),
                        CAST(:metadata AS jsonb),
                        :content_hash,
                        now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        source_file = EXCLUDED.source_file,
                        source_uri = EXCLUDED.source_uri,
                        country = EXCLUDED.country,
                        language = EXCLUDED.language,
                        document_type = EXCLUDED.document_type,
                        section_id = EXCLUDED.section_id,
                        section_title = EXCLUDED.section_title,
                        start_page = EXCLUDED.start_page,
                        end_page = EXCLUDED.end_page,
                        content = EXCLUDED.content,
                        search_text = EXCLUDED.search_text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = now()
                    """
                ),
                {
                    "id": _section_id(section),
                    "source_file": source_file,
                    "source_uri": source_uri,
                    "country": section["country"],
                    "language": section["language"],
                    "document_type": document_type,
                    "section_id": section["section_id"],
                    "section_title": section["title"],
                    "start_page": section["start_page"],
                    "end_page": section["end_page"],
                    "content": content,
                    "search_text": search_text,
                    "embedding": json.dumps(embedding) if embedding is not None else None,
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                },
            )
    return len(sections)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", required=True, type=Path, help="Path to *.sections.jsonl from extract_policy_sections.py")
    parser.add_argument("--source-uri-prefix", default="", help="Original approved document S3 prefix, used in citations")
    parser.add_argument("--document-type", default="policy")
    parser.add_argument("--replace-source", action="store_true", help="Delete existing rows for this source/country/language first")
    parser.add_argument("--embed", action="store_true", help="Generate and store Bedrock embeddings for semantic retrieval")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sections = _load_sections(args.jsonl)
    count = load_sections(
        sections,
        source_uri_prefix=args.source_uri_prefix,
        document_type=args.document_type,
        replace_source=args.replace_source,
        embed=args.embed,
    )
    print("Policy section database load complete")
    print("-------------------------------------")
    print(f"JSONL: {args.jsonl}")
    print(f"Sections loaded: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
