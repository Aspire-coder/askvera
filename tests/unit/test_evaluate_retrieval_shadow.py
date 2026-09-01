import json

from scripts.evaluate_retrieval_shadow import _load_records, main


def test_loader_accepts_jsonl_and_wrapper(tmp_path):
    jsonl = tmp_path / "comparisons.jsonl"
    jsonl.write_text('{"country":"CA"}\n{"country":"US"}\n', encoding="utf-8")
    assert len(_load_records(jsonl)) == 2

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"comparisons": [{"country": "DE"}]}), encoding="utf-8")
    assert _load_records(wrapped) == [{"country": "DE"}]


def test_cli_writes_report_and_can_enforce_gate(tmp_path, monkeypatch):
    source = tmp_path / "comparisons.json"
    source.write_text(
        json.dumps(
            [{
                "country": "CA",
                "language": "en",
                "same_section": True,
                "evidence_overlap": 0.9,
                "shadow_latency_ms": 100,
            }]
        ),
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate_retrieval_shadow", str(source), "--output", str(report), "--enforce-gate"],
    )
    assert main() == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["promotion_gate"]["passed"] is True
