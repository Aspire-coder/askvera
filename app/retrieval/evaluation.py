"""Offline metrics and promotion gates for retrieval experiments."""

from __future__ import annotations

from collections import Counter
from statistics import quantiles
from typing import Any, Iterable


def _number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _metric_values(rows: list[dict[str, Any]], *keys: str) -> tuple[list[float], int]:
    values: list[float] = []
    missing = 0
    for row in rows:
        value = None
        for key in keys:
            raw = row.get(key)
            if raw in (None, ""):
                continue
            try:
                value = float(raw)
                break
            except (TypeError, ValueError):
                continue
        if value is None:
            missing += 1
        else:
            values.append(value)
    return values, missing


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


def summarize_comparisons(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [record for record in records if isinstance(record, dict)]

    def metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        overlap = [_number(row, "evidence_overlap", "evidenceOverlap") for row in items]
        latencies, missing_latency = _metric_values(
            items, "shadow_latency_ms", "shadowLatencyMs"
        )
        input_tokens = sum(_number(row, "input_tokens", "inputTokens") for row in items)
        output_tokens = sum(_number(row, "output_tokens", "outputTokens") for row in items)
        cost = sum(_number(row, "cost_usd", "costUsd", "estimated_cost_usd") for row in items)
        return {
            "comparisons": count,
            "same_section_rate": (
                sum(bool(row.get("same_section")) for row in items) / count if count else 0.0
            ),
            "evidence_overlap_rate": sum(overlap) / count if count else 0.0,
            "vnext_confidence_wins": sum(
                bool(row.get("vnext_confidence_wins")) for row in items
            ),
            "shadow_latency_p50_ms": _percentile(latencies, 50),
            "shadow_latency_p95_ms": _percentile(latencies, 95),
            "missing_latency_count": missing_latency,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(input_tokens + output_tokens),
            "estimated_cost_usd": round(cost, 6),
        }

    countries = Counter(
        str(row.get("country", "")).strip().upper()
        for row in rows
        if row.get("country")
    )
    languages = Counter(
        str(row.get("language", "")).strip().lower()
        for row in rows
        if row.get("language")
    )
    failures = Counter(str(row.get("failure_category", "unknown")) for row in rows)
    locales: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        country = str(row.get("country", "")).strip().upper()
        language = str(row.get("language", "")).strip().lower()
        locale = "/".join(part for part in (country, language) if part) or "unknown"
        locales.setdefault(locale, []).append(row)
    return {
        **metrics(rows),
        "by_country": dict(countries),
        "by_language": dict(languages),
        "by_locale": {locale: metrics(items) for locale, items in sorted(locales.items())},
        "failure_categories": dict(failures),
    }


def promotion_gate(
    summary: dict[str, Any], *, min_same_section_rate: float,
    min_evidence_overlap: float, max_latency_ms: float,
    require_locale_gates: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if int(summary.get("comparisons", 0)) <= 0:
        reasons.append("no comparisons available")
    if float(summary.get("same_section_rate", 0)) < min_same_section_rate:
        reasons.append("same-section rate below threshold")
    if float(summary.get("evidence_overlap_rate", 0)) < min_evidence_overlap:
        reasons.append("evidence overlap below threshold")
    if float(summary.get("shadow_latency_p95_ms", 0)) > max_latency_ms:
        reasons.append("shadow p95 latency above threshold")
    if int(summary.get("missing_latency_count", 0)) > 0:
        reasons.append("latency measurements are missing or invalid")
    if require_locale_gates:
        for locale, locale_summary in summary.get("by_locale", {}).items():
            if float(locale_summary.get("same_section_rate", 0)) < min_same_section_rate:
                reasons.append(f"{locale} same-section rate below threshold")
            if float(locale_summary.get("evidence_overlap_rate", 0)) < min_evidence_overlap:
                reasons.append(f"{locale} evidence overlap below threshold")
            if float(locale_summary.get("shadow_latency_p95_ms", 0)) > max_latency_ms:
                reasons.append(f"{locale} shadow p95 latency above threshold")
            if int(locale_summary.get("missing_latency_count", 0)) > 0:
                reasons.append(f"{locale} latency measurements are missing or invalid")
    return not reasons, reasons
