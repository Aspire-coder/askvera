from __future__ import annotations

from scripts.audit_extracted_chunks import audit_records


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "source_file": "policy.pdf",
        "country": "US",
        "language": "en",
        "section_id": "1",
        "title": "Introduction",
        "start_page": 1,
        "end_page": 1,
        "content": "A complete policy statement.",
        "chunk_type": "section",
        "parent_section_id": "",
        "chunk_profile": "current",
    }
    record.update(overrides)
    return record


def test_clean_chunk_has_no_issues() -> None:
    report = audit_records([_record()])

    assert report["summary"]["errors"] == 0
    assert report["summary"]["warnings"] == 0


def test_detects_duplicate_id_mojibake_and_dangling_field() -> None:
    report = audit_records(
        [
            _record(content="Telephone Office:\nEncoding â€™ issue"),
            _record(content="Different text"),
        ]
    )
    codes = {issue["code"] for issue in report["issues"]}

    assert "duplicate_section_id" in codes
    assert "mojibake" in codes
    assert "dangling_directory_field" in codes


def test_missing_parent_is_warning_not_error() -> None:
    report = audit_records(
        [
            _record(
                section_id="12-part-1",
                parent_section_id="12",
                chunk_type="section_part",
                content="Continuation starts safely.",
            )
        ]
    )

    assert report["summary"]["errors"] == 0
    assert report["summary"]["issue_counts"]["parent_chunk_not_materialized"] == 1


def test_detects_oversized_chunk() -> None:
    report = audit_records([_record(content="x" * 2_001, chunk_profile="vnext")])

    assert report["summary"]["issue_counts"]["oversized_chunk"] == 1
