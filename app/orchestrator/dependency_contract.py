"""Exception classification for the DependencyUnavailable metric.

History: this module originally also defined a `RetrievalResult.metadata`
flag (`provider_unavailable`) as the interface for a retrieval provider to
report an outage it caught internally, for task C5 ("five failure kinds
worded distinctly"). That design is WITHDRAWN. Codex's retrieval work has an
accepted, broader contract (R02) that supersedes it:
`RetrievalResult.availability`, a `RetrievalAvailability` enum with
`AVAILABLE`, `DEGRADED` (at least one retrieval channel failed but another
completed), and `UNAVAILABLE` (no channel completed). Codex's own
orchestrator routing (added at integration, not in this module) routes
`UNAVAILABLE`, and `DEGRADED` with no usable final evidence after
country-scope reapproval, to `failure_layer=dependency_unavailable`. See
`docs/conversation-quality/codex-requests/
C5-retrieval-outage-masked-as-no-evidence.md` for the full history. This
module does not duplicate or compete with that contract, and does not import
`RetrievalAvailability` (it lives in Codex's worktree, not this project's
base).

What this module still does: classify an exception caught at the retrieve()
or generate() call sites in
`app.orchestrator.chat_orchestrator.AIOrchestrator._handle_scrubbed_chat`
into a bounded `component` label ("retrieval" / "embedding" / "generation")
for the `DependencyUnavailable` metric
(`app.metrics.responses.record_dependency_unavailable`). That classification
-- specifically, that `AwsServiceError` means the embedding path
(`services/embeddings.py`), not OpenSearch itself -- is kept in one place so
the orchestrator's except clauses and this metric's dimension never drift
apart.

What this module intentionally does NOT cover, and why
----------------------------------------------------------
- No predicate for "is this RetrievalResult a dependency outage" lives here
  any more. That question is now answered by
  `RetrievalResult.availability` (Codex-owned).
- `ConfigurationError` is a deploy defect, never classified as a dependency
  outage: telling the user "try again in a moment" would be false and would
  hide the defect from the request error-rate alarm.
- `GuardrailBlockedError` is a safety decision, never a dependency outage.
- `LowConfidenceError` / `RetrievalMissError` mean the dependency was
  reachable but had nothing to ground an answer in; not a dependency
  outage either.
"""

from __future__ import annotations

from utils.exceptions import AwsServiceError

# Bounded, enumerable component labels for the DependencyUnavailable metric's
# `component` dimension (app.metrics.responses.record_dependency_unavailable).
# Kept here, not in app.metrics, because deciding which component a given
# exception belongs to is part of this classification, not a
# metrics-plumbing concern -- duplicating the judgement in two modules would
# let them drift.
COMPONENT_RETRIEVAL = "retrieval"
COMPONENT_EMBEDDING = "embedding"
COMPONENT_GENERATION = "generation"

DEPENDENCY_COMPONENTS = frozenset({COMPONENT_RETRIEVAL, COMPONENT_EMBEDDING, COMPONENT_GENERATION})


def dependency_component_for_exception(exc: BaseException | type[BaseException]) -> str:
    """Bounded component label for an exception caught at the retrieve() site.

    ``AwsServiceError`` is raised only by the embedding path
    (``services/embeddings.py``) -- see the C5 Codex request. Every other
    exception recognized as a dependency outage at that call site
    (``BotoCoreError``, ``ClientError``, built-in ``ConnectionError``,
    ``TimeoutError``, ``OSError``) is a retrieval-layer failure, and this
    function defaults to that label for anything else it is asked about too,
    so a caller cannot accidentally create an unbounded CloudWatch
    dimension by passing an unrecognized exception type.
    """
    exc_type = exc if isinstance(exc, type) else type(exc)
    if issubclass(exc_type, AwsServiceError):
        return COMPONENT_EMBEDDING
    return COMPONENT_RETRIEVAL
