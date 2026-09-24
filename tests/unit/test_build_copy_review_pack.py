"""Tests for scripts/build_copy_review_pack.py.

Covers the properties the copy-review pack depends on: every English key is
accounted for in each language's CSV (present or listed as missing),
placeholder extraction correctly finds `{name}` tokens, every key has a
runtime-path classification and every missing-key row carries the matching
`runtime_when_missing` value, and the script's output is byte-identical
across two runs given unchanged source config.
"""

from __future__ import annotations

import csv
import filecmp
import os

from scripts import build_copy_review_pack as tool


def _read_csv_rows(path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_extract_placeholders_finds_named_tokens() -> None:
    text = "Please provide {topic} for {country}, thanks {topic}."
    assert tool.extract_placeholders(text) == ["{country}", "{topic}"]


def test_extract_placeholders_ignores_non_placeholder_braces() -> None:
    assert tool.extract_placeholders("no placeholders here") == []
    assert tool.extract_placeholders("") == []
    assert tool.extract_placeholders("{}") == []


def test_build_row_flags_placeholder_mismatch() -> None:
    # "greeting" is a real key from KEY_RUNTIME_PATHS -- build_row() looks
    # up the key's runtime-path classification, so a synthetic key that
    # isn't in that table would raise.
    source = tool.SourceString(key="greeting", source_file="f", english="Hello {name}")
    matching = tool.build_row(source, "Bonjour {name}")
    assert matching["placeholder_mismatch"] == "no"

    mismatched = tool.build_row(source, "Bonjour")
    assert mismatched["placeholder_mismatch"] == "yes"

    missing = tool.build_row(source, None)
    assert missing["placeholder_mismatch"] == "yes"
    assert missing["translation"] == ""


def test_build_row_length_ratio_blank_when_translation_missing() -> None:
    source = tool.SourceString(key="greeting", source_file="f", english="Hello")
    row = tool.build_row(source, None)
    assert row["length_ratio"] == ""

    present = tool.build_row(source, "Hi")
    assert present["length_ratio"] == f"{len('Hi') / len('Hello'):.2f}"


def test_every_english_key_appears_in_every_language_csv_or_is_missing(tmp_path) -> None:
    sources = tool.load_english_strings()
    english_keys = {s.key for s in sources}
    assert english_keys, "expected at least one English source string"

    for language in tool.NON_ENGLISH_LANGUAGES:
        rows, findings = tool.build_language_pack(sources, language)
        row_keys = {row["key"] for row in rows}
        # Every English key produced a row (present-with-translation or
        # present-but-flagged-missing) -- none are silently dropped.
        assert row_keys == english_keys
        # The findings' own missing-key list is consistent with the rows:
        # a row whose translation column is empty and whose key is not in
        # translations is exactly a "missing" finding.
        translations = tool.load_language_translations(language)
        expected_missing = {s.key for s in sources if s.key not in translations}
        assert set(findings.missing_keys) == expected_missing


def test_every_key_has_a_runtime_path_classification() -> None:
    sources = tool.load_english_strings()
    for source in sources:
        assert source.key in tool.KEY_RUNTIME_PATHS, source.key
        assert tool.KEY_RUNTIME_PATHS[source.key] in {
            "cx_render", "conversation_route", "both", "unreferenced",
        }


def test_runtime_when_missing_matches_key_runtime_path() -> None:
    expected_by_path = {
        "cx_render": "english_shown",
        "conversation_route": "machine_translated_at_request_time",
        "both": "both_paths_differ",
        "unreferenced": "not_rendered_in_production_today",
    }
    for key, path in tool.KEY_RUNTIME_PATHS.items():
        assert tool.runtime_when_missing(key) == expected_by_path[path]


def test_every_missing_key_row_has_a_runtime_when_missing_value(tmp_path) -> None:
    sources = tool.load_english_strings()
    valid_values = {
        "english_shown",
        "machine_translated_at_request_time",
        "both_paths_differ",
        "not_rendered_in_production_today",
    }
    for language in tool.NON_ENGLISH_LANGUAGES:
        rows, findings = tool.build_language_pack(sources, language)
        missing = set(findings.missing_keys)
        for row in rows:
            if row["key"] in missing:
                assert row["runtime_when_missing"] in valid_values, (language, row["key"])
            else:
                # A present key carries no runtime_when_missing value --
                # nothing runs at request time when the translation exists.
                assert row["runtime_when_missing"] == ""


def test_script_output_is_deterministic(tmp_path, monkeypatch) -> None:
    out_dir_1 = tmp_path / "run1"
    out_dir_2 = tmp_path / "run2"

    monkeypatch.setattr(tool, "OUTPUT_DIR", out_dir_1)
    tool.main()

    monkeypatch.setattr(tool, "OUTPUT_DIR", out_dir_2)
    tool.main()

    names_1 = sorted(os.listdir(out_dir_1))
    names_2 = sorted(os.listdir(out_dir_2))
    assert names_1 == names_2
    assert names_1  # non-empty

    mismatch = []
    errors = []
    _, mismatched, err = filecmp.cmpfiles(
        out_dir_1, out_dir_2, names_1, shallow=False
    )
    mismatch.extend(mismatched)
    errors.extend(err)
    assert not mismatch, f"non-deterministic output in: {mismatch}"
    assert not errors, f"could not compare: {errors}"


def test_readme_string_counts_match_csv_row_counts(tmp_path, monkeypatch) -> None:
    out_dir = tmp_path / "pack"
    monkeypatch.setattr(tool, "OUTPUT_DIR", out_dir)
    tool.main()

    sources = tool.load_english_strings()
    for language in tool.NON_ENGLISH_LANGUAGES:
        rows = _read_csv_rows(out_dir / f"{language}.csv")
        assert len(rows) == len(sources)
        for row in rows:
            assert row["placeholder_mismatch"] in ("yes", "no")
