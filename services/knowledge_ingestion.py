"""General-purpose approved-document ingestion for the admin portal.

Write-once generations (OpenSearch Serverless VECTORSEARCH)
-----------------------------------------------------------
VECTORSEARCH rejects client-supplied document ids, update-by-id,
delete_by_query, update_by_query and indices.refresh. Every portal
generation is therefore written exactly once, with status="active", and is
never updated in place. Staging, publish, retire, rollback and delete are all
database pointer operations (knowledge_active_generations).

Safety invariant: this is only safe because retrieval gates every read on
status="active" AND the chunk's ingestion_id being in the active pointer set.
That second gate is app/retrieval/opensearch_sections.py's _generation_filters
(with its "__no_active_generation__" sentinel when no pointer matches), which
applies only while ADMIN_INGESTION_GENERATION_POINTER_ENABLED is true. With
the flag off, a review-mode generation written as "active" would be served
before anyone approved it. That is why review mode is refused at upload
(api/admin_routes.py) and again in _index_sections when the flag is off, and
why scripts/validate_config.py requires the flag in deployed environments.
Do not relax any of those without first changing how retrieval gates reads.

Chunks become searchable only after a refresh (~60 s on Classic), so
writes are awaited (_await_generation) and deletes need two zero polls one
refresh interval apart (_delete_generation_chunks). Both waits are bounded by
ADMIN_INGESTION_VISIBILITY_TIMEOUT_SECONDS (never below 150 s).
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
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
from scripts.ingestion.extract_global_sponsoring_directory import extract_directory as extract_sponsoring_directory
from scripts.ingestion.extract_policy_sections import extract_sections as extract_policy_sections
from scripts.ingestion.load_policy_sections_to_opensearch import (
    _actions,
    _client,
    _index_body,
    _older_source_actions,
)
from services.aws_clients import get_aws_clients
from services.document_preflight import analyze_pdf_with_timeout, extract_pdf_page_text
from services.db import get_engine
from services.knowledge_generations import (
    build_logical_document_id,
    clear_active_generation_cache,
)
from utils.logging import get_logger
from utils.opensearch_fields import exact_term_query

LOGGER = get_logger("services.knowledge_ingestion")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".html", ".htm"}
DOCUMENT_TYPES = {
    "policy",
    "office_directory",
    "product_information",
}
ACCESS_SCOPES = {"country", "global"}
HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?[^.!?]{3,120}$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MAX_CHUNK_CHARS = 4_500
CHUNK_OVERLAP_CHARS = 450
CHUNK_PROFILES = {
    "current": (MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS),
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


def detect_upload_format(filename: str, content: bytes) -> dict[str, str]:
    """Detect the accepted document family and reject extension/content mismatches."""
    extension = Path(filename).suffix.lower()
    header = content[:8192]
    if header.startswith(b"%PDF-"):
        detected = "pdf"
        mime_type = "application/pdf"
    elif extension == ".docx" and zipfile.is_zipfile(io.BytesIO(content)):
        detected = "docx"
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif b"\x00" not in header:
        detected = "text"
        mime_type = "text/plain"
    else:
        raise ValueError("The uploaded file type could not be verified safely.")
    if extension == ".docx" and detected != "docx":
        raise ValueError("The file content does not match the DOCX extension.")
    if extension == ".pdf" and detected != "pdf":
        raise ValueError("The file content does not match the PDF extension.")
    if extension not in {".pdf", ".docx"} and detected != "text":
        raise ValueError("The file content could not be verified as readable text.")
    return {"extension": extension, "detectedType": detected, "mimeType": mime_type}


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
                      'failed_terminal', 'dead_lettered',
                      'ready_for_review', 'deleting', 'deleted', 'deletion_failed'
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
                "ready_for_review", "deleting", "deleted", "deletion_failed",
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
    if status in {"ready", "ready_for_review", "completed"}:
        return "completed"
    if status in {"failed_terminal", "dead_lettered", "cancelled", "deleted", "deletion_failed"}:
        return "terminal"
    if status is None:
        return "missing"
    return "busy"


def create_ingestion_job(
    *,
    job_id: str | None = None,
    filename: str,
    country: str,
    language: str,
    document_type: str,
    access_scope: str,
    version: str,
    effective_date: str = "",
    expiry_date: str = "",
    content_hash: str = "",
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
    review_before_publish: bool = False,
) -> str:
    job_id = job_id or uuid.uuid4().hex
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO ingestion_jobs (
                    job_id, filename, country, language, document_type,
                    access_scope, document_version, content_hash, accepted_by,
                    logical_document_id, document_owner, approval_reference,
                    review_before_publish, effective_date, expiry_date,
                    malware_scan_status, status,
                    created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :country, :language, :document_type,
                    :access_scope, :document_version, :content_hash, :accepted_by,
                    :logical_document_id, :document_owner, :approval_reference,
                    :review_before_publish, NULLIF(:effective_date, '')::date,
                    NULLIF(:expiry_date, '')::date, :malware_scan_status, 'queued',
                    now(), now()
                )
                ON CONFLICT (job_id) DO NOTHING
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
                "review_before_publish": review_before_publish,
                "effective_date": effective_date,
                "expiry_date": expiry_date,
                "malware_scan_status": "pending" if settings.ADMIN_INGESTION_MALWARE_SCAN_REQUIRED else "not_required",
            },
        )
    return job_id


def _storage_scope_path(*, country: str, access_scope: str) -> str:
    """Return the durable S3 folder for a global or market-scoped document."""
    if access_scope not in ACCESS_SCOPES:
        raise ValueError("Unsupported document access scope.")
    if access_scope == "global":
        return "global"
    normalized_country = country.upper().strip()
    if not normalized_country:
        raise ValueError("Country is required for a country-scoped document.")
    return f"countries/{normalized_country}"


def stage_ingestion_upload(
    job_id: str,
    filename: str,
    content: bytes,
    *,
    country: str,
    access_scope: str,
) -> str:
    """Persist an accepted upload before asynchronous processing begins."""
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    if not bucket:
        raise ValueError("KNOWLEDGE_UPLOAD_BUCKET is required for durable ingestion.")
    prefix = settings.ADMIN_INGESTION_QUARANTINE_PREFIX.strip("/")
    scope_path = _storage_scope_path(country=country, access_scope=access_scope)
    key = f"{prefix}/{scope_path}/{job_id}/{filename}"
    get_aws_clients().s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType="application/octet-stream",
        ServerSideEncryption="AES256",
        Metadata={"job-id": job_id, "access-scope": access_scope, "country": country.upper()},
    )
    upload_uri = f"s3://{bucket}/{key}"
    _update_job(job_id, upload_uri=upload_uri)
    return upload_uri


def cleanup_staged_ingestion_upload(upload_uri: str) -> None:
    """Remove quarantine content when queue publication fails before processing."""
    parsed = urlparse(upload_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        return
    try:
        get_aws_clients().s3.delete_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    except Exception:
        LOGGER.exception("staged_upload_cleanup_failed", upload_uri=upload_uri)


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
    expiry_date: str = "",
    content_hash: str,
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
    review_before_publish: bool = False,
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
                "expiryDate": expiry_date,
                "contentHash": content_hash,
                "acceptedBy": accepted_by,
                "logicalDocumentId": logical_document_id,
                "documentOwner": document_owner,
                "approvalReference": approval_reference,
                "reviewBeforePublish": review_before_publish,
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


def _extract_directory_sections(
    path: Path,
    *,
    version: str,
    effective_date: str,
    extracted_pages: list[tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    """Accept only international sponsoring content under the legacy directory type.

    Keep the specialized parser's country and field metadata. Never fall back
    to the retired office/staff directory or the generic chunker.
    """
    try:
        sponsoring_records = extract_sponsoring_directory(path, extracted_pages=extracted_pages)
    except ValueError:
        sponsoring_records = []
    if sponsoring_records:
        return [
            {**record.to_row(), "document_version": version, "effective_date": effective_date}
            for record in sponsoring_records
        ]

    raise ValueError(
        "Only the international sponsoring directory is supported as global content. "
        "This document does not match its format; office/staff directories are not supported."
    )


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
    expiry_date: str = "",
    upload_uri: str = "",
    accepted_by: str = "",
    logical_document_id: str = "",
    document_owner: str = "",
    approval_reference: str = "",
    review_before_publish: bool = False,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> bool:
    """Extract, embed, index, and activate one approved document."""
    path = Path(local_path)
    try:
        _update_job(job_id, status="extracting", progress=15)
        chunk_profile = settings.ADMIN_INGESTION_CHUNK_PROFILE
        use_policy_extractor = document_type == "policy" and path.suffix.lower() == ".pdf"
        # Both specialized extractors re-read the PDF directly (they don't
        # consume the OCR-extracted `pages` text), so a directory PDF that
        # requires OCR falls back to the generic chunker below, same as a
        # policy PDF does in that case.
        use_directory_extractor = document_type == "office_directory"
        normalized_pages = None
        if path.suffix.lower() == ".pdf" and settings.ADMIN_DOCUMENT_PREFLIGHT_ENABLED:
            preflight = analyze_pdf_with_timeout(
                path,
                timeout_seconds=settings.ADMIN_INGESTION_PARSER_TIMEOUT_SECONDS,
                max_pages=settings.ADMIN_INGESTION_MAX_PDF_PAGES,
                max_extracted_characters=settings.ADMIN_INGESTION_MAX_EXTRACTED_TEXT_CHARS,
            )
            if preflight.requires_ocr:
                if not settings.ADMIN_TEXTRACT_OCR_ENABLED or not upload_uri:
                    # Named precisely, because this now fires for a mostly
                    # readable document containing one scanned page, and
                    # "appears to be scanned or image-only" would send the
                    # uploader looking for a problem that is not there.
                    if preflight.scanned_page_numbers:
                        pages = ", ".join(str(n) for n in preflight.scanned_page_numbers)
                        raise ValueError(
                            f"This PDF has no extractable text on page(s) {pages}, which carry images. "
                            f"Publishing it would silently omit that content. Supply a text-based PDF "
                            f"or enable OCR before publication."
                        )
                    raise ValueError(
                        "This PDF appears to be scanned or image-only and requires OCR before publication."
                    )
                pages = _extract_pages_with_textract(upload_uri)
                normalized_pages = [(page.number, page.text) for page in pages]
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
                    **({"extracted_pages": normalized_pages} if normalized_pages is not None else {}),
                )
            ]
        elif use_directory_extractor:
            if path.suffix.lower() != ".pdf":
                normalized_pages = [(page.number, page.text) for page in pages]
            sections = _extract_directory_sections(
                path, version=version, effective_date=effective_date, extracted_pages=normalized_pages,
            )
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
        short_notice = document_type == "policy" and path.suffix.lower() != ".pdf" and len(pages) == 1
        if len(sections) < settings.ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD and not short_notice:
            # A near-empty extraction (e.g. a directory PDF whose format the
            # extractor didn't recognize, or a policy PDF that lost its
            # section structure) previously succeeded silently with a
            # single-digit section count and no error - see the fleet audit
            # that found International-Office-Directory-April-2026.pdf
            # indexed with zero sections. Fail loudly instead, matching the
            # zero-section case above.
            raise ValueError(
                f"Only {len(sections)} section(s) were extracted from this document, below "
                f"the {settings.ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD}-section minimum expected "
                "for a policy, office directory or product document. Extraction likely failed silently - check the "
                "source document's formatting before retrying."
            )

        for section in sections:
            section["expiry_date"] = expiry_date
        _update_job(job_id, status="uploading", progress=35, section_count=len(sections))
        source_uri = _upload_source(
            path,
            filename,
            job_id,
            country=country,
            access_scope=access_scope,
        )
        document_hash = _file_hash(path)
        stable_document_id = _canonical_logical_document_id(
            logical_document_id,
            access_scope=access_scope,
            document_type=document_type,
            country=str(sections[0]["country"]),
            language=str(sections[0]["language"]),
        ) or build_logical_document_id(
            logical_document_id=logical_document_id,
            country=str(sections[0]["country"]),
            language=str(sections[0]["language"]),
            document_type=document_type,
            access_scope=access_scope,
            source_file=str(sections[0]["source_file"]),
        )
        # Persist the canonical key: publish, versions, rollback and delete
        # must all use the same pointer key the worker indexes under, never
        # the raw form value typed at upload.
        _update_job(
            job_id,
            status="indexing",
            progress=55,
            source_uri=source_uri,
            content_hash=document_hash,
            logical_document_id=stable_document_id,
        )
        indexed = _index_sections(
            sections,
            source_uri=source_uri,
            document_type=document_type,
            access_scope=access_scope,
            ingestion_id=job_id,
            logical_document_id=stable_document_id,
            activated_by=accepted_by,
            review_before_publish=review_before_publish,
            sleep=sleep,
            clock=clock,
        )
        if not review_before_publish:
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
                content_hash=document_hash,
                accepted_by=accepted_by,
                logical_document_id=stable_document_id,
                document_owner=document_owner,
                approval_reference=approval_reference,
                effective_date=effective_date,
                expiry_date=expiry_date,
                malware_scan_status="clean" if settings.ADMIN_INGESTION_MALWARE_SCAN_REQUIRED else "not_required",
            )
        _update_job(
            job_id,
            status="ready_for_review" if review_before_publish else "ready",
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


def _upload_source(
    path: Path,
    filename: str,
    job_id: str,
    *,
    country: str,
    access_scope: str,
) -> str:
    bucket = settings.KNOWLEDGE_UPLOAD_BUCKET
    if not bucket:
        return ""
    prefix = settings.KNOWLEDGE_UPLOAD_PREFIX.strip("/")
    scope_path = _storage_scope_path(country=country, access_scope=access_scope)
    key = f"{prefix}/{scope_path}/{job_id}/{filename}"
    get_aws_clients().s3.upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


MAX_SECTIONS_PER_INGESTION = 10_000
# Chunk reads for review, preview and versions never need the 1024-float
# embedding; excluding it keeps a 115-record directory preview ~2 MB lighter.
_SOURCE_WITHOUT_EMBEDDING = {"excludes": ["embedding"]}


def _visibility_timeout() -> float:
    """The configured visibility wait, never below the enforced floor."""
    return float(max(
        settings.ADMIN_INGESTION_VISIBILITY_TIMEOUT_SECONDS,
        settings.ADMIN_INGESTION_VISIBILITY_TIMEOUT_MIN_SECONDS,
    ))


# Global scope is only allowed for the international sponsoring directory
# (_check_document_scope in api/admin_routes.py), whose extractor always emits
# country "GLOBAL" and language "en" regardless of the upload form's fields.
GLOBAL_DOCUMENT_COUNTRY = "GLOBAL"
GLOBAL_DOCUMENT_LANGUAGE = "en"


def _canonical_logical_document_id(
    value: str,
    *,
    access_scope: str,
    document_type: str,
    country: str,
    language: str,
) -> str:
    """Return `value` only if it is already the canonical key of THIS document's namespace.

    Canonical keys look like "<scope>:<COUNTRY>:<language>:<document_type>:<slug>"
    (exactly four colons). Every namespace part must match the upload itself -
    scope, document type, country (GLOBAL for global scope) and language - so
    a typed stable id can only name a slot in the uploader's own market and
    language. Admin RBAC is checked per market, so accepting another market's
    key would let a CA admin retire the live US document. Anything else is
    returned as "" and is slugified into the job's own namespace instead.
    """
    parts = str(value or "").strip().split(":")
    if len(parts) != 5 or not all(parts):
        return ""
    scope = access_scope.lower()
    expected_country = GLOBAL_DOCUMENT_COUNTRY if scope == "global" else country.upper()
    expected = (scope, expected_country, language.lower(), document_type.lower())
    if scope not in ACCESS_SCOPES or tuple(parts[:4]) != expected:
        return ""
    return ":".join(parts)


def _job_logical_document_id(job: dict[str, Any]) -> str:
    """Return the canonical pointer key for an ingestion job row.

    New jobs have the worker's canonical key persisted. Jobs created before
    that (or never processed) still hold the raw stable id typed at upload,
    possibly blank, so rebuild it the same way the worker does. Outside the
    worker there are no extracted sections, so the namespace comes from the
    job row, except for global scope: the only global document type is the
    sponsoring directory, whose extractor always emits GLOBAL/en, so those
    fixed values are used rather than the form's market and language.
    """
    access_scope = str(job.get("access_scope") or "country").lower()
    document_type = str(job.get("document_type") or "policy").lower()
    if access_scope == "global":
        country, language = GLOBAL_DOCUMENT_COUNTRY, GLOBAL_DOCUMENT_LANGUAGE
    else:
        country = str(job.get("country") or "")
        language = str(job.get("language") or "")
    stored = str(job.get("logical_document_id") or "")
    canonical = _canonical_logical_document_id(
        stored,
        access_scope=access_scope,
        document_type=document_type,
        country=country,
        language=language,
    )
    if canonical:
        return canonical
    return build_logical_document_id(
        logical_document_id=stored,
        country=country,
        language=language,
        document_type=document_type,
        access_scope=access_scope,
        source_file=str(job.get("filename") or ""),
    )


def _visible_ids(client: Any, index: str, ingestion_id: str) -> set[str]:
    """Return the _ids currently searchable for a generation (post-refresh)."""
    result = client.search(
        index=index,
        body={
            "size": 10_000,
            "_source": False,
            "query": exact_term_query("ingestion_id", ingestion_id),
        },
    )
    return {hit["_id"] for hit in result.get("hits", {}).get("hits", [])}


def _count_for_ingestion(client: Any, index: str, ingestion_id: str) -> int:
    result = client.count(
        index=index,
        body={"query": exact_term_query("ingestion_id", ingestion_id)},
    )
    return int(result.get("count", 0))


def _delete_ids(client: Any, index: str, ids: Any) -> None:
    """Delete chunks by their server-assigned _id (the only delete VECTORSEARCH supports)."""
    id_list = list(ids)
    if not id_list:
        return
    helpers.bulk(
        client,
        ({"_op_type": "delete", "_index": index, "_id": doc_id} for doc_id in id_list),
        raise_on_error=False,
        raise_on_exception=False,
    )


def _failure_summary(failure: dict[str, Any], position: int) -> dict[str, Any]:
    """Reduce one bulk item failure to loggable fields, never document content.

    Item-level rejections carry a dict error ({"type", "reason"}). A
    request-level failure (e.g. 429 or 5xx on the whole _bulk call) is
    reported by opensearch-py's _process_bulk_chunk_error with the error as
    a plain string, plus the exception object and the document under "data" -
    "data" is deliberately never read here.
    """
    error = failure.get("error")
    if isinstance(error, dict):
        error_type, reason = error.get("type"), error.get("reason")
    else:
        exception = failure.get("exception")
        error_type = type(exception).__name__ if exception is not None else "transport_error"
        reason = error
    return {
        "status": failure.get("status"),
        "type": error_type,
        "reason": str(reason)[:300],
        "index": position,
    }


def _is_non_retryable(failure: dict[str, Any]) -> bool:
    status = failure.get("status")
    return isinstance(status, int) and 400 <= status < 500 and status != 429


def _generation_write_error(failures: list[dict[str, Any]], written_count: int) -> Exception:
    logged = [_failure_summary(failure, position) for position, failure in enumerate(failures[:5])]
    for entry in logged:
        LOGGER.error("generation_write_rejected", **entry)
    first = logged[0]
    message = (
        f"OpenSearch rejected {len(failures)} of {len(failures) + written_count} chunks "
        f"(first: {first['type']}: {first['reason']})."
    )[:1000]
    if all(_is_non_retryable(failure) for failure in failures):
        return ValueError(message)
    return RuntimeError(message)


def _cleanup_written(client: Any, index: str, written: list[str]) -> None:
    try:
        _delete_ids(client, index, written)
    except Exception:  # noqa: BLE001 - cleanup must never mask the original failure
        LOGGER.exception("generation_write_cleanup_failed", written_count=len(written))


def _write_generation(client: Any, actions: list[dict[str, Any]]) -> set[str]:
    """Bulk-index a generation without a custom _id and return the assigned ids.

    VECTORSEARCH rejects index/create with a client-supplied _id, so callers
    must never set action["_id"] before this. On any item or request-level
    failure, every already-written id is deleted (partial generations must
    never be left behind) and an error is raised: ValueError when every
    failure is a non-retryable 4xx (other than 429), RuntimeError otherwise.
    """
    index_name = actions[0].get("_index", "") if actions else ""
    written: list[str] = []
    failures: list[dict[str, Any]] = []
    try:
        for ok, item in helpers.streaming_bulk(
            client,
            actions,
            raise_on_error=False,
            raise_on_exception=False,
        ):
            (_op, info), = item.items()
            if ok:
                written.append(info.get("_id"))
            else:
                failures.append(info)
    except Exception:
        _cleanup_written(client, index_name, written)
        raise
    if not failures:
        return set(written)
    try:
        error = _generation_write_error(failures, len(written))
    finally:
        _cleanup_written(client, index_name, written)
    raise error


def _await_generation(
    client: Any,
    index: str,
    ingestion_id: str,
    own_ids: set[str],
    *,
    timeout_seconds: float | None = None,
    poll_seconds: float = 5.0,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> None:
    """Wait for exactly `own_ids` to become searchable for `ingestion_id`.

    Any visible id not in `own_ids` is a stray from a crashed or timed-out
    earlier write attempt and is deleted along the way. On timeout, this
    attempt's own ids are deleted so nothing partial is left behind, and a
    retryable RuntimeError is raised.
    """
    timeout = _visibility_timeout() if timeout_seconds is None else timeout_seconds
    deadline = clock() + timeout
    while True:
        seen = _visible_ids(client, index, ingestion_id)
        strays = seen - own_ids
        if strays:
            _delete_ids(client, index, strays)
            seen -= strays
        if seen == own_ids and _count_for_ingestion(client, index, ingestion_id) == len(own_ids):
            return
        if clock() >= deadline:
            _delete_ids(client, index, own_ids)
            raise RuntimeError(
                f"Generation {ingestion_id} did not become fully visible within {timeout}s."
            )
        sleep(poll_seconds)


def _delete_generation_chunks(
    client: Any,
    index: str,
    ingestion_id: str,
    *,
    timeout_seconds: float | None = None,
    poll_seconds: float = 5.0,
    refresh_interval_seconds: float = 65.0,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> None:
    """Delete every chunk for a generation without the unsupported delete_by_query.

    VECTORSEARCH has no delete_by_query, so this searches and bulk-deletes by
    _id in a loop. A generation counts as fully removed only once a zero
    count has been observed on two polls at least one refresh interval
    apart - a single zero poll could just be looking at a stale, not-yet-
    refreshed view that still has visible chunks moments away. On timeout,
    this raises so the caller's existing deletion_failed path applies.
    """
    timeout = _visibility_timeout() if timeout_seconds is None else timeout_seconds
    deadline = clock() + timeout
    first_zero_at: float | None = None
    while True:
        ids = _visible_ids(client, index, ingestion_id)
        if ids:
            _delete_ids(client, index, ids)
        count = _count_for_ingestion(client, index, ingestion_id)
        if not ids and count == 0:
            now = clock()
            if first_zero_at is None:
                first_zero_at = now
            elif now - first_zero_at >= refresh_interval_seconds:
                return
        else:
            first_zero_at = None
        if clock() >= deadline:
            raise RuntimeError(
                f"Chunks for {ingestion_id} were not fully removed within {timeout}s."
            )
        sleep(poll_seconds)


def _index_sections(
    sections: list[dict[str, Any]],
    *,
    source_uri: str,
    document_type: str,
    access_scope: str,
    ingestion_id: str,
    logical_document_id: str = "",
    activated_by: str = "",
    review_before_publish: bool = False,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> int:
    if len(sections) > MAX_SECTIONS_PER_INGESTION:
        raise ValueError(
            f"This document produced {len(sections)} sections, above the "
            f"{MAX_SECTIONS_PER_INGESTION:,}-section limit for a single ingestion."
        )
    if review_before_publish and not settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
        raise ValueError("Review before publish requires ADMIN_INGESTION_GENERATION_POINTER_ENABLED.")

    client = _client()
    index = settings.OPENSEARCH_INDEX
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_body())
    source_prefix = source_uri.rsplit("/", 1)[0] if source_uri else ""
    # Chunks are written once as active and never updated in place. Retrieval
    # already gates every read on status=active AND the ingestion_id being in
    # the DB's active-generation pointer set, so an unpublished or
    # not-yet-reviewed generation stays invisible without a "staging" status.
    new_actions = list(
        _actions(
            sections,
            index=index,
            source_uri_prefix=source_prefix,
            status="active",
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

    own_ids = _write_generation(client, new_actions)
    _await_generation(client, index, ingestion_id, own_ids, sleep=sleep, clock=clock)

    if not review_before_publish:
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
        else:
            delete_actions = _older_source_actions(
                client,
                index=index,
                country=str(sections[0]["country"]),
                language=str(sections[0]["language"]),
                source_file=str(sections[0]["source_file"]),
                ingestion_id=ingestion_id,
            )
            if delete_actions:
                helpers.bulk(client, delete_actions, raise_on_error=False, raise_on_exception=False)
    return len(own_ids)


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
            # knowledge_documents is the admin-facing flat list (and what the
            # low-coverage fleet check reads) - without this it never learns
            # a generation was superseded here, so the prior version keeps
            # showing as status='active' (with its now-stale section count)
            # indefinitely alongside the new one, exactly like
            # rollback_document_generation and delete_ingestion_job already
            # retire it in their own paths.
            connection.execute(
                text(
                    """
                    UPDATE knowledge_documents
                    SET status = 'retired', updated_at = now()
                    WHERE document_id = :document_id AND status = 'active'
                    """
                ),
                {"document_id": previous_ingestion_id},
            )
        # A script-loaded generation's registry row is bulk-<sha> while its
        # pointer ingestion_id is a uuid hex, so the document_id match above
        # never retires it. Retire every other still-active row for this
        # logical document too. The new row is named by _record_document
        # with document_id = the ingestion_id being activated here.
        connection.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'retired', updated_at = now()
                WHERE logical_document_id = :logical_document_id
                  AND document_id <> :new_document_id
                  AND status = 'active'
                """
            ),
            {"logical_document_id": logical_document_id, "new_document_id": ingestion_id},
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


def _update_job(job_id: str, **values: Any) -> None:
    allowed = {
        "status",
        "progress",
        "section_count",
        "source_uri",
        "upload_uri",
        "content_hash",
        "error_message",
        "attempt_count",
        "lease_owner",
        "lease_expires_at",
        "completed_at",
        "accepted_by",
        "review_before_publish",
        "malware_scan_status",
        "logical_document_id",
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
                    approval_reference, effective_date, expiry_date, malware_scan_status,
                    status, created_at, updated_at
                ) VALUES (
                    :job_id, :filename, :source_uri, :country, :language,
                    :document_type, :access_scope, :version, :section_count,
                    :content_hash, :accepted_by, :logical_document_id, :document_owner,
                    :approval_reference, NULLIF(:effective_date, '')::date,
                    NULLIF(:expiry_date, '')::date, :malware_scan_status, 'active', now(), now()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    source_uri = EXCLUDED.source_uri,
                    section_count = EXCLUDED.section_count,
                    accepted_by = EXCLUDED.accepted_by,
                    logical_document_id = EXCLUDED.logical_document_id,
                    document_owner = EXCLUDED.document_owner,
                    approval_reference = EXCLUDED.approval_reference,
                    effective_date = EXCLUDED.effective_date,
                    expiry_date = EXCLUDED.expiry_date,
                    malware_scan_status = EXCLUDED.malware_scan_status,
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
                       accepted_by, review_before_publish, logical_document_id, document_owner,
                       approval_reference, effective_date, expiry_date, malware_scan_status,
                       attempt_count, error_message,
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
            "review_before_publish": bool(row.get("review_before_publish", False)),
            "effective_date": row["effective_date"].isoformat() if row.get("effective_date") else "",
            "expiry_date": row["expiry_date"].isoformat() if row.get("expiry_date") else "",
        }
        for row in rows
    ]


def update_ingestion_malware_status(job_id: str, status: str) -> None:
    """Persist the GuardDuty decision without storing object tags or scan details."""
    normalized = status.lower().strip()
    if normalized not in {"pending", "clean", "blocked", "not_required"}:
        raise ValueError("Unsupported malware scan status.")
    _update_job(job_id, malware_scan_status=normalized)


def list_document_generations(job_id: str) -> list[dict[str, Any]]:
    """Return version history for the stable document represented by a job."""
    job = _ingestion_job(job_id)
    logical_document_id = _job_logical_document_id(job)
    if not logical_document_id:
        return []
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT g.ingestion_id, g.status, g.activated_at, g.retired_at, g.activated_by,
                       j.filename, j.document_version, j.section_count, j.effective_date,
                       j.expiry_date, j.malware_scan_status, j.created_at
                FROM knowledge_document_generations g
                LEFT JOIN ingestion_jobs j ON j.job_id = g.ingestion_id
                WHERE g.logical_document_id = :logical_document_id
                  AND g.status <> 'deleted'
                ORDER BY COALESCE(g.activated_at, j.created_at) DESC
                """
            ),
            {"logical_document_id": logical_document_id},
        ).mappings().all()
    date_fields = {"activated_at", "retired_at", "effective_date", "expiry_date", "created_at"}
    return [
        {key: value.isoformat() if key in date_fields and value else value for key, value in dict(row).items()}
        for row in rows
    ]


def rollback_document_generation(job_id: str, target_ingestion_id: str, *, activated_by: str) -> dict[str, Any]:
    """Atomically reactivate a retained, verified generation for one document."""
    if not settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
        raise ValueError("Generation rollback is not enabled.")
    job = _ingestion_job(job_id)
    logical_document_id = _job_logical_document_id(job)
    generations = {str(item["ingestion_id"]): item for item in list_document_generations(job_id)}
    target = generations.get(target_ingestion_id)
    if not target:
        raise ValueError("The selected generation is not available for this document.")
    client = _client()
    available = client.count(
        index=settings.OPENSEARCH_INDEX,
        body={"query": exact_term_query("ingestion_id", target_ingestion_id)},
    )
    available_count = int(available.get("count", 0))
    target_section_count = target.get("section_count")
    # A script-loaded generation has no ingestion_jobs row (LEFT JOIN leaves
    # section_count NULL), so there is no expected count to match exactly -
    # require only that some chunks are actually present.
    if target_section_count is None:
        if available_count <= 0:
            raise ValueError("The selected generation is incomplete in the retrieval index.")
    elif available_count != int(target_section_count) or not available_count:
        raise ValueError("The selected generation is incomplete in the retrieval index.")
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:logical_document_id))"), {"logical_document_id": logical_document_id})
        current = connection.execute(
            text("SELECT active_ingestion_id FROM knowledge_active_generations WHERE logical_document_id = :logical_document_id FOR UPDATE"),
            {"logical_document_id": logical_document_id},
        ).scalar() or ""
        if current == target_ingestion_id:
            raise ValueError("That generation is already active.")
        connection.execute(text("UPDATE knowledge_document_generations SET status = 'retired', retired_at = now() WHERE ingestion_id = :current"), {"current": current})
        connection.execute(text("UPDATE knowledge_document_generations SET status = 'active', activated_at = now(), retired_at = NULL, activated_by = :actor WHERE ingestion_id = :target"), {"target": target_ingestion_id, "actor": activated_by})
        connection.execute(
            text("UPDATE knowledge_active_generations SET previous_ingestion_id = active_ingestion_id, active_ingestion_id = :target, activated_at = now(), activated_by = :actor WHERE logical_document_id = :logical_document_id"),
            {"target": target_ingestion_id, "actor": activated_by, "logical_document_id": logical_document_id},
        )
        connection.execute(text("UPDATE knowledge_documents SET status = CASE WHEN document_id = :target THEN 'active' ELSE 'retired' END, updated_at = now() WHERE logical_document_id = :logical_document_id"), {"target": target_ingestion_id, "logical_document_id": logical_document_id})
    clear_active_generation_cache()
    return {"active_ingestion_id": target_ingestion_id, "previous_ingestion_id": current, "logical_document_id": logical_document_id}


def _deletion_in_progress(job: dict[str, Any]) -> bool:
    """True while another request's chunk sweep may still be running.

    A sweep is bounded by the visibility timeout, so a "deleting" job whose
    last update is older than twice that (plus slack) belongs to a worker
    that died mid-sweep; allow it to be retried instead of sticking forever.
    """
    if job.get("status") != "deleting":
        return False
    try:
        started = datetime.fromisoformat(str(job.get("updated_at") or ""))
    except ValueError:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    stale_after = 2 * _visibility_timeout() + 60
    return (datetime.now(UTC) - started).total_seconds() < stale_after


def begin_ingestion_deletion(job_id: str) -> dict[str, Any]:
    """Remove a document from live retrieval and write its tombstone.

    Fast and synchronous: the publication pointer is removed first, so a
    partially completed cleanup can never leave the document eligible for
    retrieval. The slow chunk sweep and S3 cleanup run afterwards in
    finish_ingestion_deletion. Returns the job row as it was before this call.
    """
    job = _ingestion_job(job_id)
    if job.get("status") == "deleted":
        raise ValueError("This document has already been deleted.")
    if job.get("status") in {"queued", "extracting", "indexing", "retryable"} or _deletion_in_progress(job):
        raise ValueError("Wait until document processing finishes before deleting it.")
    logical_document_id = _job_logical_document_id(job)

    with get_engine().begin() as connection:
        active = connection.execute(
            text(
                """
                SELECT active_ingestion_id
                FROM knowledge_active_generations
                WHERE logical_document_id = :logical_document_id
                FOR UPDATE
                """
            ),
            {"logical_document_id": logical_document_id},
        ).scalar()
        if active == job_id:
            connection.execute(
                text(
                    """
                    DELETE FROM knowledge_active_generations
                    WHERE logical_document_id = :logical_document_id
                    """
                ),
                {"logical_document_id": logical_document_id},
            )
        connection.execute(
            text(
                """
                UPDATE knowledge_document_generations
                SET status = 'deleted', retired_at = COALESCE(retired_at, now())
                WHERE ingestion_id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        connection.execute(
            text(
                """
                UPDATE knowledge_documents
                SET status = 'deleted', updated_at = now()
                WHERE document_id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        connection.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'deleting', progress = 10, error_message = '', updated_at = now()
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        )
    clear_active_generation_cache()
    return job


def finish_ingestion_deletion(
    job: dict[str, Any],
    *,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
    raise_on_failure: bool = True,
) -> None:
    """Sweep the generation's chunks and S3 objects; end in deleted or deletion_failed."""
    job_id = str(job["job_id"])
    try:
        client = _client()
        _delete_generation_chunks(client, settings.OPENSEARCH_INDEX, job_id, sleep=sleep, clock=clock)
        for uri in (str(job.get("source_uri") or ""), str(job.get("upload_uri") or "")):
            parsed = urlparse(uri)
            if parsed.scheme == "s3" and parsed.netloc and parsed.path:
                get_aws_clients().s3.delete_object(
                    Bucket=parsed.netloc,
                    Key=parsed.path.lstrip("/"),
                )
        _update_job(job_id, status="deleted", progress=100, completed_at=datetime.now(UTC))
    except Exception as exc:
        LOGGER.exception("document_delete_cleanup_failed", job_id=job_id)
        _update_job(
            job_id,
            status="deletion_failed",
            progress=100,
            error_message="Document was removed from live retrieval, but storage cleanup needs retry.",
        )
        if raise_on_failure:
            raise RuntimeError("Document cleanup did not complete safely.") from exc
    finally:
        clear_active_generation_cache()


def delete_ingestion_job(
    job_id: str,
    *,
    deleted_by: str,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> dict[str, Any]:
    """Remove a document from live retrieval and its durable source storage, synchronously.

    The admin route instead calls begin_ingestion_deletion and runs
    finish_ingestion_deletion in the background, so the request never waits
    on OpenSearch refresh cycles. The ingestion and audit records remain as a
    tombstone for traceability.
    """
    job = begin_ingestion_deletion(job_id)
    finish_ingestion_deletion(job, sleep=sleep, clock=clock)
    return _ingestion_job(job_id)


def summarize_ingestion_chunks(
    chunks: list[dict[str, Any]],
    total_count: int,
    *,
    max_chunk_chars: int = 8_000,
) -> dict[str, Any]:
    """Return review-safe chunk quality signals without exposing full content."""
    # The API intentionally receives only a preview. Never infer that chunks
    # outside that preview are empty; their content has not been inspected.
    contents = [str(chunk.get("content") or "") for chunk in chunks]
    lengths = [len(content) for content in contents]
    hashes = [
        hashlib.sha256(content.encode("utf-8")).hexdigest()
        for content in contents
        if content.strip()
    ]
    duplicate_count = len(hashes) - len(set(hashes))
    empty_count = sum(not content.strip() for content in contents)
    oversized_count = sum(length > max_chunk_chars for length in lengths)
    warnings: list[str] = []
    if int(total_count) != len(chunks):
        warnings.append(f"Preview shows {len(chunks)} of {total_count} chunks.")
    if empty_count:
        warnings.append(f"{empty_count} chunk(s) contain no readable text.")
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate chunk(s) detected in the preview.")
    if oversized_count:
        warnings.append(f"{oversized_count} chunk(s) exceed the {max_chunk_chars:,}-character review limit.")
    return {
        "chunk_count": int(total_count),
        "preview_count": len(chunks),
        "page_count": len({str(chunk.get("page") or "") for chunk in chunks if chunk.get("page")}),
        "pages": sorted({str(chunk.get("page") or "") for chunk in chunks if chunk.get("page")}),
        "average_chars": round(sum(lengths) / len(lengths)) if lengths else 0,
        "largest_chars": max(lengths, default=0),
        "empty_chunks": empty_count,
        "oversized_chunks": oversized_count,
        "duplicate_chunks": duplicate_count,
        "warnings": warnings,
    }


def _ingestion_job(job_id: str) -> dict[str, Any]:
    jobs = list_ingestion_jobs(200)
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    raise KeyError(job_id)


def _staging_documents(job_id: str, *, limit: int = 20) -> tuple[int, list[dict[str, Any]]]:
    client = _client()
    index = settings.OPENSEARCH_INDEX
    filters = [exact_term_query("ingestion_id", job_id)]
    count = int(client.count(index=index, body={"query": {"bool": {"filter": filters}}}).get("count", 0))
    result = client.search(
        index=index,
        body={
            "size": max(1, min(int(limit), 10_000)),
            "_source": _SOURCE_WITHOUT_EMBEDDING,
            "sort": [
                {"start_page": {"order": "asc", "unmapped_type": "integer"}},
                {"id": {"order": "asc", "unmapped_type": "keyword"}},
            ],
            "query": {"bool": {"filter": filters}},
        },
    )
    documents = []
    for hit in result.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source") or {})
        documents.append({
            "id": hit.get("_id", ""),
            "sectionId": source.get("section_id", ""),
            "title": source.get("section_title") or source.get("title") or "",
            "page": source.get("page") or source.get("start_page") or "",
            "endPage": source.get("end_page") or "",
            "content": source.get("content", ""),
            "sourceFile": source.get("source_file", ""),
            "country": source.get("country", ""),
            "language": source.get("language", ""),
        })
    return count, documents


def preview_ingestion_job(job_id: str, *, limit: int = 20) -> dict[str, Any]:
    job = _ingestion_job(job_id)
    count, all_chunks = _staging_documents(job_id, limit=10000)
    chunks = all_chunks[: max(1, min(int(limit), 100))]
    summary = summarize_ingestion_chunks(all_chunks, count)
    if job.get("status") != "ready_for_review":
        return {"job": job, "summary": summary, "chunks": chunks, "can_publish": False}
    return {
        "job": job,
        "summary": summary,
        "chunks": chunks,
        "can_publish": count == int(job.get("section_count") or 0) and count > 0,
    }


def test_ingestion_job(job_id: str, message: str, *, limit: int = 5) -> dict[str, Any]:
    job = _ingestion_job(job_id)
    if job.get("status") != "ready_for_review":
        raise ValueError("This document is not ready for staging review.")
    client = _client()
    filters = [exact_term_query("ingestion_id", job_id)]
    result = client.search(
        index=settings.OPENSEARCH_INDEX,
        body={
            "size": max(1, min(int(limit), 10)),
            "_source": _SOURCE_WITHOUT_EMBEDDING,
            "query": {"bool": {"filter": filters, "must": [{"query_string": {
                "query": message,
                "fields": ["content", "search_text", "section_title"],
            }}]}},
        },
    )
    matches = []
    for hit in result.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source") or {})
        matches.append({
            "score": hit.get("_score", 0),
            "sectionId": source.get("section_id", ""),
            "title": source.get("section_title") or source.get("title") or "",
            "page": source.get("page") or source.get("start_page") or "",
            "excerpt": str(source.get("content") or "")[:1200],
        })
    return {"job": job, "message": message, "matches": matches, "matchCount": len(matches)}


def publish_ingestion_job(job_id: str, *, accepted_by: str) -> dict[str, Any]:
    job = _ingestion_job(job_id)
    if job.get("status") != "ready_for_review":
        raise ValueError("Only documents marked ready for review can be published.")
    count, documents = _staging_documents(job_id, limit=10000)
    expected = int(job.get("section_count") or 0)
    if count != expected or not documents:
        raise ValueError(f"Staged publication verification failed: expected {expected}, found {count}.")
    first = documents[0]
    logical_document_id = _job_logical_document_id(job)
    # Review mode is only reachable with the pointer flag on (enforced at
    # upload and again in _index_sections), so publication is always a
    # pointer switch - there is no OpenSearch activation step any more.
    _activate_generation_pointer(
        logical_document_id=logical_document_id,
        ingestion_id=job_id,
        country=str(job.get("country") or first.get("country") or ""),
        language=str(job.get("language") or first.get("language") or ""),
        source_file=str(first.get("sourceFile") or job.get("filename") or ""),
        document_type=str(job.get("document_type") or "policy"),
        access_scope=str(job.get("access_scope") or "country"),
        activated_by=accepted_by,
    )
    _record_document(
        job_id=job_id,
        filename=str(job.get("filename") or "document"),
        source_uri=str(job.get("source_uri") or ""),
        country=str(job.get("country") or ""),
        language=str(job.get("language") or ""),
        document_type=str(job.get("document_type") or "policy"),
        access_scope=str(job.get("access_scope") or "country"),
        version=str(job.get("document_version") or ""),
        section_count=count,
        content_hash=str(job.get("content_hash") or ""),
        accepted_by=accepted_by,
        logical_document_id=logical_document_id,
        document_owner=str(job.get("document_owner") or ""),
        approval_reference=str(job.get("approval_reference") or ""),
        effective_date=str(job.get("effective_date") or ""),
        expiry_date=str(job.get("expiry_date") or ""),
        malware_scan_status=str(job.get("malware_scan_status") or "not_required"),
    )
    _update_job(job_id, status="ready", accepted_by=accepted_by, review_before_publish=False)
    clear_active_generation_cache()
    return {"job": _ingestion_job(job_id), "publishedCount": count}
