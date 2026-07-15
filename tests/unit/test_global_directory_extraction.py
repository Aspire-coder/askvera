"""Regression coverage for global directory record extraction."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ingestion"
    / "extract_global_office_directory.py"
)
SPEC = importlib.util.spec_from_file_location("global_directory_extractor", SCRIPT_PATH)
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


def test_office_records_are_global_and_keep_record_country_metadata() -> None:
    pages = [
        (
            7,
            "MEXICO - Forever Living Products Mexico\n"
            "Country\nMEXICO\nCountry Office Name\nForever Living Products Mexico\n"
            "Office Phone 1\n800 123 4567\n"
            "CANADA - Forever Living Products Canada\n"
            "Country\nCANADA\nCountry Office Name\nForever Living Products Canada",
        )
    ]

    records = extractor._extract_group(
        source_file="directory.pdf",
        record_type="office",
        pages=pages,
        pattern=extractor.OFFICE_RECORD_RE,
    )

    assert len(records) == 2
    row = records[0].to_row()
    assert row["country"] == "GLOBAL"
    assert row["language"] == "en"
    assert row["metadata"]["record_country"] == "MEXICO"
    assert row["metadata"]["directory_section"] == "office"


def test_staff_cards_preserve_embedded_contact_details() -> None:
    pages = [
        (
            24,
            "Mexico - Regional Contact\nOperating Country\nMexico\n"
            "Main Admin. Contact\nApproved Person\n"
            "Main Admin. Email\napproved@example.com\n"
            "IT Contact\nTechnical Person\nIT Email\nit@example.com",
        )
    ]

    records = extractor._extract_group(
        source_file="directory.pdf",
        record_type="staff",
        pages=pages,
        pattern=extractor.STAFF_RECORD_RE,
    )

    assert len(records) == 1
    assert "Technical Person" in records[0].content
    assert records[0].end_page == 24


def test_clean_page_repairs_pdf_wrapped_email_addresses() -> None:
    cleaned = extractor._clean_page(
        "General Mailbox\ncentrodeatencion@foreverliving.co\nm.mx\n"
        "Admin Email\nregional.manager\n@example.com"
    )

    assert "centrodeatencion@foreverliving.com.mx" in cleaned
    assert "regional.manager@example.com" in cleaned
