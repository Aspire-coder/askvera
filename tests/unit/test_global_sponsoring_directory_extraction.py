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
