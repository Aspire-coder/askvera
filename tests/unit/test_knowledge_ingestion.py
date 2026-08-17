"""Tests for country-independent approved-document ingestion."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.ingestion.extract_policy_sections import PolicySection
from services import knowledge_generations, knowledge_ingestion
from services.knowledge_ingestion import (
    MAX_CHUNK_CHARS,
    VNEXT_MAX_CHUNK_CHARS,
    ExtractedPage,
    _activate_staged_sections,
    _extract_pages_with_textract,
    build_sections,
    detect_upload_format,
    enqueue_ingestion_job,
    extract_pages,
    process_ingestion_job,
    release_ingestion_claim,
    safe_filename,
    stage_ingestion_upload,
    validate_upload,
)


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


def test_vnext_generic_chunks_are_smaller_and_explicitly_tagged() -> None:
    content = "PRODUCT DETAILS\n" + "Useful product information. " * 500
    sections = build_sections(
        [ExtractedPage(3, content)],
        filename="facts.txt",
        country="GLOBAL",
        language="en",
        document_type="product_information",
        chunk_profile="vnext",
    )

    assert len(sections) > 1
    assert all(len(section["content"]) <= VNEXT_MAX_CHUNK_CHARS for section in sections)
    assert all(section["metadata"]["chunk_profile"] == "vnext" for section in sections)


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


def test_staged_publish_verifies_count_before_activation(monkeypatch) -> None:
    client = MagicMock()
    client.count.return_value = {"count": 2}
    monkeypatch.setattr(
        knowledge_ingestion.helpers,
        "bulk",
        lambda *_args, **_kwargs: (2, []),
    )
    actions = [
        {"_id": "one", "_source": {"id": "one"}},
        {"_id": "two", "_source": {"id": "two"}},
    ]

    _activate_staged_sections(
        client,
        index="sections",
        actions=actions,
        expected_count=2,
        ingestion_id="generation-1",
    )

    client.count.assert_called_once()


def test_staged_publish_rejects_partial_generation(monkeypatch) -> None:
    client = MagicMock()
    client.count.return_value = {"count": 1}

    with pytest.raises(RuntimeError, match="expected 2, found 1"):
        _activate_staged_sections(
            client,
            index="sections",
            actions=[],
            expected_count=2,
            ingestion_id="generation-1",
        )


def test_staged_publish_rolls_back_partial_activation(monkeypatch) -> None:
    client = MagicMock()
    client.count.return_value = {"count": 2}
    bulk_calls = []

    def fake_bulk(_client, actions, **_kwargs):
        captured = list(actions)
        bulk_calls.append(captured)
        if len(bulk_calls) == 1:
            return 1, [{"update": {"_id": "two", "status": 500}}]
        return len(captured), []

    monkeypatch.setattr(knowledge_ingestion.helpers, "bulk", fake_bulk)
    actions = [
        {"_id": "one", "_source": {"id": "one"}},
        {"_id": "two", "_source": {"id": "two"}},
    ]

    with pytest.raises(RuntimeError, match="rejected 1 activation"):
        _activate_staged_sections(
            client,
            index="sections",
            actions=actions,
            expected_count=2,
            ingestion_id="generation-1",
        )

    assert [action["doc"]["status"] for action in bulk_calls[0]] == ["active", "active"]
    assert [action["doc"]["status"] for action in bulk_calls[1]] == ["staging", "staging"]


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
