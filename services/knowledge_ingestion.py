"""General-purpose approved-document ingestion for the admin portal."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from opensearchpy import helpers
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from scripts.ingestion.extract_policy_sections import extract_sections as extract_policy_sections
from scripts.ingestion.load_policy_sections_to_opensearch import (
    _actions,
    _client,
    _index_body,
    _older_source_actions,
)
from services.aws_clients import get_aws_clients
from services.document_preflight import analyze_pdf, extract_pdf_page_text, is_table_like_layout
from services.db import get_engine
from services.knowledge_generations import (
    build_logical_document_id,
    clear_active_generation_cache,
)
from utils.logging import get_logger

LOGGER = get_logger("services.knowledge_ingestion")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm"}
DOCUMENT_TYPES = {
    "policy",
    "office_directory",
}
ACCESS_SCOPES = {"country", "global"}
HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[^.!?]{3,120}$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MAX_CHUNK_CHARS = 4_500
CHUNK_OVERLAP_CHARS = 450
VNEXT_MAX_CHUNK_CHARS = 2_000
VNEXT_CHUNK_OVERLAP_CHARS = 200
CHUNK_PROFILES = {
    "current": (MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS),
    "vnext": (VNEXT_MAX_CHUNK_CHARS, VNEXT_CHUNK_OVERLAP_CHARS),
}


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


def validate_document_content(path: Path) -> None:
    """Reject mismatched, executable, or suspicious document payloads."""
    extension = path.suffix.lower()
    payload = path.read_bytes()
    header = payload[:8192]
    if extension == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise ValueError("The file content does not match the PDF extension.")
        lowered = payload.lower()
        if any(marker in lowered for marker in (b"/javascript", b"/launch", b"/embeddedfiles")):
            raise ValueError("PDF active content and embedded files are not accepted.")
        return
    if extension == ".docx":
        if not zipfile.is_zipfile(path):
            raise ValueError("The file content does not match the DOCX extension.")
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise ValueError("The DOCX package is incomplete.")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ValueError("Macro-enabled documents are not accepted.")
            total_compressed = sum(max(1, item.compress_size) for item in archive.infolist())
            total_uncompressed = sum(item.file_size for item in archive.infolist())
            if total_uncompressed > settings.ADMIN_UPLOAD_MAX_BYTES * 4:
                raise ValueError("The expanded DOCX package exceeds the safety limit.")
            if total_uncompressed / total_compressed > settings.ADMIN_INGESTION_MAX_ARCHIVE_RATIO:
                raise ValueError("The DOCX compression ratio exceeds the safety limit.")
            relationship_files = [
                name for name in names
                if name.lower().endswith(".rels")
            ]
            for name in relationship_files:
                if b'TargetMode="External"' in archive.read(name):
                    raise ValueError("DOCX external relationships are not accepted.")
        return
    if b"\x00" in header:
        raise ValueError("Binary content is not accepted for text documents.")


def release_ingestion_claim(
    job_id: str,
    message: str,
    *,
    retryable: bool = True,
) -> str:
    """Release a worker lease and explicitly classify the next job state."""
    with get_engine().begin() as connection:
        attempt_count = connection.execute(
            text("SELECT attempt_count FROM ingestion_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar()
        exhausted = int(attempt_count or 0) >= settings.ADMIN_INGESTION_MAX_ATTEMPTS
        status = "retryable" if retryable and not exhausted else "failed_terminal"
        connection.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = :status,
                    progress = CASE WHEN :terminal THEN 100 ELSE progress END,
                    error_message = :error_message,
                    lease_owner = '',
                    lease_expires_at = NULL,
                    updated_at = now()
                WHERE job_id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "status": status,
                "terminal": status == "failed_terminal",
                "error_message": str(message or "Document processing failed.")[:1000],
            },
        )
    return status


def claim_ingestion_job(job_id: str, worker_id: str, lease_seconds: int) -> str:
    """Atomically claim a job, or report that it is complete, busy, or missing."""
    with get_engine().begin() as connection:
        row = connection.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET lease_owner = :worker_id,
                    lease_expires_at = now() + (:lease_seconds * interval '1 second'),
                    attempt_count = attempt_count + 1,
                    status = 'extracting',
                    updated_at = now()
                WHERE job_id = :job_id
                  AND status NOT IN (
                      'ready', 'completed', 'cancelled',
                      'failed_terminal', 'dead_lettered'
                  )
                  AND attempt_count < :max_attempts
                  AND (lease_expires_at IS NULL OR lease_expires_at <= now())
                RETURNING job_id
                """
            ),
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "lease_seconds": max(30, lease_seconds),
                "max_attempts": settings.ADMIN_INGESTION_MAX_ATTEMPTS,
            },
        ).first()
        if row:
            return "claimed"
        status_row = connection.execute(
            text(
                """
                SELECT status, attempt_count
                FROM ingestion_jobs
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        ).mappings().first()
        if (
            status_row
            and int(status_row["attempt_count"] or 0)
            >= settings.ADMIN_INGESTION_MAX_ATTEMPTS
            and status_row["status"] not in {
                "ready", "completed", "cancelled",
                "failed_terminal", "dead_lettered",
            }
        ):
            connection.execute(
                text(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'failed_terminal',
                        lease_owner = '',
                        lease_expires_at = NULL,
                        updated_at = now()
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            status_row = {**status_row, "status": "failed_terminal"}
    status = status_row["status"] if status_row else None
    if status in {"ready", "completed"}:
        return "completed"
    if status in {"failed_terminal", "dead_lettered", "cancelled"}:
        return "terminal"
    if status is None:
        return "missing"
    return "busy"


def create_ingestion_job(
    *,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    version: str,
    effective_date: str = "",
    content_hash: str = "",
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
) -> str:
    job_id = uuid.uuid4().hex
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ingestion_jobs (
                    job_id, filename, country, language, document_type,
                    access_scope, document_version, content_hash, accepted_by,
                    logical_document_id, document_owner, approval_reference,
                    effective_date, status,
                    created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :country, :language, :document_type,
                    :access_scope, :document_version, :content_hash, :accepted_by,
                    :logical_document_id, :document_owner, :approval_reference,
                    NULLIF(:effective_date, '')::date, 'queued',
                    now(), now()
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
                "content_hash": content_hash,
                "accepted_by": accepted_by,
                "logical_document_id": logical_document_id,
                "document_owner": document_owner,
                "approval_reference": approval_reference,
                "effective_date": effective_date,
            },
        )
    return job_id


def stage_ingestion_upload(job_id: str, filename: str, content: bytes) -> str:
    """Persist an accepted upload before asynchronous processing begins."""
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    if not bucket:
        raise ValueError("KNOWLEDGE_UPLOAD_BUCKET is required for durable ingestion.")
    prefix = settings.ADMIN_INGESTION_QUARANTINE_PREFIX.strip("/")
    key = f"{prefix}/{job_id}/{filename}"
    get_aws_clients().s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType="application/octet-stream",
        ServerSideEncryption="AES256",
        Metadata={"job-id": job_id},
    )
    upload_uri = f"s3://{bucket}/{key}"
    _update_job(job_id, upload_uri=upload_uri)
    return upload_uri


def enqueue_ingestion_job(
    *,
    job_id: str,
    upload_uri: str,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    version: str,
    effective_date: str,
    content_hash: str,
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
) -> None:
    """Place a compact, non-document ingestion command on SQS."""
    if not settings.ADMIN_INGESTION_QUEUE_URL:
        raise ValueError("ADMIN_INGESTION_QUEUE_URL is required for durable ingestion.")
    get_aws_clients().sqs.send_message(
        QueueUrl=settings.ADMIN_INGESTION_QUEUE_URL,
        MessageBody=json.dumps(
            {
                "schemaVersion": 1,
                "jobId": job_id,
                "uploadUri": upload_uri,
                "filename": filename,
                "country": country,
                "language": language,
                "documentType": document_type,
                "accessScope": access_scope,
                "version": version,
                "effectiveDate": effective_date,
                "contentHash": content_hash,
                "acceptedBy": accepted_by,
                "logicalDocumentId": logical_document_id,
                "documentOwner": document_owner,
                "approvalReference": approval_reference,
            },
            separators=(",", ":"),
        ),
    )
    _update_job(job_id, status="queued", progress=5)


def fail_ingestion_job(job_id: str, message: str) -> None:
    """Mark an accepted upload as failed without exposing internal details."""
    _update_job(
        job_id,
        status="failed",
        progress=100,
        error_message=str(message or "Ingestion could not be queued.")[:1000],
    )


def record_ingestion_attempt(job_id: str) -> None:
    """Deprecated compatibility wrapper; workers should claim atomically."""
    claim_ingestion_job(job_id, "legacy-worker", settings.ADMIN_INGESTION_WORKER_VISIBILITY_SECONDS)


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
    upload_uri: str = "",
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
) -> bool:
    """Extract, embed, index, and activate one approved document."""
    path = Path(local_path)
    try:
        _update_job(job_id, status="extracting", progress=15)
        chunk_profile = settings.ADMIN_INGESTION_CHUNK_PROFILE
        use_policy_extractor = document_type == "policy" and path.suffix.lower() == ".pdf"
        if path.suffix.lower() == ".pdf" and settings.ADMIN_DOCUMENT_PREFLIGHT_ENABLED:
            preflight = analyze_pdf(path)
            if preflight.requires_ocr:
                if not settings.ADMIN_TEXTRACT_OCR_ENABLED or not upload_uri:
                    raise ValueError(
                        "This PDF appears to be scanned or image-only and requires OCR before publication."
                    )
                pages = _extract_pages_with_textract(upload_uri)
                use_policy_extractor = False
            else:
                pages = extract_pages(path, chunk_profile=chunk_profile)
        else:
            pages = extract_pages(path, chunk_profile=chunk_profile)
        if use_policy_extractor:
            sections = [
                {
                    **asdict(section),
                    "metadata": section.metadata,
                }
                for section in extract_policy_sections(
                    path,
                    country=country,
                    language=language,
                    document_version=version,
                    effective_date=effective_date,
                    status="active",
                    chunk_profile=chunk_profile,
                )
            ]
        else:
            sections = build_sections(
                pages,
                filename=filename,
                country=country,
                language=language,
                document_type=document_type,
                version=version,
                effective_date=effective_date,
                chunk_profile=chunk_profile,
            )
        if not sections:
            raise ValueError("No readable text was found in the document.")

        _update_job(job_id, status="uploading", progress=35, section_count=len(sections))
        source_uri = _upload_source(path, filename, job_id)
        _update_job(job_id, status="indexing", progress=55, source_uri=source_uri)
        stable_document_id = build_logical_document_id(
            logical_document_id=logical_document_id,
            country=str(sections[0]["country"]),
            language=str(sections[0]["language"]),
            document_type=document_type,
            access_scope=access_scope,
            source_file=str(sections[0]["source_file"]),
        )
        indexed = _index_sections(
            sections,
            source_uri=source_uri,
            document_type=document_type,
            access_scope=access_scope,
            ingestion_id=job_id,
            logical_document_id=stable_document_id,
            activated_by=accepted_by,
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
            accepted_by=accepted_by,
            logical_document_id=stable_document_id,
            document_owner=document_owner,
            approval_reference=approval_reference,
            effective_date=effective_date,
        )
        _update_job(
            job_id,
            status="ready",
            progress=100,
            section_count=indexed,
            source_uri=source_uri,
            lease_owner="",
            lease_expires_at=None,
            completed_at=datetime.now(UTC),
        )
        return True
    except ValueError as exc:
        LOGGER.exception("admin_ingestion_rejected", job_id=job_id, filename=filename)
        release_ingestion_claim(job_id, str(exc), retryable=False)
        return False
    except Exception as exc:
        LOGGER.exception("admin_ingestion_failed", job_id=job_id, filename=filename)
        release_ingestion_claim(job_id, str(exc), retryable=True)
        return False
    finally:
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            pass


def _extract_pages_with_textract(upload_uri: str) -> list[ExtractedPage]:
    """Extract a scanned PDF from its durable S3 upload using Textract."""
    parsed = urlparse(upload_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError("OCR requires a valid S3 upload URI.")
    textract = get_aws_clients().textract
    started = textract.start_document_text_detection(
        DocumentLocation={
            "S3Object": {
                "Bucket": parsed.netloc,
                "Name": parsed.path.lstrip("/"),
            }
        }
    )
    textract_job_id = str(started["JobId"])
    deadline = time.monotonic() + max(30, settings.ADMIN_TEXTRACT_OCR_TIMEOUT_SECONDS)
    response: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = textract.get_document_text_detection(JobId=textract_job_id)
        status = str(response.get("JobStatus") or "")
        if status == "SUCCEEDED":
            break
        if status in {"FAILED", "PARTIAL_SUCCESS"}:
            raise RuntimeError(f"Textract OCR did not complete successfully: {status}.")
        time.sleep(2)
    else:
        raise TimeoutError("Textract OCR exceeded the configured timeout.")

    blocks = list(response.get("Blocks", []))
    next_token = response.get("NextToken")
    while next_token:
        response = textract.get_document_text_detection(
            JobId=textract_job_id,
            NextToken=next_token,
        )
        blocks.extend(response.get("Blocks", []))
        next_token = response.get("NextToken")

    lines_by_page: dict[int, list[str]] = {}
    for block in blocks:
        if block.get("BlockType") != "LINE":
            continue
        page = max(1, int(block.get("Page") or 1))
        value = str(block.get("Text") or "").strip()
        if value:
            lines_by_page.setdefault(page, []).append(value)
    return [
        ExtractedPage(number=page, text="\n".join(lines))
        for page, lines in sorted(lines_by_page.items())
    ]


def extract_pages(path: Path, *, chunk_profile: str = "current") -> list[ExtractedPage]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        reader = PdfReader(str(path))
        pages: list[ExtractedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            raw_text = extract_pdf_page_text(page)
            if chunk_profile == "vnext":
                layout_text = extract_pdf_page_text(page, preserve_layout=True)
                if is_table_like_layout(layout_text):
                    raw_text = layout_text
            content = _clean_text(raw_text)
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
    chunk_profile: str = "current",
) -> list[dict[str, Any]]:
    """Create retrieval-sized chunks for approved non-policy directory documents."""
    try:
        max_chars, overlap_chars = CHUNK_PROFILES[chunk_profile]
    except KeyError as exc:
        raise ValueError(f"Unknown chunk profile: {chunk_profile}") from exc

    sections: list[dict[str, Any]] = []
    section_number = 0
    for page in pages:
        blocks = _page_blocks(page.text)
        for block_title, block_text in blocks:
            for part, chunk in enumerate(
                _chunk_text(
                    block_text,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                ),
                start=1,
            ):
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
                        "metadata": {
                            "document_type": document_type,
                            "chunk_profile": chunk_profile,
                        },
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


def _chunk_text(
    text_value: str,
    *,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if overlap_chars < 0 or overlap_chars >= max_chars // 2:
        raise ValueError("overlap_chars must be non-negative and less than half of max_chars")
    if len(text_value) <= max_chars:
        return [text_value]
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(start + max_chars, len(text_value))
        if end < len(text_value):
            boundary = max(text_value.rfind("\n", start, end), text_value.rfind(". ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text_value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text_value):
            break
        start = max(end - overlap_chars, start + 1)
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
    logical_document_id: str = "",
    activated_by: str = "",
) -> int:
    client = _client()
    index = settings.OPENSEARCH_INDEX
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_body())
    source_prefix = source_uri.rsplit("/", 1)[0] if source_uri else ""
    publish_status = "staging" if settings.ADMIN_INGESTION_STAGED_PUBLISH_ENABLED else "active"
    new_actions = list(
        _actions(
            sections,
            index=index,
            source_uri_prefix=source_prefix,
            status=publish_status,
            ingestion_id=ingestion_id,
            document_type=document_type,
            access_scope=access_scope,
        )
    )
    stable_document_id = logical_document_id or build_logical_document_id(
        logical_document_id="",
        country=str(sections[0]["country"]),
        language=str(sections[0]["language"]),
        document_type=document_type,
        access_scope=access_scope,
        source_file=str(sections[0]["source_file"]),
    )
    for action in new_actions:
        action["_source"]["logical_document_id"] = stable_document_id
        action["_source"].setdefault("metadata", {})["logical_document_id"] = stable_document_id
    if settings.ADMIN_INGESTION_STAGED_PUBLISH_ENABLED:
        for action in new_actions:
            action["_id"] = action["_source"]["id"]
    success, errors = helpers.bulk(
        client,
        new_actions,
        raise_on_error=False,
    )
    if errors:
        raise RuntimeError(f"OpenSearch rejected {len(errors)} chunks.")
    if settings.ADMIN_INGESTION_STAGED_PUBLISH_ENABLED:
        _activate_staged_sections(
            client,
            index=index,
            actions=new_actions,
            expected_count=len(sections),
            ingestion_id=ingestion_id,
        )
    if settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
        _activate_generation_pointer(
            logical_document_id=stable_document_id,
            ingestion_id=ingestion_id,
            country=str(sections[0]["country"]),
            language=str(sections[0]["language"]),
            source_file=str(sections[0]["source_file"]),
            document_type=document_type,
            access_scope=access_scope,
            activated_by=activated_by,
        )
    identity = (sections[0]["country"], sections[0]["language"], sections[0]["source_file"])
    if not settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
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


def _activate_generation_pointer(
    *,
    logical_document_id: str,
    ingestion_id: str,
    country: str,
    language: str,
    source_file: str,
    document_type: str,
    access_scope: str,
    activated_by: str,
) -> None:
    """Atomically switch the stable document slot to a verified generation."""
    with get_engine().begin() as connection:
        # Serialize publication for this logical document even when its pointer
        # row does not exist yet. SELECT FOR UPDATE alone cannot lock a missing row.
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:logical_document_id))"),
            {"logical_document_id": logical_document_id},
        )
        previous_ingestion_id = connection.execute(
            text(
                """
                SELECT active_ingestion_id
                FROM knowledge_active_generations
                WHERE logical_document_id = :logical_document_id
                FOR UPDATE
                """
            ),
            {"logical_document_id": logical_document_id},
        ).scalar() or ""
        if previous_ingestion_id:
            connection.execute(
                text(
                    """
                    UPDATE knowledge_document_generations
                    SET status = 'retired', retired_at = now()
                    WHERE ingestion_id = :ingestion_id
                    """
                ),
                {"ingestion_id": previous_ingestion_id},
            )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_active_generations (
                    logical_document_id, country, language, source_file,
                    document_type, access_scope, active_ingestion_id,
                    previous_ingestion_id, activated_at, activated_by
                ) VALUES (
                    :logical_document_id, :country, :language, :source_file,
                    :document_type, :access_scope, :ingestion_id,
                    '', now(), :activated_by
                )
                ON CONFLICT (logical_document_id) DO UPDATE SET
                    country = EXCLUDED.country,
                    language = EXCLUDED.language,
                    source_file = EXCLUDED.source_file,
                    document_type = EXCLUDED.document_type,
                    access_scope = EXCLUDED.access_scope,
                    previous_ingestion_id = knowledge_active_generations.active_ingestion_id,
                    active_ingestion_id = EXCLUDED.active_ingestion_id,
                    activated_at = now(),
                    activated_by = EXCLUDED.activated_by
                """
            ),
            {
                "logical_document_id": logical_document_id,
                "country": country,
                "language": language,
                "source_file": source_file,
                "document_type": document_type,
                "access_scope": access_scope,
                "ingestion_id": ingestion_id,
                "activated_by": activated_by,
            },
        )
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
                    now(), :activated_by
                )
                ON CONFLICT (ingestion_id) DO UPDATE SET
                    logical_document_id = EXCLUDED.logical_document_id,
                    country = EXCLUDED.country,
                    language = EXCLUDED.language,
                    source_file = EXCLUDED.source_file,
                    document_type = EXCLUDED.document_type,
                    access_scope = EXCLUDED.access_scope,
                    status = 'active',
                    activated_at = now(),
                    activated_by = EXCLUDED.activated_by,
                    retired_at = NULL
                """
            ),
            {
                "ingestion_id": ingestion_id,
                "logical_document_id": logical_document_id,
                "country": country,
                "language": language,
                "source_file": source_file,
                "document_type": document_type,
                "access_scope": access_scope,
                "activated_by": activated_by,
            },
        )
    clear_active_generation_cache()


def _activate_staged_sections(
    client: Any,
    *,
    index: str,
    actions: list[dict[str, Any]],
    expected_count: int,
    ingestion_id: str,
) -> None:
    """Verify a complete generation before making its chunks retrievable."""
    client.indices.refresh(index=index)
    result = client.count(
        index=index,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"ingestion_id": ingestion_id}},
                        {"term": {"status": "staging"}},
                    ]
                }
            }
        },
    )
    actual_count = int(result.get("count", 0))
    if actual_count != expected_count:
        raise RuntimeError(
            f"Staged publication verification failed: expected {expected_count}, found {actual_count}."
        )
    action_ids = [action["_id"] for action in actions]
    activation_actions = (
        {
            "_op_type": "update",
            "_index": index,
            "_id": action_id,
            "doc": {"status": "active"},
        }
        for action_id in action_ids
    )
    _, errors = helpers.bulk(
        client,
        activation_actions,
        raise_on_error=False,
        raise_on_exception=False,
    )
    if errors:
        rollback_actions = (
            {
                "_op_type": "update",
                "_index": index,
                "_id": action_id,
                "doc": {"status": "staging"},
            }
            for action_id in action_ids
        )
        helpers.bulk(
            client,
            rollback_actions,
            raise_on_error=False,
            raise_on_exception=False,
        )
        client.indices.refresh(index=index)
        raise RuntimeError(f"OpenSearch rejected {len(errors)} activation updates.")
    client.indices.refresh(index=index)


def _update_job(job_id: str, **values: Any) -> None:
    allowed = {
        "status",
        "progress",
        "section_count",
        "source_uri",
        "upload_uri",
        "error_message",
        "attempt_count",
        "lease_owner",
        "lease_expires_at",
        "completed_at",
    }
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
                    content_hash, accepted_by, logical_document_id, document_owner,
                    approval_reference, effective_date, status, created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :source_uri, :country, :language,
                    :document_type, :access_scope, :version, :section_count,
                    :content_hash, :accepted_by, :logical_document_id, :document_owner,
                    :approval_reference, NULLIF(:effective_date, '')::date,
                    'active', now(), now()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    source_uri = EXCLUDED.source_uri,
                    section_count = EXCLUDED.section_count,
                    accepted_by = EXCLUDED.accepted_by,
                    logical_document_id = EXCLUDED.logical_document_id,
                    document_owner = EXCLUDED.document_owner,
                    approval_reference = EXCLUDED.approval_reference,
                    effective_date = EXCLUDED.effective_date,
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
                       section_count, source_uri, upload_uri, content_hash,
                       accepted_by, logical_document_id, document_owner,
                       approval_reference, attempt_count, error_message,
                       created_at, updated_at
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
