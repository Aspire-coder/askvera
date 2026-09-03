"""General-purpose approved-document ingestion for the admin portal."""

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
from scripts.ingestion.extract_global_office_directory import extract_directory as extract_office_directory
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
    if status in {"ready", "ready_for_review", "completed"}:
        return "completed"
    if status in {"failed_terminal", "dead_lettered", "cancelled"}:
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
) -> list[dict[str, Any]]:
    """Extract office_directory PDFs with the same specialized parsers that
    produced the directory content already in the index, instead of the
    generic chunker.

    The generic build_sections() path never sets record_country,
    directory_fields, directory_kind, or directory_section - metadata that
    country-scoping, contact-field restoration, and answer validation all
    depend on - so an office_directory PDF ingested through it "succeeds"
    (nonzero sections, generation activates) while silently losing all of
    that. Both known directory formats (the country-sponsoring directory and
    the office/staff contact directory) are tried in turn; a PDF matching
    neither raises rather than falling back to the generic path and
    reproducing that silent metadata loss.
    """
    try:
        sponsoring_records = extract_sponsoring_directory(path)
    except ValueError:
        sponsoring_records = []
    if sponsoring_records:
        return [
            {**record.to_row(), "document_version": version, "effective_date": effective_date}
            for record in sponsoring_records
        ]

    office_records, staff_records = extract_office_directory(path)
    directory_records = [*office_records, *staff_records]
    if directory_records:
        return [
            {**record.to_row(), "document_version": version, "effective_date": effective_date}
            for record in directory_records
        ]

    raise ValueError(
        "This document does not match a known office directory format "
        "(country sponsoring directory or office/staff contact directory)."
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
        use_directory_extractor = document_type == "office_directory" and path.suffix.lower() == ".pdf"
        if path.suffix.lower() == ".pdf" and settings.ADMIN_DOCUMENT_PREFLIGHT_ENABLED:
            preflight = analyze_pdf_with_timeout(
                path,
                timeout_seconds=settings.ADMIN_INGESTION_PARSER_TIMEOUT_SECONDS,
                max_pages=settings.ADMIN_INGESTION_MAX_PDF_PAGES,
                max_extracted_characters=settings.ADMIN_INGESTION_MAX_EXTRACTED_TEXT_CHARS,
            )
            if preflight.requires_ocr:
                if not settings.ADMIN_TEXTRACT_OCR_ENABLED or not upload_uri:
                    raise ValueError(
                        "This PDF appears to be scanned or image-only and requires OCR before publication."
                    )
                pages = _extract_pages_with_textract(upload_uri)
                use_policy_extractor = False
                use_directory_extractor = False
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
        elif use_directory_extractor:
            sections = _extract_directory_sections(path, version=version, effective_date=effective_date)
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
        if len(sections) < settings.ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD:
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
                "for a policy or office directory. Extraction likely failed silently - check the "
                "source document's formatting before retrying."
            )

        _update_job(job_id, status="uploading", progress=35, section_count=len(sections))
        source_uri = _upload_source(
            path,
            filename,
            job_id,
            country=country,
            access_scope=access_scope,
        )
        document_hash = _file_hash(path)
        _update_job(job_id, status="indexing", progress=55, source_uri=source_uri, content_hash=document_hash)
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
            review_before_publish=review_before_publish,
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
) -> int:
    client = _client()
    index = settings.OPENSEARCH_INDEX
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=_index_body())
    source_prefix = source_uri.rsplit("/", 1)[0] if source_uri else ""
    # Every generation starts invisible. Activation happens only after the
    # complete bulk write has been verified.
    publish_status = "staging"
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
    for action in new_actions:
        action["_id"] = action["_source"]["id"]
    success, errors = helpers.bulk(
        client,
        new_actions,
        raise_on_error=False,
    )
    if errors:
        try:
            client.delete_by_query(
                index=index,
                body={"query": exact_term_query("ingestion_id", ingestion_id)},
                conflicts="proceed",
                refresh=True,
            )
        except Exception:
            LOGGER.exception("partial_staged_generation_cleanup_failed", ingestion_id=ingestion_id)
        raise RuntimeError(f"OpenSearch rejected {len(errors)} chunks.")
    if not review_before_publish:
        _activate_staged_sections(
            client,
            index=index,
            actions=new_actions,
            expected_count=len(sections),
            ingestion_id=ingestion_id,
        )
    if settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED and not review_before_publish:
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
    if not settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED and not review_before_publish:
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
                        exact_term_query("ingestion_id", ingestion_id),
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
        "content_hash",
        "error_message",
        "attempt_count",
        "lease_owner",
        "lease_expires_at",
        "completed_at",
        "accepted_by",
        "review_before_publish",
        "malware_scan_status",
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
    logical_document_id = str(job.get("logical_document_id") or "")
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
                JOIN ingestion_jobs j ON j.job_id = g.ingestion_id
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
    logical_document_id = str(job.get("logical_document_id") or "")
    generations = {str(item["ingestion_id"]): item for item in list_document_generations(job_id)}
    target = generations.get(target_ingestion_id)
    if not target:
        raise ValueError("The selected generation is not available for this document.")
    client = _client()
    available = client.count(
        index=settings.OPENSEARCH_INDEX,
        body={"query": exact_term_query("ingestion_id", target_ingestion_id)},
    )
    if int(available.get("count", 0)) != int(target.get("section_count") or 0) or not int(available.get("count", 0)):
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


def delete_ingestion_job(job_id: str, *, deleted_by: str) -> dict[str, Any]:
    """Remove a document from live retrieval and its durable source storage.

    The publication pointer is removed first so a partially completed cleanup
    can never leave the document eligible for retrieval. OpenSearch chunks and
    S3 objects are then deleted, while the ingestion and audit records remain
    as a tombstone for traceability.
    """
    job = _ingestion_job(job_id)
    if job.get("status") == "deleted":
        raise ValueError("This document has already been deleted.")
    if job.get("status") in {"queued", "extracting", "indexing", "retryable"}:
        raise ValueError("Wait until document processing finishes before deleting it.")

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
            {"logical_document_id": str(job.get("logical_document_id") or "")},
        ).scalar()
        if active == job_id:
            connection.execute(
                text(
                    """
                    DELETE FROM knowledge_active_generations
                    WHERE logical_document_id = :logical_document_id
                    """
                ),
                {"logical_document_id": str(job.get("logical_document_id") or "")},
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

    try:
        client = _client()
        client.delete_by_query(
            index=settings.OPENSEARCH_INDEX,
            body={"query": exact_term_query("ingestion_id", job_id)},
            conflicts="proceed",
            refresh=True,
            wait_for_completion=True,
        )
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
        raise RuntimeError("Document cleanup did not complete safely.") from exc
    finally:
        clear_active_generation_cache()

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
    filters = [
        exact_term_query("ingestion_id", job_id),
        {"term": {"status": "staging"}},
    ]
    count = int(client.count(index=index, body={"query": {"bool": {"filter": filters}}}).get("count", 0))
    result = client.search(
        index=index,
        body={
            "size": max(1, min(int(limit), 10_000)),
            "sort": [
                {"start_page": {"order": "asc", "unmapped_type": "integer"}},
                {"_id": {"order": "asc"}},
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
    filters = [exact_term_query("ingestion_id", job_id), {"term": {"status": "staging"}}]
    result = client.search(
        index=settings.OPENSEARCH_INDEX,
        body={
            "size": max(1, min(int(limit), 10)),
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
    client = _client()
    actions = [{"_id": document["id"]} for document in documents]
    _activate_staged_sections(
        client,
        index=settings.OPENSEARCH_INDEX,
        actions=actions,
        expected_count=expected,
        ingestion_id=job_id,
    )
    first = documents[0]
    logical_document_id = str(job.get("logical_document_id") or build_logical_document_id(
        logical_document_id="",
        country=str(first.get("country") or job.get("country") or ""),
        language=str(first.get("language") or job.get("language") or ""),
        document_type=str(job.get("document_type") or "policy"),
        access_scope=str(job.get("access_scope") or "country"),
        source_file=str(first.get("sourceFile") or job.get("filename") or ""),
    ))
    if settings.ADMIN_INGESTION_GENERATION_POINTER_ENABLED:
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
    else:
        delete_actions = _older_source_actions(
            client,
            index=settings.OPENSEARCH_INDEX,
            country=str(job.get("country") or first.get("country") or ""),
            language=str(job.get("language") or first.get("language") or ""),
            source_file=str(first.get("sourceFile") or job.get("filename") or ""),
            ingestion_id=job_id,
        )
        if delete_actions:
            helpers.bulk(client, delete_actions, raise_on_error=False, raise_on_exception=False)
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
