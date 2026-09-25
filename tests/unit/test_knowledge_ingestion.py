"""Tests for country-independent approved-document ingestion."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from opensearchpy.exceptions import TransportError

from app.retrieval import opensearch_sections
from scripts.ingestion.extract_global_sponsoring_directory import SponsoringRecord
from scripts.ingestion.extract_policy_sections import PolicySection
from services import knowledge_generations, knowledge_ingestion
from services.knowledge_ingestion import (
    MAX_CHUNK_CHARS,
    MAX_SECTIONS_PER_INGESTION,
    ExtractedPage,
    _await_generation,
    _delete_generation_chunks,
    _extract_pages_with_textract,
    _index_sections,
    _write_generation,
    build_sections,
    claim_ingestion_job,
    create_ingestion_job,
    delete_ingestion_job,
    detect_upload_format,
    enqueue_ingestion_job,
    extract_pages,
    list_document_generations,
    preview_ingestion_job,
    process_ingestion_job,
    publish_ingestion_job,
    release_ingestion_claim,
    rollback_document_generation,
    safe_filename,
    stage_ingestion_upload,
    validate_upload,
)
from tests.fakes.fake_aoss import FakeAOSSVector
from tests.fakes.fake_ingestion_db import FakeIngestionDB


def _make_sections(count, *, country="CA", language="en", source_file="policy.pdf"):
    return [
        {
            "country": country,
            "language": language,
            "source_file": source_file,
            "section_id": f"s{i:04d}",
            "title": f"Section {i}",
            "start_page": (i // 20) + 1,
            "end_page": (i // 20) + 1,
            "content": f"Content {i}",
            "document_version": "",
            "effective_date": "",
            "status": "active",
            "chunk_type": "document_section",
            "parent_section_id": "",
            "metadata": {},
        }
        for i in range(count)
    ]


class _StepClock:
    """A fake monotonic clock that advances by `step` seconds each call."""

    def __init__(self, step: float = 5.0) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    """Never call Bedrock: the loader's _document embeds every chunk."""
    from scripts.ingestion import load_policy_sections_to_opensearch as loader
    from services import embeddings

    monkeypatch.setattr(loader, "embed_text", lambda _text: [0.0, 0.0, 0.0, 0.0])

    def _no_aws():
        raise AssertionError("tests must not create AWS clients for embeddings")

    monkeypatch.setattr(embeddings, "get_aws_clients", _no_aws)


LIVE_DIRECTORY_ID = "global:GLOBAL:en:office_directory:international-sponsoring-directory"
SCRIPT_GENERATION_ID = "808b466afd484e6890812fe6f4461f4e"
DIRECTORY_FILENAME = "International-Sponsoring-Directory.pdf"


def _directory_sections(count, source_file=DIRECTORY_FILENAME):
    # The sponsoring-directory extractor always emits country GLOBAL.
    return _make_sections(count, country="GLOBAL", source_file=source_file)


def _wire_directory_fakes(monkeypatch):
    """Fakes plus the live script-loaded directory the owner has today."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(knowledge_generations, "get_engine", lambda: db)
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True)
    monkeypatch.setattr(knowledge_ingestion.settings, "KNOWLEDGE_UPLOAD_BUCKET", "")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_DOCUMENT_PREFLIGHT_ENABLED", False)
    knowledge_generations.clear_active_generation_cache()
    _write_generation(
        aoss,
        knowledge_ingestion._actions(
            _directory_sections(115),
            index=knowledge_ingestion.settings.OPENSEARCH_INDEX,
            source_uri_prefix="s3://kb/approved/Global_en/directories",
            status="active",
            ingestion_id=SCRIPT_GENERATION_ID,
            document_type="office_directory",
            access_scope="global",
        ),
    )
    aoss.tick()
    db.active_generations[LIVE_DIRECTORY_ID] = {
        "logical_document_id": LIVE_DIRECTORY_ID, "country": "GLOBAL", "language": "en",
        "source_file": DIRECTORY_FILENAME, "document_type": "office_directory", "access_scope": "global",
        "previous_ingestion_id": "", "active_ingestion_id": SCRIPT_GENERATION_ID, "activated_by": "backfill",
    }
    db.document_generations[SCRIPT_GENERATION_ID] = {
        "ingestion_id": SCRIPT_GENERATION_ID, "logical_document_id": LIVE_DIRECTORY_ID, "country": "GLOBAL",
        "language": "en", "source_file": DIRECTORY_FILENAME, "document_type": "office_directory",
        "access_scope": "global", "status": "active", "activated_at": None, "retired_at": None,
        "activated_by": "backfill",
    }
    db.documents["bulk-3f9a1c"] = {
        "document_id": "bulk-3f9a1c", "logical_document_id": LIVE_DIRECTORY_ID, "status": "active",
    }
    return aoss, db


def _upload_through_worker(
    monkeypatch, tmp_path, aoss, *, job_id, stable_id, filename, review=True, form_language="en",
):
    """What the portal does: create_ingestion_job with the raw form value, then the worker."""
    safe_name = safe_filename(filename)
    create_ingestion_job(
        job_id=job_id,
        filename=safe_name,
        country="US",  # the upload form's market, which the worker does not key on
        language=form_language,  # likewise: the directory extractor always emits "en"
        document_type="office_directory",
        access_scope="global",
        version="2026-09",
        logical_document_id=stable_id.strip(),
        review_before_publish=review,
    )
    monkeypatch.setattr(knowledge_ingestion, "extract_pages", lambda *_a, **_k: [ExtractedPage(1, "directory")])
    monkeypatch.setattr(
        knowledge_ingestion,
        "_extract_directory_sections",
        lambda *_a, **_k: _directory_sections(115, source_file=safe_name),
    )
    upload_dir = tmp_path / job_id
    upload_dir.mkdir()
    local_path = upload_dir / safe_name
    local_path.write_bytes(b"%PDF-1.4 fake")
    assert process_ingestion_job(
        job_id,
        str(local_path),
        filename=safe_name,
        country="US",
        language=form_language,
        document_type="office_directory",
        access_scope="global",
        version="2026-09",
        effective_date="",
        accepted_by="owner@example.invalid",
        logical_document_id=stable_id.strip(),
        review_before_publish=review,
        sleep=lambda _s: aoss.tick(),
        clock=_StepClock(),
    )


def _retrievable_global(aoss):
    knowledge_generations.clear_active_generation_cache()
    active = knowledge_generations.active_generation_ids(countries=set(), languages=set(), access_scope="global")
    counts = {}
    for doc in aoss.docs.values():
        if doc["status"] == "active" and doc["ingestion_id"] in active:
            counts[doc["ingestion_id"]] = counts.get(doc["ingestion_id"], 0) + 1
    return counts


def test_safe_filename_removes_paths_and_unsafe_characters() -> None:
    assert safe_filename("../../Benelux product facts (final).PDF") == "Benelux-product-facts-final.pdf"


def test_validate_upload_rejects_unknown_type_and_empty_file() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload("payload.exe", 20)
    with pytest.raises(ValueError, match="empty"):
        validate_upload("guide.pdf", 0)


def test_detect_upload_format_accepts_text_families_and_rejects_binary_payload() -> None:
    for filename in ("guide.txt", "guide.md", "guide.csv", "guide.html"):
        result = detect_upload_format(filename, b"Approved content\n")
        assert result["detectedType"] == "text"
    with pytest.raises(ValueError, match="verified safely"):
        detect_upload_format("payload.txt", b"MZ\x00\x01")


def test_plain_text_extraction_and_generic_section_chunking(tmp_path: Path) -> None:
    source = tmp_path / "product.md"
    source.write_text("PRODUCT BENEFITS\nAloe Vera Gel supports everyday wellness.\n\nUSAGE\nTake 30 ml daily.", encoding="utf-8")

    sections = build_sections(
        extract_pages(source),
        filename=source.name,
        country="BE",
        language="en",
        document_type="product_information",
        version="2026.1",
    )

    assert len(sections) == 2
    assert sections[0]["title"] == "PRODUCT BENEFITS"
    assert sections[0]["metadata"]["document_type"] == "product_information"
    assert sections[1]["content"] == "Take 30 ml daily."


def test_long_sections_have_bounded_overlapping_chunks() -> None:
    content = "PRODUCT DETAILS\n" + "Useful product information. " * 500
    sections = build_sections(
        [ExtractedPage(3, content)],
        filename="facts.txt",
        country="GLOBAL",
        language="en",
        document_type="product_information",
    )

    assert len(sections) > 1
    assert all(len(section["content"]) <= MAX_CHUNK_CHARS for section in sections)
    assert all(section["start_page"] == 3 for section in sections)


def test_current_generic_chunk_profile_remains_the_default() -> None:
    sections = build_sections(
        [ExtractedPage(1, "OVERVIEW\nApproved information.")],
        filename="facts.txt",
        country="CA",
        language="en",
        document_type="product_information",
    )

    assert sections[0]["metadata"]["chunk_profile"] == "current"


def test_policy_pdf_uses_policy_aware_extractor(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "policy.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    policy_section = PolicySection(
        source_file=source.name,
        country="CA",
        language="fr",
        section_id="4.01",
        title="Qualification",
        start_page=8,
        end_page=9,
        content="4.01 Approved qualification requirements.",
    )
    indexed_sections: list[dict[str, object]] = []
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_DOCUMENT_PREFLIGHT_ENABLED",
        False,
    )
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_CHUNK_PROFILE",
        "current",
    )
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD", 1)
    monkeypatch.setattr(
        knowledge_ingestion,
        "extract_pages",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "extract_policy_sections",
        lambda *_args, **_kwargs: [policy_section],
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "build_sections",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic chunking must not handle native policy PDFs")
        ),
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "_index_sections",
        lambda sections, **_kwargs: indexed_sections.extend(sections) or len(sections),
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "_upload_source",
        lambda *_args, **_kwargs: "s3://approved/policy.pdf",
    )
    monkeypatch.setattr(knowledge_ingestion, "_record_document", lambda **_kwargs: None)
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    assert process_ingestion_job(
        "generation-1",
        str(source),
        filename=source.name,
        country="CA",
        language="fr",
        document_type="policy",
        access_scope="country",
        version="2026.1",
        effective_date="2026-07-01",
    ) is True
    assert indexed_sections[0]["section_id"] == "4.01"
    assert indexed_sections[0]["content"] == policy_section.content


def _office_directory_common_mocks(monkeypatch, indexed_sections: list[dict[str, object]]) -> None:
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_DOCUMENT_PREFLIGHT_ENABLED", False)
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_CHUNK_PROFILE", "current")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD", 1)
    monkeypatch.setattr(knowledge_ingestion, "extract_pages", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        knowledge_ingestion,
        "build_sections",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic chunking must not handle office_directory PDFs")
        ),
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "_index_sections",
        lambda sections, **_kwargs: indexed_sections.extend(sections) or len(sections),
    )
    monkeypatch.setattr(
        knowledge_ingestion,
        "_upload_source",
        lambda *_args, **_kwargs: "s3://approved/global/directory.pdf",
    )
    monkeypatch.setattr(knowledge_ingestion, "_record_document", lambda **_kwargs: None)
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)


def test_office_directory_pdf_uses_sponsoring_extractor_when_it_matches(monkeypatch, tmp_path: Path) -> None:
    """A country-sponsoring-directory-shaped PDF must keep record_country and
    directory_kind metadata, not lose it to the generic chunker."""
    source = tmp_path / "International-Sponsoring-Directory.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    record = SponsoringRecord(
        source_file=source.name,
        section_id="sponsoring-037-kyrgyzstan",
        title="Forever Kyrgyzstan",
        start_page=40,
        end_page=41,
        content="Welcome to Forever Kyrgyzstan!",
        record_country="Kyrgyzstan",
    )
    indexed_sections: list[dict[str, object]] = []
    _office_directory_common_mocks(monkeypatch, indexed_sections)
    monkeypatch.setattr(
        knowledge_ingestion,
        "extract_sponsoring_directory",
        lambda *_args, **_kwargs: [record],
    )

    assert process_ingestion_job(
        "generation-1",
        str(source),
        filename=source.name,
        country="GLOBAL",
        language="en",
        document_type="office_directory",
        access_scope="global",
        version="2026.1",
        effective_date="2026-07-01",
    ) is True
    assert indexed_sections[0]["section_id"] == "sponsoring-037-kyrgyzstan"
    assert indexed_sections[0]["metadata"]["record_country"] == "Kyrgyzstan"
    assert indexed_sections[0]["metadata"]["directory_kind"] == "international_sponsoring"


def test_office_directory_pdf_is_rejected_before_publication(monkeypatch, tmp_path: Path) -> None:
    """Retired directory content must not reach storage or indexing."""
    source = tmp_path / "International-Office-Directory.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    indexed_sections: list[dict[str, object]] = []
    _office_directory_common_mocks(monkeypatch, indexed_sections)
    monkeypatch.setattr(
        knowledge_ingestion,
        "extract_sponsoring_directory",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("No country sponsoring sections were found in the PDF.")),
    )

    def unexpected_publication(*_args, **_kwargs):
        pytest.fail("Rejected directory must not reach publication")

    monkeypatch.setattr(knowledge_ingestion, "_upload_source", unexpected_publication)
    monkeypatch.setattr(knowledge_ingestion, "_index_sections", unexpected_publication)
    monkeypatch.setattr(knowledge_ingestion, "_record_document", unexpected_publication)
    releases = []
    monkeypatch.setattr(
        knowledge_ingestion, "release_ingestion_claim",
        lambda job_id, message, **kwargs: releases.append({"message": message, **kwargs}),
    )

    assert process_ingestion_job(
        "generation-2",
        str(source),
        filename=source.name,
        country="GLOBAL",
        language="en",
        document_type="office_directory",
        access_scope="global",
        version="2026.1",
        effective_date="2026-07-01",
    ) is False
    assert not indexed_sections
    assert "Only the international sponsoring directory" in releases[0]["message"]
    assert releases[0]["retryable"] is False


def test_office_directory_pdf_raises_instead_of_silently_using_generic_chunker(monkeypatch, tmp_path: Path) -> None:
    """A document matching neither known directory format must fail loudly,
    not silently fall through to the generic chunker and lose all
    directory-specific metadata with no error."""
    source = tmp_path / "unrecognized-directory.pdf"
    source.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_DOCUMENT_PREFLIGHT_ENABLED", False)
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_CHUNK_PROFILE", "current")
    monkeypatch.setattr(knowledge_ingestion, "extract_pages", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        knowledge_ingestion,
        "extract_sponsoring_directory",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("No country sponsoring sections were found in the PDF.")),
    )
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)
    releases: list[dict[str, object]] = []
    monkeypatch.setattr(
        knowledge_ingestion,
        "release_ingestion_claim",
        lambda job_id, message, **kwargs: releases.append({"job_id": job_id, "message": message, **kwargs}),
    )

    result = process_ingestion_job(
        "generation-3",
        str(source),
        filename=source.name,
        country="GLOBAL",
        language="en",
        document_type="office_directory",
        access_scope="global",
        version="2026.1",
        effective_date="2026-07-01",
    )

    assert result is False
    assert releases
    assert "Only the international sponsoring directory" in releases[0]["message"]
    assert releases[0]["retryable"] is False


def test_process_ingestion_job_rejects_suspiciously_low_section_count(monkeypatch, tmp_path: Path) -> None:
    """A near-empty extraction (a handful of sections instead of the dozens
    or hundreds a real policy/directory document produces) must fail loudly
    at upload time instead of completing silently - this is the same class
    of bug that let International-Office-Directory-April-2026.pdf sit
    active in production with zero indexed sections for months with no
    error raised anywhere."""
    source = tmp_path / "sparse.md"
    source.write_text("content", encoding="utf-8")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD", 2)
    monkeypatch.setattr(knowledge_ingestion, "build_sections", lambda *_args, **_kwargs: [{"dummy": "one-section"}])
    releases: list[dict[str, object]] = []
    monkeypatch.setattr(
        knowledge_ingestion,
        "release_ingestion_claim",
        lambda job_id, message, **kwargs: releases.append({"job_id": job_id, "message": message, **kwargs}),
    )
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    result = process_ingestion_job(
        "generation-sparse",
        str(source),
        filename=source.name,
        country="US",
        language="en",
        document_type="product_information",
        access_scope="country",
        version="2026.1",
        effective_date="2026-07-01",
    )

    assert result is False
    assert releases
    assert "below the 2-section minimum" in releases[0]["message"]
    assert releases[0]["retryable"] is False


def test_process_ingestion_job_accepts_section_count_at_the_threshold(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "product.md"
    source.write_text(
        "PRODUCT BENEFITS\nAloe Vera Gel supports everyday wellness.\n\nUSAGE\nTake 30 ml daily.",
        encoding="utf-8",
    )
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_LOW_COVERAGE_THRESHOLD", 2)
    monkeypatch.setattr(knowledge_ingestion, "_index_sections", lambda sections, **_kwargs: len(sections))
    monkeypatch.setattr(knowledge_ingestion, "_upload_source", lambda *_args, **_kwargs: "s3://approved/product.md")
    monkeypatch.setattr(knowledge_ingestion, "_record_document", lambda **_kwargs: None)
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    assert process_ingestion_job(
        "generation-ok",
        str(source),
        filename=source.name,
        country="BE",
        language="en",
        document_type="product_information",
        access_scope="country",
        version="2026.1",
        effective_date="2026-07-01",
    ) is True


def test_release_claim_marks_exhausted_retry_as_terminal(monkeypatch) -> None:
    connection = MagicMock()
    connection.execute.side_effect = [
        MagicMock(scalar=lambda: 5),
        MagicMock(),
    ]
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    transaction.__exit__.return_value = False
    engine = MagicMock()
    engine.begin.return_value = transaction
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: engine)
    monkeypatch.setattr(
        knowledge_ingestion.settings,
        "ADMIN_INGESTION_MAX_ATTEMPTS",
        5,
    )

    status = release_ingestion_claim("job-1", "temporary failure", retryable=True)

    assert status == "failed_terminal"
    assert connection.execute.call_args_list[1].args[1]["terminal"] is True


def test_durable_upload_uses_private_encrypted_s3_object(monkeypatch) -> None:
    s3 = MagicMock()
    monkeypatch.setattr(knowledge_ingestion, "get_aws_clients", lambda: SimpleNamespace(s3=s3))
    monkeypatch.setattr(knowledge_ingestion.settings, "KNOWLEDGE_UPLOAD_BUCKET", "knowledge-bucket")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_QUARANTINE_PREFIX", "quarantine")
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    uri = stage_ingestion_upload(
        "job-1",
        "policy.pdf",
        b"approved",
        country="CA",
        access_scope="country",
    )

    assert uri == "s3://knowledge-bucket/quarantine/countries/CA/job-1/policy.pdf"
    assert s3.put_object.call_args.kwargs["ServerSideEncryption"] == "AES256"


def test_global_upload_uses_global_quarantine_folder(monkeypatch) -> None:
    s3 = MagicMock()
    monkeypatch.setattr(knowledge_ingestion, "get_aws_clients", lambda: SimpleNamespace(s3=s3))
    monkeypatch.setattr(knowledge_ingestion.settings, "KNOWLEDGE_UPLOAD_BUCKET", "knowledge-bucket")
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_QUARANTINE_PREFIX", "quarantine")
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    uri = stage_ingestion_upload(
        "job-2",
        "directory.pdf",
        b"approved",
        country="US",
        access_scope="global",
    )

    assert uri == "s3://knowledge-bucket/quarantine/global/job-2/directory.pdf"
    assert s3.put_object.call_args.kwargs["Metadata"] == {
        "job-id": "job-2",
        "access-scope": "global",
        "country": "US",
    }


def test_final_source_upload_uses_country_folder(monkeypatch, tmp_path: Path) -> None:
    s3 = MagicMock()
    monkeypatch.setattr(knowledge_ingestion, "get_aws_clients", lambda: SimpleNamespace(s3=s3))
    monkeypatch.setattr(knowledge_ingestion.settings, "KNOWLEDGE_UPLOAD_BUCKET", "knowledge-bucket")
    source = tmp_path / "policy.pdf"
    source.write_bytes(b"approved")

    uri = knowledge_ingestion._upload_source(
        source,
        source.name,
        "job-3",
        country="IT",
        access_scope="country",
    )

    assert uri == "s3://knowledge-bucket/approved-knowledge/countries/IT/job-3/policy.pdf"
    assert s3.upload_file.call_args.args == (
        str(source),
        "knowledge-bucket",
        "approved-knowledge/countries/IT/job-3/policy.pdf",
    )


def test_final_source_upload_uses_global_folder(monkeypatch, tmp_path: Path) -> None:
    s3 = MagicMock()
    monkeypatch.setattr(knowledge_ingestion, "get_aws_clients", lambda: SimpleNamespace(s3=s3))
    monkeypatch.setattr(knowledge_ingestion.settings, "KNOWLEDGE_UPLOAD_BUCKET", "knowledge-bucket")
    source = tmp_path / "directory.pdf"
    source.write_bytes(b"approved")

    uri = knowledge_ingestion._upload_source(
        source,
        source.name,
        "job-4",
        country="US",
        access_scope="global",
    )

    assert uri == "s3://knowledge-bucket/approved-knowledge/global/job-4/directory.pdf"
    assert s3.upload_file.call_args.args[2] == "approved-knowledge/global/job-4/directory.pdf"


def test_queue_command_contains_reference_instead_of_document_bytes(monkeypatch) -> None:
    sqs = MagicMock()
    monkeypatch.setattr(knowledge_ingestion, "get_aws_clients", lambda: SimpleNamespace(sqs=sqs))
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_QUEUE_URL", "queue-url")
    monkeypatch.setattr(knowledge_ingestion, "_update_job", lambda *_args, **_kwargs: None)

    enqueue_ingestion_job(
        job_id="job-1",
        upload_uri="s3://bucket/key",
        filename="policy.pdf",
        country="CA",
        language="fr",
        document_type="policy",
        access_scope="country",
        version="2026.1",
        effective_date="2026-01-01",
        content_hash="a" * 64,
        accepted_by="reviewer@example.com",
    )

    body = sqs.send_message.call_args.kwargs["MessageBody"]
    assert '"uploadUri":"s3://bucket/key"' in body
    assert '"contentHash":"' + ("a" * 64) + '"' in body
    assert '"acceptedBy":"reviewer@example.com"' in body
    assert "approved document contents" not in body


def test_textract_ocr_reconstructs_pages(monkeypatch) -> None:
    textract = MagicMock()
    textract.start_document_text_detection.return_value = {"JobId": "ocr-1"}
    textract.get_document_text_detection.return_value = {
        "JobStatus": "SUCCEEDED",
        "Blocks": [
            {"BlockType": "LINE", "Page": 1, "Text": "First page"},
            {"BlockType": "WORD", "Page": 1, "Text": "ignored"},
            {"BlockType": "LINE", "Page": 2, "Text": "Second page"},
        ],
    }
    monkeypatch.setattr(
        knowledge_ingestion,
        "get_aws_clients",
        lambda: SimpleNamespace(textract=textract),
    )

    pages = _extract_pages_with_textract("s3://bucket/quarantine/policy.pdf")

    assert pages == [
        ExtractedPage(number=1, text="First page"),
        ExtractedPage(number=2, text="Second page"),
    ]


def test_write_generation_indexes_active_status_with_no_custom_id() -> None:
    """Spec test 1: no _id in the portal bulk actions; status=active and the
    job's ingestion_id are set on every chunk."""
    aoss = FakeAOSSVector()
    actions = list(
        knowledge_ingestion._actions(
            _make_sections(5),
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket/policy",
            status="active",
            ingestion_id="job-1",
            document_type="policy",
            access_scope="country",
        )
    )
    assert all("_id" not in action for action in actions)

    own_ids = _write_generation(aoss, actions)

    assert len(own_ids) == 5
    for doc_id in own_ids:
        doc = aoss.docs[doc_id]
        assert doc["status"] == "active"
        assert doc["ingestion_id"] == "job-1"


def test_review_then_direct_publish_flows_avoid_refresh_update_and_delete_by_query(
    monkeypatch,
) -> None:
    """Spec test 2. FakeAOSSVector raises on indices.refresh, update and
    delete_by_query, so this flow completing without an exception is the
    proof that none of them are called."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    clock = _StepClock()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )

    direct_sections = _make_sections(10, source_file="direct.pdf")
    indexed = _index_sections(
        direct_sections,
        source_uri="s3://bucket/direct.pdf",
        document_type="policy",
        access_scope="country",
        ingestion_id="direct-job",
        activated_by="tester",
        review_before_publish=False,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )
    assert indexed == 10
    assert db.active_generations["country:CA:en:policy:direct"]["active_ingestion_id"] == "direct-job"

    review_sections = _make_sections(6, source_file="review.pdf")
    indexed_review = _index_sections(
        review_sections,
        source_uri="s3://bucket/review.pdf",
        document_type="policy",
        access_scope="country",
        ingestion_id="review-job",
        activated_by="tester",
        review_before_publish=True,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )
    assert indexed_review == 6
    assert "country:CA:en:policy:review" not in db.active_generations

    db.seed_job(
        "review-job",
        status="ready_for_review",
        section_count=6,
        logical_document_id="country:CA:en:policy:review",
        country="CA",
        language="en",
        document_type="policy",
        access_scope="country",
        filename="review.pdf",
        source_uri="s3://bucket/review.pdf",
    )
    result = publish_ingestion_job("review-job", accepted_by="reviewer")

    assert result["publishedCount"] == 6
    assert db.active_generations["country:CA:en:policy:review"]["active_ingestion_id"] == "review-job"


def test_review_upload_reaches_ready_for_review_only_after_chunks_visible(
    monkeypatch,
) -> None:
    """Spec test 3."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    clock = _StepClock()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )

    sections = _make_sections(115, source_file="directory.pdf")
    indexed = _index_sections(
        sections,
        source_uri="s3://bucket/directory.pdf",
        document_type="office_directory",
        access_scope="global",
        ingestion_id="review-115",
        activated_by="tester",
        review_before_publish=True,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )
    # _index_sections only returns once _await_generation has confirmed every
    # chunk is visible, so the caller can now mark the job ready_for_review.
    assert indexed == 115
    db.seed_job(
        "review-115",
        status="ready_for_review",
        section_count=115,
        logical_document_id="global:GLOBAL:en:office_directory:directory",
    )

    preview = preview_ingestion_job("review-115")

    assert preview["summary"]["chunk_count"] == 115
    assert preview["can_publish"] is True


def test_generation_filters_exclude_review_chunks_until_pointer_switch(monkeypatch) -> None:
    """Spec test 4, using the real query builders in app/retrieval/opensearch_sections.py."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    clock = _StepClock()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(knowledge_generations, "get_engine", lambda: db)
    monkeypatch.setattr(opensearch_sections, "_client", lambda: aoss)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )
    knowledge_generations.clear_active_generation_cache()

    sections = _make_sections(3, source_file="policy.pdf")
    _index_sections(
        sections,
        source_uri="s3://bucket/policy.pdf",
        document_type="policy",
        access_scope="country",
        ingestion_id="review-job",
        activated_by="tester",
        review_before_publish=True,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )
    before_query = opensearch_sections._exact_section_query("s0000", "CA", "en")

    assert aoss.search(index="askvera-policy-sections", body=before_query)["hits"]["hits"] == []

    db.seed_job(
        "review-job",
        status="ready_for_review",
        section_count=3,
        logical_document_id="country:CA:en:policy:policy",
    )
    publish_ingestion_job("review-job", accepted_by="reviewer")
    knowledge_generations.clear_active_generation_cache()

    # _generation_filters bakes the currently active ingestion_ids into the
    # query, so the filter must be rebuilt after the pointer switch - a
    # query built before publish would stay pinned to the old (empty) set.
    after_query = opensearch_sections._exact_section_query("s0000", "CA", "en")
    hits = aoss.search(index="askvera-policy-sections", body=after_query)["hits"]["hits"]
    assert len(hits) == 1
    assert hits[0]["_source"]["section_id"] == "s0000"


def test_same_filename_reupload_in_review_mode_leaves_live_generation_untouched(
    monkeypatch,
) -> None:
    """Spec test 5: the latent overwrite bug this design removes - a staged
    re-upload of the same filename must never collide with, or disturb, the
    live generation's chunks or pointer."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    clock = _StepClock()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )

    live_sections = _make_sections(10, source_file="policy.pdf")
    _index_sections(
        live_sections,
        source_uri="s3://bucket/policy.pdf",
        document_type="policy",
        access_scope="country",
        ingestion_id="live-job",
        activated_by="tester",
        review_before_publish=False,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )
    live_ids = set(aoss.docs)
    assert db.active_generations["country:CA:en:policy:policy"]["active_ingestion_id"] == "live-job"

    staged_sections = _make_sections(10, source_file="policy.pdf")
    _index_sections(
        staged_sections,
        source_uri="s3://bucket/policy.pdf",
        document_type="policy",
        access_scope="country",
        ingestion_id="staged-job",
        activated_by="tester",
        review_before_publish=True,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )

    assert db.active_generations["country:CA:en:policy:policy"]["active_ingestion_id"] == "live-job"
    staged_ids = {doc_id for doc_id, doc in aoss.docs.items() if doc["ingestion_id"] == "staged-job"}
    assert not (live_ids & staged_ids)
    assert sum(1 for doc in aoss.docs.values() if doc["ingestion_id"] == "live-job") == 10


def test_await_generation_sweeps_strays_from_a_crashed_retry() -> None:
    """Spec test 6."""
    aoss = FakeAOSSVector()
    clock = _StepClock()

    def _write(ingestion_id):
        actions = list(
            knowledge_ingestion._actions(
                _make_sections(4, source_file="crash.pdf"),
                index="askvera-policy-sections",
                source_uri_prefix="s3://bucket",
                status="active",
                ingestion_id=ingestion_id,
                document_type="policy",
                access_scope="country",
            )
        )
        return _write_generation(aoss, actions)

    _write("crash-job")  # attempt 1: written, then the worker crashed before awaiting
    own_ids = _write("crash-job")  # attempt 2, the retry

    _await_generation(
        aoss,
        "askvera-policy-sections",
        "crash-job",
        own_ids,
        sleep=lambda _s: aoss.tick(),
        clock=clock,
    )

    remaining = {doc_id for doc_id, doc in aoss.docs.items() if doc["ingestion_id"] == "crash-job"}
    assert remaining == own_ids
    assert len(remaining) == 4


def test_write_generation_deletes_written_ids_and_is_non_retryable_on_4xx(monkeypatch) -> None:
    """Spec test 7 (4xx branch). Replaces test_staged_publish_rolls_back_partial_activation,
    which asserted an OpenSearch bulk-update rollback from active back to
    staging - that status-flip-on-failure path no longer exists, because
    chunks are written once as active and deleted (never updated) on failure."""
    aoss = FakeAOSSVector()
    actions = list(
        knowledge_ingestion._actions(
            _make_sections(3, source_file="bad.pdf"),
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="bad-job",
            document_type="policy",
            access_scope="country",
        )
    )
    # A client-supplied _id always 400s on VECTORSEARCH.
    actions[0]["_id"] = actions[0]["_source"]["id"]
    actions[1]["_id"] = actions[1]["_source"]["id"]

    logged = []
    monkeypatch.setattr(
        knowledge_ingestion.LOGGER,
        "error",
        lambda _event, **fields: logged.append(fields),
    )

    with pytest.raises(ValueError, match=r"OpenSearch rejected 2 of 3 chunks"):
        _write_generation(aoss, actions)

    assert len(logged) == 2
    assert all(entry["status"] == 400 for entry in logged)
    assert all(entry.get("type") and entry.get("reason") for entry in logged)
    # The one accepted item is deleted too - nothing partial survives.
    assert not any(doc["ingestion_id"] == "bad-job" for doc in aoss.docs.values())


def test_write_generation_is_retryable_on_5xx(monkeypatch) -> None:
    """Spec test 7 (5xx/429 branch), using the real request-level failure shape.
    It previously synthesized a dict error, which opensearch-py never yields
    for a request-level 5xx; that hid the AttributeError found in review."""
    aoss = FakeAOSSVector()
    actions = list(
        knowledge_ingestion._actions(
            _make_sections(2, source_file="ok.pdf"),
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="ok-job",
            document_type="policy",
            access_scope="country",
        )
    )

    def fake_streaming_bulk(_client, _actions, **_kwargs):
        # The exact shape opensearch-py 3.2.0's _process_bulk_chunk_error
        # yields for a failed _bulk request: error is a STRING, plus the
        # exception and the document itself under "data".
        exception = TransportError(503, "503 Service Unavailable", {})
        yield True, {"index": {"_id": "kept-1"}}
        yield False, {
            "index": {
                "error": str(exception),
                "status": 503,
                "exception": exception,
                "data": {"content": "Content that must never be logged"},
                "_index": "askvera-policy-sections",
            }
        }

    monkeypatch.setattr(knowledge_ingestion.helpers, "streaming_bulk", fake_streaming_bulk)

    with pytest.raises(RuntimeError, match=r"OpenSearch rejected 1 of 2 chunks \(first: TransportError") as excinfo:
        _write_generation(aoss, actions)

    assert "must never be logged" not in str(excinfo.value)


def test_await_generation_timeout_deletes_own_chunks_and_is_retryable() -> None:
    """Spec test 8."""
    aoss = FakeAOSSVector()
    actions = list(
        knowledge_ingestion._actions(
            _make_sections(3, source_file="slow.pdf"),
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="slow-job",
            document_type="policy",
            access_scope="country",
        )
    )
    own_ids = _write_generation(aoss, actions)
    # Never ticked: the chunks stay invisible forever, as if VECTORSEARCH
    # never refreshed within the timeout.
    clock = _StepClock(step=100.0)

    with pytest.raises(RuntimeError, match="did not become fully visible"):
        _await_generation(
            aoss,
            "askvera-policy-sections",
            "slow-job",
            own_ids,
            timeout_seconds=180,
            sleep=lambda _s: None,
            clock=clock,
        )

    assert not any(doc["ingestion_id"] == "slow-job" for doc in aoss.docs.values())


def test_publish_fails_closed_on_count_mismatch(monkeypatch) -> None:
    """Spec test 9. Replaces test_staged_publish_rejects_partial_generation,
    which asserted the old OpenSearch-side activation count check; that
    check now lives in publish_ingestion_job itself, before any pointer
    switch, since there is no separate OpenSearch activation step any more."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )

    actions = list(
        knowledge_ingestion._actions(
            _make_sections(2, source_file="partial.pdf"),
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="partial-job",
            document_type="policy",
            access_scope="country",
        )
    )
    _write_generation(aoss, actions)
    aoss.tick()
    db.seed_job(
        "partial-job",
        status="ready_for_review",
        section_count=5,  # expects 5, only 2 chunks actually exist
        logical_document_id="country:CA:en:policy:partial",
    )

    with pytest.raises(ValueError, match="expected 5, found 2"):
        publish_ingestion_job("partial-job", accepted_by="reviewer")

    assert "country:CA:en:policy:partial" not in db.active_generations


def test_generation_activation_locks_logical_document_before_read(
    monkeypatch,
) -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = ""
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = transaction
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: engine)
    monkeypatch.setattr(
        knowledge_ingestion,
        "clear_active_generation_cache",
        lambda: None,
    )

    knowledge_ingestion._activate_generation_pointer(
        logical_document_id="country:CA:en:policy:company-policy",
        ingestion_id="generation-2",
        country="CA",
        language="en",
        source_file="CA-EN-Company-Policy.pdf",
        document_type="policy",
        access_scope="country",
        activated_by="reviewer@example.invalid",
    )

    first_statement = str(connection.execute.call_args_list[0].args[0])
    second_statement = str(connection.execute.call_args_list[1].args[0])
    assert "pg_advisory_xact_lock" in first_statement
    assert "FOR UPDATE" in second_statement


def test_generation_activation_retires_the_previous_flat_document_row(
    monkeypatch,
) -> None:
    """When a new generation supersedes a prior one, the flat
    knowledge_documents row for that prior generation must also flip to
    'retired' - otherwise it lingers as status='active' with a stale
    section count forever, exactly like International-Office-Directory-
    April-2026.pdf did (a pre-pipeline legacy row, but the same failure
    mode applies to any normal re-upload once a generation pointer already
    exists), confusing both the admin document list and the low-coverage
    fleet check."""
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = "generation-1"
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = transaction
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: engine)
    monkeypatch.setattr(
        knowledge_ingestion,
        "clear_active_generation_cache",
        lambda: None,
    )

    knowledge_ingestion._activate_generation_pointer(
        logical_document_id="country:CA:en:policy:company-policy",
        ingestion_id="generation-2",
        country="CA",
        language="en",
        source_file="CA-EN-Company-Policy.pdf",
        document_type="policy",
        access_scope="country",
        activated_by="reviewer@example.invalid",
    )

    retire_calls = [
        call for call in connection.execute.call_args_list
        if "UPDATE knowledge_documents" in str(call.args[0])
    ]
    # Two retirements now: the prior generation's row by document_id (as
    # before), plus spec D2's sweep of any other active row for the same
    # logical document (e.g. a script-loaded bulk-<sha> row).
    by_document_id = [call for call in retire_calls if "document_id" in call.args[1]]
    by_logical_id = [call for call in retire_calls if "new_document_id" in call.args[1]]
    assert len(retire_calls) == 2
    assert len(by_document_id) == 1
    assert "status = 'retired'" in str(by_document_id[0].args[0])
    assert by_document_id[0].args[1]["document_id"] == "generation-1"
    assert by_logical_id[0].args[1] == {
        "logical_document_id": "country:CA:en:policy:company-policy",
        "new_document_id": "generation-2",
    }


def test_generation_activation_skips_flat_row_retirement_when_no_prior_generation(
    monkeypatch,
) -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = ""
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine = MagicMock()
    engine.begin.return_value = transaction
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: engine)
    monkeypatch.setattr(
        knowledge_ingestion,
        "clear_active_generation_cache",
        lambda: None,
    )

    knowledge_ingestion._activate_generation_pointer(
        logical_document_id="country:CA:en:policy:company-policy",
        ingestion_id="generation-1",
        country="CA",
        language="en",
        source_file="CA-EN-Company-Policy.pdf",
        document_type="policy",
        access_scope="country",
        activated_by="reviewer@example.invalid",
    )

    # No prior generation, so no retirement by previous document_id. Spec
    # D2's logical-document sweep still runs (it is what retires a
    # script-loaded row that no pointer ever named), excluding the new row.
    retire_calls = [
        call for call in connection.execute.call_args_list
        if "UPDATE knowledge_documents" in str(call.args[0])
    ]
    assert not any("document_id" in call.args[1] for call in retire_calls)
    assert [call.args[1] for call in retire_calls] == [
        {
            "logical_document_id": "country:CA:en:policy:company-policy",
            "new_document_id": "generation-1",
        }
    ]


def test_publish_retires_script_loaded_registry_row_for_same_logical_document(
    monkeypatch, tmp_path,
) -> None:
    """Spec D2, driven through create_ingestion_job and the worker (not a seeded
    canonical id): a script-loaded registry row (document_id bulk-<sha>) is
    never named by the pointer's uuid-hex ingestion_id, so only the
    logical-document sweep can retire it when a portal job publishes."""
    aoss, db = _wire_directory_fakes(monkeypatch)
    other_logical_id = "country:CA:en:policy:company-policy"
    db.documents["other-doc"] = {
        "document_id": "other-doc", "logical_document_id": other_logical_id, "status": "active",
    }

    _upload_through_worker(
        monkeypatch, tmp_path, aoss, job_id="portal-job",
        stable_id="international-sponsoring-directory", filename=DIRECTORY_FILENAME,
    )
    publish_ingestion_job("portal-job", accepted_by="reviewer")

    assert db.active_generations[LIVE_DIRECTORY_ID]["active_ingestion_id"] == "portal-job"
    assert db.documents["bulk-3f9a1c"]["status"] == "retired"
    assert db.documents["portal-job"]["status"] == "active"
    assert db.documents["other-doc"]["status"] == "active"


def test_logical_document_ids_are_namespaced_by_locale() -> None:
    canada = knowledge_generations.build_logical_document_id(
        logical_document_id="company-policy",
        country="CA",
        language="en",
        document_type="policy",
        access_scope="country",
        source_file="policy.pdf",
    )
    united_states = knowledge_generations.build_logical_document_id(
        logical_document_id="company-policy",
        country="US",
        language="en",
        document_type="policy",
        access_scope="country",
        source_file="policy.pdf",
    )

    assert canada == "country:CA:en:policy:company-policy"
    assert united_states == "country:US:en:policy:company-policy"


def test_delete_generation_chunks_removes_only_its_own_and_needs_two_zero_polls() -> None:
    """Spec test 10 (a): delete removes only this job's chunks and needs two
    zero polls at least one refresh interval apart before it converges."""
    aoss = FakeAOSSVector()
    clock = _StepClock(step=70.0)

    def _write(ingestion_id, count, source_file):
        actions = list(
            knowledge_ingestion._actions(
                _make_sections(count, source_file=source_file),
                index="askvera-policy-sections",
                source_uri_prefix="s3://bucket",
                status="active",
                ingestion_id=ingestion_id,
                document_type="policy",
                access_scope="country",
            )
        )
        return _write_generation(aoss, actions)

    _write("del-job", 4, "del.pdf")
    _write("keep-job", 2, "keep.pdf")
    aoss.tick()

    polls = []

    def fake_sleep(_seconds):
        polls.append(1)
        aoss.tick()

    _delete_generation_chunks(
        aoss,
        "askvera-policy-sections",
        "del-job",
        timeout_seconds=600,
        sleep=fake_sleep,
        clock=clock,
    )

    assert not any(doc["ingestion_id"] == "del-job" for doc in aoss.docs.values())
    assert sum(1 for doc in aoss.docs.values() if doc["ingestion_id"] == "keep-job") == 2
    assert len(polls) >= 2


def test_delete_ingestion_job_timeout_marks_deletion_failed_with_pointer_already_removed(
    monkeypatch,
) -> None:
    """Spec test 10 (b)."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    # Force a permanently non-zero visible count so the delete loop can
    # never converge, deterministically triggering the timeout path rather
    # than depending on exact fake-clock/tick arithmetic.
    monkeypatch.setattr(knowledge_ingestion, "_visible_ids", lambda *_a, **_k: {"stray-forever"})
    monkeypatch.setattr(knowledge_ingestion, "_count_for_ingestion", lambda *_a, **_k: 1)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_VISIBILITY_TIMEOUT_SECONDS", 10
    )

    logical_id = "country:CA:en:policy:stuck"
    db.seed_job(
        "stuck-job",
        status="ready",
        logical_document_id=logical_id,
        source_uri="s3://bucket/stuck.pdf",
        country="CA", language="en", access_scope="country", document_type="policy",
    )
    db.active_generations[logical_id] = {
        "logical_document_id": logical_id,
        "country": "CA",
        "language": "en",
        "source_file": "stuck.pdf",
        "document_type": "policy",
        "access_scope": "country",
        "previous_ingestion_id": "",
        "active_ingestion_id": "stuck-job",
        "activated_by": "tester",
    }

    clock = _StepClock(step=20.0)
    with pytest.raises(RuntimeError, match="did not complete safely"):
        delete_ingestion_job("stuck-job", deleted_by="tester", sleep=lambda _s: None, clock=clock)

    assert logical_id not in db.active_generations
    assert db.jobs["stuck-job"]["status"] == "deletion_failed"


def test_rollback_to_portal_and_script_style_generation(monkeypatch) -> None:
    """Spec test 11: rollback to a portal generation (with an ingestion_jobs
    row) and to a script-style generation (none - D1's LEFT JOIN)."""
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(
        knowledge_ingestion.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", True
    )

    logical_id = "country:CA:en:policy:rollback-doc"

    def _write(ingestion_id, count):
        actions = list(
            knowledge_ingestion._actions(
                _make_sections(count, source_file="rollback-doc.pdf"),
                index="askvera-policy-sections",
                source_uri_prefix="s3://bucket",
                status="active",
                ingestion_id=ingestion_id,
                document_type="policy",
                access_scope="country",
            )
        )
        _write_generation(aoss, actions)
        aoss.tick()

    # A portal-style prior generation: it has a matching ingestion_jobs row.
    _write("portal-gen", 3)
    db.seed_job(
        "portal-gen", status="ready", section_count=3, logical_document_id=logical_id,
        country="CA", language="en", access_scope="country", document_type="policy",
    )
    db.document_generations["portal-gen"] = {
        "ingestion_id": "portal-gen",
        "logical_document_id": logical_id,
        "country": "CA",
        "language": "en",
        "source_file": "rollback-doc.pdf",
        "document_type": "policy",
        "access_scope": "country",
        "status": "retired",
        "activated_at": None,
        "retired_at": None,
        "activated_by": "tester",
    }
    db.documents["portal-gen"] = {
        "document_id": "portal-gen", "logical_document_id": logical_id, "status": "retired",
    }

    db.seed_job(
        "current-gen", status="ready", logical_document_id=logical_id,
        country="CA", language="en", access_scope="country", document_type="policy",
    )
    db.active_generations[logical_id] = {
        "logical_document_id": logical_id,
        "country": "CA",
        "language": "en",
        "source_file": "rollback-doc.pdf",
        "document_type": "policy",
        "access_scope": "country",
        "previous_ingestion_id": "portal-gen",
        "active_ingestion_id": "current-gen",
        "activated_by": "tester",
    }
    db.documents["current-gen"] = {
        "document_id": "current-gen", "logical_document_id": logical_id, "status": "active",
    }

    result = rollback_document_generation("current-gen", "portal-gen", activated_by="reviewer")

    assert result["active_ingestion_id"] == "portal-gen"
    assert db.active_generations[logical_id]["active_ingestion_id"] == "portal-gen"

    # A script-loaded generation: no ingestion_jobs row at all. list_document_generations'
    # LEFT JOIN must still surface it, and rollback must accept it on chunk
    # presence alone (no exact section_count to compare against).
    _write("bulk-abc123", 7)
    db.document_generations["bulk-abc123"] = {
        "ingestion_id": "bulk-abc123",
        "logical_document_id": logical_id,
        "country": "CA",
        "language": "en",
        "source_file": "rollback-doc.pdf",
        "document_type": "policy",
        "access_scope": "country",
        "status": "retired",
        "activated_at": None,
        "retired_at": None,
        "activated_by": "script",
    }
    db.documents["bulk-abc123"] = {
        "document_id": "bulk-abc123", "logical_document_id": logical_id, "status": "retired",
    }

    generations = list_document_generations("current-gen")
    script_style = next(g for g in generations if g["ingestion_id"] == "bulk-abc123")
    assert script_style["section_count"] is None

    result2 = rollback_document_generation("current-gen", "bulk-abc123", activated_by="reviewer")

    assert result2["active_ingestion_id"] == "bulk-abc123"
    assert db.active_generations[logical_id]["active_ingestion_id"] == "bulk-abc123"


def test_index_sections_rejects_documents_above_the_section_limit() -> None:
    with pytest.raises(ValueError, match=r"10,000-section limit"):
        _index_sections(
            _make_sections(MAX_SECTIONS_PER_INGESTION + 1),
            source_uri="s3://bucket/policy.pdf",
            document_type="policy",
            access_scope="country",
            ingestion_id="job-huge",
        )


def test_review_mode_rejected_in_worker_when_pointer_flag_off() -> None:
    """Spec test 12 (worker half)."""
    with pytest.raises(ValueError, match="ADMIN_INGESTION_GENERATION_POINTER_ENABLED"):
        _index_sections(
            _make_sections(1),
            source_uri="s3://bucket/policy.pdf",
            document_type="policy",
            access_scope="country",
            ingestion_id="job-x",
            review_before_publish=True,
        )


def test_upload_rejects_review_before_publish_when_pointer_flag_off(monkeypatch) -> None:
    """Spec test 12 (upload half): reject at upload time, before a job is
    even created, so an unreviewable staged upload can never be queued."""
    import asyncio

    from fastapi import BackgroundTasks, HTTPException

    from api import admin_routes

    monkeypatch.setattr(admin_routes.settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", False)
    monkeypatch.setattr(admin_routes, "require_admin_access", lambda *_a, **_k: {"role": "admin"})
    monkeypatch.setattr(admin_routes, "get_country_codes", lambda: {"CA"})
    monkeypatch.setattr(admin_routes, "get_language_codes_for_country", lambda _c: {"en"})

    class _FakeUploadFile:
        filename = "policy.pdf"

        async def read(self, _n):
            return b"%PDF-1.4 test"

    fake_request = SimpleNamespace(
        state=SimpleNamespace(admin_identity={"role": "admin", "email": "a@example.invalid"})
    )

    async def _call():
        return await admin_routes.upload_document(
            request=fake_request,
            background_tasks=BackgroundTasks(),
            file=_FakeUploadFile(),
            country="CA",
            language="en",
            document_type="policy",
            access_scope="country",
            review_before_publish=True,
        )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(_call())

    assert excinfo.value.status_code == 400
    assert "ADMIN_INGESTION_GENERATION_POINTER_ENABLED" in str(excinfo.value.detail)


def test_claim_ingestion_job_does_not_reclaim_ready_for_review_or_deleting(monkeypatch) -> None:
    """Spec test 13."""
    db = FakeIngestionDB()
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_MAX_ATTEMPTS", 5)

    db.seed_job("review-job", status="ready_for_review")
    db.seed_job("deleting-job", status="deleting")
    db.seed_job("deleted-job", status="deleted")
    db.seed_job("failed-job", status="deletion_failed")
    db.seed_job("queued-job", status="queued")

    assert claim_ingestion_job("review-job", "worker-1", 60) == "completed"
    assert claim_ingestion_job("deleting-job", "worker-1", 60) == "busy"
    assert claim_ingestion_job("deleted-job", "worker-1", 60) == "terminal"
    assert claim_ingestion_job("failed-job", "worker-1", 60) == "terminal"
    assert claim_ingestion_job("queued-job", "worker-1", 60) == "claimed"
    # A duplicate SQS delivery for an already-completed job must never re-run it.
    assert db.jobs["review-job"]["status"] == "ready_for_review"
    assert db.jobs["deleting-job"]["status"] == "deleting"


def test_loader_actions_are_byte_identical_between_portal_and_script(monkeypatch) -> None:
    """Spec test 15 (regression): the portal must keep importing and using
    _actions/_index_body unchanged from the script loader, never a forked
    copy, so their bulk actions stay byte-identical."""
    from scripts.ingestion import load_policy_sections_to_opensearch as loader

    assert knowledge_ingestion._actions is loader._actions
    assert knowledge_ingestion._index_body is loader._index_body

    monkeypatch.setattr(loader, "embed_text", lambda _text: [0.0, 0.0, 0.0, 0.0])

    sections = _make_sections(4, source_file="parity.pdf")
    portal_actions = list(
        knowledge_ingestion._actions(
            sections,
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="job-1",
            document_type="policy",
            access_scope="country",
        )
    )
    script_actions = list(
        loader._actions(
            sections,
            index="askvera-policy-sections",
            source_uri_prefix="s3://bucket",
            status="active",
            ingestion_id="job-1",
            document_type="policy",
            access_scope="country",
        )
    )

    assert portal_actions == script_actions


@pytest.mark.parametrize(
    "stable_id",
    ["international-sponsoring-directory", "", "  international-sponsoring-directory  "],
    ids=["typed-stable-id", "blank-stable-id", "padded-stable-id"],
)
def test_directory_reupload_replaces_live_script_generation_under_one_pointer(
    monkeypatch, tmp_path, stable_id,
) -> None:
    """Review BLOCKING 1: the pointer key must be the canonical one the worker
    indexes under, never the raw form value, or a second directory goes live."""
    aoss, db = _wire_directory_fakes(monkeypatch)

    _upload_through_worker(
        monkeypatch, tmp_path, aoss, job_id="portal-job", stable_id=stable_id, filename=DIRECTORY_FILENAME,
    )

    assert db.jobs["portal-job"]["logical_document_id"] == LIVE_DIRECTORY_ID
    assert db.jobs["portal-job"]["status"] == "ready_for_review"
    assert _retrievable_global(aoss) == {SCRIPT_GENERATION_ID: 115}

    publish_ingestion_job("portal-job", accepted_by="owner@example.invalid")

    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert db.active_generations[LIVE_DIRECTORY_ID]["active_ingestion_id"] == "portal-job"
    assert _retrievable_global(aoss) == {"portal-job": 115}
    assert db.documents["bulk-3f9a1c"]["status"] == "retired"
    assert db.documents["portal-job"]["status"] == "active"

    rollback_document_generation("portal-job", SCRIPT_GENERATION_ID, activated_by="owner@example.invalid")
    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert _retrievable_global(aoss) == {SCRIPT_GENERATION_ID: 115}

    rollback_document_generation("portal-job", "portal-job", activated_by="owner@example.invalid")
    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert _retrievable_global(aoss) == {"portal-job": 115}


def test_directory_upload_with_a_different_filename_stem_is_a_separate_document(
    monkeypatch, tmp_path,
) -> None:
    aoss, db = _wire_directory_fakes(monkeypatch)

    _upload_through_worker(
        monkeypatch, tmp_path, aoss, job_id="variant-job", stable_id="",
        filename="International Sponsoring Directory (1).pdf",
    )
    publish_ingestion_job("variant-job", accepted_by="owner@example.invalid")

    variant_id = "global:GLOBAL:en:office_directory:international-sponsoring-directory-1"
    assert db.jobs["variant-job"]["logical_document_id"] == variant_id
    assert db.active_generations[LIVE_DIRECTORY_ID]["active_ingestion_id"] == SCRIPT_GENERATION_ID
    assert db.active_generations[variant_id]["active_ingestion_id"] == "variant-job"
    assert db.documents["bulk-3f9a1c"]["status"] == "active"
    assert sum(1 for doc in aoss.docs.values() if doc["ingestion_id"] == SCRIPT_GENERATION_ID) == 115


def test_job_logical_document_id_rebuilds_raw_values_from_legacy_job_rows() -> None:
    """Jobs created before the worker persisted the canonical key still hold the
    raw form value; every reader must rebuild the same key the worker used."""
    base = {
        "access_scope": "global", "document_type": "office_directory", "country": "US",
        "language": "en", "filename": DIRECTORY_FILENAME,
    }
    helper = knowledge_ingestion._job_logical_document_id

    assert helper({**base, "logical_document_id": "international-sponsoring-directory"}) == LIVE_DIRECTORY_ID
    assert helper({**base, "logical_document_id": ""}) == LIVE_DIRECTORY_ID
    assert helper({**base, "logical_document_id": LIVE_DIRECTORY_ID}) == LIVE_DIRECTORY_ID
    # A canonical-looking key for another scope/type is treated as raw text,
    # so a typed id can never address a different document's pointer slot.
    assert helper({**base, "logical_document_id": "country:CA:en:policy:company-policy"}) != (
        "country:CA:en:policy:company-policy"
    )
    assert helper({
        "access_scope": "country", "document_type": "policy", "country": "ca", "language": "EN",
        "filename": "CA-EN-Company-Policy.pdf", "logical_document_id": "company-policy",
    }) == "country:CA:en:policy:company-policy"


def test_legacy_job_row_with_raw_stable_id_publishes_under_the_canonical_pointer(monkeypatch) -> None:
    """The owner's stuck jobs: processed before the canonical key was
    persisted, so the row still holds the raw form value."""
    aoss, db = _wire_directory_fakes(monkeypatch)
    create_ingestion_job(
        job_id="stuck-job", filename=DIRECTORY_FILENAME, country="US", language="en",
        document_type="office_directory", access_scope="global", version="",
        logical_document_id="international-sponsoring-directory", review_before_publish=True,
    )
    _write_generation(
        aoss,
        knowledge_ingestion._actions(
            _directory_sections(115), index=knowledge_ingestion.settings.OPENSEARCH_INDEX,
            source_uri_prefix="s3://up", status="active", ingestion_id="stuck-job",
            document_type="office_directory", access_scope="global",
        ),
    )
    aoss.tick()
    knowledge_ingestion._update_job("stuck-job", status="ready_for_review", section_count=115)
    assert db.jobs["stuck-job"]["logical_document_id"] == "international-sponsoring-directory"

    publish_ingestion_job("stuck-job", accepted_by="owner@example.invalid")

    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert _retrievable_global(aoss) == {"stuck-job": 115}
    assert db.documents["bulk-3f9a1c"]["status"] == "retired"
    generations = {g["ingestion_id"] for g in list_document_generations("stuck-job")}
    assert generations == {"stuck-job", SCRIPT_GENERATION_ID}


def test_write_generation_cleans_up_after_a_request_level_429(monkeypatch) -> None:
    """Review BLOCKING 2: opensearch-py reports a failed _bulk request with the
    error as a plain string. The first 500-action chunk is already written when
    the second is throttled; every written chunk must still be deleted."""

    class ThrottleSecondChunk(FakeAOSSVector):
        def __init__(self):
            super().__init__()
            self.bulk_calls = 0

        def bulk(self, body, index=None, **params):
            self.bulk_calls += 1
            if self.bulk_calls == 2:
                raise TransportError(429, "429 Too Many Requests", {"error": "throttled"})
            return super().bulk(body, index=index, **params)

    aoss = ThrottleSecondChunk()
    logged = []
    monkeypatch.setattr(
        knowledge_ingestion.LOGGER, "error", lambda _event, **fields: logged.append(fields),
    )
    actions = list(
        knowledge_ingestion._actions(
            _make_sections(600, source_file="big.pdf"), index="askvera-policy-sections",
            source_uri_prefix="s3://bucket", status="active", ingestion_id="big-job",
            document_type="policy", access_scope="country",
        )
    )

    with pytest.raises(RuntimeError, match=r"OpenSearch rejected 100 of 600 chunks") as excinfo:
        _write_generation(aoss, actions)

    assert aoss.docs == {}
    assert len(logged) == 5
    assert logged[0]["status"] == 429
    assert logged[0]["type"] == "TransportError"
    assert "429 Too Many Requests" in logged[0]["reason"]
    assert "Content " not in str(excinfo.value)
    assert all("Content " not in entry["reason"] for entry in logged)


def test_index_sections_never_activates_a_pointer_after_a_partial_failure(monkeypatch) -> None:
    """A direct publish whose second bulk chunk fails must leave no chunks and
    no pointer change, and must not retire the generation that is live today."""
    aoss, db = _wire_directory_fakes(monkeypatch)
    calls = {"bulk": 0}
    original_bulk = aoss.bulk

    def flaky_bulk(body, index=None, **params):
        calls["bulk"] += 1
        if calls["bulk"] == 2:
            raise TransportError(503, "503 Service Unavailable", {})
        return original_bulk(body, index=index, **params)

    monkeypatch.setattr(aoss, "bulk", flaky_bulk)

    with pytest.raises(RuntimeError, match=r"OpenSearch rejected 100 of 600 chunks"):
        _index_sections(
            _directory_sections(600),
            source_uri="s3://up/global/direct-job/International-Sponsoring-Directory.pdf",
            document_type="office_directory",
            access_scope="global",
            ingestion_id="direct-job",
            logical_document_id=LIVE_DIRECTORY_ID,
            activated_by="owner@example.invalid",
            review_before_publish=False,
            sleep=lambda _s: aoss.tick(),
            clock=_StepClock(),
        )

    assert not any(doc["ingestion_id"] == "direct-job" for doc in aoss.docs.values())
    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert db.active_generations[LIVE_DIRECTORY_ID]["active_ingestion_id"] == SCRIPT_GENERATION_ID
    assert "direct-job" not in db.document_generations
    assert db.documents["bulk-3f9a1c"]["status"] == "active"
    assert _retrievable_global(aoss) == {SCRIPT_GENERATION_ID: 115}


def test_preview_and_review_reads_exclude_the_embedding(monkeypatch) -> None:
    aoss = FakeAOSSVector()
    db = FakeIngestionDB()
    db.seed_job("any-job", status="ready_for_review")
    bodies = []
    original_search = aoss.search

    def recording_search(index, body=None, **kwargs):
        bodies.append(body)
        return original_search(index, body=body, **kwargs)

    monkeypatch.setattr(aoss, "search", recording_search)
    monkeypatch.setattr(knowledge_ingestion, "_client", lambda: aoss)
    monkeypatch.setattr(knowledge_ingestion, "get_engine", lambda: db)

    preview_ingestion_job("any-job")
    knowledge_ingestion.test_ingestion_job("any-job", "sponsor")

    assert len(bodies) == 2
    assert all(body["_source"] == {"excludes": ["embedding"]} for body in bodies)


def test_delete_route_returns_before_the_sweep_and_the_job_ends_deleted(monkeypatch) -> None:
    """Review R1: the sweep takes minutes (two refresh cycles), past the 90 s
    proxy timeout, so the route removes the pointer, writes the tombstone and
    returns; the sweep runs as a background task."""
    import asyncio

    from fastapi import BackgroundTasks, HTTPException

    from api import admin_routes

    aoss, db = _wire_directory_fakes(monkeypatch)
    db.seed_job(
        SCRIPT_GENERATION_ID, status="ready", logical_document_id=LIVE_DIRECTORY_ID, source_uri="",
        access_scope="global", document_type="office_directory", filename=DIRECTORY_FILENAME,
    )
    monkeypatch.setattr(admin_routes, "require_admin_access", lambda *_a, **_k: {"role": "super_admin"})
    audit = []
    monkeypatch.setattr(admin_routes, "record_admin_audit_event", lambda *args: audit.append(args))
    slept = []

    def finish_with_fake_time(job, **kwargs):
        clock = _StepClock(step=0.0)

        def fake_sleep(seconds):
            slept.append(seconds)
            clock.now += seconds
            aoss.tick()

        return knowledge_ingestion.finish_ingestion_deletion(job, sleep=fake_sleep, clock=clock, **kwargs)

    monkeypatch.setattr(admin_routes, "finish_ingestion_deletion", finish_with_fake_time)
    request = SimpleNamespace(
        state=SimpleNamespace(admin_identity={"role": "super_admin", "email": "owner@example.invalid"})
    )
    tasks = BackgroundTasks()

    response = admin_routes.delete_ingestion(SCRIPT_GENERATION_ID, request, tasks)

    # Returned without waiting: pointer gone, tombstone written, chunks not yet swept.
    assert slept == []
    assert response["data"]["job"]["status"] == "deleting"
    assert db.jobs[SCRIPT_GENERATION_ID]["status"] == "deleting"
    assert LIVE_DIRECTORY_ID not in db.active_generations
    assert sum(1 for doc in aoss.docs.values() if doc["ingestion_id"] == SCRIPT_GENERATION_ID) == 115
    assert audit and audit[0][1] == "knowledge.document_deleted"

    # A second request while the sweep is pending must not start another one.
    with pytest.raises(HTTPException) as excinfo:
        admin_routes.delete_ingestion(SCRIPT_GENERATION_ID, request, BackgroundTasks())
    assert excinfo.value.status_code == 409

    asyncio.run(tasks())

    assert db.jobs[SCRIPT_GENERATION_ID]["status"] == "deleted"
    assert not any(doc["ingestion_id"] == SCRIPT_GENERATION_ID for doc in aoss.docs.values())
    assert sum(slept) >= 65


def test_delete_route_is_registered_with_202_accepted() -> None:
    from api import admin_routes

    routes = [
        route for route in admin_routes.admin_router.routes
        if getattr(route, "path", "").endswith("/ingestions/{job_id}") and "DELETE" in getattr(route, "methods", set())
    ]
    assert [route.status_code for route in routes] == [202]


def test_background_delete_failure_ends_in_deletion_failed_without_raising(monkeypatch) -> None:
    aoss, db = _wire_directory_fakes(monkeypatch)
    db.seed_job(
        SCRIPT_GENERATION_ID, status="ready", logical_document_id=LIVE_DIRECTORY_ID, source_uri="",
        access_scope="global", document_type="office_directory", filename=DIRECTORY_FILENAME,
    )
    monkeypatch.setattr(knowledge_ingestion, "_visible_ids", lambda *_a, **_k: {"stray-forever"})
    monkeypatch.setattr(knowledge_ingestion, "_count_for_ingestion", lambda *_a, **_k: 1)

    job = knowledge_ingestion.begin_ingestion_deletion(SCRIPT_GENERATION_ID)
    knowledge_ingestion.finish_ingestion_deletion(
        job, sleep=lambda _s: None, clock=_StepClock(step=1000.0), raise_on_failure=False,
    )

    assert db.jobs[SCRIPT_GENERATION_ID]["status"] == "deletion_failed"
    assert LIVE_DIRECTORY_ID not in db.active_generations


def test_a_stale_deleting_job_can_be_retried() -> None:
    from datetime import UTC, datetime, timedelta

    fresh = {"status": "deleting", "updated_at": datetime.now(UTC).isoformat()}
    stale = {"status": "deleting", "updated_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}

    assert knowledge_ingestion._deletion_in_progress(fresh) is True
    assert knowledge_ingestion._deletion_in_progress(stale) is False
    assert knowledge_ingestion._deletion_in_progress({"status": "deletion_failed"}) is False


def test_visibility_timeout_is_floored_at_the_minimum(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_VISIBILITY_TIMEOUT_SECONDS", 61)
    assert knowledge_ingestion._visibility_timeout() == 150
    monkeypatch.setattr(knowledge_ingestion.settings, "ADMIN_INGESTION_VISIBILITY_TIMEOUT_SECONDS", 240)
    assert knowledge_ingestion._visibility_timeout() == 240


US_POLICY_ID = "country:US:en:policy:company-policy"
CA_POLICY_ID = "country:CA:en:policy:company-policy"


def _seed_live_policy(aoss, db, *, logical_id, country, ingestion_id):
    """A live, published company policy for one market."""
    _write_generation(
        aoss,
        knowledge_ingestion._actions(
            _make_sections(3, country=country, source_file=f"{country}-EN-Company-Policy.pdf"),
            index=knowledge_ingestion.settings.OPENSEARCH_INDEX, source_uri_prefix="s3://kb",
            status="active", ingestion_id=ingestion_id, document_type="policy", access_scope="country",
        ),
    )
    aoss.tick()
    db.active_generations[logical_id] = {
        "logical_document_id": logical_id, "country": country, "language": "en",
        "source_file": f"{country}-EN-Company-Policy.pdf", "document_type": "policy",
        "access_scope": "country", "previous_ingestion_id": "", "active_ingestion_id": ingestion_id,
        "activated_by": "owner",
    }
    db.document_generations[ingestion_id] = {
        "ingestion_id": ingestion_id, "logical_document_id": logical_id, "country": country,
        "language": "en", "source_file": f"{country}-EN-Company-Policy.pdf", "document_type": "policy",
        "access_scope": "country", "status": "active", "activated_at": None, "retired_at": None,
        "activated_by": "owner",
    }
    db.documents[ingestion_id] = {"document_id": ingestion_id, "logical_document_id": logical_id, "status": "active"}


def _upload_policy_through_worker(monkeypatch, tmp_path, aoss, *, job_id, stable_id, country="CA", language="en"):
    """A market admin's policy upload: create_ingestion_job with the raw form value, then the worker."""
    filename = f"{country}-{language.upper()}-Company-Policy.txt"
    create_ingestion_job(
        job_id=job_id, filename=filename, country=country, language=language, document_type="policy",
        access_scope="country", version="2026-09", logical_document_id=stable_id.strip(),
        review_before_publish=True,
    )
    monkeypatch.setattr(knowledge_ingestion, "extract_pages", lambda *_a, **_k: [ExtractedPage(1, "policy")])
    monkeypatch.setattr(
        knowledge_ingestion,
        "build_sections",
        lambda *_a, **_k: _make_sections(3, country=country, language=language, source_file=filename),
    )
    upload_dir = tmp_path / job_id
    upload_dir.mkdir()
    local_path = upload_dir / filename
    local_path.write_text("policy", encoding="utf-8")
    assert process_ingestion_job(
        job_id, str(local_path), filename=filename, country=country, language=language,
        document_type="policy", access_scope="country", version="2026-09", effective_date="",
        accepted_by="ca-admin@example.invalid", logical_document_id=stable_id.strip(),
        review_before_publish=True, sleep=lambda _s: aoss.tick(), clock=_StepClock(),
    )


def _country_retrievable(country):
    knowledge_generations.clear_active_generation_cache()
    return knowledge_generations.active_generation_ids(
        countries={country}, languages={"en"}, access_scope="country", document_type="policy",
    )


def test_typed_stable_id_for_another_market_is_confined_to_the_uploaders_market(
    monkeypatch, tmp_path,
) -> None:
    """Delta re-review: RBAC is per market, so a CA admin typing the US
    policy's canonical key must not be able to retire the live US policy."""
    aoss, db = _wire_directory_fakes(monkeypatch)
    _seed_live_policy(aoss, db, logical_id=US_POLICY_ID, country="US", ingestion_id="us-gen")

    _upload_policy_through_worker(monkeypatch, tmp_path, aoss, job_id="ca-job", stable_id=US_POLICY_ID)
    publish_ingestion_job("ca-job", accepted_by="ca-admin@example.invalid")

    confined_id = "country:CA:en:policy:country-us-en-policy-company-policy"
    assert db.jobs["ca-job"]["logical_document_id"] == confined_id
    assert db.active_generations[confined_id]["active_ingestion_id"] == "ca-job"
    assert db.active_generations[US_POLICY_ID]["active_ingestion_id"] == "us-gen"
    assert db.document_generations["us-gen"]["status"] == "active"
    assert db.documents["us-gen"]["status"] == "active"
    assert _country_retrievable("US") == {"us-gen"}
    assert _country_retrievable("CA") == {"ca-job"}
    assert sum(1 for doc in aoss.docs.values() if doc["ingestion_id"] == "us-gen") == 3


def test_typed_stable_id_in_another_language_is_slugified(monkeypatch, tmp_path) -> None:
    aoss, db = _wire_directory_fakes(monkeypatch)

    _upload_policy_through_worker(
        monkeypatch, tmp_path, aoss, job_id="ca-en-job", stable_id="country:CA:fr:policy:x",
    )

    assert db.jobs["ca-en-job"]["logical_document_id"] == "country:CA:en:policy:country-ca-fr-policy-x"
    assert knowledge_ingestion._job_logical_document_id({
        "access_scope": "country", "document_type": "policy", "country": "CA", "language": "en",
        "filename": "CA-EN-Company-Policy.txt", "logical_document_id": "country:CA:fr:policy:x",
    }) == "country:CA:en:policy:country-ca-fr-policy-x"


@pytest.mark.parametrize(
    "stable_id",
    ["international-sponsoring-directory", "", LIVE_DIRECTORY_ID],
    ids=["typed-slug", "blank", "typed-canonical-key"],
)
def test_directory_uploaded_with_a_non_english_form_language_keys_on_global_en(
    monkeypatch, tmp_path, stable_id,
) -> None:
    """The owner's form showed Dutch; the directory extractor always emits en,
    so the key must stay global:GLOBAL:en:... and replace the live directory."""
    aoss, db = _wire_directory_fakes(monkeypatch)

    _upload_through_worker(
        monkeypatch, tmp_path, aoss, job_id="portal-job", stable_id=stable_id,
        filename=DIRECTORY_FILENAME, form_language="nl",
    )
    publish_ingestion_job("portal-job", accepted_by="owner@example.invalid")

    assert db.jobs["portal-job"]["logical_document_id"] == LIVE_DIRECTORY_ID
    assert set(db.active_generations) == {LIVE_DIRECTORY_ID}
    assert _retrievable_global(aoss) == {"portal-job": 115}
    assert db.documents["bulk-3f9a1c"]["status"] == "retired"
    # A legacy row (raw value never rewritten by the worker) resolves the same way.
    legacy = {**db.jobs["portal-job"], "logical_document_id": stable_id}
    assert knowledge_ingestion._job_logical_document_id(legacy) == LIVE_DIRECTORY_ID


def test_same_market_canonical_stable_id_replaces_that_document(monkeypatch, tmp_path) -> None:
    """The intended feature: typing your own market's canonical key replaces that document."""
    aoss, db = _wire_directory_fakes(monkeypatch)
    _seed_live_policy(aoss, db, logical_id=CA_POLICY_ID, country="CA", ingestion_id="ca-old")

    _upload_policy_through_worker(monkeypatch, tmp_path, aoss, job_id="ca-new", stable_id=CA_POLICY_ID)
    publish_ingestion_job("ca-new", accepted_by="ca-admin@example.invalid")

    assert db.jobs["ca-new"]["logical_document_id"] == CA_POLICY_ID
    assert db.active_generations[CA_POLICY_ID]["active_ingestion_id"] == "ca-new"
    assert db.documents["ca-old"]["status"] == "retired"
    assert _country_retrievable("CA") == {"ca-new"}
