"""Tests for source-ground-truth reconciliation packets."""

from scripts.build_fixture_reconciliation_packet import build_packet


def _fixture(section: str = "5.01"):
    return {
        "cases": [
            {
                "id": "CASE-1",
                "question": "How do I become a Manager?",
                "country": "CA",
                "language": "en",
                "scope": "locale_policy",
                "scoring_rule": "governing",
                "relevant_sections": [section],
                "governing_section": section,
            }
        ]
    }


def _report():
    profile = {
        "candidate_metrics": {
            "top_candidates": [
                {"rank": 1, "id": "candidate-1", "section_id": "4.01-d"}
            ]
        }
    }
    return {"cases": [{"id": "CASE-1", "current": profile, "candidate": profile}]}


def test_packet_reports_declared_and_retrieved_source_passages() -> None:
    rows = [
        {
            "source_file": "CA.pdf",
            "country": "CA",
            "language": "en",
            "section_id": "5.01",
            "title": "Manager status",
            "content": "A Recognized Manager qualifies under this section.",
        },
        {
            "source_file": "CA.pdf",
            "country": "CA",
            "language": "en",
            "section_id": "4.01-d",
            "title": "Manager qualification",
            "content": "Manager is achieved by generating the required case credits.",
        },
    ]

    packet = build_packet(_fixture(), _report(), rows)
    case = packet["cases"][0]

    assert case["status"] == "source_ids_found"
    assert case["label_matches"]["5.01"][0]["title"] == "Manager status"
    assert case["current"][0]["source_matches"][0]["section_id"] == "4.01-d"


def test_packet_keeps_missing_labels_for_review() -> None:
    packet = build_packet(_fixture("99.99"), _report(), [])

    assert packet["cases"][0]["status"] == "needs_review"
    assert packet["cases"][0]["missing_labels"] == ["99.99"]


def test_packet_maps_directory_fixture_slug_to_real_country_record() -> None:
    fixture = _fixture("sponsoring-directory-algeria")
    fixture["cases"][0].update(
        {
            "scope": "global_directory",
            "target_country": "DZ",
        }
    )
    rows = [
        {
            "source_file": "International-Sponsoring-Directory.pdf",
            "country": "GLOBAL",
            "language": "en",
            "section_id": "sponsoring-001-algeria",
            "title": "Forever Algeria",
            "content": "Approved Algeria directory record.",
            "metadata": {"record_country": "Algeria"},
        }
    ]

    packet = build_packet(fixture, {"cases": []}, rows)

    assert packet["cases"][0]["status"] == "source_ids_found"
    assert packet["cases"][0]["governing_matches"][0]["section_id"] == "sponsoring-001-algeria"
