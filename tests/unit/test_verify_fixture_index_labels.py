from scripts.verify_fixture_index_labels import matching_rows, nearby_rows


def test_matching_rows_obeys_locale_and_section_boundaries() -> None:
    case = {
        "scope": "locale_policy",
        "country": "CA",
        "relevant_sections": ["5.01"],
        "expected_behavior": "answer",
    }
    rows = [
        {"section_id": "5.01-a", "country": "CA", "access_scope": "country"},
        {"section_id": "15.01", "country": "CA", "access_scope": "country"},
        {"section_id": "5.01", "country": "US", "access_scope": "country"},
    ]

    assert matching_rows(rows, case) == [rows[0]]


def test_matching_rows_accepts_directory_country_name_for_code_label() -> None:
    case = {
        "scope": "global_directory",
        "country": "CA",
        "target_country": "BD",
        "relevant_sections": ["sponsoring-directory-bangladesh"],
        "expected_behavior": "answer",
    }
    rows = [
        {
            "section_id": "sponsoring-010-bangladesh",
            "record_country": "Bangladesh",
            "access_scope": "global",
        },
        {
            "section_id": "sponsoring-011-india",
            "record_country": "India",
            "access_scope": "global",
        },
    ]

    assert matching_rows(rows, case) == [rows[0]]


def test_nearby_rows_prefers_same_numeric_section_stem() -> None:
    case = {
        "scope": "locale_policy",
        "country": "CA",
        "relevant_sections": ["6.03-a"],
        "expected_behavior": "answer",
    }
    rows = [
        {"section_id": "6.02-a", "country": "CA"},
        {"section_id": "6.03-b", "country": "CA"},
        {"section_id": "6.03-c", "country": "CA"},
        {"section_id": "16.03-a", "country": "CA"},
    ]

    assert nearby_rows(rows, case) == [rows[1], rows[2]]


def test_nearby_rows_falls_back_to_same_numeric_chapter() -> None:
    case = {
        "scope": "locale_policy",
        "country": "CA",
        "relevant_sections": ["14.01-a"],
        "expected_behavior": "answer",
    }
    rows = [
        {"section_id": "14.02-a", "country": "CA"},
        {"section_id": "4.01-a", "country": "CA"},
    ]

    assert nearby_rows(rows, case) == [rows[0]]


def test_nearby_rows_finds_directory_country_or_label_tokens() -> None:
    case = {
        "scope": "global_directory",
        "country": "US",
        "target_country": "CN",
        "relevant_sections": ["sponsoring-directory-china"],
        "expected_behavior": "answer",
    }
    rows = [
        {"section_id": "sponsoring-020-china", "record_country": "Mainland China"},
        {"section_id": "sponsoring-021-india", "record_country": "India"},
    ]

    assert nearby_rows(rows, case) == [rows[0]]
