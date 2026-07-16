"""General-purpose approved-document ingestion for the admin portal."""

from __future__ import annotations

import csv
import hashlib
import html
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from opensearchpy import helpers
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from scripts.ingestion.load_policy_sections_to_opensearch import (
    _actions,
    _client,
    _index_body,
    _older_source_actions,
)
from services.aws_clients import get_aws_clients
from services.db import get_engine
from utils.logging import get_logger

LOGGER = get_logger("services.knowledge_ingestion")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm"}
DOCUMENT_TYPES = {
    "policy",
    "product_information",
    "training",
    "marketing",
    "legal",
    "faq",
    "operations",
    "other",
}
ACCESS_SCOPES = {"country", "global"}
HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[^.!?]{3,120}$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MAX_CHUNK_CHARS = 4_500
CHUNK_OVERLAP_CHARS = 450


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str


def safe_filename(filename: str) -> str:
    """Return a storage-safe filename while preserving the extension."""
    path = Path(filename or "document")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-.") or "document"
    suffix = path.suffix.lower()
    return f"{stem[:120]}{suffix}"


def validate_upload(filename: str, size: int) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension or 'unknown'}")
    if size <= 0:
        raise ValueError("The uploaded file is empty.")
    if size > settings.ADMIN_UPLOAD_MAX_BYTES:
        raise ValueError(f"File exceeds the {settings.ADMIN_UPLOAD_MAX_BYTES // (1024 * 1024)} MB limit.")


def create_ingestion_job(
    *,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    version: str,
) -> str:
    job_id = uuid.uuid4().hex
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ingestion_jobs (
                    job_id, filename, country, language, document_type,
                    access_scope, document_version, status, created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :country, :language, :document_type,
                    :access_scope, :document_version, 'queued', now(), now()
                )
                """
            ),
            {
                "job_id": job_id,
                "filename": filename,
                "country": country,
                "language": language,
                "document_type": document_type,
                "access_scope": access_scope,
                "document_version": version,
            },
        )
    return job_id


def process_ingestion_job(
    job_id: str,
    local_path: str,
    *,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    version: str,
    effective_date: str,
) -> None:
    """Extract, embed, index, and activate one approved document."""
    path = Path(local_path)
    try:
        _update_job(job_id, status="extracting", progress=15)
        pages = extract_pages(path)
        sections = build_sections(
            pages,
            filename=filename,
            country=country,
            language=language,
            document_type=document_type,
            version=version,
            effective_date=effective_date,
        )
        if not sections:
            raise ValueError("No readable text was found in the document.")

        _update_job(job_id, status="uploading", progress=35, section_count=len(sections))
        source_uri = _upload_source(path, filename, job_id)
        _update_job(job_id, status="indexing", progress=55, source_uri=source_uri)
        indexed = _index_sections(
            sections,
            source_uri=source_uri,
            document_type=document_type,
            access_scope=access_scope,
            ingestion_id=job_id,
        )
        _record_document(
            job_id=job_id,
            filename=filename,
            source_uri=source_uri,
            country=country,
            language=language,
            document_type=document_type,
            access_scope=access_scope,
            version=version,
            section_count=indexed,
            content_hash=_file_hash(path),
        )
        _update_job(job_id, status="ready", progress=100, section_count=indexed, source_uri=source_uri)
    except Exception as exc:
        LOGGER.exception("admin_ingestion_failed", job_id=job_id, filename=filename)
        _update_job(job_id, status="failed", progress=100, error_message=str(exc)[:1000])
    finally:
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            pass


def extract_pages(path: Path) -> list[ExtractedPage]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        reader = PdfReader(str(path))
        pages: list[ExtractedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            content = _clean_text(page.extract_text() or "")
            if content:
                pages.append(ExtractedPage(index, content))
        return pages
    if extension == ".docx":
        return [ExtractedPage(1, _extract_docx(path))]
    if extension == ".csv":
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            rows = [" | ".join(row) for row in csv.reader(handle)]
        return [ExtractedPage(1, _clean_text("\n".join(rows)))]
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    if extension in {".html", ".htm"}:
        raw = html.unescape(HTML_TAG_RE.sub(" ", raw))
    return [ExtractedPage(1, _clean_text(raw))]


def _extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text_parts = [
            node.text or ""
            for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        ]
        value = "".join(text_parts).strip()
        if value:
            paragraphs.append(value)
    return _clean_text("\n".join(paragraphs))


def _clean_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line)


def build_sections(
    pages: list[ExtractedPage],
    *,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    version: str = "",
    effective_date: str = "",
) -> list[dict[str, Any]]:
    """Create retrieval-sized chunks for policies, product sheets, FAQs, and training material."""
    sections: list[dict[str, Any]] = []
    section_number = 0
    for page in pages:
        blocks = _page_blocks(page.text)
        for block_title, block_text in blocks:
            for part, chunk in enumerate(_chunk_text(block_text), start=1):
                section_number += 1
                section_id = f"doc-{section_number:04d}"
                title = block_title or f"{Path(filename).stem} — page {page.number}"
                if part > 1:
                    title = f"{title} (part {part})"
                sections.append(
                    {
                        "source_file": filename,
                        "country": country,
                        "language": language,
                        "section_id": section_id,
                        "title": title[:160],
                        "start_page": page.number,
                        "end_page": page.number,
                        "content": chunk,
                        "document_version": version,
                        "effective_date": effective_date,
                        "status": "active",
                        "chunk_type": "document_section",
                        "parent_section_id": "",
                        "metadata": {"document_type": document_type},
                    }
                )
    return sections


def _page_blocks(text_value: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text_value.splitlines() if line.strip()]
    if not lines:
        return []
    blocks: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in lines:
        looks_like_heading = (
            len(line) <= 120
            and bool(HEADING_RE.match(line))
            and (line.isupper() or re.match(r"^\d+(?:\.\d+)*[.)]?\s+", line) is not None)
        )
        if looks_like_heading and current_lines:
            blocks.append((current_title, current_lines))
            current_title = line
            current_lines = []
        elif looks_like_heading:
            current_title = line
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append((current_title, current_lines))
    if not blocks:
        blocks.append((lines[0][:120], lines))
    return [(title, "\n".join(content)) for title, content in blocks if content]


def _chunk_text(text_value: str) -> list[str]:
    if len(text_value) <= MAX_CHUNK_CHARS:
        return [text_value]
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(start + MAX_CHUNK_CHARS, len(text_value))
        if end < len(text_value):
            boundary = max(text_value.rfind("\n", start, end), text_value.rfind(". ", start, end))
            if boundary > start + MAX_CHUNK_CHARS // 2:
                end = boundary + 1
        chunk = text_value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text_value):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


def _upload_source(path: Path, filename: str, job_id: str) -> str:
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    if not bucket:
        return ""
    key = f"{settings.KNOWLEDGE_UPLOAD_PREFIX.strip('/')}/{job_id}/{filename}"
    get_aws_clients().s3.upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


def _index_sections(
    sections: list[dict[str, Any]],
    *,
    source_uri: str,
    document_type: str,
    access_scope: str,
    ingestion_id: str,
) -> int:
    client = _client()
    index = settings.OPENSEARCH_INDEX
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_body())
    source_prefix = source_uri.rsplit("/", 1)[0] if source_uri else ""
    success, errors = helpers.bulk(
        client,
        _actions(
            sections,
            index=index,
            source_uri_prefix=source_prefix,
            status="active",
            ingestion_id=ingestion_id,
            document_type=document_type,
            access_scope=access_scope,
        ),
        raise_on_error=False,
    )
    if errors:
        raise RuntimeError(f"OpenSearch rejected {len(errors)} chunks.")
    identity = (sections[0]["country"], sections[0]["language"], sections[0]["source_file"])
    delete_actions = _older_source_actions(
        client,
        index=index,
        country=str(identity[0]),
        language=str(identity[1]),
        source_file=str(identity[2]),
        ingestion_id=ingestion_id,
    )
    if delete_actions:
        helpers.bulk(client, delete_actions, raise_on_error=False, raise_on_exception=False)
    return int(success)


def _update_job(job_id: str, **values: Any) -> None:
    allowed = {"status", "progress", "section_count", "source_uri", "error_message"}
    updates = {key: value for key, value in values.items() if key in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    try:
        with get_engine().begin() as connection:
            connection.execute(
                text(f"UPDATE ingestion_jobs SET {assignments}, updated_at = now() WHERE job_id = :job_id"),
                {"job_id": job_id, **updates},
            )
    except SQLAlchemyError:
        LOGGER.exception("ingestion_job_update_failed", job_id=job_id)


def _record_document(**values: Any) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO knowledge_documents (
                    document_id, filename, source_uri, country, language,
                    document_type, access_scope, document_version, section_count,
                    content_hash, status, created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :source_uri, :country, :language,
                    :document_type, :access_scope, :version, :section_count,
                    :content_hash, 'active', now(), now()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    source_uri = EXCLUDED.source_uri,
                    section_count = EXCLUDED.section_count,
                    status = 'active',
                    updated_at = now()
                """
            ),
            values,
        )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def list_ingestion_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT job_id, filename, country, language, document_type,
                       access_scope, document_version, status, progress,
                       section_count, source_uri, error_message, created_at, updated_at
                FROM ingestion_jobs ORDER BY created_at DESC LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit), 200))},
        ).mappings().all()
    return [
        {
            **dict(row),
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
        }
        for row in rows
    ]
