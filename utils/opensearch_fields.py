"""OpenSearch helpers for exact matching across legacy and current mappings."""

from __future__ import annotations

from typing import Any


def exact_field_paths(field_name: str) -> tuple[str, str]:
    """Return both supported exact-match paths for a field."""
    return field_name, f"{field_name}.keyword"


def exact_term_query(field_name: str, value: str) -> dict[str, Any]:
    """Match one value whether the index uses keyword or text.keyword."""
    return {
        "bool": {
            "should": [
                {"term": {path: value}}
                for path in exact_field_paths(field_name)
            ],
            "minimum_should_match": 1,
        }
    }


def exact_terms_query(field_name: str, values: list[str]) -> dict[str, Any]:
    """Match values whether the index uses keyword or text.keyword."""
    return {
        "bool": {
            "should": [
                {"terms": {path: values}}
                for path in exact_field_paths(field_name)
            ],
            "minimum_should_match": 1,
        }
    }


def has_exact_keyword_mapping(field: dict[str, Any]) -> bool:
    """Return whether a field provides a usable exact-match keyword path."""
    if field.get("type") == "keyword":
        return True
    keyword = (field.get("fields") or {}).get("keyword", {})
    return keyword.get("type") == "keyword"
