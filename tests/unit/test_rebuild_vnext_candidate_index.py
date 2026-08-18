import pytest
from dataclasses import dataclass

from config import settings
from scripts.rebuild_vnext_candidate_index import (
    _build_candidate,
    _s3_location,
    _section_documents,
    _source_documents,
    _source_plan,
    _validate_candidate_index,
)


def _row(**overrides):
    row = {
        "source_uri": "s3://approved/approved/US_en/policies/policy.pdf",
        "country": "US",
        "language": "en",
        "document_type": "policy",
        "access_scope": "country",
        "logical_document_id": "US:en:policy:policy",
        "document_version": "2026-08",
        "effective_date": "2026-08-01",
    }
    row.update(overrides)
    return row


def test_s3_location_accepts_approved_pdf() -> None:
    assert _s3_location("s3://approved/approved/US_en/policies/policy.pdf") == (
        "approved",
        "approved/US_en/policies/policy.pdf",
        "policy.pdf",
    )


def test_source_plan_preserves_current_metadata() -> None:
    plan = _source_plan([_row()])

    assert plan == [_row()]


def test_section_documents_serializes_extractor_dataclasses() -> None:
    @dataclass
    class Section:
        content: str
        page: int

    assert _section_documents([Section("text", 2), {"content": "existing"}]) == [
        {"content": "text", "page": 2},
        {"content": "existing"},
    ]


def test_source_plan_rejects_conflicting_active_metadata() -> None:
    with pytest.raises(ValueError, match="conflicting metadata"):
        _source_plan([_row(), _row(document_version="2026-09")])


def test_candidate_index_must_be_isolated(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENSEARCH_INDEX", "askvera-current")
    monkeypatch.setattr(settings, "OPENSEARCH_VNEXT_INDEX", "askvera-vnext")

    with pytest.raises(ValueError, match="must differ"):
        _validate_candidate_index("askvera-current")
    with pytest.raises(ValueError, match="contain both"):
        _validate_candidate_index("askvera-test")

    _validate_candidate_index("askvera-vnext-candidate-20260818")


def test_candidate_cleanup_refuses_nonempty_index() -> None:
    class Indices:
        @staticmethod
        def exists(*, index):
            return True

    class Client:
        indices = Indices()

        @staticmethod
        def count(*, index):
            return {"count": 1}

    with pytest.raises(ValueError, match="contains 1 records"):
        _build_candidate(
            client=Client(),
            s3=object(),
            candidate_index="askvera-vnext-candidate-test",
            plan=[],
            replace_empty_candidate=True,
        )


def test_resume_candidate_does_not_require_empty_index() -> None:
    class Indices:
        created = False

        @staticmethod
        def exists(*, index):
            return True

        @classmethod
        def create(cls, **kwargs):
            cls.created = True

        @staticmethod
        def refresh(*, index):
            return None

    class Client:
        indices = Indices()

    result = _build_candidate(
        client=Client(),
        s3=object(),
        candidate_index="askvera-vnext-candidate-test",
        plan=[],
        resume_candidate=True,
    )

    assert result["completed_sources"] == 0
    assert Indices.created is False


def test_sponsoring_directory_uses_record_extractor(tmp_path, monkeypatch) -> None:
    class Record:
        @staticmethod
        def to_row():
            return {
                "source_file": "International-Sponsoring-Directory.pdf",
                "country": "GLOBAL",
                "language": "en",
                "section_id": "sponsoring-001-canada",
                "title": "Forever Canada",
                "start_page": 1,
                "end_page": 2,
                "content": "Approved sponsoring information.",
                "metadata": {"record_country": "Canada"},
            }

    monkeypatch.setattr(
        "scripts.rebuild_vnext_candidate_index.extract_sponsoring_directory",
        lambda _path: [Record()],
    )
    source = _row(
        source_uri=(
            "s3://approved/approved/Global_en/directories/"
            "International-Sponsoring-Directory.pdf"
        ),
        country="GLOBAL",
        document_type="office_directory",
        access_scope="global",
    )

    rows = _source_documents(
        tmp_path / "International-Sponsoring-Directory.pdf",
        source,
        chunk_profile="vnext_r4",
    )

    assert len(rows) == 1
    assert rows[0]["section_id"] == "sponsoring-001-canada"
    assert rows[0]["chunk_profile"] == "vnext_r4"
