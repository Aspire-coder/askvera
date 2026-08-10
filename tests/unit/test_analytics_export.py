from __future__ import annotations

import io
import zipfile

import services.analytics as analytics


def test_interaction_export_xlsx_is_a_valid_redacted_workbook(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "interaction_list",
        lambda **_: [
            {
                "created_at": "2026-08-10T12:00:00+00:00",
                "correlation_id": "cid-1",
                "session_id": "session-1",
                "country": "US",
                "language": "en",
                "traffic_source": "widget",
                "question": "[REDACTED]",
                "answer": "Approved answer",
                "topic": "policy",
                "confidence": 0.91,
                "source_count": 1,
                "tokens": 123,
                "fallback": False,
                "failure_layer": "",
                "rating": -1,
                "comment": "Needs more detail",
                "expected_answer": "",
            }
        ],
    )

    workbook = analytics.interaction_export_xlsx(redact_content=True, limit=5000)

    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        assert "xl/worksheets/sheet1.xml" in archive.namelist()
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "Feedback" not in sheet
    assert "correlation_id" in sheet
    assert "Approved answer" in sheet
    assert "[REDACTED]" in sheet
