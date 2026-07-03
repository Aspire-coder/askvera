"""Legal document loading from S3 with process-level memory caching."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from services.aws_clients import get_aws_clients
from utils.exceptions import ConfigurationError
from utils.logging import get_logger

LOGGER = get_logger("services.legal_service")

LEGAL_DOCUMENTS = [
    {
        "id": "privacy",
        "title": "Privacy Notice",
        "file": "Privacy Notice.html",
        "required": True,
    },
    {
        "id": "privacy-addendum",
        "title": "Privacy Addendum",
        "file": "Privacy-Addendum.html",
        "required": True,
    },
    {
        "id": "arbitration",
        "title": "FLP Individual Arbitration and Class Action Waiver Agreement",
        "file": "FLP Individual Arbitration and Class Action Waiver Agreement.html",
        "required": True,
    },
]


def legal_document_key(filename: str) -> str:
    """Build the S3 object key for a legal HTML document."""
    prefix = settings.LEGAL_PREFIX.strip("/")
    version = settings.LEGAL_VERSION.strip("/")
    return f"{prefix}/{version}/html/{filename}"


def _read_s3_text(bucket: str, key: str, title: str, filename: str) -> str:
    """Read one legal document from S3 as UTF-8 HTML."""
    try:
        response = get_aws_clients().s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        html = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    except (BotoCoreError, ClientError, KeyError, UnicodeDecodeError) as exc:
        LOGGER.error("legal_document_missing", document_title=title, filename=filename, bucket=bucket, key=key)
        raise ConfigurationError(f"{key} missing from S3 bucket {bucket}.") from exc

    if not html.strip():
        LOGGER.error("legal_document_empty", document_title=title, filename=filename, bucket=bucket, key=key)
        raise ConfigurationError(f"{key} is empty in S3 bucket {bucket}.")
    return html


@lru_cache(maxsize=1)
def load_legal_documents() -> dict[str, Any]:
    """Load all required legal documents from S3 once per process."""
    LOGGER.info(
        "legal_documents_loading",
        bucket=settings.LEGAL_BUCKET,
        prefix=settings.LEGAL_PREFIX,
        version=settings.LEGAL_VERSION,
    )
    documents: list[dict[str, Any]] = []
    for document in LEGAL_DOCUMENTS:
        key = legal_document_key(document["file"])
        html = _read_s3_text(settings.LEGAL_BUCKET, key, document["title"], document["file"])
        LOGGER.info(
            "legal_document_loaded",
            document_id=document["id"],
            document_title=document["title"],
            filename=document["file"],
            key=key,
        )
        documents.append(
            {
                "id": document["id"],
                "title": document["title"],
                "required": document["required"],
                "html": html,
            }
        )

    LOGGER.info("legal_documents_loaded_successfully", document_count=len(documents), version=settings.LEGAL_VERSION)
    return {"version": settings.LEGAL_VERSION, "documents": documents}


def get_legal_documents() -> dict[str, Any]:
    """Return cached legal documents for API responses."""
    return load_legal_documents()
