"""Usage counting and the corpus fingerprint, offline.

Two measurement defects that would only have shown up as a wrong number, which
is the kind that gets believed:

  a request that exhausted its retries and failed reported ZERO application
  calls and three HTTP attempts, so every attempt looked like a retry of
  nothing and the call itself vanished from the cost;

  the corpus fingerprint aggregated ingestion_id.keyword, which does not exist
  in this index - ingestion_id is mapped as a keyword - so it returned no
  generations, silently, and would have matched anything.

Neither raises. Both make the harness confidently wrong.
"""

from __future__ import annotations

import pytest

from scripts import run_grounding_comparison as comparison


class _Boom(RuntimeError):
    pass


# --- usage ----------------------------------------------------------------


def test_a_call_that_fails_after_its_retries_is_still_one_call() -> None:
    """The defect. Counting after the request meant a failure counted as none.

    Three HTTP attempts, one application call, two retries - not zero calls and
    three retries.
    """
    meter = comparison._UsageMeter()
    wrapped = comparison._metered(
        meter, lambda **kwargs: (_ for _ in ()).throw(_Boom()), reports_usage=True
    )

    with pytest.raises(_Boom):
        wrapped(modelId="claude")
    meter.http_attempts = 3

    snapshot = meter.snapshot()

    assert snapshot["application_calls"] == 1
    assert snapshot["failed_calls"] == 1
    assert snapshot["successful_calls"] == 0
    assert snapshot["sdk_retry_attempts"] == 2


def test_a_successful_call_records_its_tokens_against_its_model() -> None:
    meter = comparison._UsageMeter()
    wrapped = comparison._metered(
        meter,
        lambda **kwargs: {"usage": {"inputTokens": 120, "outputTokens": 40}},
        reports_usage=True,
    )

    wrapped(modelId="claude-sonnet")
    meter.http_attempts = 1

    snapshot = meter.snapshot()

    assert snapshot["by_model"]["claude-sonnet"] == {
        "calls": 1,
        "succeeded": 1,
        "failed": 0,
        "input_tokens": 120,
        "output_tokens": 40,
    }
    assert snapshot["sdk_retry_attempts"] == 0


def test_usage_is_kept_per_model_because_a_rate_applies_to_a_model() -> None:
    meter = comparison._UsageMeter()
    converse = comparison._metered(
        meter, lambda **kwargs: {"usage": {"inputTokens": 10, "outputTokens": 5}}, reports_usage=True
    )
    embed = comparison._metered(meter, lambda **kwargs: {"body": b""}, reports_usage=False)

    converse(modelId="claude-sonnet")
    embed(modelId="titan-embed")

    snapshot = meter.snapshot()

    assert set(snapshot["by_model"]) == {"claude-sonnet", "titan-embed"}
    assert snapshot["application_calls"] == 2


def test_an_embedding_call_is_counted_with_its_tokens_marked_unknown() -> None:
    """invoke_model returns no usage, so zero would be a false measurement."""
    meter = comparison._UsageMeter()
    embed = comparison._metered(meter, lambda **kwargs: {"body": b""}, reports_usage=False)

    embed(modelId="titan-embed")

    snapshot = meter.snapshot()

    assert snapshot["by_model"]["titan-embed"]["calls"] == 1
    assert snapshot["calls_without_reported_tokens"] == 1
    assert "must be read from the console" in snapshot["note"]


def test_both_invocation_methods_are_wrapped() -> None:
    """converse alone missed every embedding, one per turn."""
    import inspect

    source = inspect.getsource(comparison._instrument_usage)

    assert "converse" in source
    assert "invoke_model" in source


def test_instrumentation_failure_refuses_rather_than_reporting_zero(monkeypatch) -> None:
    """A silent zero reads as "this costs nothing"."""

    class _NoClient:
        @property
        def bedrock_runtime(self):
            raise RuntimeError("no credentials")

    monkeypatch.setattr(
        "services.aws_clients.get_aws_clients", lambda: _NoClient(), raising=False
    )

    with pytest.raises(SystemExit):
        comparison._instrument_usage()


# --- the corpus fingerprint ----------------------------------------------


def test_the_index_maps_ingestion_id_as_a_keyword_field() -> None:
    """The premise of the bug, asserted so it cannot drift back.

    ingestion_id is a keyword, so ingestion_id.keyword does not exist and an
    aggregation on it returns nothing without error.
    """
    from scripts.ingestion.load_policy_sections_to_opensearch import _index_body

    mapping = _index_body()["mappings"]["properties"]

    assert mapping["ingestion_id"] == {"type": "keyword"}


def test_the_fingerprint_aggregates_the_field_that_exists() -> None:
    import inspect
    import re

    source = inspect.getsource(comparison._indexed_generation_ids)
    # Docstring stripped: it explains the wrong field, and matching raw text
    # finds the explanation rather than the code.
    code = re.sub(r'"""(?:.|\n)*?"""', "", source)

    assert '"field": "ingestion_id"' in code
    assert "ingestion_id.keyword" not in code


def _pointer_signature(monkeypatch, rows, *, active=17896, enabled=True):
    monkeypatch.setattr(comparison, "_active_section_total", lambda: active)
    monkeypatch.setattr(comparison, "_active_generation_rows", lambda: rows)
    from config import settings

    monkeypatch.setattr(
        settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", enabled, raising=False
    )
    return comparison._corpus_signature()


def test_a_pointer_only_switch_changes_the_signature(monkeypatch) -> None:
    """The case an index aggregation cannot see.

    Both generations are already indexed, so the active section count does not
    move. Only the pointer changed - and it changes every answer for that
    market, so a resume must not accept it as the same corpus.
    """
    before = _pointer_signature(
        monkeypatch, ["DZ:fr:policy:country:ingest-old", "FR:fr:policy:country:ingest-a"]
    )
    after = _pointer_signature(
        monkeypatch, ["DZ:fr:policy:country:ingest-new", "FR:fr:policy:country:ingest-a"]
    )

    assert before != after
    # And the section count really was unchanged, so nothing else explains it.
    assert "active=17896" in before and "active=17896" in after


def test_an_unchanged_pointer_mapping_gives_a_stable_signature(monkeypatch) -> None:
    """A fingerprint that changes on its own would refuse every resume."""
    rows = ["DZ:fr:policy:country:ingest-a", "FR:fr:policy:country:ingest-b"]

    assert _pointer_signature(monkeypatch, rows) == _pointer_signature(monkeypatch, rows)


def test_a_new_publication_changes_the_signature_through_the_count(monkeypatch) -> None:
    rows = ["DZ:fr:policy:country:ingest-a"]

    assert _pointer_signature(monkeypatch, rows, active=17896) != _pointer_signature(
        monkeypatch, rows, active=18010
    )


def test_the_signature_names_which_authority_it_read(monkeypatch) -> None:
    """Pointer-enabled and pointer-disabled deployments read different things."""
    with_pointer = _pointer_signature(monkeypatch, ["DZ:fr:policy:country:a"], enabled=True)
    monkeypatch.setattr(comparison, "_indexed_generation_ids", lambda: ["a", "b"])
    without = _pointer_signature(monkeypatch, [], enabled=False)

    assert with_pointer.startswith("pointer;")
    assert without.startswith("index;")


def test_an_unreadable_corpus_reports_unavailable(monkeypatch) -> None:
    def _fail():
        raise RuntimeError("opensearch unreachable")

    monkeypatch.setattr(comparison, "_active_section_total", _fail)

    assert comparison._corpus_signature() == "unavailable"


def test_the_signature_reads_the_pointer_table_not_the_index(monkeypatch) -> None:
    """The pointer table is what retrieval filters on, so it is the authority."""
    import inspect

    source = inspect.getsource(comparison._active_generation_rows)

    assert "knowledge_active_generations" in source
    assert "active_ingestion_id <> ''" in source


# --- the environment gate -------------------------------------------------


def _environment(monkeypatch, *, sections=17896, rows=None, rows_raise=False,
                 pointer=True, sentinel_for=()):
    """A fake environment. sentinel_for names probes that match nothing."""
    from config import settings

    monkeypatch.setattr(
        settings, "ADMIN_INGESTION_GENERATION_POINTER_ENABLED", pointer, raising=False
    )
    monkeypatch.setattr(comparison, "_active_section_total", lambda: sections)

    def _rows():
        if rows_raise:
            raise RuntimeError("connection timeout expired")
        return rows if rows is not None else ["DZ:fr:policy:country:a"]

    monkeypatch.setattr(comparison, "_active_generation_rows", _rows)
    monkeypatch.setattr(comparison, "_corpus_signature", lambda: "pointer;active=1;slots=1;abc")

    from app.retrieval import opensearch_sections

    def _filters(country, language, scope, *, document_type=""):
        label = "global" if scope == "global" else f"country:{country}:{language}"
        if rows_raise or rows == [] or label in sentinel_for:
            return [{"bool": {"should": [{"term": {"ingestion_id": "__no_active_generation__"}}]}}]
        return [{"bool": {"should": [{"term": {"ingestion_id": "ingest-a"}}]}}]

    monkeypatch.setattr(opensearch_sections, "_generation_filters", _filters)
    return comparison.check_environment(
        [{"id": "algeria-delivery-cost", "country": "DZ", "language": "en"}]
    )


def test_an_unreachable_pointer_table_makes_the_environment_unready(monkeypatch) -> None:
    """The failure that would have bought six refusals.

    With the pointer enabled and its table unreachable, active_generation_ids
    catches the error and returns nothing, so retrieval is filtered to
    __no_active_generation__ and every case abstains. Nothing raises, nothing
    is free, and no turn reaches numeric repair.
    """
    report = _environment(monkeypatch, rows_raise=True)

    assert report["ready"] is False
    assert any("unreachable" in problem for problem in report["problems"])


def test_a_country_without_its_own_generation_does_not_condemn_the_run(
    monkeypatch,
) -> None:
    """The false negative that stopped a healthy pilot.

    Most of this corpus is the global sponsoring directory, so a market can
    legitimately have no country-scoped generation and still be answerable. An
    earlier probe asked only for country scope with document_type="policy" and
    read the correct answer "nothing" as a dead environment.
    """
    report = _environment(monkeypatch, sentinel_for=("country:DZ:en",))

    assert report["ready"] is True
    labels = {probe["probe"]: probe["matches_documents"] for probe in report["retrieval_probes"]}
    assert labels["global"] is True
    assert labels["country:DZ:en"] is False


def test_the_probes_ask_the_way_retrieval_asks() -> None:
    """No document_type, because real callers pass none."""
    import inspect
    import re

    source = inspect.getsource(comparison._retrieval_probes)
    code = re.sub(r'"""(?:.|\n)*?"""', "", source)

    assert "document_type" not in code
    assert '("", "en", "global")' in code


def test_every_probe_dead_is_a_refusal(monkeypatch) -> None:
    report = _environment(monkeypatch, sentinel_for=("global", "country:DZ:en"))

    assert report["ready"] is False
    assert any("every retrieval probe" in problem for problem in report["problems"])


def test_a_healthy_environment_is_ready(monkeypatch) -> None:
    """The gate must not refuse a run that would have worked."""
    report = _environment(monkeypatch)

    assert report["ready"] is True
    assert report["problems"] == []
    assert report["active_sections"] == 17896


def test_freeze_refuses_when_the_environment_cannot_retrieve(
    tmp_path, capsys, monkeypatch
) -> None:
    """The guard is wired to the paid path, not only to preflight."""
    import sys

    monkeypatch.setattr(
        comparison,
        "check_environment",
        lambda cases=None: {
            "ready": False,
            "problems": ["retrieval is filtered to __no_active_generation__"],
        },
    )
    monkeypatch.setattr(
        comparison, "freeze", lambda *a, **k: pytest.fail("freeze ran in a dead environment")
    )

    argv = sys.argv
    sys.argv = [
        "x",
        "--freeze",
        str(tmp_path / "out.json"),
        "--i-have-approval-for-paid-model-calls",
        "--max-turns",
        "6",
    ]
    try:
        assert comparison.main() == 2
    finally:
        sys.argv = argv

    output = capsys.readouterr().out
    assert "refused" in output
    assert "measure nothing" in output
    assert not (tmp_path / "out.json").exists()
