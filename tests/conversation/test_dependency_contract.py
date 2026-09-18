"""Deterministic/local tests for app.orchestrator.dependency_contract.

Pure classification tests: no orchestrator, no network, no monkeypatching.
This module now only classifies an exception caught at the retrieve() or
generate() call sites into a bounded `component` label for the
DependencyUnavailable metric. It no longer defines a `RetrievalResult`
metadata predicate -- that design (a `provider_unavailable` flag) was
withdrawn in favor of Codex's accepted R02 contract
(`RetrievalResult.availability`, a `RetrievalAvailability` enum), which this
project does not duplicate or import (it lives in Codex's worktree). See
docs/conversation-quality/codex-requests/
C5-retrieval-outage-masked-as-no-evidence.md for the history.
"""

from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError

from app.orchestrator.dependency_contract import (
    COMPONENT_EMBEDDING,
    COMPONENT_GENERATION,
    COMPONENT_RETRIEVAL,
    DEPENDENCY_COMPONENTS,
    dependency_component_for_exception,
)
from utils.exceptions import AwsServiceError


def test_component_for_embedding_error():
    assert dependency_component_for_exception(AwsServiceError("embedding down")) == COMPONENT_EMBEDDING
    assert dependency_component_for_exception(AwsServiceError) == COMPONENT_EMBEDDING


def test_component_for_other_recognized_errors_is_retrieval():
    assert dependency_component_for_exception(BotoCoreError()) == COMPONENT_RETRIEVAL
    assert dependency_component_for_exception(ConnectionError()) == COMPONENT_RETRIEVAL
    assert dependency_component_for_exception(TimeoutError()) == COMPONENT_RETRIEVAL
    assert dependency_component_for_exception(OSError()) == COMPONENT_RETRIEVAL


def test_component_for_client_error_is_retrieval():
    error_response = {"Error": {"Code": "Throttling", "Message": "rate limited"}}
    assert dependency_component_for_exception(ClientError(error_response, "Search")) == COMPONENT_RETRIEVAL


def test_component_for_an_unrecognized_exception_still_returns_a_bounded_label():
    """Anything not specifically recognized defaults to "retrieval" rather
    than raising or returning the exception's own class name -- a caller
    cannot accidentally create an unbounded CloudWatch dimension here."""
    assert dependency_component_for_exception(ValueError("surprise")) == COMPONENT_RETRIEVAL


def test_components_are_bounded_and_include_generation():
    """`generation` is used directly by the orchestrator (no exception maps
    to it here, since Bedrock generate() failures are classified at the call
    site, not through this helper)."""
    assert DEPENDENCY_COMPONENTS == {COMPONENT_RETRIEVAL, COMPONENT_EMBEDDING, COMPONENT_GENERATION}
