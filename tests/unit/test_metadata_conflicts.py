"""Metadata conflicts must be reported, never guessed away.

The rule these tests defend: where metadata is missing or disagrees with the
document it describes, a person decides. Inferring a country from a filename or
stamping a date on an undated policy would put a fabricated fact into the corpus
carrying the authority of approved content.

They also defend the distinction between a contradiction and an absence. An
expiry preceding its effective date cannot be correct under any reading. A
missing effective date may be entirely fine - 15 of 28 documents in the corpus
have none - and needs a decision rather than a rejection.
"""

from __future__ import annotations

from datetime import date

import pytest

from services.metadata_conflicts import (
    Severity,
    blocking_findings,
    detect_metadata_conflicts,
)

TODAY = date(2026, 9, 8)


def _detect(**overrides):
    arguments = {
        "filename": "DK-EN-Company-Policy.pdf",
        "country": "DK",
        "language": "EN",
        "document_type": "policy",
        "version": "2026-07",
        "effective_date": "2026-07-01",
        "expiry_date": "",
        "today": TODAY,
    }
    arguments.update(overrides)
    return detect_metadata_conflicts(**arguments)


def test_consistent_metadata_produces_no_findings() -> None:
    """The control. Without it every assertion below could pass on noise."""
    assert _detect() == []


def test_a_filename_naming_another_country_is_reported() -> None:
    """Uploading Denmark's document as Sweden's is the mistake that puts one
    market's rules under another market's flag, and retrieval would then serve
    it to the wrong readers with no visible symptom."""
    findings = _detect(filename="DK-EN-Company-Policy.pdf", country="SE")

    assert [finding.field for finding in findings] == ["country"]
    assert findings[0].severity == Severity.UNRESOLVED
    assert "DK" in findings[0].detail and "SE" in findings[0].detail
    # Reported, not corrected: which of the two is wrong cannot be decided here.
    assert blocking_findings(findings) == []


def test_a_market_alias_is_not_a_conflict() -> None:
    """GB is served by documents tagged UK. Reporting that as a mismatch would
    train reviewers to dismiss the warning."""
    assert _detect(filename="UK-EN-Company-Policy.pdf", country="GB", language="EN") == []


def test_a_filename_naming_another_language_is_reported() -> None:
    findings = _detect(filename="SE-SV-Company-Policy.pdf", country="SE", language="EN")
    assert [finding.field for finding in findings] == ["language"]


def test_a_filename_without_a_locale_prefix_is_not_second_guessed() -> None:
    """The sponsoring directory is one global document with no market prefix."""
    assert _detect(
        filename="International-Sponsoring-Directory.pdf",
        country="GLOBAL",
        language="EN",
        document_type="office_directory",
    ) == []


def test_a_missing_effective_date_is_unresolved_and_never_filled_in() -> None:
    """15 of 28 documents in the corpus have no effective date.

    That is not automatically wrong, so it must not block. It is also not
    nothing: date-scope protection does nothing without a date, so a question
    about an earlier year is answered from this document as though its rules had
    always applied.
    """
    findings = _detect(effective_date="")

    dates = [finding for finding in findings if finding.field == "effective_date"]
    assert len(dates) == 1
    assert dates[0].severity == Severity.UNRESOLVED
    assert blocking_findings(findings) == []
    # The detail explains the consequence rather than only naming the field.
    assert "date-scope" in dates[0].detail.lower()


def test_an_expiry_before_its_effective_date_is_a_contradiction() -> None:
    """No reviewer decision makes this valid; the document was never in force."""
    findings = _detect(effective_date="2026-07-01", expiry_date="2026-01-01")

    blocking = blocking_findings(findings)
    assert [finding.field for finding in blocking] == ["expiry_date"]
    assert blocking[0].severity == Severity.CONTRADICTION


def test_a_future_effective_date_is_unresolved_rather_than_blocked() -> None:
    """Staging a document ahead of its date is legitimate; publishing it now is
    the question a reviewer has to answer."""
    findings = _detect(effective_date="2027-01-01")

    future = [finding for finding in findings if finding.field == "effective_date"]
    assert future and future[0].severity == Severity.UNRESOLVED
    assert blocking_findings(findings) == []


@pytest.mark.parametrize("value", ["01/07/2026", "July 2026", "2026-13-01x", "soon"])
def test_a_date_that_is_not_a_date_is_a_contradiction(value: str) -> None:
    """A malformed date silently becomes no date at all downstream, which is
    indistinguishable from a document that never had one."""
    findings = _detect(effective_date=value)
    assert any(
        finding.field == "effective_date" and finding.severity == Severity.CONTRADICTION
        for finding in findings
    )


def test_a_missing_version_is_reported() -> None:
    """Without a version a replacement cannot be told from what it replaces."""
    findings = _detect(version="")
    assert [finding.field for finding in findings] == ["version"]


def test_several_problems_are_all_reported() -> None:
    """A reviewer should see every problem at once rather than one per attempt."""
    findings = _detect(
        filename="DK-EN-Company-Policy.pdf",
        country="SE",
        language="SV",
        version="",
        effective_date="2026-07-01",
        expiry_date="2026-01-01",
    )

    assert {finding.field for finding in findings} == {
        "country",
        "language",
        "expiry_date",
        "version",
    }
    assert len(blocking_findings(findings)) == 1


def test_nothing_in_this_module_writes_a_value() -> None:
    """The guarantee the module exists to make.

    Every function returns findings; none returns corrected metadata, so there
    is no path by which a guessed country or an invented date reaches the
    corpus.
    """
    import inspect

    from services import metadata_conflicts

    source = inspect.getsource(metadata_conflicts)
    assert "date.today()" in source  # used only to judge "in the future"
    for forbidden in ("effective_date =", "country =", "language ="):
        assert f"    {forbidden}" not in source, f"module assigns {forbidden!r}"
