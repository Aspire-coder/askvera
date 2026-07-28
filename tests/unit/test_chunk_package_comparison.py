"""Tests for offline current-versus-vNext chunk package reporting."""

from __future__ import annotations

import json

from scripts.ingestion.compare_chunk_packages import summarize


def test_chunk_package_summary_reports_profile_sizes_and_types(tmp_path) -> None:
    path = tmp_path / "policy.sections.jsonl"
    rows = [
        {
            "section_id": "1-part-1",
            "parent_section_id": "1",
            "content": "First approved policy chunk.",
            "chunk_type": "section_part",
            "chunk_profile": "vnext",
        },
        {
            "section_id": "1-definition-1",
            "parent_section_id": "1",
            "content": "Term: Approved definition.",
            "chunk_type": "definition",
            "chunk_profile": "vnext",
        },
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    report = summarize(path)

    assert report["chunks"] == 2
    assert report["parent_sections"] == 1
    assert report["profiles"] == {"vnext": 2}
    assert report["chunk_types"] == {"definition": 1, "section_part": 1}
    assert report["characters"]["maximum"] == len(rows[0]["content"])
