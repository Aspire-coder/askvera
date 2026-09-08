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
