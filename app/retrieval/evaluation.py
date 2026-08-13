"""Offline metrics and promotion gates for retrieval experiments."""

from __future__ import annotations

from collections import Counter
from statistics import quantiles
from typing import Any, Iterable


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


def summarize_comparisons(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [record for record in records if isinstance(record, dict)]
    count = len(rows)
    same_section = sum(bool(row.get("same_section")) for row in rows)
    overlap = [float(row.get("evidence_overlap", 0) or 0) for row in rows]
    latencies = [float(row.get("shadow_latency_ms", 0) or 0) for row in rows]
    confidence_wins = sum(bool(row.get("vnext_confidence_wins")) for row in rows)
    countries = Counter(str(row.get("country", "")) for row in rows if row.get("country"))
    languages = Counter(str(row.get("language", "")) for row in rows if row.get("language"))
    failures = Counter(str(row.get("failure_category", "unknown")) for row in rows)
    return {
        "comparisons": count,
        "same_section_rate": same_section / count if count else 0.0,
        "evidence_overlap_rate": sum(overlap) / count if count else 0.0,
        "vnext_confidence_wins": confidence_wins,
        "shadow_latency_p50_ms": _percentile(latencies, 50),
        "shadow_latency_p95_ms": _percentile(latencies, 95),
        "by_country": dict(countries),
        "by_language": dict(languages),
        "failure_categories": dict(failures),
    }


def promotion_gate(
    summary: dict[str, Any], *, min_same_section_rate: float,
    min_evidence_overlap: float, max_latency_ms: float
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
    return not reasons, reasons
