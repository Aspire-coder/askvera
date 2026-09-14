from pathlib import Path

from scripts.ingestion.extract_global_sponsoring_directory import extract_directory


def test_extracts_split_welcome_headings_and_global_metadata(tmp_path: Path, monkeypatch):
    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, _path: str):
            self.pages = [
                FakePage("Contents\nWelcome to Forever Algeria!"),
                FakePage("Welcome to\nForever Canada!\nPhone\n123-456-7890"),
                FakePage("Welcome to\nForever United States!\nFAQ\nCan I sponsor?"),
            ]

    monkeypatch.setattr(
        "scripts.ingestion.extract_global_sponsoring_directory.PdfReader",
        FakeReader,
    )
    records = extract_directory(tmp_path / "International_Sponsoring_Directory.pdf")

    assert [record.record_country for record in records] == [
        "Algeria",
        "Canada",
        "United States",
    ]
    assert records[1].start_page == 2
    assert records[1].end_page == 2
    assert records[1].to_row()["country"] == "GLOBAL"
    assert records[1].to_row()["metadata"]["directory_section"] == "sponsoring"
    assert records[1].to_row()["metadata"]["directory_kind"] == "international_sponsoring"


def test_extracts_bounded_wrapped_country_headings_without_section_bleed(tmp_path: Path):
    records = extract_directory(
        tmp_path / "International_Sponsoring_Directory.pdf",
        extracted_pages=[
            (24, "Welcome to Forever Ghana!\nGhana-only content."),
            (
                25,
                "Welcome to Forever Guinea\n"
                "Bissau and Guinea Conakry!\n"
                "Guinea-only content.",
            ),
            (193, "Welcome to Forever France!\nFrance-only content."),
            (
                194,
                "Welcome to\n"
                "Forever St Marteen\n"
                "& St Barthelemy!\n"
                "St Marteen-only content.",
            ),
        ],
    )

    assert [record.record_country for record in records] == [
        "Ghana",
        "Guinea Bissau and Guinea Conakry",
        "France",
        "St Marteen & St Barthelemy",
    ]
    assert records[0].content == "Welcome to Forever Ghana!\nGhana-only content."
    assert records[0].end_page == 24
    assert records[1].start_page == 25
    assert records[2].content == "Welcome to Forever France!\nFrance-only content."
    assert records[2].end_page == 193
    assert records[3].start_page == 194


def test_does_not_treat_paragraph_continuation_as_a_wrapped_country_heading(tmp_path: Path):
    records = extract_directory(
        tmp_path / "International_Sponsoring_Directory.pdf",
        extracted_pages=[
            (1, "Welcome to Forever Canada!\nCanada-only content."),
            (
                2,
                "Welcome to Forever Billing\n"
                "This is an ordinary paragraph!\n"
                "It is not a country section.",
            ),
            (3, "Welcome to Forever United States!\nUnited States-only content."),
        ],
    )

    assert [record.record_country for record in records] == ["Canada", "United States"]
    assert "Welcome to Forever Billing" in records[0].content
    assert records[0].end_page == 2


def test_does_not_allow_multiple_wrapped_heading_lines(tmp_path: Path):
    records = extract_directory(
        tmp_path / "International_Sponsoring_Directory.pdf",
        extracted_pages=[
            (1, "Welcome to Forever Canada!\nCanada-only content."),
            (
                2,
                "Welcome to Forever Billing\n"
                "Customer Service\n"
                "Office Hours!\n"
                "It is not a country section.",
            ),
            (3, "Welcome to Forever United States!\nUnited States-only content."),
        ],
    )

    assert [record.record_country for record in records] == ["Canada", "United States"]
    assert "Welcome to Forever Billing" in records[0].content
    assert records[0].end_page == 2


def test_does_not_allow_wrapped_heading_to_continue_onto_next_page(tmp_path: Path):
    records = extract_directory(
        tmp_path / "International_Sponsoring_Directory.pdf",
        extracted_pages=[
            (1, "Welcome to Forever Canada!\nCanada-only content."),
            (2, "Welcome to Forever Billing\nCustomer Service"),
            (3, "Office Hours!\nIt is not a country section."),
            (4, "Welcome to Forever United States!\nUnited States-only content."),
        ],
    )

    assert [record.record_country for record in records] == ["Canada", "United States"]
    assert "Welcome to Forever Billing" in records[0].content
    assert records[0].end_page == 3
