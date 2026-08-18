from pathlib import Path

from app.retrieval.quality_dataset import dataset_summary, parse_interaction_history


HEADER = (
    "| created_at | correlation_id | session_id | country | language | traffic_source | "
    "question | answer | topic | confidence | source_count | tokens | fallback | "
    "failure_layer | rating | comment | expected_answer |"
)
SEPARATOR = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"


def _write(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join([HEADER, SEPARATOR, *rows]), encoding="utf-8")


def test_history_parser_accounts_for_every_valid_row(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    _write(
        source,
        [
            "| 2026-08-01 | cid-1 | sid | DE | de | widget | Was ist FPC? | Alt \\| Antwort | topic | 0.18 | 1 | 30 | False |  | \\-1 | FPC ist Preferred Customer |  |",
            "| 2026-08-02 | cid-2 | sid | US | en | widget | hi | Hello | General | 0 | 0 | 2 | False |  | 1 |  |  |",
        ],
    )

    cases, issues = parse_interaction_history(source)

    assert issues == []
    assert len(cases) == 2
    assert cases[0].rating == -1
    assert cases[0].historical_answer == "Alt | Antwort"
    assert cases[0].has_review_guidance is True
    assert cases[1].evaluation_group == "conversation"
    assert dataset_summary(cases, issues)["case_count"] == 2


def test_history_parser_reports_malformed_rows_instead_of_skipping_silently(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    _write(source, ["| too | few | fields |"])

    cases, issues = parse_interaction_history(source)

    assert cases == []
    assert len(issues) == 1
    assert issues[0].code == "FIELD_COUNT"


def test_testing_comment_is_not_treated_as_expected_guidance(tmp_path: Path) -> None:
    source = tmp_path / "history.md"
    _write(
        source,
        [
            "| 2026-08-01 | cid-1 | sid | US | en | widget | question | answer | topic | 0.7 | 1 | 30 | False |  | \\-1 | testing the changes |  |"
        ],
    )

    cases, _issues = parse_interaction_history(source)

    assert cases[0].has_review_guidance is False
    assert cases[0].review_state == "negative_without_guidance"
